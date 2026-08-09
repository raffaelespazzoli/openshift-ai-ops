"""LangGraph StateGraph definition for the diagnosis pipeline (AD-1).

Stages are graph nodes. The 'diagnose' node invokes the Orchestrator agent
(Story 2.2). A completeness gate conditional edge retries diagnosis up to
2 times if not all alerts are addressed. Conditional edges for skeptic and
remediation are stubs for later stories.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from ..config.logging import Component, get_logger
from ..models.diagnosis import (
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
)
from .audit_hook import pipeline_audit_log

logger = get_logger(Component.PIPELINE)


MAX_COMPLETENESS_RETRIES = 2


class DiagnosisState(TypedDict):
    """Typed state schema for the LangGraph diagnosis pipeline."""

    incident_id: str
    root_cause_event: dict
    alerts: list[dict]
    mcp_evidence: list[dict]
    evidence_gaps: list[dict]
    diagnosis: dict | None
    stage: str
    # Fields added in Story 2.2:
    runbook_context: list[dict]
    completeness_attempts: int
    coverage_gaps: list[str]
    rejected_hypotheses: list[dict]
    unaddressed_alerts: list[str]
    evidence_ledger: list[dict]


async def diagnose_node(state: DiagnosisState) -> dict:
    """Diagnosis stage node — invokes the Orchestrator agent (Story 2.2).

    Delegates to the orchestrator agent which uses tools to gather evidence,
    searches runbooks, and produces a structured DiagnosisObject.
    """
    incident_id = state["incident_id"]
    logger.info("Diagnosis node started", extra={"incident_id": incident_id})

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="diagnose",
        state_before=state.get("stage", "entered"),
        state_after="diagnosing",
    )

    try:
        from ..agents.orchestrator import run_orchestrator

        result = await run_orchestrator(state)
        return result
    except Exception:
        logger.exception(
            "Orchestrator agent failed, producing fallback diagnosis",
            extra={"incident_id": incident_id},
        )
        from ..agents.orchestrator import _build_fallback_diagnosis

        fallback = _build_fallback_diagnosis(incident_id, [])
        return {
            "diagnosis": fallback.model_dump(mode="json"),
            "runbook_context": [],
            "completeness_attempts": state.get("completeness_attempts", 0) + 1,
            "coverage_gaps": [],
            "rejected_hypotheses": [],
            "stage": "diagnosed",
        }


async def completeness_gate_node(state: DiagnosisState) -> dict:
    """Evaluate diagnosis completeness and store result in state (AC #6).

    This node runs after the diagnose node. It checks whether the
    diagnosis addresses all alerts and stores the result so the
    routing function can decide finalize vs. retry.
    """
    from ..agents.completeness_gate import evaluate_completeness

    diagnosis_dict = state.get("diagnosis")
    alerts = state.get("alerts", [])
    attempts = state.get("completeness_attempts", 0)

    if diagnosis_dict is None:
        return {"unaddressed_alerts": []}

    try:
        diagnosis = DiagnosisObject.model_validate(diagnosis_dict)
    except Exception:
        logger.warning(
            "Could not validate diagnosis for completeness check",
            extra={"incident_id": state["incident_id"]},
        )
        return {"unaddressed_alerts": []}

    evidence_ledger = state.get("evidence_ledger", [])
    result = evaluate_completeness(diagnosis, alerts, evidence_ledger=evidence_ledger)

    if result.complete:
        logger.info(
            "Completeness gate passed",
            extra={"incident_id": state["incident_id"], "attempts": attempts},
        )
        return {"unaddressed_alerts": []}

    if attempts > MAX_COMPLETENESS_RETRIES:
        gap = EvidenceGap(
            query="completeness_check",
            reason=(
                f"Completeness gate failed after {MAX_COMPLETENESS_RETRIES} retries. "
                f"Unaddressed alerts: {result.unaddressed_alerts}"
            ),
        )
        gaps = list(diagnosis.evidence_gaps) + [gap]
        updated_diag = diagnosis.model_copy(update={"evidence_gaps": gaps})
        logger.warning(
            "Completeness gate exhausted retries — passing with evidence gap",
            extra={
                "incident_id": state["incident_id"],
                "unaddressed": result.unaddressed_alerts,
            },
        )
        return {
            "diagnosis": updated_diag.model_dump(mode="json"),
            "unaddressed_alerts": [],
        }

    logger.info(
        "Completeness gate failed — routing back to diagnose",
        extra={
            "incident_id": state["incident_id"],
            "attempt": attempts,
            "unaddressed": result.unaddressed_alerts,
        },
    )
    return {"unaddressed_alerts": result.unaddressed_alerts}


def _completeness_routing(state: DiagnosisState) -> str:
    """Conditional edge: route based on completeness gate result.

    Returns "finalize" when the diagnosis is complete or retries are
    exhausted. Returns "orchestrate" to re-diagnose when unaddressed
    alerts remain and retries are available.
    """
    unaddressed = state.get("unaddressed_alerts", [])
    attempts = state.get("completeness_attempts", 0)

    if not unaddressed or attempts > MAX_COMPLETENESS_RETRIES:
        return "finalize"
    return "orchestrate"


async def finalize_node(state: DiagnosisState) -> dict:
    """Finalize stage — transitions state, emits events.

    The runner handles actual DB updates and SSE emission after
    graph completion. This node logs the transition and emits
    SSE progress events.
    """
    incident_id = state["incident_id"]
    logger.info("Finalize node reached", extra={"incident_id": incident_id})

    audit_detail: dict = {
        "state_before": state.get("stage", "diagnosing"),
        "state_after": "finalized",
    }
    rejected = state.get("rejected_hypotheses", [])
    if rejected:
        audit_detail["alternative_hypotheses"] = rejected
    coverage = state.get("coverage_gaps", [])
    if coverage:
        audit_detail["coverage_gaps"] = coverage

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="finalize",
        state_before=state.get("stage", "diagnosing"),
        state_after="finalized",
        extra_detail=audit_detail,
    )

    # NOTE: The `diagnosed` SSE event is intentionally NOT emitted here.
    # Terminal state events must only be emitted by the runner AFTER the
    # pipeline completion transaction commits successfully. Emitting here
    # would leak a premature success event if the transaction later fails.

    return {"stage": "finalized"}


def build_diagnosis_graph() -> StateGraph:
    """Build the LangGraph StateGraph for diagnosis (not yet compiled).

    Graph structure:
      diagnose → completeness_gate → (routing) → finalize | diagnose
      finalize → END

    The completeness gate evaluates whether all alerts are addressed.
    If not, it routes back to diagnose (max 2 retries). This makes
    retries checkpointable at the graph level (Tasks 6.3, 7.2).
    """
    builder = StateGraph(DiagnosisState)
    builder.add_node("diagnose", diagnose_node)
    builder.add_node("completeness_gate", completeness_gate_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge("diagnose", "completeness_gate")
    builder.add_conditional_edges(
        "completeness_gate",
        _completeness_routing,
        {"finalize": "finalize", "orchestrate": "diagnose"},
    )
    builder.add_edge("finalize", END)
    builder.set_entry_point("diagnose")
    return builder
