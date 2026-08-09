"""Pipeline runner — invokes the LangGraph diagnosis graph (AD-1, AD-3).

Bridges the dispatcher's queue items to LangGraph graph invocations.
Uses incident UUID as the LangGraph thread_id for checkpoint
addressing and resumption (AD-3 checkpoint persistence).
"""

from __future__ import annotations

import uuid

from ..config.logging import Component, get_logger
from ..db import get_pool
from ..db.checkpointer import get_checkpointer
from ..db.queue import get_rce_alert_data, get_rce_incident_ids, mark_pipeline_complete
from ..models.events import EventNames, SSEEventData
from ..models.state_machine import IncidentState, transition
from .diagnosis_graph import DiagnosisState, build_diagnosis_graph

logger = get_logger(Component.PIPELINE)


async def run_diagnosis_pipeline(item: dict) -> None:
    """Run the diagnosis pipeline for a dequeued queue item.

    Args:
        item: A dequeued queue row dict with at minimum:
              id, incident_id, root_cause_event_id, priority_score.
    """
    incident_id = str(item["incident_id"])
    queue_item_id = item["id"]

    logger.info(
        "Starting diagnosis pipeline",
        extra={
            "incident_id": incident_id,
            "queue_item_id": str(queue_item_id),
        },
    )

    all_ids: list[uuid.UUID] | None = None
    try:
        all_ids = await _get_all_incident_ids(item)

        for iid in all_ids:
            await _emit_stage_event(iid, "diagnose", "diagnosing")

        alerts = await _fetch_rce_alerts(item["root_cause_event_id"])

        checkpointer = await get_checkpointer()
        builder = build_diagnosis_graph()
        graph = builder.compile(checkpointer=checkpointer)

        initial_state: DiagnosisState = {
            "incident_id": incident_id,
            "root_cause_event": {
                "id": str(item["root_cause_event_id"]),
                "priority_score": item["priority_score"],
            },
            "alerts": alerts,
            "mcp_evidence": [],
            "evidence_gaps": [],
            "diagnosis": None,
            "stage": "entered",
            "runbook_context": [],
            "completeness_attempts": 0,
            "coverage_gaps": [],
            "rejected_hypotheses": [],
            "unaddressed_alerts": [],
            "evidence_ledger": [],
        }

        config = {"configurable": {"thread_id": incident_id}}
        final_state = await graph.ainvoke(initial_state, config=config)

        for iid in all_ids:
            await _emit_stage_event(iid, "finalize", "finalizing")

        await _handle_success(item, final_state, all_ids)
    except Exception:
        logger.exception(
            "Diagnosis pipeline failed",
            extra={"incident_id": incident_id},
        )
        await _handle_failure(item, all_ids)


async def _fetch_rce_alerts(root_cause_event_id: uuid.UUID) -> list[dict]:
    """Fetch all alert data for the RCE so the orchestrator has real metadata."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await get_rce_alert_data(conn, root_cause_event_id)

    alerts = []
    for row in rows:
        alerts.append({
            "fingerprint": row["fingerprint"],
            "labels": row["labels"] if isinstance(row["labels"], dict) else {},
            "annotations": row["annotations"] if isinstance(row["annotations"], dict) else {},
            "status": row["status"],
        })
    return alerts


async def _get_all_incident_ids(item: dict) -> list[uuid.UUID]:
    """Resolve all incident IDs for this queue item's RCE group."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        ids = await get_rce_incident_ids(conn, item["root_cause_event_id"])
    if not ids:
        ids = [item["incident_id"]]
    return ids


async def _transition_all_incidents(
    conn,
    incident_ids: list[uuid.UUID],
    target: IncidentState,
) -> None:
    """Transition all sibling incidents to the target state (AD-19).

    Must be called within the caller's transaction scope so that incident
    state writes and queue completion are atomic. Raises on any failure
    so the caller's transaction rolls back everything together.
    """
    for iid in incident_ids:
        current_state_val = await conn.fetchval(
            "SELECT state FROM incidents WHERE id = $1", iid
        )
        if current_state_val is None:
            raise ValueError(f"Incident {iid} not found")
        current = IncidentState(current_state_val)
        new_state = transition(current, target)
        await conn.execute(
            "UPDATE incidents SET state = $2, updated_at = NOW() WHERE id = $1",
            iid,
            new_state.value,
        )


