"""LangGraph StateGraph definition for the diagnosis pipeline (AD-1).

Stages are graph nodes. The 'diagnose' node is a STUB in Story 2.1 —
Story 2.2 replaces it with the full Orchestrator agent. Conditional
edges for skeptic and remediation are stubs for later stories.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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


class DiagnosisState(TypedDict):
    """Typed state schema for the LangGraph diagnosis pipeline."""

    incident_id: str
    root_cause_event: dict
    alerts: list[dict]
    mcp_evidence: list[dict]
    evidence_gaps: list[dict]
    diagnosis: dict | None
    stage: str


async def _gather_mcp_evidence(
    incident_id: str,
) -> tuple[list[EvidenceArtifact], list[EvidenceGap]]:
    """Query cluster state via the read-only MCP client (AD-2, AD-15).

    Produces evidence artifacts on success and evidence gaps on timeout
    or connection failure. Timeouts never fail the pipeline.
    """
    from .mcp_client import ReadOnlyMCPClient

    client = ReadOnlyMCPClient()
    evidence: list[EvidenceArtifact] = []
    gaps: list[EvidenceGap] = []

    queries = [
        ("get_resources", {"kind": "Pod", "namespace": "default"}),
        ("get_events", {}),
    ]

    for tool_name, arguments in queries:
        result = await client.query(tool_name, arguments)
        if isinstance(result, EvidenceArtifact):
            evidence.append(result)
        else:
            gaps.append(result)
            logger.info(
                "MCP evidence gap recorded",
                extra={
                    "incident_id": incident_id,
                    "query": result.query,
                    "reason": result.reason,
                },
            )

    return evidence, gaps


async def diagnose_node(state: DiagnosisState) -> dict:
    """Diagnosis stage node — STUB for Story 2.1.

    Queries the cluster via MCP for evidence (AC #4, #7), then produces a
    placeholder DiagnosisObject. Story 2.2 replaces the diagnosis logic
    with the full Orchestrator agent.
    """
    incident_id = state["incident_id"]
    logger.info("Diagnosis node started (stub)", extra={"incident_id": incident_id})

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="diagnose",
        state_before=state.get("stage", "entered"),
        state_after="diagnosing",
    )

    mcp_evidence: list[EvidenceArtifact] = []
    evidence_gaps: list[EvidenceGap] = []
    try:
        mcp_evidence, evidence_gaps = await _gather_mcp_evidence(incident_id)
    except Exception:
        logger.warning(
            "MCP evidence gathering failed, continuing with partial evidence",
            extra={"incident_id": incident_id},
        )

    all_evidence = mcp_evidence or [
        EvidenceArtifact(
            source=EvidenceSource.MCP_CLUSTER,
            query="stub_query",
            result="stub — Story 2.2 implements real diagnosis",
            timestamp=datetime.now(timezone.utc),
        ),
    ]

    placeholder = DiagnosisObject(
        incident_id=uuid.UUID(incident_id),
        root_cause_component="unknown",
        failure_mode="unclassified",
        root_cause_code="unknown/unclassified",
        causal_chain=["placeholder — pending orchestrator implementation"],
        affected_resources=[],
        evidence=all_evidence,
        evidence_gaps=evidence_gaps,
        confidence=0.0,
        agent_summary="Stub diagnosis — pipeline infrastructure validated",
    )

    return {
        "diagnosis": placeholder.model_dump(mode="json"),
        "mcp_evidence": [e.model_dump(mode="json") for e in mcp_evidence],
        "evidence_gaps": [g.model_dump(mode="json") for g in evidence_gaps],
        "stage": "diagnosed",
    }


async def finalize_node(state: DiagnosisState) -> dict:
    """Finalize stage — transitions state, emits events.

    The runner handles actual DB updates and SSE emission after
    graph completion. This node logs the transition.
    """
    incident_id = state["incident_id"]
    logger.info("Finalize node reached", extra={"incident_id": incident_id})

    await pipeline_audit_log(
        incident_id=incident_id,
        stage_name="finalize",
        state_before=state.get("stage", "diagnosing"),
        state_after="finalized",
    )

    return {"stage": "finalized"}


def build_diagnosis_graph() -> StateGraph:
    """Build the LangGraph StateGraph for diagnosis (not yet compiled)."""
    builder = StateGraph(DiagnosisState)
    builder.add_node("diagnose", diagnose_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge("diagnose", "finalize")
    builder.add_edge("finalize", END)
    builder.set_entry_point("diagnose")
    return builder
