"""Unit tests for the remediation LangGraph graph (Story 3.1).

Tests graph compilation, plan node execution with mocked planner,
and state management.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

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
from src.pipeline.remediation_graph import (
    RemediationState,
    build_remediation_graph,
    plan_node,
)


def _make_artifact_dict(incident_id=None) -> dict:
    """Create a valid ImmutableDiagnosisArtifact dict for state."""
    iid = incident_id or uuid.uuid4()
    artifact = ImmutableDiagnosisArtifact(
        id=uuid.uuid4(),
        incident_id=iid,
        root_cause_component="workload",
        failure_mode="crash-loop-backoff",
        root_cause_code="workload/crash-loop-backoff",
        causal_chain=(
            "Pod entered CrashLoopBackOff",
            "Container OOM killed",
        ),
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
    return artifact.model_dump(mode="json")


def _make_plan(incident_id=None, diagnosis_id=None, **overrides) -> RemediationPlan:
    defaults = dict(
        incident_id=incident_id or uuid.uuid4(),
        diagnosis_id=diagnosis_id or uuid.uuid4(),
        steps=[
            RemediationStep(
                order=1,
                description="Fix step",
                resource="pod/test",
                action="restart",
                expected_outcome="Pod running",
            ),
        ],
        blast_radius=BlastRadius.WORKLOAD,
        rollback_plan=[
            RemediationStep(
                order=1,
                description="Rollback",
                resource="pod/test",
                action="rollback",
                expected_outcome="Reverted",
            ),
        ],
        estimated_risk=RiskLevel.LOW,
        preconditions=[
            Precondition(
                type="rbac",
                description="Pod delete",
                requirement="delete on pods",
            ),
        ],
        plan_summary="Fix the crash loop",
    )
    defaults.update(overrides)
    return RemediationPlan(**defaults)


def _make_initial_state(incident_id=None) -> RemediationState:
    iid = incident_id or str(uuid.uuid4())
    return {
        "incident_id": iid,
        "immutable_artifact": _make_artifact_dict(uuid.UUID(iid)),
        "remediation_plan": None,
        "stage": "entered",
    }


class TestGraphCompilation:
    """Remediation graph compiles and has correct structure."""

    @pytest.mark.unit
    def test_graph_compiles(self):
        builder = build_remediation_graph()
        graph = builder.compile()
        assert graph is not None

    @pytest.mark.unit
    def test_graph_has_plan_node(self):
        builder = build_remediation_graph()
        graph = builder.compile()
        assert "plan" in graph.nodes


class TestPlanNode:
    """Plan node invokes the planner and stores result in state."""

    @pytest.mark.unit
    async def test_plan_node_produces_plan(self):
        iid = uuid.uuid4()
        state = _make_initial_state(str(iid))
        plan = _make_plan(incident_id=iid)

        with (
            patch(
                "src.agents.planner.run_planner",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                "src.pipeline.remediation_graph.pipeline_audit_log",
                new_callable=AsyncMock,
            ),
        ):
            result = await plan_node(state)

        assert "remediation_plan" in result
        assert result["remediation_plan"] is not None
        validated = RemediationPlan.model_validate(result["remediation_plan"])
        assert len(validated.steps) >= 1

    @pytest.mark.unit
    async def test_plan_node_sets_stage_to_planned(self):
        state = _make_initial_state()
        plan = _make_plan()

        with (
            patch(
                "src.agents.planner.run_planner",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                "src.pipeline.remediation_graph.pipeline_audit_log",
                new_callable=AsyncMock,
            ),
        ):
            result = await plan_node(state)

        assert result["stage"] == "planned"

    @pytest.mark.unit
    async def test_plan_node_result_has_blast_radius(self):
        state = _make_initial_state()
        plan = _make_plan(blast_radius=BlastRadius.NODE)

        with (
            patch(
                "src.agents.planner.run_planner",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                "src.pipeline.remediation_graph.pipeline_audit_log",
                new_callable=AsyncMock,
            ),
        ):
            result = await plan_node(state)

        validated = RemediationPlan.model_validate(result["remediation_plan"])
        assert validated.blast_radius == BlastRadius.NODE


class TestFullGraphExecution:
    """Full graph execution with mocked planner produces a plan in final state."""

    @pytest.mark.unit
    async def test_full_graph_produces_plan(self):
        iid = uuid.uuid4()
        state = _make_initial_state(str(iid))
        plan = _make_plan(incident_id=iid)

        with (
            patch(
                "src.agents.planner.run_planner",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                "src.pipeline.remediation_graph.pipeline_audit_log",
                new_callable=AsyncMock,
            ),
        ):
            builder = build_remediation_graph()
            graph = builder.compile()
            final_state = await graph.ainvoke(state)

        assert final_state["remediation_plan"] is not None
        validated = RemediationPlan.model_validate(final_state["remediation_plan"])
        assert validated.incident_id == iid
        assert validated.blast_radius in BlastRadius

    @pytest.mark.unit
    async def test_full_graph_stage_is_planned(self):
        state = _make_initial_state()
        plan = _make_plan()

        with (
            patch(
                "src.agents.planner.run_planner",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                "src.pipeline.remediation_graph.pipeline_audit_log",
                new_callable=AsyncMock,
            ),
        ):
            builder = build_remediation_graph()
            graph = builder.compile()
            final_state = await graph.ainvoke(state)

        assert final_state["stage"] == "planned"
