"""LangGraph StateGraph definition for the remediation pipeline (AD-1, Story 3.1).

Initial graph structure: entry → plan → END
Story 3.2 adds skeptic_validation node after plan.
Story 3.3 adds dry_run and policy_gate nodes.
The graph grows incrementally per story.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from .audit_hook import pipeline_audit_log

logger = get_logger(Component.PIPELINE)


class RemediationState(TypedDict):
    """Typed state schema for the LangGraph remediation pipeline."""

    incident_id: str
    immutable_artifact: dict
    remediation_plan: dict | None
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


def build_remediation_graph() -> StateGraph:
    """Build the LangGraph StateGraph for remediation (not yet compiled).

    Graph structure (Story 3.1): entry → plan → END
    """
    builder = StateGraph(RemediationState)
    builder.add_node("plan", plan_node)
    builder.set_entry_point("plan")
    builder.add_edge("plan", END)
    return builder
