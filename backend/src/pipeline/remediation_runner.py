"""Remediation pipeline runner (AD-1, Story 3.1/3.2).

Bridges the dispatcher to the remediation LangGraph graph.
Loads the sealed ImmutableDiagnosisArtifact from the database,
invokes the remediation graph, and persists the resulting plan
and skeptic artifacts.

On failure the runner transitions the incident to ``failed`` so it
does not get stranded in ``planning``.  The success-path exit
(``planning → awaiting_approval`` or ``planning → executing``) is
handled by Story 3.3's policy gate.
"""

from __future__ import annotations

import uuid

from ..config.logging import Component, get_logger
from ..db import get_pool
from ..db.checkpointer import get_checkpointer
from ..db.remediation import load_immutable_artifact, persist_remediation_plan
from ..db.remediation_skeptic import persist_remediation_skeptic_record
from ..models.events import EventNames, SSEEventData
from ..models.remediation import RemediationPlan
from ..models.state_machine import IncidentState, transition
from .audit_hook import pipeline_audit_log
from .remediation_graph import RemediationState, build_remediation_graph

logger = get_logger(Component.PIPELINE)


async def run_remediation_pipeline(incident_id: uuid.UUID) -> RemediationPlan | None:
    """Run the remediation pipeline for an incident.

    Loads the sealed artifact from immutable_diagnoses, invokes the
    remediation graph, persists the plan, and emits SSE events.

    Args:
        incident_id: The incident UUID to plan remediation for.

    Returns:
        The persisted RemediationPlan, or None on failure.
    """
    logger.info(
        "Starting remediation pipeline",
        extra={"incident_id": str(incident_id)},
    )

    await _emit_remediation_event(incident_id, "remediation_plan", "planning")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            artifact = await load_immutable_artifact(conn, incident_id)

        checkpointer = await get_checkpointer()
        builder = build_remediation_graph()
        graph = builder.compile(checkpointer=checkpointer)

        initial_state: RemediationState = {
            "incident_id": str(incident_id),
            "immutable_artifact": artifact.model_dump(mode="json"),
            "remediation_plan": None,
            "skeptic_challenge": None,
            "skeptic_verdict": None,
            "stage": "entered",
        }

        thread_id = f"remediation-{incident_id}"
        config = {"configurable": {"thread_id": thread_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        plan_dict = final_state.get("remediation_plan")
        if plan_dict is None:
            logger.error(
                "Remediation graph produced no plan",
                extra={"incident_id": str(incident_id)},
            )
            await _transition_to_failed(incident_id)
            await _emit_remediation_event(incident_id, "remediation_plan", "failed")
            return None

        plan = RemediationPlan.model_validate(plan_dict)

        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await persist_remediation_plan(conn, plan)
                    await _persist_skeptic_artifacts(
                        conn, incident_id, final_state
                    )
                    if final_state.get("skeptic_verdict"):
                        verdict = final_state["skeptic_verdict"]
                        await pipeline_audit_log(
                            incident_id=str(incident_id),
                            stage_name="skeptic_validation",
                            state_before="validating",
                            state_after="validated",
                            extra_detail={
                                "rounds_completed": verdict.get("rounds_completed"),
                                "hash_changed": (
                                    verdict.get("original_plan_hash")
                                    != verdict.get("final_plan_hash")
                                ),
                                "degraded": verdict.get("degraded", False),
                                "verdict_note": verdict.get("verdict_note"),
                            },
                            conn=conn,
                        )
        except Exception:
            if final_state.get("skeptic_verdict"):
                await _emit_remediation_event(
                    incident_id, "skeptic_validation", "failed"
                )
            raise

        if final_state.get("skeptic_verdict"):
            verdict = final_state["skeptic_verdict"]
            await _emit_remediation_event(
                incident_id,
                "skeptic_validation",
                "validated",
                payload={
                    "degraded": verdict.get("degraded", False),
                    "verdict_note": verdict.get("verdict_note"),
                },
            )
        await _emit_remediation_event(incident_id, "remediation_plan", "planned")

        logger.info(
            "Remediation pipeline completed successfully",
            extra={
                "incident_id": str(incident_id),
                "plan_id": str(plan.id),
                "step_count": len(plan.steps),
            },
        )

        return plan

    except Exception:
        logger.exception(
            "Remediation pipeline failed",
            extra={"incident_id": str(incident_id)},
        )
        await _transition_to_failed(incident_id)
        await _emit_remediation_event(incident_id, "skeptic_validation", "failed")
        await _emit_remediation_event(incident_id, "remediation_plan", "failed")
        return None


async def _persist_skeptic_artifacts(
    conn,
    incident_id: uuid.UUID,
    final_state: dict,
) -> None:
    """Persist remediation skeptic challenge/response records from graph state."""
    verdict_dict = final_state.get("skeptic_verdict")
    if not verdict_dict:
        return

    challenge_history = verdict_dict.get("challenge_history", [])
    for entry in challenge_history:
        round_number = entry.get("round", 1)
        challenge = entry.get("challenge", {})
        response = entry.get("response", {})
        is_final = round_number == len(challenge_history)
        await persist_remediation_skeptic_record(
            conn,
            incident_id=incident_id,
            round_number=round_number,
            challenge=challenge,
            response=response,
            verdict=verdict_dict if is_final else None,
        )


async def _transition_to_failed(incident_id: uuid.UUID) -> None:
    """Transition the incident from planning → failed so it is not stranded."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            current_val = await conn.fetchval(
                "SELECT state FROM incidents WHERE id = $1", incident_id
            )
            if current_val is None:
                return
            current = IncidentState(current_val)
            new_state = transition(current, IncidentState.FAILED)
            await conn.execute(
                "UPDATE incidents SET state = $2, updated_at = NOW() WHERE id = $1",
                incident_id,
                new_state.value,
            )
            logger.info(
                "Incident transitioned to failed after remediation failure",
                extra={"incident_id": str(incident_id)},
            )
    except Exception:
        logger.warning(
            "Could not transition incident to failed",
            extra={"incident_id": str(incident_id)},
        )


async def _emit_remediation_event(
    incident_id: uuid.UUID,
    stage: str,
    state: str,
    *,
    payload: dict | None = None,
) -> None:
    """Emit an SSE event for remediation pipeline stage transitions."""
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
            "Failed to emit remediation stage event",
            extra={"incident_id": str(incident_id), "stage": stage},
        )
