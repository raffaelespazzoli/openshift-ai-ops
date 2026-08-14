"""LangGraph StateGraph definition for the remediation pipeline (AD-1, Story 3.1–4.0).

Graph structure (planning only):
  entry → plan → skeptic_validation → manifest_generation → dry_run → policy_gate → END

Execution nodes (freshness_gate, execute, observe) are defined here as functions
but are NOT wired into the graph — the execution_dispatcher calls them directly.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph

from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.events import EventNames, SSEEventData
from ..models.execution import ExecutionLog
from ..models.policy_gate import DryRunResult
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
    dry_run_result: dict | None
    policy_decision: dict | None
    freshness_result: dict | None
    execution_log: dict | None
    outcome_result: dict | None
    alert_severity: str | None
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


async def manifest_generation_node(state: RemediationState) -> dict:
    """Generate YAML manifests for eligible remediation steps (Story 4.0).

    Queries current cluster state via the read-write MCP Server,
    produces patched YAML manifests, and stores them as file artifacts
    for downstream dry-run and execution stages.
    """
    from .manifest_generator import generate_manifests
    from .mcp_readwrite_client import ReadWriteMCPClient

    incident_id = state["incident_id"]
    logger.info(
        "Manifest generation node started",
        extra={"incident_id": incident_id},
    )

    await _emit_stage_sse(incident_id, "manifest_generation", "running")

    plan = RemediationPlan.model_validate(state["remediation_plan"])
    mcp_client = ReadWriteMCPClient()

    manifest_plan = await generate_manifests(plan, mcp_client)

    eligible = sum(
        1 for s in plan.steps
        if s.command is not None and s.action.lower() in {"apply", "create"}
    )
    generated = sum(1 for s in manifest_plan.steps if s.manifest_path is not None)
    failed = sum(1 for s in manifest_plan.steps if s.manifest_generation_failed)
    skipped = len(plan.steps) - eligible

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="manifest_generation",
        state_before="validated",
        state_after="manifests_generated",
        extra_detail={
            "eligible": eligible,
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
        },
    )

    await _emit_stage_sse(incident_id, "manifest_generation", "complete")

    return {
        "remediation_plan": manifest_plan.model_dump(mode="json"),
        "stage": "manifests_generated",
    }


async def dry_run_node(state: RemediationState) -> dict:
    """Dry-run pre-flight validation (Story 3.3)."""
    from .dry_run import run_dry_run_preflight

    incident_id = state["incident_id"]
    logger.info("Dry-run node started", extra={"incident_id": incident_id})

    await _emit_stage_sse(incident_id, "dry_run", "running")

    plan = RemediationPlan.model_validate(state["remediation_plan"])
    artifact = ImmutableDiagnosisArtifact.model_validate(state["immutable_artifact"])

    dry_run_result = await run_dry_run_preflight(plan, artifact)

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="dry_run",
        state_before="validated",
        state_after="dry_run_complete",
        extra_detail={
            "dry_run_passed": dry_run_result.dry_run_passed,
            "error_count": len(dry_run_result.dry_run_errors),
        },
    )

    return {
        "dry_run_result": dry_run_result.model_dump(mode="json"),
        "stage": "dry_run_complete",
    }


async def policy_gate_node(state: RemediationState) -> dict:
    """Policy gate evaluation — decides auto-execute or human approval (Story 3.3)."""
    from .policy_gate import evaluate_policy_gate

    incident_id = state["incident_id"]
    logger.info("Policy gate node started", extra={"incident_id": incident_id})

    plan = RemediationPlan.model_validate(state["remediation_plan"])
    artifact = ImmutableDiagnosisArtifact.model_validate(state["immutable_artifact"])
    dry_run = DryRunResult.model_validate(state["dry_run_result"])
    alert_severity = state.get("alert_severity")

    decision = await evaluate_policy_gate(
        plan, artifact, dry_run, alert_severity=alert_severity,
    )

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="policy_gate",
        state_before="dry_run_complete",
        state_after="policy_decided",
        extra_detail={
            "auto_approved": decision.auto_execution_approved,
            "reasoning": decision.reasoning,
        },
    )

    return {
        "policy_decision": decision.model_dump(mode="json"),
        "stage": "policy_decided",
    }


def build_remediation_graph() -> StateGraph:
    """Build the LangGraph StateGraph for remediation planning (not yet compiled).

    Planning-only graph:
      entry → plan → skeptic_validation → manifest_generation → dry_run → policy_gate → END

    Execution (freshness_gate → execute → observe) is handled by the
    execution_dispatcher, which calls the node functions directly.
    """
    builder = StateGraph(RemediationState)
    builder.add_node("plan", plan_node)
    builder.add_node("skeptic_validation", skeptic_validation_node)
    builder.add_node("manifest_generation", manifest_generation_node)
    builder.add_node("dry_run", dry_run_node)
    builder.add_node("policy_gate", policy_gate_node)
    builder.set_entry_point("plan")
    builder.add_edge("plan", "skeptic_validation")
    builder.add_edge("skeptic_validation", "manifest_generation")
    builder.add_edge("manifest_generation", "dry_run")
    builder.add_edge("dry_run", "policy_gate")
    builder.add_edge("policy_gate", END)
    return builder


async def freshness_gate_node(state: RemediationState) -> dict:
    """Freshness gate — verifies alert still firing before execution (AD-16)."""
    from .freshness_gate import check_freshness

    incident_id = uuid.UUID(state["incident_id"])
    artifact = ImmutableDiagnosisArtifact.model_validate(state["immutable_artifact"])

    from ..db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await check_freshness(incident_id, artifact, conn)

    await _emit_stage_sse(incident_id, "freshness_gate", "checked")

    return {
        "freshness_result": {
            "is_fresh": result.is_fresh,
            "alert_still_firing": result.alert_still_firing,
            "diagnosis_still_relevant": result.diagnosis_still_relevant,
            "reason": result.reason,
        },
        "stage": "freshness_checked",
    }


async def execute_node(state: RemediationState) -> dict:
    """Execute the remediation plan via read-write MCP (Story 3.5)."""
    from .execution_engine import execute_remediation
    from .mcp_readwrite_client import ReadWriteMCPClient

    incident_id = state["incident_id"]
    logger.info("Execute node started", extra={"incident_id": incident_id})

    await _emit_stage_sse(incident_id, "execution", "running")

    plan = RemediationPlan.model_validate(state["remediation_plan"])
    mcp_client = ReadWriteMCPClient()

    execution_log = await execute_remediation(plan, mcp_client)

    await _emit_stage_sse(incident_id, "execution", "completed")

    return {
        "execution_log": execution_log.model_dump(mode="json"),
        "stage": "executed",
    }


async def observe_node(state: RemediationState) -> dict:
    """Observe remediation outcome (Story 3.5)."""
    from .outcome_observer import observe_outcome

    incident_id = uuid.UUID(state["incident_id"])
    artifact = ImmutableDiagnosisArtifact.model_validate(state["immutable_artifact"])
    execution_log = ExecutionLog.model_validate(state["execution_log"])

    await _emit_stage_sse(state["incident_id"], "observation", "monitoring")

    outcome = await observe_outcome(incident_id, artifact, execution_log)

    await _emit_stage_sse(
        state["incident_id"], "observation",
        "resolved" if outcome.alert_resolved else "failed",
    )

    return {
        "outcome_result": outcome.model_dump(mode="json"),
        "stage": "observed",
    }


def should_execute(state: RemediationState) -> str:
    """Conditional edge: skip execution if freshness gate fails."""
    freshness = state.get("freshness_result", {})
    if freshness and freshness.get("is_fresh", False):
        return "execute"
    return "end_stale"


async def _emit_skeptic_sse(incident_id: str, state: str) -> None:
    """Emit an SSE event for the skeptic_validation stage."""
    await _emit_stage_sse(incident_id, "skeptic_validation", state)


async def _emit_stage_sse(incident_id: str, stage: str, state: str) -> None:
    """Emit an SSE event for a pipeline stage transition."""
    try:
        from ..api.event_bus import get_event_bus

        bus = get_event_bus()
        await bus.emit(
            EventNames.INCIDENT_STAGE_CHANGED,
            SSEEventData(
                incident_id=uuid.UUID(incident_id),
                stage=stage,
                state=state,
                payload={},
            ),
        )
    except Exception:
        logger.warning(
            "Failed to emit stage SSE event",
            extra={"incident_id": incident_id, "stage": stage, "state": state},
        )
