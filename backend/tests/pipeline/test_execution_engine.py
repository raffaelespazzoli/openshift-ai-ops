"""Unit tests for the execution engine (Story 3.5).

Tests: all steps succeed; step failure stops execution; MCP calls logged;
informational steps handled.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.models.remediation import RemediationPlan, RemediationStep, BlastRadius, RiskLevel
from src.pipeline.execution_engine import execute_remediation

pytestmark = pytest.mark.unit


def _make_plan(steps=None, **overrides) -> RemediationPlan:
    defaults = dict(
        incident_id=uuid.uuid4(),
        diagnosis_id=uuid.uuid4(),
        steps=steps or [
            RemediationStep(
                order=1,
                description="Apply fix",
                command="kubectl apply -f fix.yaml",
                resource="deployment/app",
                action="apply",
                expected_outcome="Deployment updated",
            ),
        ],
        blast_radius=BlastRadius.WORKLOAD,
        rollback_plan=[],
        estimated_risk=RiskLevel.LOW,
        plan_summary="Fix the issue",
    )
    defaults.update(overrides)
    return RemediationPlan(**defaults)


class TestExecutionAllStepsSucceed:
    """All steps succeed → status 'completed'."""

    async def test_single_step_success(self):
        plan = _make_plan()
        mcp_client = AsyncMock()
        mcp_client.execute = AsyncMock(return_value="resource applied")

        log = await execute_remediation(plan, mcp_client)

        assert log.status == "completed"
        assert len(log.steps) == 1
        assert log.steps[0].success is True
        assert log.steps[0].output == "resource applied"
        assert log.incident_id == plan.incident_id
        assert log.plan_id == plan.id

    async def test_multiple_steps_success(self):
        steps = [
            RemediationStep(
                order=1,
                description="Step 1",
                command="cmd1",
                resource="pod/a",
                action="apply",
                expected_outcome="Done",
            ),
            RemediationStep(
                order=2,
                description="Step 2",
                command="cmd2",
                resource="pod/b",
                action="apply",
                expected_outcome="Done",
            ),
        ]
        plan = _make_plan(steps=steps)
        mcp_client = AsyncMock()
        mcp_client.execute = AsyncMock(return_value="ok")

        log = await execute_remediation(plan, mcp_client)

        assert log.status == "completed"
        assert len(log.steps) == 2
        assert all(s.success for s in log.steps)

    async def test_mcp_calls_recorded(self):
        plan = _make_plan()
        mcp_client = AsyncMock()
        mcp_client.execute = AsyncMock(return_value="applied successfully")

        log = await execute_remediation(plan, mcp_client)

        assert len(log.mcp_calls) == 1
        assert log.mcp_calls[0]["tool"] == "apply_resource"
        assert log.mcp_calls[0]["step_order"] == 1


class TestExecutionStepFailure:
    """Step failure stops execution → status 'failed'."""

    async def test_step_failure_stops_execution(self):
        steps = [
            RemediationStep(
                order=1,
                description="Will fail",
                command="bad-cmd",
                resource="pod/a",
                action="apply",
                expected_outcome="Done",
            ),
            RemediationStep(
                order=2,
                description="Never reached",
                command="cmd2",
                resource="pod/b",
                action="apply",
                expected_outcome="Done",
            ),
        ]
        plan = _make_plan(steps=steps)
        mcp_client = AsyncMock()
        mcp_client.execute = AsyncMock(side_effect=RuntimeError("MCP error"))

        log = await execute_remediation(plan, mcp_client)

        assert log.status == "failed"
        assert len(log.steps) == 1
        assert log.steps[0].success is False
        assert log.steps[0].error == "MCP error"

    async def test_partial_failure_first_succeeds(self):
        steps = [
            RemediationStep(
                order=1,
                description="Succeeds",
                command="cmd1",
                resource="pod/a",
                action="apply",
                expected_outcome="Done",
            ),
            RemediationStep(
                order=2,
                description="Fails",
                command="cmd2",
                resource="pod/b",
                action="apply",
                expected_outcome="Done",
            ),
        ]
        plan = _make_plan(steps=steps)
        mcp_client = AsyncMock()
        mcp_client.execute = AsyncMock(
            side_effect=["success", RuntimeError("failed")]
        )

        log = await execute_remediation(plan, mcp_client)

        assert log.status == "failed"
        assert len(log.steps) == 2
        assert log.steps[0].success is True
        assert log.steps[1].success is False


class TestInformationalSteps:
    """Steps without commands are logged as informational."""

    async def test_informational_step_no_mcp_call(self):
        steps = [
            RemediationStep(
                order=1,
                description="Informational",
                command=None,
                resource="pod/info",
                action="verify",
                expected_outcome="N/A",
            ),
        ]
        plan = _make_plan(steps=steps)
        mcp_client = AsyncMock()

        log = await execute_remediation(plan, mcp_client)

        assert log.status == "completed"
        assert len(log.steps) == 1
        assert log.steps[0].success is True
        assert log.steps[0].command == "(informational)"
        mcp_client.execute.assert_not_called()

    async def test_mixed_informational_and_real_steps(self):
        steps = [
            RemediationStep(
                order=1,
                description="Info",
                command=None,
                resource="pod/info",
                action="verify",
                expected_outcome="N/A",
            ),
            RemediationStep(
                order=2,
                description="Real",
                command="kubectl apply",
                resource="pod/real",
                action="apply",
                expected_outcome="Applied",
            ),
        ]
        plan = _make_plan(steps=steps)
        mcp_client = AsyncMock()
        mcp_client.execute = AsyncMock(return_value="done")

        log = await execute_remediation(plan, mcp_client)

        assert log.status == "completed"
        assert len(log.steps) == 2
        assert log.mcp_calls[0]["step_order"] == 2


class TestExecutionTimestamps:
    """Execution logs have proper timestamps."""

    async def test_started_at_and_completed_at(self):
        plan = _make_plan()
        mcp_client = AsyncMock()
        mcp_client.execute = AsyncMock(return_value="ok")

        log = await execute_remediation(plan, mcp_client)

        assert log.started_at is not None
        assert log.completed_at is not None
        assert log.completed_at >= log.started_at
