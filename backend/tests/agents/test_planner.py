"""Unit tests for the remediation planner agent (Story 3.1).

Tests that the planner produces a valid RemediationPlan with mocked LLM,
rollback plan is present, preconditions are populated, and the diagnosis
artifact fields appear in the planning prompt.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.planner import (
    build_planner_agent,
    build_planning_prompt,
    get_planner_tools,
    run_planner,
    set_rw_mcp_client,
)
from src.models.diagnosis import (
    EvidenceArtifact,
    EvidenceGap,
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
from tests.agents.conftest import FakeChatModel


def _make_artifact(incident_id=None, diagnosis_id=None) -> ImmutableDiagnosisArtifact:
    """Create a valid ImmutableDiagnosisArtifact for testing."""
    iid = incident_id or uuid.uuid4()
    did = diagnosis_id or uuid.uuid4()
    return ImmutableDiagnosisArtifact(
        id=did,
        incident_id=iid,
        root_cause_component="workload",
        failure_mode="crash-loop-backoff",
        root_cause_code="workload/crash-loop-backoff",
        causal_chain=(
            "Pod entered CrashLoopBackOff state",
            "Container OOM killed repeatedly",
            "Memory limit too low for workload",
        ),
        affected_resources=("pod/test-app-xyz-123",),
        evidence=(
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources({'kind': 'Pod', 'namespace': 'default'})",
                result='{"status": {"phase": "CrashLoopBackOff"}}',
                timestamp=datetime.now(timezone.utc),
            ),
        ),
        evidence_gaps=(),
        confidence=0.85,
        agent_summary="Pod crash-loop due to OOM kills — memory limit insufficient",
        skeptic_verdict={
            "passed": True,
            "rounds_completed": 1,
            "original_hash": "a" * 64,
            "final_hash": "a" * 64,
            "challenge_history": [{"round": 1}],
            "verdict_reasoning": "validated",
        },
        sealed_at=datetime.now(timezone.utc),
    )


def _make_plan(incident_id=None, diagnosis_id=None) -> RemediationPlan:
    """Create a valid RemediationPlan for mocked returns."""
    return RemediationPlan(
        incident_id=incident_id or uuid.uuid4(),
        diagnosis_id=diagnosis_id or uuid.uuid4(),
        steps=[
            RemediationStep(
                order=1,
                description="Increase memory limit for deployment test-app",
                command="kubectl set resources deployment/test-app -c app --limits=memory=512Mi",
                resource="deployment/test-app",
                action="patch",
                expected_outcome="Pod restarts with higher memory limit",
            ),
        ],
        blast_radius=BlastRadius.WORKLOAD,
        rollback_plan=[
            RemediationStep(
                order=1,
                description="Revert memory limit",
                command="kubectl set resources deployment/test-app -c app --limits=memory=256Mi",
                resource="deployment/test-app",
                action="patch",
                expected_outcome="Pod reverts to original memory limit",
            ),
        ],
        estimated_risk=RiskLevel.LOW,
        preconditions=[
            Precondition(
                type="rbac",
                description="Can patch deployments",
                requirement="patch verbs on deployments resource",
                satisfied=True,
            ),
        ],
        plan_summary="Increase memory limit to prevent OOM kills",
    )


class TestBuildPlanningPrompt:
    """build_planning_prompt extracts diagnosis fields for the LLM context."""

    @pytest.mark.unit
    def test_prompt_contains_root_cause_code(self):
        artifact = _make_artifact()
        prompt = build_planning_prompt(artifact)
        assert "workload/crash-loop-backoff" in prompt

    @pytest.mark.unit
    def test_prompt_contains_affected_resources(self):
        artifact = _make_artifact()
        prompt = build_planning_prompt(artifact)
        assert "pod/test-app-xyz-123" in prompt

    @pytest.mark.unit
    def test_prompt_contains_causal_chain(self):
        artifact = _make_artifact()
        prompt = build_planning_prompt(artifact)
        assert "Container OOM killed repeatedly" in prompt

    @pytest.mark.unit
    def test_prompt_contains_incident_id(self):
        iid = uuid.uuid4()
        artifact = _make_artifact(incident_id=iid)
        prompt = build_planning_prompt(artifact)
        assert str(iid) in prompt

    @pytest.mark.unit
    def test_prompt_contains_confidence(self):
        artifact = _make_artifact()
        prompt = build_planning_prompt(artifact)
        assert "0.85" in prompt

    @pytest.mark.unit
    def test_prompt_contains_agent_summary(self):
        artifact = _make_artifact()
        prompt = build_planning_prompt(artifact)
        assert "OOM kills" in prompt


class TestGetPlannerTools:
    """get_planner_tools returns the correct tool list."""

    @pytest.mark.unit
    def test_returns_three_tools(self):
        tools = get_planner_tools()
        assert len(tools) == 3

    @pytest.mark.unit
    def test_tool_names(self):
        tools = get_planner_tools()
        names = {t.name for t in tools}
        assert "query_cluster_state" in names
        assert "check_rbac_permissions" in names
        assert "check_resource_quota" in names


class TestBuildPlannerAgent:
    """build_planner_agent compiles a valid LangGraph agent."""

    @pytest.mark.unit
    def test_agent_compiles(self):
        fake_llm = FakeChatModel(responses=[AIMessage(content="planning...")])
        agent = build_planner_agent(llm=fake_llm, tools=[])
        assert agent is not None

    @pytest.mark.unit
    def test_agent_with_empty_tools(self):
        fake_llm = FakeChatModel(responses=[AIMessage(content="planning...")])
        agent = build_planner_agent(llm=fake_llm, tools=[])
        assert agent is not None


class TestRunPlanner:
    """run_planner produces a valid RemediationPlan with mocked agent."""

    @pytest.mark.unit
    async def test_planner_produces_valid_plan(self):
        artifact = _make_artifact()
        expected_plan = _make_plan(
            incident_id=artifact.incident_id,
            diagnosis_id=artifact.id,
        )

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"structured_response": expected_plan}

        with patch("src.agents.planner.build_planner_agent", return_value=mock_agent):
            plan = await run_planner(artifact)

        assert isinstance(plan, RemediationPlan)
        assert plan.incident_id == artifact.incident_id
        assert plan.diagnosis_id == artifact.id
        assert len(plan.steps) >= 1

    @pytest.mark.unit
    async def test_planner_plan_has_rollback(self):
        artifact = _make_artifact()
        expected_plan = _make_plan(
            incident_id=artifact.incident_id,
            diagnosis_id=artifact.id,
        )

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"structured_response": expected_plan}

        with patch("src.agents.planner.build_planner_agent", return_value=mock_agent):
            plan = await run_planner(artifact)

        assert len(plan.rollback_plan) > 0

    @pytest.mark.unit
    async def test_planner_plan_has_preconditions(self):
        artifact = _make_artifact()
        expected_plan = _make_plan(
            incident_id=artifact.incident_id,
            diagnosis_id=artifact.id,
        )

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"structured_response": expected_plan}

        with patch("src.agents.planner.build_planner_agent", return_value=mock_agent):
            plan = await run_planner(artifact)

        assert len(plan.preconditions) > 0
        assert any(p.type == "rbac" for p in plan.preconditions)

    @pytest.mark.unit
    async def test_planner_sets_incident_and_diagnosis_ids(self):
        iid = uuid.uuid4()
        did = uuid.uuid4()
        artifact = _make_artifact(incident_id=iid, diagnosis_id=did)

        raw_plan = _make_plan()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"structured_response": raw_plan}

        with patch("src.agents.planner.build_planner_agent", return_value=mock_agent):
            plan = await run_planner(artifact)

        assert plan.incident_id == iid
        assert plan.diagnosis_id == did

    @pytest.mark.unit
    async def test_planner_prompt_sent_to_agent(self):
        artifact = _make_artifact()
        expected_plan = _make_plan(
            incident_id=artifact.incident_id,
            diagnosis_id=artifact.id,
        )

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"structured_response": expected_plan}

        with patch("src.agents.planner.build_planner_agent", return_value=mock_agent):
            await run_planner(artifact)

        call_args = mock_agent.ainvoke.call_args
        messages = call_args[0][0]["messages"]
        assert len(messages) == 1
        assert "workload/crash-loop-backoff" in messages[0].content
