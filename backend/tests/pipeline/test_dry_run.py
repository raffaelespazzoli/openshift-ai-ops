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
                description="Apply fixed deployment manifest",
                command="oc apply -f deployment-fix.yaml",
                resource="deployment/test",
                action="apply",
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

        assert result.dry_run_passed is True
        assert result.dry_run_errors == []
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

        assert result.dry_run_passed is True
        assert result.dry_run_errors == []
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

        assert result.dry_run_passed is False
        assert len(result.dry_run_errors) >= 1
        assert result.step_results[0].success is False
        assert result.step_results[0].error_detail is not None


class TestDryRunErrorPayload:
    """MCP responses containing error indicators must be treated as failures."""

    @pytest.mark.unit
    async def test_error_payload_without_exception_fails_step(self):
        """Server-side denial returned as text, not an exception."""
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(
            return_value="Error from server: admission webhook denied the request"
        )

        plan = _make_plan()
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is False
        assert len(result.dry_run_errors) >= 1
        assert result.step_results[0].success is False
        assert result.step_results[0].error_detail is not None
        assert "admission webhook" in result.step_results[0].error_detail.lower()

    @pytest.mark.unit
    async def test_forbidden_text_response_fails_step(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(
            return_value="forbidden: User 'system:serviceaccount:ns:sa' cannot create"
        )

        plan = _make_plan()
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is False
        assert result.step_results[0].success is False

    @pytest.mark.unit
    async def test_clean_response_still_passes(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(
            return_value="deployment.apps/test configured (server dry run)"
        )

        plan = _make_plan()
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is True
        assert result.step_results[0].success is True


class TestDryRunRBACDenied:
    @pytest.mark.unit
    async def test_rbac_denied_via_dry_run_403(self):
        """RBAC failures surface as dry-run=server 403 errors."""
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(
            side_effect=RuntimeError("403 Forbidden: insufficient permissions")
        )

        plan = _make_plan()
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is False
        assert len(result.dry_run_errors) >= 1


class TestDryRunQuotaViaServerDryRun:
    @pytest.mark.unit
    async def test_quota_always_true_relies_on_server_dry_run(self):
        """Quota is validated implicitly by server-side dry-run, not a separate check."""
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="resource applied (dry-run)")

        plan = _make_plan()
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is True
        assert result.dry_run_errors == []


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

        assert result.dry_run_passed is True
        assert result.dry_run_errors == []
        assert len(result.step_results) == 2
        assert result.step_results[0].command == "(no command)"
        assert result.step_results[0].success is True
        assert result.step_results[0].skipped is True
        assert result.step_results[1].success is True
        assert result.step_results[1].skipped is False


class TestDryRunManifestPath:
    """Story 4.0: steps with manifest_path send manifest body to MCP."""

    @pytest.mark.unit
    async def test_manifest_content_sent_to_apply_resource(self, tmp_path):
        manifest_file = tmp_path / "step-1.yaml"
        manifest_file.write_text("apiVersion: v1\nkind: ConfigMap\n")

        mock_client = AsyncMock()
        mock_client.query = AsyncMock(
            return_value="configmap/test configured (server dry run)",
        )

        steps = [
            RemediationStep(
                order=1,
                description="Apply manifest",
                command="oc apply -f fix.yaml",
                resource="configmap/test",
                action="apply",
                expected_outcome="Applied",
                manifest_path=str(manifest_file),
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is True
        assert result.step_results[0].success is True
        mock_client.query.assert_called_once_with(
            "apply_resource",
            {"manifest": "apiVersion: v1\nkind: ConfigMap\n", "dry_run": "server"},
        )

    @pytest.mark.unit
    async def test_manifest_generation_failed_returns_failure(self):
        mock_client = AsyncMock()

        steps = [
            RemediationStep(
                order=1,
                description="Failed manifest step",
                command="oc apply -f fix.yaml",
                resource="deployment/test",
                action="apply",
                expected_outcome="Fixed",
                manifest_generation_failed=True,
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is False
        assert result.step_results[0].success is False
        assert "Manifest generation failed" in result.step_results[0].message
        mock_client.query.assert_not_called()

    @pytest.mark.unit
    async def test_missing_manifest_file_returns_failure(self):
        mock_client = AsyncMock()

        steps = [
            RemediationStep(
                order=1,
                description="Missing manifest",
                command="oc apply -f fix.yaml",
                resource="deployment/test",
                action="apply",
                expected_outcome="Fixed",
                manifest_path="/tmp/nonexistent/step-1.yaml",
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is False
        assert result.step_results[0].success is False
        assert "Manifest file not found" in result.step_results[0].message

    @pytest.mark.unit
    async def test_step_without_manifest_uses_command(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="resource applied (dry-run)")

        steps = [
            RemediationStep(
                order=1,
                description="No manifest",
                command="oc apply -f fix.yaml",
                resource="deployment/test",
                action="apply",
                expected_outcome="Fixed",
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is True
        mock_client.query.assert_called_once_with(
            "apply_resource",
            {"command": "oc apply -f fix.yaml", "resource": "deployment/test", "dry_run": "server"},
        )


class TestDryRunImperativeSteps:
    """Imperative actions (restart, scale, patch, etc.) are not dry-runnable."""

    @pytest.mark.unit
    async def test_imperative_restart_skipped(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="ok")

        steps = [
            RemediationStep(
                order=1,
                description="Restart deployment",
                command="oc rollout restart deployment/test",
                resource="deployment/test",
                action="restart",
                expected_outcome="Deployment restarted",
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is True
        assert result.step_results[0].skipped is True
        assert result.step_results[0].success is True
        assert "not dry-runnable" in result.step_results[0].message
        mock_client.query.assert_not_called()

    @pytest.mark.unit
    async def test_imperative_scale_skipped(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="ok")

        steps = [
            RemediationStep(
                order=1,
                description="Scale deployment",
                command="oc scale deployment/test --replicas=3",
                resource="deployment/test",
                action="scale",
                expected_outcome="Scaled to 3",
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is True
        assert result.step_results[0].skipped is True
        assert "not dry-runnable" in result.step_results[0].message
        mock_client.query.assert_not_called()

    @pytest.mark.unit
    async def test_imperative_patch_skipped(self):
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="ok")

        steps = [
            RemediationStep(
                order=1,
                description="Patch resources",
                command="oc set resources deployment/test --limits=memory=512Mi",
                resource="deployment/test",
                action="patch",
                expected_outcome="Memory limit increased",
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is True
        assert result.step_results[0].skipped is True
        mock_client.query.assert_not_called()

    @pytest.mark.unit
    async def test_mixed_apply_and_imperative(self):
        """Apply steps are dry-run validated; imperative steps are skipped."""
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value="resource applied (dry-run)")

        steps = [
            RemediationStep(
                order=1,
                description="Apply manifest",
                command="oc apply -f fix.yaml",
                resource="pod/test",
                action="apply",
                expected_outcome="Applied",
            ),
            RemediationStep(
                order=2,
                description="Restart deployment",
                command="oc rollout restart deployment/test",
                resource="deployment/test",
                action="restart",
                expected_outcome="Restarted",
            ),
            RemediationStep(
                order=3,
                description="Create resource",
                command="oc create -f new.yaml",
                resource="configmap/test",
                action="create",
                expected_outcome="Created",
            ),
        ]
        plan = _make_plan(steps=steps)
        artifact = _make_artifact(plan.incident_id)

        result = await run_dry_run_preflight(plan, artifact, mcp_client=mock_client)

        assert result.dry_run_passed is True
        assert result.step_results[0].skipped is False
        assert result.step_results[0].success is True
        assert result.step_results[1].skipped is True
        assert result.step_results[1].success is True
        assert result.step_results[2].skipped is False
        assert result.step_results[2].success is True
        assert mock_client.query.call_count == 2
