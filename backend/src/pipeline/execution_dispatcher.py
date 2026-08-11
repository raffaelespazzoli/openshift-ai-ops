"""Background execution dispatcher with global lock (AD-18, Story 3.5).

Polls for incidents in 'executing' state. Acquires the global
remediation lock before proceeding. Only one execution at a time.
After execution + observation + cooldown: releases lock.
"""

from __future__ import annotations

import asyncio
import uuid

from ..config.execution_settings import ExecutionSettings, get_execution_settings
from ..config.logging import Component, get_logger
from ..db.connection import get_pool
from ..db.execution import persist_execution_log, persist_outcome_result
from ..db.incidents import transition_incident_state
from ..db.remediation_lock import acquire_remediation_lock, release_remediation_lock
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.execution import ExecutionLog
from ..models.remediation import RemediationPlan
from ..models.state_machine import IncidentState, transition
from .audit_hook import pipeline_audit_log
from .execution_engine import execute_remediation
from .mcp_readwrite_client import ReadWriteMCPClient
from .outcome_observer import monitor_for_refire, observe_outcome

logger = get_logger(Component.PIPELINE)


async def run_execution_dispatcher(
    settings: ExecutionSettings | None = None,
) -> None:
    """Background loop for dispatching remediation execution.

    Polls for incidents in 'executing' state. Acquires the global
    remediation lock before proceeding. Only one execution at a time.
    """
    config = settings or get_execution_settings()

    while True:
        try:
            await _dispatch_one(config)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Execution dispatcher error")

        await asyncio.sleep(config.lock_poll_interval_seconds)


async def _dispatch_one(config: ExecutionSettings) -> None:
    """Attempt to dispatch one execution cycle."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.id, rp.plan, rp.id AS plan_id
            FROM incidents i
            JOIN remediation_plans rp ON rp.incident_id = i.id
            WHERE i.state = 'executing'
            ORDER BY i.updated_at ASC
            LIMIT 1
            """
        )

    if row is None:
        return

    incident_id = row["id"]
    await _execute_with_lock(incident_id, row, config)


async def _execute_with_lock(
    incident_id: uuid.UUID,
    row: dict,
    config: ExecutionSettings,
) -> None:
    """Acquire lock, run execution + observation + cooldown, then release."""
    pool = await get_pool()

    async with pool.acquire() as lock_conn:
        async with lock_conn.transaction():
            acquired = await acquire_remediation_lock(lock_conn, incident_id)
            if not acquired:
                logger.info(
                    "Lock not available — another execution in progress",
                    extra={"incident_id": str(incident_id)},
                )
                return

            try:
                await _run_execution_cycle(incident_id, row, config)
            finally:
                await release_remediation_lock(lock_conn)


async def _run_execution_cycle(
    incident_id: uuid.UUID,
    row: dict,
    config: ExecutionSettings,
) -> None:
    """Full execution cycle: freshness → execute → persist → observe → cooldown."""
    import json as _json

    from .freshness_gate import check_freshness

    pool = await get_pool()

    plan_data = row["plan"]
    if isinstance(plan_data, str):
        plan_data = _json.loads(plan_data)
    plan = RemediationPlan.model_validate(plan_data)

    async with pool.acquire() as conn:
        artifact_row = await conn.fetchrow(
            "SELECT diagnosis FROM immutable_diagnoses WHERE incident_id = $1",
            incident_id,
        )

    if artifact_row is None:
        logger.error(
            "No immutable artifact found for incident",
            extra={"incident_id": str(incident_id)},
        )
        return

    diagnosis_data = artifact_row["diagnosis"]
    if isinstance(diagnosis_data, str):
        diagnosis_data = _json.loads(diagnosis_data)
    artifact = ImmutableDiagnosisArtifact.model_validate(diagnosis_data)

    async with pool.acquire() as conn:
        freshness = await check_freshness(incident_id, artifact, conn)

    if not freshness.is_fresh:
        logger.info(
            "Freshness gate failed — skipping execution",
            extra={
                "incident_id": str(incident_id),
                "reason": freshness.reason,
            },
        )
        async with pool.acquire() as conn:
            await transition_incident_state(
                conn,
                incident_id,
                IncidentState.EXECUTING.value,
                IncidentState.OBSERVING.value,
            )
            transition(IncidentState.OBSERVING, IncidentState.FAILED)
            await transition_incident_state(
                conn,
                incident_id,
                IncidentState.OBSERVING.value,
                IncidentState.FAILED.value,
            )
        return

    await pipeline_audit_log(
        incident_id=str(incident_id),
        stage_name="execution",
        state_before="executing",
        state_after="running",
    )

    mcp_client = ReadWriteMCPClient()
    execution_log = await execute_remediation(plan, mcp_client)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await persist_execution_log(conn, execution_log)

    new_state = transition(IncidentState.EXECUTING, IncidentState.OBSERVING)
    async with pool.acquire() as conn:
        await transition_incident_state(
            conn, incident_id,
            IncidentState.EXECUTING.value, new_state.value,
        )

    await _emit_execution_event(incident_id, "execution", "completed")

    await pipeline_audit_log(
        incident_id=str(incident_id),
        stage_name="execution",
        state_before="running",
        state_after="observing",
    )

    outcome = await observe_outcome(incident_id, artifact, execution_log)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await persist_outcome_result(conn, outcome)

    if outcome.alert_resolved:
        final_state = transition(IncidentState.OBSERVING, IncidentState.RESOLVED)
    else:
        final_state = transition(IncidentState.OBSERVING, IncidentState.FAILED)

    async with pool.acquire() as conn:
        await transition_incident_state(
            conn, incident_id,
            IncidentState.OBSERVING.value, final_state.value,
        )

    await _emit_execution_event(
        incident_id, "observation",
        "resolved" if outcome.alert_resolved else "failed",
    )

    await pipeline_audit_log(
        incident_id=str(incident_id),
        stage_name="observation",
        state_before="observing",
        state_after=final_state.value,
        extra_detail={
            "outcome_confidence": outcome.outcome_confidence,
            "resolution_method": outcome.resolution_method,
        },
    )

    if outcome.alert_resolved:
        asyncio.create_task(_background_refire_monitor(incident_id))

    if config.cooldown_seconds > 0:
        await asyncio.sleep(config.cooldown_seconds)


async def _background_refire_monitor(incident_id: uuid.UUID) -> None:
    """Background task for re-fire detection (non-blocking)."""
    try:
        await monitor_for_refire(incident_id)
    except Exception:
        logger.warning(
            "Re-fire monitor failed",
            extra={"incident_id": str(incident_id)},
        )


async def _emit_execution_event(
    incident_id: uuid.UUID,
    stage: str,
    state: str,
) -> None:
    """Emit an SSE event for execution pipeline stage transitions."""
    try:
        from ..api.event_bus import get_event_bus
        from ..models.events import EventNames, SSEEventData

        bus = get_event_bus()
        await bus.emit(
            EventNames.INCIDENT_STAGE_CHANGED,
            SSEEventData(
                incident_id=incident_id,
                stage=stage,
                state=state,
                payload={},
            ),
        )
    except Exception:
        logger.warning(
            "Failed to emit execution stage event",
            extra={"incident_id": str(incident_id), "stage": stage},
        )
