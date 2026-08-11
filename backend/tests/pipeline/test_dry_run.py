"""Unit tests for the dry-run pre-flight executor (Story 3.3).

Tests with mocked MCP client: all pass, partial fail, RBAC denied,
and informational step skipping.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.models.diagnosis import (
    EvidenceArtifact,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)
from src.models.remediation import (
    BlastRadius,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from src.pipeline.dry_run import run_dry_run_preflight


def _make_artifact(incident_id=None) -> ImmutableDiagnosisArtifact:
    return ImmutableDiagnosisArtifact(
        id=uuid.uuid4(),
        incident_id=incident_id or uuid.uuid4(),
        root_cause_component="workload",
        failure_mode="crash-loop-backoff",
        root_cause_code="workload/crash-loop-backoff",
        causal_chain=("Pod CrashLoopBackOff",),
        affected_resources=("pod/test-pod",),
        evidence=(
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources",
                result="Pod CrashLoopBackOff",
                timestamp=datetime.now(timezone.utc),
            ),
        ),
        confidence=0.85,
        agent_summary="OOM crash loop",
        skeptic_verdict={"passed": True, "rounds_completed": 1,
                         "original_hash": "a" * 64, "final_hash": "a" * 64,
                         "challenge_history": [{"round": 1}],
                         "verdict_reasoning": "ok"},
        sealed_at=datetime.now(timezone.utc),
    )


def _make_plan(incident_id=None, steps=None) -> RemediationPlan:
    iid = incident_id or uuid.uuid4()
    return RemediationPlan(
        incident_id=iid,
        diagnosis_id=uuid.uuid4(),
        steps=steps or [
            RemediationStep(
                order=1,
                description="Increase memory limit",
                command="oc set resources deployment/test --limits=memory=512Mi",
                resource="deployment/test",
                action="patch",
                expected_outcome="Memory limit increased",
            ),
        ],
        blast_radius=BlastRadius.WORKLOAD,
        estimated_risk=RiskLevel.LOW,
        plan_summary="Fix crash loop",
    )


class TestDryRunAllPass:
    @pytest.mark.unit
    async def test_all_steps_pass_overall_true(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="resource applied (dry-run)")

        plan = _make_plan()
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.overall_passed is True
        assert result.rbac_check_passed is True
        assert result.quota_check_passed is True
        assert result.admission_check_passed is True
        assert len(result.step_results) == 1
        assert result.step_results[0].success is True

    @pytest.mark.unit
    async def test_multi_step_all_pass(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="ok")

        steps = [
            RemediationStep(
                order=i,
                description=f"Step {i}",
                command=f"oc apply -f step{i}.yaml",
                resource=f"pod/test-{i}",
                action="apply",
                expected_outcome=f"Step {i} done",
            )
            for i in range(1, 4)
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.overall_passed is True
        assert len(result.step_results) == 3
        assert all(s.success for s in result.step_results)


class TestDryRunPartialFail:
    @pytest.mark.unit
    async def test_one_step_fails_overall_false(self):
        call_count = 0

        async def mock_query(tool_name, arguments, **kwargs):
            nonlocal call_count
            call_count += 1
            if tool_name == "apply_resource" and call_count == 1:
                raise RuntimeError("admission webhook denied")
            return "ok"

        mock_client = AsyncMock()
        mock_client.query = mock_query

        steps = [
            RemediationStep(
                order=1,
                description="Step 1",
                command="oc apply -f bad.yaml",
                resource="pod/bad",
                action="apply",
                expected_outcome="Should fail",
            ),
            RemediationStep(
                order=2,
                description="Step 2",
                command="oc apply -f good.yaml",
                resource="pod/good",
                action="apply",
                expected_outcome="Should pass",
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.overall_passed is False
        assert result.step_results[0].success is False
        assert result.step_results[0].error_detail is not None


class TestDryRunRBACDenied:
    @pytest.mark.unit
    async def test_rbac_denied_overall_false(self):
        async def mock_query(tool_name, arguments, **kwargs):
            if tool_name == "get_resources" and arguments.get("kind") == "SelfSubjectAccessReview":
                return "allowed: false — denied: insufficient permissions"
            return "ok"

        mock_client = AsyncMock()
        mock_client.query = mock_query

        plan = _make_plan()
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.rbac_check_passed is False
        assert result.overall_passed is False


class TestDryRunQuotaViaServerDryRun:
    @pytest.mark.unit
    async def test_quota_always_true_relies_on_server_dry_run(self):
        """Quota is validated implicitly by server-side dry-run, not a separate check."""
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="resource applied (dry-run)")

        plan = _make_plan()
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.quota_check_passed is True


class TestDryRunInformationalSteps:
    @pytest.mark.unit
    async def test_skips_steps_without_commands(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="ok")

        steps = [
            RemediationStep(
                order=1,
                description="Informational note",
                command=None,
                resource="pod/test",
                action="verify",
                expected_outcome="Noted",
            ),
            RemediationStep(
                order=2,
                description="Real step",
                command="oc apply -f fix.yaml",
                resource="pod/test",
                action="apply",
                expected_outcome="Fixed",
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.overall_passed is True
        assert len(result.step_results) == 2
        assert result.step_results[0].command == "(no command)"
        assert result.step_results[0].success is True
        assert result.step_results[1].success is True
