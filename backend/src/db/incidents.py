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

    Returns (incidents, total_count) for pagination metadata.
    The 'active' status filter maps to non-terminal pipeline states.
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
    total = await conn.fetchval(count_query, *params)

    offset = (page - 1) * page_size
    param_idx += 1
    limit_param = param_idx
    param_idx += 1
    offset_param = param_idx

    data_query = f"""
        SELECT i.id, i.state, i.severity, i.created_at, i.updated_at, i.fast_path
        FROM incidents i
        {where_clause}
        ORDER BY i.created_at DESC
        LIMIT ${limit_param} OFFSET ${offset_param}
    """
    rows = await conn.fetch(data_query, *params, page_size, offset)
    return [dict(r) for r in rows], total


async def get_incident_detail(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
) -> dict | None:
    """Get full incident detail including correlated alerts.

    Returns None if the incident does not exist.
    """
    incident_row = await conn.fetchrow(
        """
        SELECT id, state, severity, created_at, updated_at,
               fast_path, fast_path_similarity, fast_path_case_record_id
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
    result["correlation_evidence"] = {}
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
