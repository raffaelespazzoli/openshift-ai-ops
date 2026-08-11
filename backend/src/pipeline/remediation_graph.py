"""LangGraph StateGraph definition for the remediation pipeline (AD-1, Story 3.1/3.2).

Graph structure: entry → plan → skeptic_validation → END
Story 3.3 adds dry_run and policy_gate nodes.
The graph grows incrementally per story.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph

from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.events import EventNames, SSEEventData
from ..models.remediation import RemediationPlan
from .audit_hook import pipeline_audit_log

logger = get_logger(Component.PIPELINE)


class RemediationState(TypedDict):
    """Typed state schema for the LangGraph remediation pipeline."""

    incident_id: str
    immutable_artifact: dict
    remediation_plan: dict | None
    skeptic_challenge: dict | None
    skeptic_verdict: dict | None
    stage: str


async def plan_node(state: RemediationState) -> dict:
    """Plan stage node — invokes the remediation planner agent.

    Loads the ImmutableDiagnosisArtifact from state, invokes run_planner(),
    and stores the resulting RemediationPlan in state.
    """
    incident_id = state["incident_id"]
    logger.info("Plan node started", extra={"incident_id": incident_id})

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="remediation_plan",
        state_before=state.get("stage", "entered"),
        state_after="planning",
    )

    artifact_dict = state["immutable_artifact"]
    artifact = ImmutableDiagnosisArtifact.model_validate(artifact_dict)

    from ..agents.planner import run_planner

    plan = await run_planner(artifact)

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="remediation_plan",
        state_before="planning",
        state_after="planned",
        extra_detail={
            "step_count": len(plan.steps),
            "blast_radius": plan.blast_radius.value,
            "risk_level": plan.estimated_risk.value,
        },
    )

    return {
        "remediation_plan": plan.model_dump(mode="json"),
        "stage": "planned",
    }


async def skeptic_validation_node(state: RemediationState) -> dict:
    """Remediation skeptic validation — challenges the plan (Story 3.2).

    Loads the plan from state, runs the skeptic validation loop,
    and updates state with the verdict and possibly revised plan.

    SSE "validating" fires here (before the loop), while "validated"
    fires in the runner after artifacts are persisted transactionally.
    """
    from .remediation_skeptic_validation import run_remediation_skeptic_validation

    incident_id = state["incident_id"]
    logger.info(
        "Skeptic validation node started", extra={"incident_id": incident_id}
    )

    await _emit_skeptic_sse(incident_id, "validating")

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="skeptic_validation",
        state_before=state.get("stage", "planned"),
        state_after="validating",
    )

    plan_dict = state.get("remediation_plan")
    artifact_dict = state.get("immutable_artifact")

    plan = RemediationPlan.model_validate(plan_dict)
    artifact = ImmutableDiagnosisArtifact.model_validate(artifact_dict)

    validated_plan, verdict = await run_remediation_skeptic_validation(
        plan, artifact
    )

    return {
        "remediation_plan": validated_plan.model_dump(mode="json"),
        "skeptic_challenge": (
            verdict.challenge_history[-1]["challenge"]
            if verdict.challenge_history
            else None
        ),
        "skeptic_verdict": verdict.model_dump(mode="json"),
        "stage": "validated",
    }


def build_remediation_graph() -> StateGraph:
    """Build the LangGraph StateGraph for remediation (not yet compiled).

    Graph structure (Story 3.2): entry → plan → skeptic_validation → END
    """
    builder = StateGraph(RemediationState)
    builder.add_node("plan", plan_node)
    builder.add_node("skeptic_validation", skeptic_validation_node)
    builder.set_entry_point("plan")
    builder.add_edge("plan", "skeptic_validation")
    builder.add_edge("skeptic_validation", END)
    return builder


async def _emit_skeptic_sse(incident_id: str, state: str) -> None:
    """Emit an SSE event for the skeptic_validation stage."""
    try:
        from ..api.event_bus import get_event_bus

        bus = get_event_bus()
        await bus.emit(
            EventNames.INCIDENT_STAGE_CHANGED,
            SSEEventData(
                incident_id=uuid.UUID(incident_id),
                stage="skeptic_validation",
                state=state,
                payload={},
            ),
        )
    except Exception:
        logger.warning(
            "Failed to emit skeptic validation SSE event",
            extra={"incident_id": incident_id, "state": state},
        )
