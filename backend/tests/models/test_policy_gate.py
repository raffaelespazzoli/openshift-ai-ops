"""Unit tests for policy gate models (Story 3.3).

Tests DryRunResult, DryRunStepResult, PolicyDimension, PolicyDecision validation.
"""

import uuid
from datetime import datetime, timezone

import pytest

from src.models.policy_gate import (
    DryRunResult,
    DryRunStepResult,
    PolicyDecision,
    PolicyDimension,
    PolicyMatrix,
)


class TestDryRunStepResult:
    @pytest.mark.unit
    def test_create_success_step(self):
        step = DryRunStepResult(
            step_order=1,
            command="oc apply -f deployment.yaml",
            success=True,
            message="Dry-run passed",
        )
        assert step.step_order == 1
        assert step.success is True
        assert step.error_detail is None

    @pytest.mark.unit
    def test_create_failed_step(self):
        step = DryRunStepResult(
            step_order=2,
            command="oc apply -f bad.yaml",
            success=False,
            message="Validation failed",
            error_detail="RBAC denied",
        )
        assert step.success is False
        assert step.error_detail == "RBAC denied"


class TestDryRunResult:
    @pytest.mark.unit
    def test_create_passing_result(self):
        result = DryRunResult(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            step_results=[
                DryRunStepResult(
                    step_order=1, command="cmd", success=True, message="ok"
                ),
            ],
            rbac_check_passed=True,
            quota_check_passed=True,
            admission_check_passed=True,
            overall_passed=True,
        )
        assert result.overall_passed is True
        assert result.id is not None
        assert result.created_at is not None

    @pytest.mark.unit
    def test_overall_reflects_step_failure(self):
        result = DryRunResult(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            step_results=[
                DryRunStepResult(
                    step_order=1, command="cmd", success=False, message="fail"
                ),
            ],
            rbac_check_passed=True,
            quota_check_passed=True,
            admission_check_passed=False,
            overall_passed=False,
        )
        assert result.overall_passed is False

    @pytest.mark.unit
    def test_overall_reflects_rbac_failure(self):
        result = DryRunResult(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            step_results=[
                DryRunStepResult(
                    step_order=1, command="cmd", success=True, message="ok"
                ),
            ],
            rbac_check_passed=False,
            quota_check_passed=True,
            admission_check_passed=True,
            overall_passed=False,
        )
        assert result.rbac_check_passed is False
        assert result.overall_passed is False

    @pytest.mark.unit
    def test_serialization_roundtrip(self):
        result = DryRunResult(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            step_results=[
                DryRunStepResult(
                    step_order=1, command="cmd", success=True, message="ok"
                ),
            ],
            rbac_check_passed=True,
            quota_check_passed=True,
            admission_check_passed=True,
            overall_passed=True,
        )
        data = result.model_dump(mode="json")
        restored = DryRunResult.model_validate(data)
        assert restored.id == result.id
        assert restored.overall_passed is True
        assert len(restored.step_results) == 1


class TestPolicyDimension:
    @pytest.mark.unit
    def test_valid_severity_dimension(self):
        dim = PolicyDimension(
            name="severity",
            value="warning",
            threshold="info,warning",
            passed=True,
        )
        assert dim.name == "severity"
        assert dim.passed is True

    @pytest.mark.unit
    def test_valid_blast_radius_dimension(self):
        dim = PolicyDimension(
            name="blast_radius",
            value="namespace",
            threshold="workload",
            passed=False,
        )
        assert dim.name == "blast_radius"
        assert dim.passed is False

    @pytest.mark.unit
    def test_valid_confidence_dimension(self):
        dim = PolicyDimension(
            name="confidence",
            value=0.85,
            threshold=0.8,
            passed=True,
        )
        assert dim.name == "confidence"
        assert dim.passed is True

    @pytest.mark.unit
    def test_invalid_dimension_name_rejected(self):
        with pytest.raises(Exception):
            PolicyDimension(
                name="invalid_name",
                value="x",
                threshold="y",
                passed=False,
            )


class TestPolicyDecision:
    @pytest.mark.unit
    def test_create_approved_decision(self):
        decision = PolicyDecision(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            dimensions=[
                PolicyDimension(
                    name="severity", value="info", threshold="info", passed=True
                ),
                PolicyDimension(
                    name="blast_radius",
                    value="workload",
                    threshold="workload",
                    passed=True,
                ),
                PolicyDimension(
                    name="confidence", value=0.95, threshold=0.8, passed=True
                ),
            ],
            evidence_complete=True,
            evidence_gaps_empty=True,
            auto_execution_approved=True,
            reasoning="All checks pass",
        )
        assert decision.auto_execution_approved is True
        assert isinstance(decision.auto_execution_approved, bool)

    @pytest.mark.unit
    def test_create_denied_decision(self):
        decision = PolicyDecision(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            dimensions=[
                PolicyDimension(
                    name="severity",
                    value="critical",
                    threshold="(none)",
                    passed=False,
                ),
            ],
            evidence_complete=True,
            evidence_gaps_empty=True,
            auto_execution_approved=False,
            reasoning="Severity not auto-approved",
        )
        assert decision.auto_execution_approved is False

    @pytest.mark.unit
    def test_serialization_roundtrip(self):
        decision = PolicyDecision(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            dimensions=[
                PolicyDimension(
                    name="confidence", value=0.9, threshold=0.8, passed=True
                ),
            ],
            evidence_complete=True,
            evidence_gaps_empty=True,
            auto_execution_approved=True,
            reasoning="All pass",
        )
        data = decision.model_dump(mode="json")
        restored = PolicyDecision.model_validate(data)
        assert restored.id == decision.id
        assert restored.auto_execution_approved is True


class TestPolicyMatrix:
    @pytest.mark.unit
    def test_create_policy_matrix(self):
        matrix = PolicyMatrix(
            severity_thresholds={"auto_approve": ["info", "warning"]},
            blast_radius_thresholds={"auto_approve": ["workload"]},
            confidence_threshold=0.8,
        )
        assert matrix.confidence_threshold == 0.8
