"""Remediation pipeline runner (AD-1, Story 3.1/3.2/3.3).

Bridges the dispatcher to the remediation LangGraph graph.
Loads the sealed ImmutableDiagnosisArtifact from the database,
invokes the remediation graph, persists the resulting plan
and skeptic artifacts, and transitions incident state based
on the policy gate decision.
"""

from __future__ import annotations

import uuid

from ..config.logging import Component, get_logger
from ..db import get_pool
from ..db.checkpointer import get_checkpointer
from ..db.policy_gate import persist_dry_run_result, persist_policy_decision
from ..db.remediation import load_immutable_artifact, persist_remediation_plan
from ..db.remediation_skeptic import persist_remediation_skeptic_record
from ..models.events import EventNames, SSEEventData
from ..models.policy_gate import DryRunResult, PolicyDecision
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
            alert_severity = await conn.fetchval(
                "SELECT severity FROM incidents WHERE id = $1", incident_id
            )

        checkpointer = await get_checkpointer()
        builder = build_remediation_graph()
        graph = builder.compile(checkpointer=checkpointer)

        initial_state: RemediationState = {
            "incident_id": str(incident_id),
            "immutable_artifact": artifact.model_dump(mode="json"),
            "remediation_plan": None,
            "skeptic_challenge": None,
            "skeptic_verdict": None,
            "dry_run_result": None,
            "policy_decision": None,
            "alert_severity": alert_severity,
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
                    await _persist_policy_artifacts(
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
                    await _handle_policy_decision(
                        conn, incident_id, final_state
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

        decision_dict = final_state.get("policy_decision")
        if decision_dict:
            decision = PolicyDecision.model_validate(decision_dict)
            if decision.auto_execution_approved:
                await _emit_remediation_event(
                    incident_id, "policy_gate", "approved",
                    payload={"reasoning": decision.reasoning},
                )
            else:
                await _emit_remediation_event(
                    incident_id, "policy_gate", "denied",
                    payload={"reasoning": decision.reasoning},
                )

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


async def _persist_policy_artifacts(
    conn,
    incident_id: uuid.UUID,
    final_state: dict,
) -> None:
    """Persist dry-run result and policy decision from graph state."""
    dry_run_dict = final_state.get("dry_run_result")
    if dry_run_dict:
        dr = DryRunResult.model_validate(dry_run_dict)
        await persist_dry_run_result(conn, dr)

    decision_dict = final_state.get("policy_decision")
    if decision_dict:
        pd = PolicyDecision.model_validate(decision_dict)
        await persist_policy_decision(conn, pd)


async def _handle_policy_decision(
    conn,
    incident_id: uuid.UUID,
    graph_output: dict,
) -> None:
    """Transition incident state based on policy gate decision (AD-19)."""
    decision_dict = graph_output.get("policy_decision")
    if decision_dict is None:
        return

    decision = PolicyDecision.model_validate(decision_dict)

    current_val = await conn.fetchval(
        "SELECT state FROM incidents WHERE id = $1", incident_id
    )
    if current_val is None:
        logger.warning(
            "Incident not found for policy decision",
            extra={"incident_id": str(incident_id)},
        )
        return
    current = IncidentState(current_val)

    if decision.auto_execution_approved:
        new_state = transition(current, IncidentState.EXECUTING)
    else:
        new_state = transition(current, IncidentState.AWAITING_APPROVAL)

    await conn.execute(
        "UPDATE incidents SET state = $1, updated_at = NOW() "
        "WHERE id = $2 AND state = $3",
        new_state.value,
        incident_id,
        current_val,
    )

    from ..db.audit import write_audit_log

    await write_audit_log(
        conn,
        actor="pipeline",
        action="pipeline.policy_gate.decision",
        target_resource=f"incident/{incident_id}",
        detail={
            "auto_approved": decision.auto_execution_approved,
            "reasoning": decision.reasoning,
        },
    )

    logger.info(
        "Incident state transitioned based on policy decision",
        extra={
            "incident_id": str(incident_id),
            "new_state": new_state.value,
            "auto_approved": decision.auto_execution_approved,
        },
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
