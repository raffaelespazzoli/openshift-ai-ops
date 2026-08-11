"""Unit tests for the remediation skeptic agent (Story 3.2).

Tests that the remediation skeptic produces a valid RemediationSkepticChallenge
with mocked LLM, and the fallback works correctly.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.remediation_skeptic import (
    build_remediation_skeptic_agent,
    run_remediation_skeptic,
    _build_fallback_challenge,
)
from src.models.diagnosis import (
    EvidenceArtifact,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)
from src.models.remediation import (
    BlastRadius,
    Precondition,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from src.models.remediation_skeptic import RemediationSkepticChallenge
from tests.agents.conftest import FakeChatModel


def _make_artifact(incident_id=None) -> ImmutableDiagnosisArtifact:
    iid = incident_id or uuid.uuid4()
    return ImmutableDiagnosisArtifact(
        id=uuid.uuid4(),
        incident_id=iid,
        root_cause_component="workload",
        failure_mode="crash-loop-backoff",
        root_cause_code="workload/crash-loop-backoff",
        causal_chain=("Pod CrashLoopBackOff", "OOM killed"),
        affected_resources=("pod/test-pod",),
        evidence=(
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources",
                result="{}",
                timestamp=datetime.now(timezone.utc),
            ),
        ),
        confidence=0.85,
        agent_summary="OOM crash loop",
        skeptic_verdict={
            "passed": True,
            "rounds_completed": 1,
            "original_hash": "a" * 64,
            "final_hash": "a" * 64,
            "challenge_history": [{"round": 1}],
            "verdict_reasoning": "ok",
        },
        sealed_at=datetime.now(timezone.utc),
    )


def _make_plan(incident_id=None) -> RemediationPlan:
    return RemediationPlan(
        incident_id=incident_id or uuid.uuid4(),
        diagnosis_id=uuid.uuid4(),
        steps=[
            RemediationStep(
                order=1,
                description="Increase memory limit",
                command="kubectl set resources",
                resource="deployment/test-app",
                action="patch",
                expected_outcome="Higher memory limit",
            ),
        ],
        blast_radius=BlastRadius.WORKLOAD,
        rollback_plan=[
            RemediationStep(
                order=1,
                description="Revert memory",
                resource="deployment/test-app",
                action="patch",
                expected_outcome="Original limit",
            ),
        ],
        estimated_risk=RiskLevel.LOW,
        preconditions=[
            Precondition(
                type="rbac",
                description="Patch deployments",
                requirement="patch on deployments",
            ),
        ],
        plan_summary="Increase memory limit to prevent OOM kills",
    )


class TestBuildRemediationSkepticAgent:
    """build_remediation_skeptic_agent compiles a valid agent."""

    @pytest.mark.unit
    def test_agent_compiles(self):
        fake_llm = FakeChatModel(responses=[AIMessage(content="reviewing...")])
        with patch("src.agents.remediation_skeptic.get_chat_model", return_value=fake_llm):
            agent = build_remediation_skeptic_agent()
        assert agent is not None

    @pytest.mark.unit
    def test_agent_uses_remediation_skeptic_role(self):
        fake_llm = FakeChatModel(responses=[AIMessage(content="reviewing...")])
        with patch(
            "src.agents.remediation_skeptic.get_chat_model", return_value=fake_llm
        ) as mock_get:
            build_remediation_skeptic_agent()
        from src.config.llm_settings import AgentRole

        mock_get.assert_called_once_with(AgentRole.REMEDIATION_SKEPTIC)


class TestRunRemediationSkeptic:
    """run_remediation_skeptic produces a valid challenge with mocked agent."""

    @pytest.mark.unit
    async def test_produces_valid_challenge(self):
        plan = _make_plan()
        artifact = _make_artifact(incident_id=plan.incident_id)

        expected_challenge = RemediationSkepticChallenge(
            step_correctness_issues=["Step 1 targets wrong resource"],
            blast_radius_assessment="Blast radius assessment is accurate",
            rollback_feasibility_issues=[],
            precondition_gaps=["Missing quota check"],
            risk_assessment_critique="Risk should be medium given partial reversibility",
            overall_verdict="Plan needs minor revisions for precondition completeness",
        )

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": expected_challenge
        }

        with patch(
            "src.agents.remediation_skeptic.build_remediation_skeptic_agent",
            return_value=mock_agent,
        ):
            challenge = await run_remediation_skeptic(plan, artifact)

        assert isinstance(challenge, RemediationSkepticChallenge)
        assert len(challenge.step_correctness_issues) == 1
        assert challenge.overall_verdict == expected_challenge.overall_verdict

    @pytest.mark.unit
    async def test_fallback_on_agent_failure(self):
        plan = _make_plan()
        artifact = _make_artifact(incident_id=plan.incident_id)

        mock_agent = AsyncMock()
        mock_agent.ainvoke.side_effect = RuntimeError("LLM unavailable")

        with patch(
            "src.agents.remediation_skeptic.build_remediation_skeptic_agent",
            return_value=mock_agent,
        ):
            challenge = await run_remediation_skeptic(plan, artifact)

        assert isinstance(challenge, RemediationSkepticChallenge)
        assert "fallback" in challenge.overall_verdict.lower()

    @pytest.mark.unit
    async def test_fallback_on_no_structured_response(self):
        plan = _make_plan()
        artifact = _make_artifact(incident_id=plan.incident_id)

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"structured_response": None}

        with patch(
            "src.agents.remediation_skeptic.build_remediation_skeptic_agent",
            return_value=mock_agent,
        ):
            challenge = await run_remediation_skeptic(plan, artifact)

        assert isinstance(challenge, RemediationSkepticChallenge)
        assert "fallback" in challenge.overall_verdict.lower()


class TestFallbackChallenge:
    """_build_fallback_challenge produces a valid challenge."""

    @pytest.mark.unit
    def test_fallback_has_blast_radius_info(self):
        plan = _make_plan()
        c = _build_fallback_challenge(plan)
        assert plan.blast_radius.value in c.blast_radius_assessment

    @pytest.mark.unit
    def test_fallback_has_risk_info(self):
        plan = _make_plan()
        c = _build_fallback_challenge(plan)
        assert plan.estimated_risk.value in c.risk_assessment_critique

    @pytest.mark.unit
    def test_fallback_has_step_issues(self):
        plan = _make_plan()
        c = _build_fallback_challenge(plan)
        assert len(c.step_correctness_issues) >= 1
