"""Remediation Skeptic agent — adversarial plan reviewer (AD-1, Story 3.2).

The remediation skeptic is a LangGraph create_react_agent subgraph with
NO tools. It reasons over the remediation plan and diagnosis context only
and produces a structured RemediationSkepticChallenge. Same pattern as
the Diagnosis Skeptic (agents/skeptic.py).
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from ..config.llm_settings import AgentRole
from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.remediation import RemediationPlan
from ..models.remediation_skeptic import RemediationSkepticChallenge
from .llm_client import get_chat_model
from .prompts import (
    REMEDIATION_SKEPTIC_STRUCTURED_PROMPT,
    REMEDIATION_SKEPTIC_SYSTEM_PROMPT,
)

logger = get_logger(Component.AGENT)


def build_remediation_skeptic_agent():
    """Build the remediation skeptic as a LangGraph create_react_agent subgraph.

    The remediation skeptic has NO tools — it reasons over the plan and
    diagnosis context only. Same pattern as the Diagnosis Skeptic.
    """
    llm = get_chat_model(AgentRole.REMEDIATION_SKEPTIC)
    return create_react_agent(
        model=llm,
        tools=[],
        prompt=REMEDIATION_SKEPTIC_SYSTEM_PROMPT,
        response_format=(
            REMEDIATION_SKEPTIC_STRUCTURED_PROMPT,
            RemediationSkepticChallenge,
        ),
    )


async def run_remediation_skeptic(
    plan: RemediationPlan,
    artifact: ImmutableDiagnosisArtifact,
) -> RemediationSkepticChallenge:
    """Run the remediation skeptic to produce an adversarial challenge.

    The skeptic receives both the plan AND the diagnosis context so it can
    evaluate whether the plan correctly addresses the diagnosed root cause.

    Args:
        plan: The RemediationPlan to challenge.
        artifact: The sealed diagnosis artifact (read-only context).

    Returns:
        A structured RemediationSkepticChallenge.
    """
    incident_id = str(plan.incident_id)
    logger.info(
        "Remediation skeptic starting challenge",
        extra={"incident_id": incident_id},
    )

    agent = build_remediation_skeptic_agent()

    prompt_text = (
        f"Review this remediation plan and produce a structured challenge.\n\n"
        f"DIAGNOSIS CONTEXT:\n"
        f"{json.dumps(artifact.model_dump(mode='json'), indent=2, default=str)}\n\n"
        f"REMEDIATION PLAN:\n{plan.model_dump_json(indent=2)}"
    )

    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=prompt_text)]},
        )

        structured_response = result.get("structured_response")
        if structured_response and isinstance(
            structured_response, RemediationSkepticChallenge
        ):
            challenge = structured_response
        elif structured_response:
            challenge = RemediationSkepticChallenge.model_validate(
                structured_response
            )
        else:
            challenge = _build_fallback_challenge(plan)
    except Exception as exc:
        logger.warning(
            "Remediation skeptic agent invocation failed, using fallback",
            extra={"incident_id": incident_id, "error": str(exc)},
        )
        challenge = _build_fallback_challenge(plan)

    logger.info(
        "Remediation skeptic produced challenge",
        extra={
            "incident_id": incident_id,
            "step_issues_count": len(challenge.step_correctness_issues),
            "rollback_issues_count": len(challenge.rollback_feasibility_issues),
            "precondition_gaps_count": len(challenge.precondition_gaps),
        },
    )

    return challenge


def _build_fallback_challenge(plan: RemediationPlan) -> RemediationSkepticChallenge:
    """Build a minimal challenge when the LLM fails to produce structured output.

    Design decision (Story 3.2): this fallback is intentionally permissive.
    Per the spec ("after the second round, the plan passes regardless of hash
    change — no infinite loops"), a failed skeptic does NOT block remediation.
    The fallback produces a minimal challenge record for audit completeness but
    does not block the plan.  The ``degraded`` flag on the
    RemediationSkepticVerdict (set when rebuttal_failed) signals to consumers
    that the validation was degraded.
    """
    return RemediationSkepticChallenge(
        step_correctness_issues=[
            "Fallback challenge: the skeptic agent could not produce a structured "
            "challenge — manual review of plan steps recommended"
        ],
        blast_radius_assessment=(
            f"Fallback: blast radius is {plan.blast_radius.value} — "
            f"requires manual verification"
        ),
        rollback_feasibility_issues=[],
        precondition_gaps=[],
        risk_assessment_critique=(
            f"Fallback: risk level is {plan.estimated_risk.value} — "
            f"requires manual verification"
        ),
        overall_verdict=(
            "Skeptic agent fallback: plan requires manual verification "
            "before execution"
        ),
    )
