"""Case record creation service (Story 4.1, AD-20).

Assembles incident data, generates vector embeddings, and persists
case records to the Learning Store. Best-effort: failures are logged
but never propagated — the execution cycle is unaffected.
"""

from __future__ import annotations

import json
import os
import uuid

from ..config.logging import Component, get_logger
from ..db.case_records import persist_case_record
from ..db.connection import get_pool
from ..models.case_record import CaseRecord

logger = get_logger(Component.PIPELINE)


def build_alert_signature(alerts: list[dict]) -> str:
    """Build a deterministic alert signature for embedding.

    Combines alert names, labels, and annotations into a
    searchable text string for pgvector similarity matching.
    """
    parts = []
    for alert in sorted(alerts, key=lambda a: a.get("name", "")):
        name = alert.get("name", "")
        labels = alert.get("labels", {})
        namespace = labels.get("namespace", "")
        severity = labels.get("severity", "")
        summary = alert.get("annotations", {}).get("summary", "")
        parts.append(f"{name} {namespace} {severity} {summary}")
    return " | ".join(parts)


async def create_case_record(incident_id: uuid.UUID) -> CaseRecord | None:
    """Create and persist a Case Record after incident resolution.

    Assembles all incident data (diagnosis, plan, outcome, cluster context),
    generates vector embeddings, and persists to case_records.

    Best-effort: failures are logged but never propagated to the caller.
    The execution cycle and incident state are never affected by case
    record creation failures.
    """
    try:
        pool = await get_pool()

        async with pool.acquire() as conn:
            alerts = await _load_incident_alerts(conn, incident_id)
            artifact = await _load_diagnosis(conn, incident_id)
            plan = await _load_remediation_plan(conn, incident_id)
            outcome = await _load_outcome(conn, incident_id)
            rollback_exists = await _check_rollback_exists(conn, incident_id)

        if artifact is None or outcome is None:
            logger.warning(
                "Missing required artifacts for case record",
                extra={"incident_id": str(incident_id)},
            )
            return None

        alert_signature = build_alert_signature(alerts)

        embedding = None
        try:
            from ..knowledge.embeddings import embed_texts

            embeddings = await embed_texts([alert_signature])
            if embeddings:
                embedding = embeddings[0]
        except Exception:
            logger.warning(
                "Embedding generation failed — persisting without vector",
                extra={"incident_id": str(incident_id)},
            )

        is_success = outcome.get("alert_resolved", False)
        refire_detected = outcome.get("refire_detected", False)
        fast_path_eligible = is_success and not rollback_exists and not refire_detected

        case_record = CaseRecord(
            incident_id=incident_id,
            alert_signature=alert_signature,
            root_cause_code=_extract_root_cause_code(artifact),
            diagnosis_object=artifact,
            remediation_plan=plan or {},
            outcome="success" if is_success else "failure",
            outcome_confidence=outcome.get("outcome_confidence", 0.2),
            outcome_details=outcome,
            ocp_version=_get_ocp_version(),
            cluster_context=_build_cluster_context(),
            diagnosis_summary=_summarize_diagnosis(artifact),
            remediation_summary=_summarize_plan(plan),
            fast_path_eligible=fast_path_eligible,
        )

        async with pool.acquire() as conn:
            await persist_case_record(conn, case_record, embedding)

        logger.info(
            "Case record created",
            extra={
                "incident_id": str(incident_id),
                "outcome": case_record.outcome,
                "fast_path_eligible": fast_path_eligible,
                "has_embedding": embedding is not None,
            },
        )

        return case_record

    except Exception:
        logger.exception(
            "Case record creation failed — non-fatal",
            extra={"incident_id": str(incident_id)},
        )
        return None


async def _load_incident_alerts(conn, incident_id: uuid.UUID) -> list[dict]:
    """Load alert data for the incident."""
    rows = await conn.fetch(
        """
        SELECT name, labels, annotations, status, fingerprint
        FROM alerts WHERE incident_id = $1
        """,
        incident_id,
    )
    results = []
    for row in rows:
        alert = {"name": row["name"], "status": row["status"]}
        labels = row.get("labels")
        if labels:
            alert["labels"] = json.loads(labels) if isinstance(labels, str) else labels
        else:
            alert["labels"] = {}
        annotations = row.get("annotations")
        if annotations:
            alert["annotations"] = (
                json.loads(annotations) if isinstance(annotations, str) else annotations
            )
        else:
            alert["annotations"] = {}
        results.append(alert)
    return results


async def _load_diagnosis(conn, incident_id: uuid.UUID) -> dict | None:
    """Load the immutable diagnosis artifact as a dict."""
    row = await conn.fetchrow(
        "SELECT diagnosis FROM immutable_diagnoses WHERE incident_id = $1",
        incident_id,
    )
    if row is None:
        return None
    diag = row["diagnosis"]
    if isinstance(diag, str):
        diag = json.loads(diag)
    return diag


async def _load_remediation_plan(conn, incident_id: uuid.UUID) -> dict | None:
    """Load the remediation plan as a dict."""
    row = await conn.fetchrow(
        "SELECT plan FROM remediation_plans WHERE incident_id = $1",
        incident_id,
    )
    if row is None:
        return None
    plan = row["plan"]
    if isinstance(plan, str):
        plan = json.loads(plan)
    return plan


async def _load_outcome(conn, incident_id: uuid.UUID) -> dict | None:
    """Load the outcome result as a dict."""
    row = await conn.fetchrow(
        """
        SELECT alert_resolved, resolution_method, resource_verification,
               outcome_confidence, refire_detected
        FROM outcome_results WHERE incident_id = $1
        """,
        incident_id,
    )
    if row is None:
        return None
    result = dict(row)
    rv = result.get("resource_verification")
    if rv and isinstance(rv, str):
        result["resource_verification"] = json.loads(rv)
    return result


async def _check_rollback_exists(conn, incident_id: uuid.UUID) -> bool:
    """Check if a rollback record exists for this incident."""
    val = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM rollback_records WHERE incident_id = $1)",
        incident_id,
    )
    return bool(val)


def _extract_root_cause_code(artifact: dict) -> str:
    """Extract root_cause_code from a diagnosis artifact dict."""
    return artifact.get("root_cause_code", "unknown/unknown")


def _get_ocp_version() -> str:
    """Get OCP version from environment or default."""
    return os.environ.get("OCP_VERSION", "4.x")


def _build_cluster_context() -> dict:
    """Build cluster context from available environment data."""
    return {
        "ocp_version": _get_ocp_version(),
        "cluster_id": os.environ.get("CLUSTER_ID", ""),
    }


def _summarize_diagnosis(artifact: dict) -> str:
    """Build a summary string from the diagnosis artifact."""
    if not artifact:
        return ""
    component = artifact.get("root_cause_component", "")
    mode = artifact.get("failure_mode", "")
    summary = artifact.get("agent_summary", "")
    if summary:
        return summary
    return f"{component}/{mode}" if component else ""


def _summarize_plan(plan: dict | None) -> str:
    """Build a summary string from the remediation plan."""
    if not plan:
        return ""
    return plan.get("plan_summary", "")
