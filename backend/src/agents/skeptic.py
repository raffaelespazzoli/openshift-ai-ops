"""Skeptic agent — adversarial diagnosis reviewer (AD-1).

The skeptic is a LangGraph create_react_agent subgraph with NO tools.
It reasons over the presented diagnosis only and produces a structured
SkepticChallenge. It does NOT query the cluster or search runbooks.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from ..config.llm_settings import AgentRole
from ..config.logging import Component, get_logger
from ..models.diagnosis import DiagnosisObject
from ..models.skeptic import SkepticChallenge
from .llm_client import get_chat_model
from .prompts import SKEPTIC_STRUCTURED_PROMPT, SKEPTIC_SYSTEM_PROMPT

logger = get_logger(Component.AGENT)


def build_skeptic_agent():
    """Build the skeptic as a LangGraph create_react_agent subgraph.

    The skeptic has NO tools — it reasons over the diagnosis only.
    Uses response_format to produce a structured SkepticChallenge.
    """
    llm = get_chat_model(AgentRole.SKEPTIC)
    return create_react_agent(
        model=llm,
        tools=[],
        prompt=SKEPTIC_SYSTEM_PROMPT,
        response_format=(SKEPTIC_STRUCTURED_PROMPT, SkepticChallenge),
    )


async def run_skeptic(
    diagnosis: DiagnosisObject,
    state: dict,
) -> SkepticChallenge:
    """Run the skeptic agent to produce an adversarial challenge.

    Args:
        diagnosis: The DiagnosisObject to challenge.
        state: The DiagnosisState dict (for context).

    Returns:
        A structured SkepticChallenge.
    """
    incident_id = state.get("incident_id", "unknown")
    logger.info(
        "Skeptic agent starting challenge",
        extra={"incident_id": incident_id},
    )

    agent = build_skeptic_agent()

    diagnosis_json = diagnosis.model_dump_json(indent=2)
    prompt_text = (
        f"Review this diagnosis and produce a structured challenge:\n\n"
        f"{diagnosis_json}"
    )

    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=prompt_text)]},
        )

        structured_response = result.get("structured_response")
        if structured_response and isinstance(structured_response, SkepticChallenge):
            challenge = structured_response
        elif structured_response:
            challenge = SkepticChallenge.model_validate(structured_response)
        else:
            challenge = _build_fallback_challenge(diagnosis)
    except Exception as exc:
        logger.warning(
            "Skeptic agent invocation failed, using fallback challenge",
            extra={"incident_id": incident_id, "error": str(exc)},
        )
        challenge = _build_fallback_challenge(diagnosis)

    challenge = _ensure_evidence_gaps_challenged(diagnosis, challenge)

    logger.info(
        "Skeptic agent produced challenge",
        extra={
            "incident_id": incident_id,
            "alternative_hypotheses_count": len(challenge.alternative_hypotheses),
            "evidence_gap_challenges_count": len(challenge.evidence_gap_challenges),
            "logical_weaknesses_count": len(challenge.logical_weaknesses),
        },
    )

    return challenge


def _ensure_evidence_gaps_challenged(
    diagnosis: DiagnosisObject,
    challenge: SkepticChallenge,
) -> SkepticChallenge:
    """Ensure every non-empty evidence_gaps entry is represented in the challenge (AC #8).

    If the LLM-produced challenge omits any evidence gap, this augments
    the challenge with the missing gap-specific entries. Matches on both
    query AND reason to distinguish gaps that share query text but have
    different reasons.
    """
    if not diagnosis.evidence_gaps:
        return challenge

    existing_challenges = challenge.evidence_gap_challenges
    missing: list[str] = []
    for gap in diagnosis.evidence_gaps:
        gap_covered = any(
            gap.query.lower() in c.lower() and gap.reason.lower() in c.lower()
            for c in existing_challenges
        )
        if not gap_covered:
            missing.append(
                f"Evidence gap not addressed: {gap.query} — {gap.reason}"
            )

    if not missing:
        return challenge

    return challenge.model_copy(update={
        "evidence_gap_challenges": list(existing_challenges) + missing,
    })


def _build_fallback_challenge(diagnosis: DiagnosisObject) -> SkepticChallenge:
    """Build a minimal challenge when the LLM fails to produce structured output."""
    evidence_gap_challenges = [
        f"Evidence gap not addressed: {gap.query} — {gap.reason}"
        for gap in diagnosis.evidence_gaps
    ]

    return SkepticChallenge(
        alternative_hypotheses=[
            f"The evidence could also indicate a different root cause than "
            f"{diagnosis.root_cause_code}"
        ],
        evidence_gap_challenges=evidence_gap_challenges,
        logical_weaknesses=[
            "Fallback challenge: the skeptic agent could not produce a structured "
            "challenge — manual review recommended"
        ],
        overall_assessment=(
            f"Skeptic agent fallback: diagnosis {diagnosis.root_cause_code} "
            f"with confidence {diagnosis.confidence} requires manual verification"
        ),
    )
