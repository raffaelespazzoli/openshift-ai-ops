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
    ImmutableDiagnosisArtifact,
)
from ..models.skeptic import SkepticVerdict
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
    # Fields added in Story 2.4:
    skeptic_challenge: dict | None
    skeptic_verdict: dict | None
    immutable_artifact: dict | None


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

    Returns "skeptic_validation" when the diagnosis is complete or retries
    are exhausted. Returns "orchestrate" to re-diagnose when unaddressed
    alerts remain and retries are available.
    """
    unaddressed = state.get("unaddressed_alerts", [])
    attempts = state.get("completeness_attempts", 0)

    if not unaddressed or attempts > MAX_COMPLETENESS_RETRIES:
        return "skeptic_validation"
    return "orchestrate"


async def skeptic_validation_node(state: DiagnosisState) -> dict:
    """Skeptic validation stage — runs adversarial challenge/response loop (Story 2.4).

    Invokes the skeptic agent and orchestrator rebuttal inside a single
    graph node. The skeptic loop runs as plain Python (not graph edges).
    After validation, seals the diagnosis into an ImmutableDiagnosisArtifact.
    """
    from .skeptic_validation import run_skeptic_validation, seal_diagnosis

    incident_id = state["incident_id"]
    diagnosis_dict = state.get("diagnosis")

    if diagnosis_dict is None:
        logger.warning(
            "Skeptic node reached with no diagnosis — skipping validation",
            extra={"incident_id": incident_id},
        )
        return {}

    logger.info("Skeptic validation node started", extra={"incident_id": incident_id})

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="skeptic_validation",
        state_before=state.get("stage", "diagnosing"),
        state_after="validating",
    )

    diagnosis = DiagnosisObject.model_validate(diagnosis_dict)
    final_diagnosis, verdict = await run_skeptic_validation(diagnosis, state)

    sealed = seal_diagnosis(final_diagnosis, verdict)

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="skeptic_validation",
        state_before="validating",
        state_after="validated",
        extra_detail={
            "rounds_completed": verdict.rounds_completed,
            "hash_changed": verdict.original_hash != verdict.final_hash,
        },
    )

    return {
        "diagnosis": final_diagnosis.model_dump(mode="json"),
        "skeptic_challenge": verdict.challenge_history[-1]["challenge"] if verdict.challenge_history else None,
        "skeptic_verdict": verdict.model_dump(mode="json"),
        "immutable_artifact": sealed.model_dump(mode="json"),
    }


async def persist_skeptic_artifacts(
    conn,
    incident_id: str,
    verdict: SkepticVerdict,
    sealed: ImmutableDiagnosisArtifact,
) -> None:
    """Persist skeptic review rounds and immutable diagnosis to the database.

    Must be called within the caller's transaction scope so that skeptic
    persistence, incident state transition, and queue completion are all
    atomic. Raises on failure to trigger transaction rollback.

    When called for grouped-incident fan-out, rewrites any nested
    incident_id references in challenge_history responses to match the
    current incident_id, preventing primary ID leakage into sibling rows.
    """
    from ..db.diagnosis import persist_immutable_diagnosis
    from ..db.skeptic import persist_skeptic_record

    for entry in verdict.challenge_history:
        response = entry["response"]
        if isinstance(response, dict):
            response = _rewrite_nested_incident_ids(response, incident_id)

        await persist_skeptic_record(
            conn,
            incident_id=incident_id,
            round_number=entry["round"],
            challenge=entry["challenge"],
            response=response,
            verdict=verdict.model_dump(mode="json")
            if entry == verdict.challenge_history[-1]
            else None,
        )

    diagnosis_data = sealed.model_dump(mode="json")
    diagnosis_data["incident_id"] = str(incident_id)

    await persist_immutable_diagnosis(
        conn,
        incident_id=incident_id,
        diagnosis=diagnosis_data,
        skeptic_verdict=_rewrite_nested_incident_ids(
            verdict.model_dump(mode="json"), incident_id
        ),
        sealed_at=sealed.sealed_at,
    )

    logger.info(
        "Skeptic artifacts persisted",
        extra={"incident_id": incident_id},
    )


def _rewrite_nested_incident_ids(data: dict, target_id: str) -> dict:
    """Recursively rewrite any 'incident_id' fields in nested dicts/lists.

    Prevents primary incident ID leakage into sibling skeptic_reviews rows
    during grouped-incident fan-out.
    """
    import copy

    result = copy.deepcopy(data)

    def _walk(obj):
        if isinstance(obj, dict):
            if "incident_id" in obj:
                obj["incident_id"] = str(target_id)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(result)
    return result


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

    Graph structure (Story 2.4):
      diagnose → completeness_gate → (routing) → skeptic_validation | diagnose
      skeptic_validation → finalize → END

    The completeness gate evaluates whether all alerts are addressed.
    If not, it routes back to diagnose (max 2 retries). After the
    completeness gate passes, the skeptic validation node runs the
    adversarial challenge/response loop and seals the diagnosis.
    """
    builder = StateGraph(DiagnosisState)
    builder.add_node("diagnose", diagnose_node)
    builder.add_node("completeness_gate", completeness_gate_node)
    builder.add_node("skeptic_validation", skeptic_validation_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge("diagnose", "completeness_gate")
    builder.add_conditional_edges(
        "completeness_gate",
        _completeness_routing,
        {"skeptic_validation": "skeptic_validation", "orchestrate": "diagnose"},
    )
    builder.add_edge("skeptic_validation", "finalize")
    builder.add_edge("finalize", END)
    builder.set_entry_point("diagnose")
    return builder
