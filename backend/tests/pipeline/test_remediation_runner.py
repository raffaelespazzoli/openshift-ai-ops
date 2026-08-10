"""Integration tests for the remediation pipeline runner (Story 3.1).

Tests that the runner loads the artifact from DB, invokes the graph,
and persists the plan. Mocks the planner agent and event bus.
"""

import contextlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _make_mock_pool(mock_conn=None):
    """Create a properly structured mock pool with async context manager."""
    conn = mock_conn or AsyncMock()

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
                "src.pipeline.remediation_runner.build_remediation_graph"
            ) as mock_build,
            patch(
                "src.pipeline.remediation_runner._emit_remediation_event",
                new_callable=AsyncMock,
            ),
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
        ):
            result = await run_remediation_pipeline(incident_id)

        assert result is None

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
