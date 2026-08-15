"""Incident and alert persistence functions.

All database writes for incident/alert creation go through this module.
Uses asyncpg and the state machine transition function (AD-19).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import asyncpg

from ..config.logging import Component, get_logger
from ..models.state_machine import initial_state

logger = get_logger(Component.DB)


async def create_incident(
    conn: asyncpg.Connection | asyncpg.Pool,
    severity: str,
) -> dict:
    """Create a new incident in the `received` state.

    Uses the state machine transition function to validate the initial state.
    Returns a dict with the new incident row data.
    """
    state = initial_state()

    incident_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    row = await conn.fetchrow(
        """
        INSERT INTO incidents (id, state, severity, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, state, severity, created_at, updated_at
        """,
        incident_id,
        state.value,
        severity,
        now,
        now,
    )
    logger.info(
        "Incident created",
        extra={
            "incident_id": str(incident_id),
            "severity": severity,
            "state": state.value,
        },
    )
    return dict(row)


async def create_alert(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
    fingerprint: str,
    labels: dict,
    annotations: dict,
    status: str,
    fired_at: datetime,
) -> dict:
    """Persist an alert row linked to an incident.

    Returns a dict with the new alert row data.
    """
    alert_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    row = await conn.fetchrow(
        """
        INSERT INTO alerts (id, incident_id, fingerprint, labels, annotations, status, fired_at, created_at)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
        RETURNING id, incident_id, fingerprint, labels, annotations, status, fired_at, created_at
        """,
        alert_id,
        incident_id,
        fingerprint,
        json.dumps(labels),
        json.dumps(annotations),
        status,
        fired_at,
        now,
    )
    logger.info(
        "Alert persisted",
        extra={
            "alert_id": str(alert_id),
            "incident_id": str(incident_id),
            "fingerprint": fingerprint,
        },
    )
    return dict(row)


_ACTIVE_STATES = (
    "received",
    "correlating",
    "queued",
    "diagnosing",
    "diagnosed",
    "planning",
    "awaiting_approval",
    "executing",
    "observing",
)


async def list_incidents(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    statuses: list[str] | None = None,
    severities: list[str] | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Query incidents with filtering and pagination.

    The 'active' status filter maps to non-terminal pipeline states.
    Returns ``(rows, total_count)`` where *total_count* is the number
    of rows matching the filters before LIMIT/OFFSET are applied.
    """
    conditions: list[str] = []
    params: list = []
    param_idx = 0

    if statuses:
        expanded_statuses: list[str] = []
        for s in statuses:
            if s == "active":
                expanded_statuses.extend(_ACTIVE_STATES)
            else:
                expanded_statuses.append(s)
        param_idx += 1
        conditions.append(f"i.state = ANY(${param_idx}::text[])")
        params.append(expanded_statuses)

    if severities:
        param_idx += 1
        conditions.append(f"i.severity = ANY(${param_idx}::text[])")
        params.append(severities)

    if from_time:
        param_idx += 1
        conditions.append(f"i.created_at >= ${param_idx}")
        params.append(from_time)

    if to_time:
        param_idx += 1
        conditions.append(f"i.created_at <= ${param_idx}")
        params.append(to_time)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    count_query = f"SELECT COUNT(*) FROM incidents i {where_clause}"
    total: int = await conn.fetchval(count_query, *params)

    offset = (page - 1) * page_size
    param_idx += 1
    limit_param = f"${param_idx}"
    param_idx += 1
    offset_param = f"${param_idx}"

    data_query = f"""
        SELECT i.id, i.state, i.severity, i.created_at, i.updated_at, i.fast_path
        FROM incidents i
        {where_clause}
        ORDER BY CASE i.severity
            WHEN 'critical' THEN 1
            WHEN 'warning' THEN 2
            WHEN 'info' THEN 3
            ELSE 4
        END, i.created_at DESC
        LIMIT {limit_param} OFFSET {offset_param}
    """
    rows = await conn.fetch(data_query, *params, page_size, offset)
    return [dict(r) for r in rows], total


async def get_incident_detail(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
) -> dict | None:
    """Get full incident detail including correlated alerts and pipeline stages.

    Returns None if the incident does not exist.
    """
    incident_row = await conn.fetchrow(
        """
        SELECT id, state, severity, created_at, updated_at,
               fast_path, fast_path_similarity, fast_path_case_record_id,
               root_cause_event_id
        FROM incidents
        WHERE id = $1
        """,
        incident_id,
    )
    if incident_row is None:
        return None

    alert_rows = await conn.fetch(
        """
        SELECT id, fingerprint, labels, annotations, status, fired_at, resolved_at, created_at
        FROM alerts
        WHERE incident_id = $1
        ORDER BY fired_at ASC
        """,
        incident_id,
    )

    result = dict(incident_row)
    result["alerts"] = [dict(r) for r in alert_rows]

    correlation_evidence: dict = {}
    if result.get("root_cause_event_id"):
        corr_row = await conn.fetchrow(
            "SELECT correlation_evidence FROM correlation_groups WHERE id = $1",
            result["root_cause_event_id"],
        )
        if corr_row and corr_row["correlation_evidence"]:
            raw = corr_row["correlation_evidence"]
            if isinstance(raw, str):
                correlation_evidence = json.loads(raw)
            else:
                correlation_evidence = raw
    result["correlation_evidence"] = correlation_evidence

    diag_row = await conn.fetchrow(
        "SELECT diagnosis, skeptic_verdict, sealed_at, created_at "
        "FROM immutable_diagnoses WHERE incident_id = $1",
        incident_id,
    )
    if diag_row:
        diag_data = diag_row["diagnosis"]
        if isinstance(diag_data, str):
            diag_data = json.loads(diag_data)
        result["diagnosis"] = diag_data
        sv = diag_row["skeptic_verdict"]
        if isinstance(sv, str):
            sv = json.loads(sv)
        result["skeptic_verdict"] = sv
    else:
        result["diagnosis"] = None
        result["skeptic_verdict"] = None

    skeptic_rows = await conn.fetch(
        "SELECT round_number, response, created_at "
        "FROM skeptic_reviews WHERE incident_id = $1 ORDER BY round_number",
        incident_id,
    )
    diagnosis_attempts: list[dict] = []
    for srow in skeptic_rows:
        resp = srow["response"]
        if isinstance(resp, str):
            resp = json.loads(resp)
        revised = resp.get("revised_diagnosis") if isinstance(resp, dict) else None
        if revised:
            revised["created_at"] = srow["created_at"]
            diagnosis_attempts.append(revised)
    if diag_row and result["diagnosis"]:
        result["diagnosis"]["created_at"] = diag_row["created_at"]
        diagnosis_attempts.append(result["diagnosis"])
    result["diagnosis_attempts"] = diagnosis_attempts if len(diagnosis_attempts) > 1 else []

    plan_row = await conn.fetchrow(
        "SELECT plan, created_at FROM remediation_plans WHERE incident_id = $1",
        incident_id,
    )
    if plan_row:
        plan_data = plan_row["plan"]
        if isinstance(plan_data, str):
            plan_data = json.loads(plan_data)
        result["remediation_plan"] = plan_data
    else:
        result["remediation_plan"] = None

    exec_row = await conn.fetchrow(
        "SELECT steps, mcp_calls, started_at, completed_at, status "
        "FROM execution_logs WHERE incident_id = $1",
        incident_id,
    )
    if exec_row:
        steps = exec_row["steps"]
        if isinstance(steps, str):
            steps = json.loads(steps)
        mcp_calls = exec_row["mcp_calls"]
        if isinstance(mcp_calls, str):
            mcp_calls = json.loads(mcp_calls)
        result["execution_log"] = {
            "steps": steps or [],
            "mcp_calls": mcp_calls or [],
            "started_at": exec_row["started_at"],
            "completed_at": exec_row["completed_at"],
            "status": exec_row["status"],
        }
    else:
        result["execution_log"] = None

    outcome_row = await conn.fetchrow(
        "SELECT alert_resolved, resolution_method, resource_verification, "
        "outcome_confidence, refire_detected, observation_started_at, "
        "observation_completed_at "
        "FROM outcome_results WHERE incident_id = $1",
        incident_id,
    )
    if outcome_row:
        rv = outcome_row["resource_verification"]
        if isinstance(rv, str):
            rv = json.loads(rv)
        result["outcome"] = {
            "alert_resolved": outcome_row["alert_resolved"],
            "resolution_method": outcome_row["resolution_method"],
            "resource_verification": rv,
            "outcome_confidence": outcome_row["outcome_confidence"],
            "refire_detected": outcome_row["refire_detected"],
            "observation_started_at": outcome_row["observation_started_at"],
            "observation_completed_at": outcome_row["observation_completed_at"],
        }
    else:
        result["outcome"] = None

    return result


async def transition_incident_state(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
    from_state: str,
    to_state: str,
) -> bool:
    """Atomically transition an incident from one state to another.

    Uses a CAS (compare-and-swap) pattern: the UPDATE only succeeds
    if the row's current state matches from_state.

    Returns True if the transition was applied, False if the row was
    not found or the state had already changed (concurrent modification).
    """
    result = await conn.execute(
        "UPDATE incidents SET state = $1, updated_at = NOW() "
        "WHERE id = $2 AND state = $3",
        to_state,
        incident_id,
        from_state,
    )
    applied = result != "UPDATE 0"
    if applied:
        logger.info(
            "Incident state transitioned",
            extra={
                "incident_id": str(incident_id),
                "from_state": from_state,
                "to_state": to_state,
            },
        )
    else:
        logger.warning(
            "Incident state transition failed — concurrent modification or missing row",
            extra={
                "incident_id": str(incident_id),
                "expected_from": from_state,
                "target_to": to_state,
            },
        )
    return applied


async def record_fast_path(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
    case_record_id: uuid.UUID,
    similarity: float,
) -> None:
    """Record fast-path metadata on an incident."""
    await conn.execute(
        """
        UPDATE incidents
        SET fast_path = TRUE,
            fast_path_similarity = $2,
            fast_path_case_record_id = $3,
            updated_at = NOW()
        WHERE id = $1
        """,
        incident_id,
        similarity,
        case_record_id,
    )
    logger.info(
        "Fast-path metadata recorded on incident",
        extra={
            "incident_id": str(incident_id),
            "case_record_id": str(case_record_id),
            "similarity": similarity,
        },
    )


async def record_resolved_alert(
    conn: asyncpg.Connection | asyncpg.Pool,
    fingerprint: str,
    resolved_at: datetime,
) -> dict | None:
    """Record resolved status for an alert by fingerprint.

    Looks up the most recent firing alert with the given fingerprint.
    If found, updates its status to resolved and sets resolved_at.
    If no matching alert exists, logs and returns None.
    """
    row = await conn.fetchrow(
        """
        UPDATE alerts
        SET status = 'resolved', resolved_at = $2
        WHERE id = (
            SELECT id FROM alerts
            WHERE fingerprint = $1 AND status = 'firing'
            ORDER BY created_at DESC
            LIMIT 1
        )
        RETURNING id, incident_id, fingerprint, status, resolved_at
        """,
        fingerprint,
        resolved_at,
    )
    if row is None:
        logger.info(
            "Resolved alert has no matching firing alert — skipping",
            extra={"fingerprint": fingerprint},
        )
        return None

    logger.info(
        "Alert resolved",
        extra={
            "alert_id": str(row["id"]),
            "incident_id": str(row["incident_id"]),
            "fingerprint": fingerprint,
        },
    )
    return dict(row)
