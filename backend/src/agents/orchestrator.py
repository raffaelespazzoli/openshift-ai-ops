"""Orchestrator agent — AI-powered root-cause diagnosis (AD-1).

The orchestrator is a LangGraph create_react_agent subgraph invoked by the
diagnosis stage node. It runs INSIDE the diagnosis node, not as a separate
graph node. Uses tools from agents/tools.py to gather evidence and produce
a structured DiagnosisObject.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from ..config.llm_settings import AgentRole
from ..config.logging import Component, get_logger
from ..models.diagnosis import (
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
)
from .completeness_gate import evaluate_completeness
from .llm_client import get_chat_model
from .prompts import STRUCTURED_OUTPUT_PROMPT, build_diagnosis_prompt, get_system_prompt
from .tools import get_orchestrator_tools

logger = get_logger(Component.AGENT)

MAX_COMPLETENESS_RETRIES = 2


def build_orchestrator_agent(
    tools: list | None = None,
    alert_count: int = 1,
    checkpointer: Any | None = None,
):
    """Build the orchestrator as a LangGraph create_react_agent subgraph.

    Args:
        tools: Override tool list (for testing). Uses default tools if None.
        alert_count: Number of alerts in the RCE — embedded in the system
            prompt so the agent knows how many alerts it must address.
        checkpointer: Optional checkpointer to share with the parent graph.
            When provided, the subgraph resumes from nested checkpoints on
            pod restart instead of replaying the entire tool loop.

    Returns:
        A compiled LangGraph agent ready for invocation.
    """
    llm = get_chat_model(AgentRole.ORCHESTRATOR)
    agent_tools = tools if tools is not None else get_orchestrator_tools()

    return create_react_agent(
        model=llm,
        tools=agent_tools,
        prompt=get_system_prompt(alert_count=max(alert_count, 1)),
        response_format=(STRUCTURED_OUTPUT_PROMPT, DiagnosisObject),
        checkpointer=checkpointer,
    )


async def run_orchestrator(state: dict, config: dict | None = None) -> dict:
    """Run the orchestrator agent on the given diagnosis state.

    This is called by the diagnosis graph node. It invokes the
    create_react_agent subgraph once and returns updated state fields.
    Completeness retries are handled at the graph level via the
    completeness_gate_node and _completeness_routing conditional edge.

    Args:
        state: The DiagnosisState dict from the parent graph.
        config: Optional LangGraph config dict.

    Returns:
        Dict with updated state fields: diagnosis, runbook_context,
        coverage_gaps, rejected_hypotheses, completeness_attempts.
    """
    incident_id = state["incident_id"]
    alerts = state.get("alerts", [])
    root_cause_event = state.get("root_cause_event", {})
    completeness_attempts = state.get("completeness_attempts", 0)
    rejected_hypotheses: list[dict] = list(state.get("rejected_hypotheses", []))
    unaddressed = state.get("unaddressed_alerts", [])

    logger.info(
        "Orchestrator starting diagnosis",
        extra={
            "incident_id": incident_id,
            "alert_count": len(alerts),
            "attempt": completeness_attempts + 1,
        },
    )

    alert_types = [
        a.get("labels", a).get("alertname", "unknown") for a in alerts
    ]
    coverage_gaps = [
        f"no specialist covers: {at}" for at in alert_types
    ] if alert_types else ["no specialist covers: unknown (MVP generalist mode)"]

    prompt_text = build_diagnosis_prompt(
        alerts=alerts,
        root_cause_event=root_cause_event,
        coverage_gaps=coverage_gaps,
    )

    if completeness_attempts > 0 and unaddressed:
        prompt_text += (
            f"\n\nCOMPLETENESS CHECK FAILED (attempt {completeness_attempts}):\n"
            f"Unaddressed alerts: {unaddressed}\n"
            f"Please address ALL alerts in your diagnosis."
        )

    checkpointer = None
    try:
        from ..db.checkpointer import get_checkpointer
        checkpointer = await get_checkpointer()
    except Exception:
        logger.debug("Could not obtain parent checkpointer for orchestrator subgraph")

    orchestrator = build_orchestrator_agent(
        alert_count=len(alerts),
        checkpointer=checkpointer,
    )
    diagnosis: DiagnosisObject | None = None

    try:
        invoke_config = dict(config or {})
        if checkpointer is not None:
            configurable = invoke_config.setdefault("configurable", {})
            configurable.setdefault(
                "thread_id",
                f"{incident_id}:orchestrator:{completeness_attempts}",
            )

        result = await orchestrator.ainvoke(
            {"messages": [HumanMessage(content=prompt_text)]},
            config=invoke_config,
        )

        structured_response = result.get("structured_response")
        if structured_response and isinstance(structured_response, DiagnosisObject):
            diagnosis = structured_response
        elif structured_response:
            diagnosis = DiagnosisObject.model_validate(structured_response)
        else:
            diagnosis = _build_fallback_diagnosis(incident_id, coverage_gaps)

    except Exception as exc:
        logger.warning(
            "Orchestrator agent invocation failed, using fallback",
            extra={"incident_id": incident_id, "error": str(exc)},
        )
        diagnosis = _build_fallback_diagnosis(incident_id, coverage_gaps)

    if completeness_attempts > 0 and state.get("diagnosis"):
        prev_diag = DiagnosisObject.model_validate(state["diagnosis"])
        rejected_hypotheses.append({
            "attempt": completeness_attempts,
            "root_cause_code": prev_diag.root_cause_code,
            "confidence": prev_diag.confidence,
            "reason": f"Incomplete: unaddressed alerts {unaddressed}",
        })

    if diagnosis is not None:
        model_alternatives = list(diagnosis.alternative_hypotheses or [])
        combined_alternatives = model_alternatives + [
            h for h in rejected_hypotheses if h not in model_alternatives
        ]
        diagnosis = diagnosis.model_copy(update={
            "coverage_gaps": coverage_gaps,
            "alternative_hypotheses": combined_alternatives,
        })

    agent_result = result if "result" in dir() else {}
    runbook_context = _extract_runbook_context(agent_result)
    evidence_ledger = _extract_evidence_ledger(agent_result)

    return {
        "diagnosis": diagnosis.model_dump(mode="json") if diagnosis else None,
        "runbook_context": runbook_context,
        "completeness_attempts": completeness_attempts + 1,
        "coverage_gaps": coverage_gaps,
        "rejected_hypotheses": rejected_hypotheses,
        "evidence_ledger": evidence_ledger,
        "stage": "diagnosed",
    }


def _build_fallback_diagnosis(
    incident_id: str,
    coverage_gaps: list[str],
) -> DiagnosisObject:
    """Create a fallback diagnosis when the LLM invocation fails."""
    return DiagnosisObject(
        incident_id=uuid.UUID(incident_id),
        root_cause_component="unknown",
        failure_mode="unclassified",
        root_cause_code="unknown/unclassified",
        causal_chain=["Orchestrator failed to produce diagnosis — fallback applied"],
        affected_resources=[],
        evidence=[
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="orchestrator_fallback",
                result="Agent invocation failed — no evidence gathered",
                timestamp=datetime.now(timezone.utc),
            )
        ],
        evidence_gaps=[
            EvidenceGap(
                query="orchestrator_diagnosis",
                reason="Agent invocation failed or produced invalid output",
            )
        ],
        confidence=0.0,
        agent_summary=(
            f"Fallback diagnosis — orchestrator could not complete. "
            f"Coverage gaps: {', '.join(coverage_gaps)}"
        ),
    )


def _extract_runbook_context(result: dict) -> list[dict]:
    """Extract runbook context from agent messages (if any tool calls returned runbook data)."""
    runbook_context: list[dict] = []
    messages = result.get("messages", [])
    for msg in messages:
        if hasattr(msg, "content") and isinstance(msg.content, str):
            if "runbook" in msg.content.lower() and "source_file" in msg.content:
                runbook_context.append({"content": msg.content[:2000]})
    return runbook_context


def _extract_evidence_ledger(result: dict) -> list[dict]:
    """Extract all gathered evidence from tool call results in agent messages.

    Builds a ledger of every piece of evidence returned by tools so the
    completeness gate can verify none was left unexamined (AC #6).
    Stores result summaries alongside queries so the gate can verify
    that concrete findings (not just query strings) appear in the diagnosis.
    Runbook searches with no hits are recorded as no-hit markers.
    """
    import json as _json

    _MAX_SUMMARY_LEN = 300

    ledger: list[dict] = []
    messages = result.get("messages", [])
    for msg in messages:
        if not hasattr(msg, "content"):
            continue
        content = msg.content
        if isinstance(content, str):
            try:
                parsed = _json.loads(content)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict) and parsed.get("type") in ("evidence", "evidence_gap"):
                ledger.append(_ledger_entry(parsed, _MAX_SUMMARY_LEN))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    try:
                        parsed = _json.loads(block["text"])
                    except (ValueError, TypeError):
                        continue
                    if isinstance(parsed, dict) and parsed.get("type") in ("evidence", "evidence_gap"):
                        ledger.append(_ledger_entry(parsed, _MAX_SUMMARY_LEN))
    return ledger


def _ledger_entry(parsed: dict, max_summary: int) -> dict:
    """Build a single evidence ledger entry with a result summary."""
    result_raw = parsed.get("result", "")
    if isinstance(result_raw, dict):
        import json as _json
        result_text = _json.dumps(result_raw, default=str)
    else:
        result_text = str(result_raw)
    summary = result_text[:max_summary] if result_text else ""

    source = parsed.get("source", "")
    is_runbook_no_hit = (
        source == "runbook"
        and (not result_raw or "no relevant" in str(result_raw).lower()
             or "no matching" in str(result_raw).lower()
             or "no runbook" in str(result_raw).lower()
             or result_raw == "[]"
             or result_raw == [])
    )

    return {
        "source": source,
        "query": parsed.get("query", ""),
        "type": parsed["type"],
        "result_summary": summary,
        "no_hit": is_runbook_no_hit,
    }
