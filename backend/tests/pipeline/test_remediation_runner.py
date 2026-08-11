"""Integration tests for the remediation pipeline runner (Story 3.1/3.3).

Tests that the runner loads the artifact from DB, invokes the graph,
persists the plan, and transitions state based on policy decision.
"""

import contextlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.policy_gate import (
    DryRunResult,
    DryRunStepResult,
    PolicyDecision,
    PolicyDimension,
)
from src.models.remediation import (
    BlastRadius,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from src.pipeline.remediation_runner import run_remediation_pipeline


def _make_plan(incident_id=None, diagnosis_id=None) -> RemediationPlan:
    return RemediationPlan(
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
        estimated_risk=RiskLevel.LOW,
        preconditions=[],
        plan_summary="Fix it",
    )


def _make_mock_pool(mock_conn=None, current_state="planning"):
    """Create a properly structured mock pool with async context manager."""
    conn = mock_conn or AsyncMock()

    @contextlib.asynccontextmanager
    async def _transaction():
        yield

    conn.transaction = _transaction

    original_fetchval = conn.fetchval

    async def _fetchval(query, *args, **kwargs):
        if "SELECT severity" in query:
            return "warning"
        if "SELECT state" in query:
            return current_state
        if hasattr(original_fetchval, 'return_value'):
            return await original_fetchval(query, *args, **kwargs)
        return None

    conn.fetchval = _fetchval

    @contextlib.asynccontextmanager
    async def _acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = _acquire
    return pool


class TestRunRemediationPipeline:
    """Runner loads artifact, invokes graph, and persists plan."""

    @pytest.mark.unit
    async def test_runner_returns_plan_on_success(self):
        incident_id = uuid.uuid4()
        diagnosis_id = uuid.uuid4()
        plan = _make_plan(incident_id=incident_id, diagnosis_id=diagnosis_id)

        mock_artifact = MagicMock()
        mock_artifact.model_dump.return_value = {"id": str(diagnosis_id)}

        mock_pool = _make_mock_pool()

        async def mock_get_pool():
            return mock_pool

        with (
            patch("src.pipeline.remediation_runner.get_pool", side_effect=mock_get_pool),
            patch(
                "src.pipeline.remediation_runner.load_immutable_artifact",
                new_callable=AsyncMock,
                return_value=mock_artifact,
            ),
            patch(
                "src.pipeline.remediation_runner.get_checkpointer",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.pipeline.remediation_runner.build_remediation_graph"
            ) as mock_build,
            patch(
                "src.pipeline.remediation_runner.persist_remediation_plan",
                new_callable=AsyncMock,
            ) as mock_persist,
            patch(
                "src.pipeline.remediation_runner._emit_remediation_event",
                new_callable=AsyncMock,
            ),
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "remediation_plan": plan.model_dump(mode="json"),
                "stage": "planned",
            }
            mock_builder = MagicMock()
            mock_builder.compile.return_value = mock_graph
            mock_build.return_value = mock_builder

            result = await run_remediation_pipeline(incident_id)

        assert result is not None
        assert result.incident_id == incident_id
        mock_persist.assert_called_once()

    @pytest.mark.unit
    async def test_runner_returns_none_on_no_plan(self):
        incident_id = uuid.uuid4()

        mock_artifact = MagicMock()
        mock_artifact.model_dump.return_value = {}

        mock_pool = _make_mock_pool()

        async def mock_get_pool():
            return mock_pool

        with (
            patch("src.pipeline.remediation_runner.get_pool", side_effect=mock_get_pool),
            patch(
                "src.pipeline.remediation_runner.load_immutable_artifact",
                new_callable=AsyncMock,
                return_value=mock_artifact,
            ),
            patch(
                "src.pipeline.remediation_runner.get_checkpointer",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.pipeline.remediation_runner.build_remediation_graph"
            ) as mock_build,
            patch(
                "src.pipeline.remediation_runner._emit_remediation_event",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner._transition_to_failed",
                new_callable=AsyncMock,
            ) as mock_fail,
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "remediation_plan": None,
                "stage": "failed",
            }
            mock_builder = MagicMock()
            mock_builder.compile.return_value = mock_graph
            mock_build.return_value = mock_builder

            result = await run_remediation_pipeline(incident_id)

        assert result is None
        mock_fail.assert_called_once_with(incident_id)

    @pytest.mark.unit
    async def test_runner_returns_none_on_exception(self):
        incident_id = uuid.uuid4()

        async def mock_get_pool():
            raise ValueError("DB error")

        with (
            patch("src.pipeline.remediation_runner.get_pool", side_effect=mock_get_pool),
            patch(
                "src.pipeline.remediation_runner._emit_remediation_event",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner._transition_to_failed",
                new_callable=AsyncMock,
            ) as mock_fail,
        ):
            result = await run_remediation_pipeline(incident_id)

        assert result is None
        mock_fail.assert_called_once_with(incident_id)

    @pytest.mark.unit
    async def test_runner_emits_planning_and_planned_events(self):
        incident_id = uuid.uuid4()
        plan = _make_plan(incident_id=incident_id)

        mock_artifact = MagicMock()
        mock_artifact.model_dump.return_value = {}

        mock_pool = _make_mock_pool()

        async def mock_get_pool():
            return mock_pool

        with (
            patch("src.pipeline.remediation_runner.get_pool", side_effect=mock_get_pool),
            patch(
                "src.pipeline.remediation_runner.load_immutable_artifact",
                new_callable=AsyncMock,
                return_value=mock_artifact,
            ),
            patch(
                "src.pipeline.remediation_runner.get_checkpointer",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.pipeline.remediation_runner.build_remediation_graph"
            ) as mock_build,
            patch(
                "src.pipeline.remediation_runner.persist_remediation_plan",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner._emit_remediation_event",
                new_callable=AsyncMock,
            ) as mock_emit,
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "remediation_plan": plan.model_dump(mode="json"),
                "stage": "planned",
            }
            mock_builder = MagicMock()
            mock_builder.compile.return_value = mock_graph
            mock_build.return_value = mock_builder

            await run_remediation_pipeline(incident_id)

        emit_calls = [c[0] for c in mock_emit.call_args_list]
        states = [c[2] for c in emit_calls]
        assert "planning" in states
        assert "planned" in states


def _make_policy_decision(incident_id, plan_id, approved=False) -> dict:
    decision = PolicyDecision(
        incident_id=incident_id,
        plan_id=plan_id,
        dimensions=[
            PolicyDimension(name="severity", value="warning", threshold="(none)", passed=False),
            PolicyDimension(name="blast_radius", value="workload", threshold="(none)", passed=False),
            PolicyDimension(name="confidence", value=0.85, threshold=1.0, passed=False),
        ],
        evidence_complete=True,
        evidence_gaps_empty=True,
        auto_execution_approved=approved,
        reasoning="Test decision",
    )
    return decision.model_dump(mode="json")


def _make_dry_run_dict(incident_id, plan_id) -> dict:
    dr = DryRunResult(
        incident_id=incident_id,
        plan_id=plan_id,
        step_results=[
            DryRunStepResult(step_order=1, command="cmd", success=True, message="ok"),
        ],
        dry_run_passed=True,
        dry_run_errors=[],
    )
    return dr.model_dump(mode="json")


class TestRunnerPolicyDecision:
    """Runner transitions incident state based on policy gate decision."""

    @pytest.mark.unit
    async def test_runner_transitions_to_awaiting_approval_on_deny(self):
        incident_id = uuid.uuid4()
        plan = _make_plan(incident_id=incident_id)

        mock_artifact = MagicMock()
        mock_artifact.model_dump.return_value = {}

        mock_conn = AsyncMock()
        mock_pool = _make_mock_pool(mock_conn, current_state="planning")

        async def mock_get_pool():
            return mock_pool

        graph_output = {
            "remediation_plan": plan.model_dump(mode="json"),
            "dry_run_result": _make_dry_run_dict(incident_id, plan.id),
            "policy_decision": _make_policy_decision(incident_id, plan.id, approved=False),
            "stage": "policy_decided",
        }

        with (
            patch("src.pipeline.remediation_runner.get_pool", side_effect=mock_get_pool),
            patch(
                "src.pipeline.remediation_runner.load_immutable_artifact",
                new_callable=AsyncMock,
                return_value=mock_artifact,
            ),
            patch(
                "src.pipeline.remediation_runner.get_checkpointer",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.pipeline.remediation_runner.build_remediation_graph"
            ) as mock_build,
            patch(
                "src.pipeline.remediation_runner.persist_remediation_plan",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner.persist_dry_run_result",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner.persist_policy_decision",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner._emit_remediation_event",
                new_callable=AsyncMock,
            ),
            patch(
                "src.db.audit.write_audit_log",
                new_callable=AsyncMock,
            ),
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = graph_output
            mock_builder = MagicMock()
            mock_builder.compile.return_value = mock_graph
            mock_build.return_value = mock_builder

            result = await run_remediation_pipeline(incident_id)

        assert result is not None
        mock_conn.execute.assert_called()
        update_call = [
            c for c in mock_conn.execute.call_args_list
            if "UPDATE incidents" in str(c)
        ]
        assert len(update_call) >= 1
        assert "awaiting_approval" in str(update_call[0])

    @pytest.mark.unit
    async def test_runner_transitions_to_executing_on_approve(self):
        incident_id = uuid.uuid4()
        plan = _make_plan(incident_id=incident_id)

        mock_artifact = MagicMock()
        mock_artifact.model_dump.return_value = {}

        mock_conn = AsyncMock()
        mock_pool = _make_mock_pool(mock_conn, current_state="planning")

        async def mock_get_pool():
            return mock_pool

        graph_output = {
            "remediation_plan": plan.model_dump(mode="json"),
            "dry_run_result": _make_dry_run_dict(incident_id, plan.id),
            "policy_decision": _make_policy_decision(incident_id, plan.id, approved=True),
            "stage": "policy_decided",
        }

        with (
            patch("src.pipeline.remediation_runner.get_pool", side_effect=mock_get_pool),
            patch(
                "src.pipeline.remediation_runner.load_immutable_artifact",
                new_callable=AsyncMock,
                return_value=mock_artifact,
            ),
            patch(
                "src.pipeline.remediation_runner.get_checkpointer",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.pipeline.remediation_runner.build_remediation_graph"
            ) as mock_build,
            patch(
                "src.pipeline.remediation_runner.persist_remediation_plan",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner.persist_dry_run_result",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner.persist_policy_decision",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner._emit_remediation_event",
                new_callable=AsyncMock,
            ),
            patch(
                "src.db.audit.write_audit_log",
                new_callable=AsyncMock,
            ),
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = graph_output
            mock_builder = MagicMock()
            mock_builder.compile.return_value = mock_graph
            mock_build.return_value = mock_builder

            result = await run_remediation_pipeline(incident_id)

        assert result is not None
        mock_conn.execute.assert_called()
        update_call = [
            c for c in mock_conn.execute.call_args_list
            if "UPDATE incidents" in str(c)
        ]
        assert len(update_call) >= 1
        assert "executing" in str(update_call[0])

    @pytest.mark.unit
    async def test_runner_emits_policy_gate_event(self):
        incident_id = uuid.uuid4()
        plan = _make_plan(incident_id=incident_id)

        mock_artifact = MagicMock()
        mock_artifact.model_dump.return_value = {}

        mock_pool = _make_mock_pool()

        async def mock_get_pool():
            return mock_pool

        graph_output = {
            "remediation_plan": plan.model_dump(mode="json"),
            "dry_run_result": _make_dry_run_dict(incident_id, plan.id),
            "policy_decision": _make_policy_decision(incident_id, plan.id, approved=False),
            "stage": "policy_decided",
        }

        with (
            patch("src.pipeline.remediation_runner.get_pool", side_effect=mock_get_pool),
            patch(
                "src.pipeline.remediation_runner.load_immutable_artifact",
                new_callable=AsyncMock,
                return_value=mock_artifact,
            ),
            patch(
                "src.pipeline.remediation_runner.get_checkpointer",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.pipeline.remediation_runner.build_remediation_graph"
            ) as mock_build,
            patch(
                "src.pipeline.remediation_runner.persist_remediation_plan",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner.persist_dry_run_result",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner.persist_policy_decision",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.remediation_runner._emit_remediation_event",
                new_callable=AsyncMock,
            ) as mock_emit,
            patch(
                "src.db.audit.write_audit_log",
                new_callable=AsyncMock,
            ),
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = graph_output
            mock_builder = MagicMock()
            mock_builder.compile.return_value = mock_graph
            mock_build.return_value = mock_builder

            await run_remediation_pipeline(incident_id)

        emit_calls = [c[0] for c in mock_emit.call_args_list]
        stages = [c[1] for c in emit_calls]
        states = [c[2] for c in emit_calls]
        assert "policy_gate" in stages
        assert "denied" in states