async def _complete_pipeline(
    item: dict,
    incident_ids: list[uuid.UUID],
    target: IncidentState,
    final_state: dict | None = None,
) -> bool:
    """Atomically transition all incidents AND complete the queue item (AD-19).

    Wraps incident state writes, queue completion, and skeptic artifact
    persistence in a single DB transaction so they either all succeed or
    all roll back together. This prevents the state where incidents reach
    a terminal state but the queue row remains 'processing' (which creates
    poison retries), and ensures the audit trail and immutable handoff
    record are always present when the pipeline reports success.

    Returns True only when the entire transaction committed successfully.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _transition_all_incidents(conn, incident_ids, target)
                await mark_pipeline_complete(conn, item["id"])

                if final_state and target == IncidentState.DIAGNOSED:
                    await _persist_skeptic_artifacts_in_txn(
                        conn, incident_ids, final_state,
                    )
    except Exception:
        logger.warning(
            "Pipeline completion failed — transaction rolled back, queue slot NOT freed",
            extra={
                "target": target.value,
                "incident_count": len(incident_ids),
                "queue_item_id": str(item["id"]),
            },
        )
        return False
    return True


async def _persist_skeptic_artifacts_in_txn(
    conn,
    incident_ids: list[uuid.UUID],
    final_state: dict,
) -> None:
    """Persist skeptic artifacts for ALL incidents in the RCE group."""
    from .diagnosis_graph import persist_skeptic_artifacts
    from ..models.diagnosis import ImmutableDiagnosisArtifact
    from ..models.skeptic import SkepticVerdict

    verdict_dict = final_state.get("skeptic_verdict")
    artifact_dict = final_state.get("immutable_artifact")

    if not verdict_dict or not artifact_dict:
        return

    verdict = SkepticVerdict.model_validate(verdict_dict)
    sealed = ImmutableDiagnosisArtifact.model_validate(artifact_dict)

    for iid in incident_ids:
        await persist_skeptic_artifacts(conn, str(iid), verdict, sealed)


async def _handle_success(
    item: dict,
    final_state: dict,
    all_ids: list[uuid.UUID] | None = None,
) -> None:
    """Handle successful graph completion: transition ALL sibling incidents + mark complete atomically.

    Both incident state writes and queue completion happen in a single
    transaction. If anything fails, the entire transaction rolls back and
    the queue slot stays occupied for dispatcher retry.
    """
    if all_ids is None:
        all_ids = await _get_all_incident_ids(item)

    committed = await _complete_pipeline(
        item, all_ids, IncidentState.DIAGNOSED, final_state=final_state,
    )

    if not committed:
        logger.error(
            "Terminal state + queue completion failed — queue slot NOT freed",
            extra={
                "incident_id": str(item["incident_id"]),
                "queue_item_id": str(item["id"]),
            },
        )
        return

    skeptic_verdict = final_state.get("skeptic_verdict") if final_state else None
    if skeptic_verdict:
        for iid in all_ids:
            await _emit_stage_event(
                iid, "skeptic_validation", "validated",
                payload={"skeptic_verdict": skeptic_verdict},
            )

    for iid in all_ids:
        await _emit_stage_event(iid, "diagnosed", "diagnosed")

    logger.info(
        "Diagnosis pipeline completed successfully",
        extra={
            "incident_id": str(item["incident_id"]),
            "sibling_count": len(all_ids),
        },
    )


async def _handle_failure(
    item: dict,
    all_ids: list[uuid.UUID] | None = None,
) -> None:
    """Handle pipeline failure: transition ALL sibling incidents to failed + mark complete atomically.

    Same atomic pattern as _handle_success — both incident state writes
    and queue completion happen in a single transaction.
    """
    if all_ids is None:
        all_ids = await _get_all_incident_ids(item)

    committed = await _complete_pipeline(item, all_ids, IncidentState.FAILED)

    if not committed:
        logger.error(
            "Terminal state + queue completion failed on failure path — queue slot NOT freed",
            extra={
                "incident_id": str(item["incident_id"]),
                "queue_item_id": str(item["id"]),
            },
        )
        return

    for iid in all_ids:
        await _emit_stage_event(iid, "failed", "failed")

    logger.info(
        "Diagnosis pipeline failed — slot freed",
        extra={
            "incident_id": str(item["incident_id"]),
            "sibling_count": len(all_ids),
        },
    )


async def _emit_stage_event(
    incident_id: uuid.UUID,
    stage: str,
    state: str,
    payload: dict | None = None,
) -> None:
    """Emit an SSE event for pipeline stage transitions (AD-24)."""
    try:
        from ..api.event_bus import get_event_bus

        bus = get_event_bus()
        await bus.emit(
            EventNames.INCIDENT_STAGE_CHANGED,
            SSEEventData(
                incident_id=incident_id,
                stage=stage,
                state=state,
                payload=payload or {},
            ),
        )
    except Exception:
        logger.warning(
            "Failed to emit stage change event",
            extra={"incident_id": str(incident_id), "stage": stage},
        )
