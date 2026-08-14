"""Unit tests for the manifest generation pipeline stage (Story 4.0).

Tests: apply/create steps get manifests, imperative steps skipped,
informational steps skipped, MCP failures set manifest_generation_failed,
temp directory structure, YAML validity.
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from src.models.remediation import (
    BlastRadius,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from src.pipeline.manifest_generator import (
    MANIFEST_ELIGIBLE_ACTIONS,
    generate_manifests,
)

pytestmark = pytest.mark.unit

SAMPLE_DEPLOYMENT_YAML = yaml.dump({
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "my-app",
        "namespace": "default",
        "resourceVersion": "12345",
        "uid": "abc-123",
        "creationTimestamp": "2026-01-01T00:00:00Z",
        "generation": 3,
        "managedFields": [{"manager": "kubectl"}],
    },
    "spec": {
        "replicas": 1,
        "selector": {"matchLabels": {"app": "my-app"}},
        "template": {
            "metadata": {"labels": {"app": "my-app"}},
            "spec": {
                "containers": [{
                    "name": "app",
                    "image": "my-app:latest",
                    "resources": {"limits": {"memory": "256Mi"}},
                }],
            },
        },
    },
    "status": {"readyReplicas": 1},
}, default_flow_style=False)


def _make_step(**overrides) -> RemediationStep:
    defaults = {
        "order": 1,
        "description": "Apply deployment fix",
        "command": "oc apply -f deployment-fix.yaml",
        "resource": "deployments/my-app",
        "action": "apply",
        "expected_outcome": "Deployment updated",
    }
    defaults.update(overrides)
    return RemediationStep(**defaults)


def _make_plan(steps=None, **overrides) -> RemediationPlan:
    defaults = dict(
        incident_id=uuid.uuid4(),
        diagnosis_id=uuid.uuid4(),
        steps=steps or [_make_step()],
        blast_radius=BlastRadius.WORKLOAD,
        rollback_plan=[],
        estimated_risk=RiskLevel.LOW,
        plan_summary="Fix deployment",
    )
    defaults.update(overrides)
    return RemediationPlan(**defaults)


class TestManifestEligibleActions:
    def test_eligible_actions_match_dry_run(self):
        assert MANIFEST_ELIGIBLE_ACTIONS == frozenset({"apply", "create"})


class TestApplyStep:
    async def test_apply_step_gets_manifest(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan(steps=[_make_step(action="apply")])
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_path is not None
        assert Path(result.steps[0].manifest_path).exists()
        assert result.steps[0].manifest_generation_failed is False

    async def test_apply_step_queries_resource(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan(steps=[
            _make_step(resource="deployments/my-app", action="apply"),
        ])
        await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        mcp.query.assert_called_once_with(
            "resources_get",
            {"resource": "deployments/my-app"},
        )

    async def test_written_yaml_is_valid(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan()
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        content = Path(result.steps[0].manifest_path).read_text()
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)
        assert parsed["apiVersion"] == "apps/v1"
        assert parsed["kind"] == "Deployment"

    async def test_manifest_strips_server_metadata(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan()
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        content = Path(result.steps[0].manifest_path).read_text()
        parsed = yaml.safe_load(content)
        metadata = parsed.get("metadata", {})
        assert "resourceVersion" not in metadata
        assert "uid" not in metadata
        assert "creationTimestamp" not in metadata
        assert "generation" not in metadata
        assert "managedFields" not in metadata
        assert "status" not in parsed

    async def test_manifest_preserves_name_and_namespace(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan()
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        content = Path(result.steps[0].manifest_path).read_text()
        parsed = yaml.safe_load(content)
        assert parsed["metadata"]["name"] == "my-app"
        assert parsed["metadata"]["namespace"] == "default"


class TestCreateStep:
    async def test_create_step_gets_manifest(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan(steps=[
            _make_step(action="create", order=1, resource="configmaps/new-cm"),
        ])
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_path is not None
        assert result.steps[0].manifest_generation_failed is False


class TestImperativeStepSkipped:
    async def test_restart_step_skipped(self, tmp_path: Path):
        mcp = AsyncMock()

        plan = _make_plan(steps=[
            _make_step(action="restart", order=1),
        ])
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_path is None
        assert result.steps[0].manifest_generation_failed is False
        mcp.query.assert_not_called()

    async def test_scale_step_skipped(self, tmp_path: Path):
        mcp = AsyncMock()

        plan = _make_plan(steps=[
            _make_step(action="scale", order=1),
        ])
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_path is None
        mcp.query.assert_not_called()

    async def test_patch_step_skipped(self, tmp_path: Path):
        mcp = AsyncMock()

        plan = _make_plan(steps=[
            _make_step(action="patch", order=1),
        ])
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_path is None
        mcp.query.assert_not_called()


class TestInformationalStepSkipped:
    async def test_step_without_command_skipped(self, tmp_path: Path):
        mcp = AsyncMock()

        plan = _make_plan(steps=[
            _make_step(command=None, action="verify", order=1),
        ])
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_path is None
        assert result.steps[0].manifest_generation_failed is False
        mcp.query.assert_not_called()


class TestMCPFailures:
    async def test_mcp_timeout_sets_failed(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(side_effect=TimeoutError("MCP timed out"))

        plan = _make_plan()
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_generation_failed is True
        assert result.steps[0].manifest_path is None

    async def test_mcp_error_sets_failed(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(
            side_effect=ConnectionError("resource not found"),
        )

        plan = _make_plan()
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_generation_failed is True

    async def test_yaml_parse_error_sets_failed(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value="{{invalid yaml{{")

        plan = _make_plan()
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_generation_failed is True

    async def test_empty_yaml_response_sets_failed(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value="")

        plan = _make_plan()
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_generation_failed is True

    async def test_pipeline_continues_after_failure(self, tmp_path: Path):
        call_count = 0

        async def mock_query(tool_name, arguments, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("step 1 failed")
            return SAMPLE_DEPLOYMENT_YAML

        mcp = AsyncMock()
        mcp.query = mock_query

        steps = [
            _make_step(order=1, resource="deployments/bad"),
            _make_step(order=2, resource="deployments/good"),
        ]
        plan = _make_plan(steps=steps)
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_generation_failed is True
        assert result.steps[0].manifest_path is None
        assert result.steps[1].manifest_generation_failed is False
        assert result.steps[1].manifest_path is not None


class TestMultipleSteps:
    async def test_only_eligible_steps_get_manifests(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        steps = [
            _make_step(order=1, action="apply"),
            _make_step(order=2, action="restart"),
            _make_step(order=3, action="create"),
            _make_step(order=4, command=None, action="verify"),
        ]
        plan = _make_plan(steps=steps)
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert result.steps[0].manifest_path is not None
        assert result.steps[1].manifest_path is None
        assert result.steps[2].manifest_path is not None
        assert result.steps[3].manifest_path is None
        assert mcp.query.call_count == 2


class TestTempDirectoryStructure:
    async def test_incident_scoped_directory(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan()
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        manifest_path = Path(result.steps[0].manifest_path)
        assert manifest_path.parent.name == str(plan.incident_id)

    async def test_manifest_filename_matches_step_order(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan(steps=[_make_step(order=3)])
        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        manifest_path = Path(result.steps[0].manifest_path)
        assert manifest_path.name == "step-3.yaml"


class TestPlanImmutability:
    async def test_original_plan_unchanged(self, tmp_path: Path):
        mcp = AsyncMock()
        mcp.query = AsyncMock(return_value=SAMPLE_DEPLOYMENT_YAML)

        plan = _make_plan()
        original_step = plan.steps[0]

        result = await generate_manifests(plan, mcp, base_temp_dir=str(tmp_path))

        assert original_step.manifest_path is None
        assert result.steps[0].manifest_path is not None
        assert result is not plan
