"""Unit tests for RemediationPlan, BlastRadius, RiskLevel, RemediationStep, Precondition."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.remediation import (
    BlastRadius,
    Precondition,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)


def _make_step(**overrides) -> RemediationStep:
    defaults = {
        "order": 1,
        "description": "Restart the pod",
        "command": "kubectl delete pod test-pod -n default",
        "resource": "pod/test-pod",
        "action": "restart",
        "expected_outcome": "Pod restarts with fresh state",
    }
    defaults.update(overrides)
    return RemediationStep(**defaults)


def _make_precondition(**overrides) -> Precondition:
    defaults = {
        "type": "rbac",
        "description": "Can delete pods",
        "requirement": "delete verbs on pods resource",
        "satisfied": None,
    }
    defaults.update(overrides)
    return Precondition(**defaults)


def _make_plan(**overrides) -> RemediationPlan:
    incident_id = overrides.pop("incident_id", uuid.uuid4())
    diagnosis_id = overrides.pop("diagnosis_id", uuid.uuid4())
    defaults = {
        "incident_id": incident_id,
        "diagnosis_id": diagnosis_id,
        "steps": [_make_step()],
        "blast_radius": BlastRadius.WORKLOAD,
        "rollback_plan": [_make_step(order=1, description="Rollback step", action="rollback")],
        "estimated_risk": RiskLevel.LOW,
        "preconditions": [_make_precondition()],
        "plan_summary": "Restart the crashing pod to clear transient state",
    }
    defaults.update(overrides)
    return RemediationPlan(**defaults)


class TestBlastRadiusEnum:
    """BlastRadius enum contains the four correct values."""

    @pytest.mark.unit
    def test_blast_radius_values(self):
        assert BlastRadius.WORKLOAD == "workload"
        assert BlastRadius.NAMESPACE == "namespace"
        assert BlastRadius.NODE == "node"
        assert BlastRadius.CLUSTER == "cluster"

    @pytest.mark.unit
    def test_blast_radius_has_four_members(self):
        assert len(BlastRadius) == 4


class TestRiskLevelEnum:
    """RiskLevel enum contains the four correct values."""

    @pytest.mark.unit
    def test_risk_level_values(self):
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.CRITICAL == "critical"

    @pytest.mark.unit
    def test_risk_level_has_four_members(self):
        assert len(RiskLevel) == 4


class TestRemediationStep:
    """RemediationStep validates order >= 1 and required fields."""

    @pytest.mark.unit
    def test_valid_step(self):
        step = _make_step()
        assert step.order == 1
        assert step.description == "Restart the pod"
        assert step.resource == "pod/test-pod"

    @pytest.mark.unit
    def test_step_order_must_be_ge_1(self):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            _make_step(order=0)

    @pytest.mark.unit
    def test_step_order_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_step(order=-1)

    @pytest.mark.unit
    def test_step_command_optional(self):
        step = _make_step(command=None)
        assert step.command is None

    @pytest.mark.unit
    def test_step_command_with_value(self):
        step = _make_step(command="kubectl scale deploy/test --replicas=2")
        assert step.command == "kubectl scale deploy/test --replicas=2"


class TestPrecondition:
    """Precondition accepts rbac, quota, resource types with optional satisfied flag."""

    @pytest.mark.unit
    def test_valid_rbac_precondition(self):
        p = _make_precondition(type="rbac")
        assert p.type == "rbac"

    @pytest.mark.unit
    def test_valid_quota_precondition(self):
        p = _make_precondition(type="quota")
        assert p.type == "quota"

    @pytest.mark.unit
    def test_valid_resource_precondition(self):
        p = _make_precondition(type="resource")
        assert p.type == "resource"

    @pytest.mark.unit
    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            _make_precondition(type="network")

    @pytest.mark.unit
    def test_empty_string_type_rejected(self):
        with pytest.raises(ValidationError):
            _make_precondition(type="")

    @pytest.mark.unit
    def test_numeric_type_rejected(self):
        with pytest.raises(ValidationError):
            _make_precondition(type=123)

    @pytest.mark.unit
    def test_satisfied_defaults_to_none(self):
        p = _make_precondition()
        assert p.satisfied is None

    @pytest.mark.unit
    def test_satisfied_can_be_set(self):
        p = _make_precondition(satisfied=True)
        assert p.satisfied is True


class TestRemediationPlan:
    """RemediationPlan validates steps non-empty and all field types."""

    @pytest.mark.unit
    def test_valid_plan(self):
        plan = _make_plan()
        assert isinstance(plan.id, uuid.UUID)
        assert isinstance(plan.incident_id, uuid.UUID)
        assert isinstance(plan.diagnosis_id, uuid.UUID)
        assert len(plan.steps) >= 1
        assert plan.blast_radius == BlastRadius.WORKLOAD
        assert plan.estimated_risk == RiskLevel.LOW

    @pytest.mark.unit
    def test_steps_must_be_non_empty(self):
        with pytest.raises(ValidationError, match="too_short"):
            _make_plan(steps=[])

    @pytest.mark.unit
    def test_rollback_plan_can_be_empty(self):
        plan = _make_plan(rollback_plan=[])
        assert plan.rollback_plan == []

    @pytest.mark.unit
    def test_preconditions_can_be_empty(self):
        plan = _make_plan(preconditions=[])
        assert plan.preconditions == []

    @pytest.mark.unit
    def test_plan_auto_generates_id(self):
        plan1 = _make_plan()
        plan2 = _make_plan()
        assert plan1.id != plan2.id

    @pytest.mark.unit
    def test_plan_auto_generates_created_at(self):
        plan = _make_plan()
        assert isinstance(plan.created_at, datetime)
        assert plan.created_at.tzinfo is not None

    @pytest.mark.unit
    def test_plan_json_roundtrip(self):
        plan = _make_plan()
        data = plan.model_dump(mode="json")
        restored = RemediationPlan.model_validate(data)
        assert restored.incident_id == plan.incident_id
        assert restored.blast_radius == plan.blast_radius
        assert restored.estimated_risk == plan.estimated_risk
        assert len(restored.steps) == len(plan.steps)

    @pytest.mark.unit
    def test_plan_with_multiple_steps(self):
        steps = [
            _make_step(order=1, description="Step 1"),
            _make_step(order=2, description="Step 2"),
            _make_step(order=3, description="Step 3"),
        ]
        plan = _make_plan(steps=steps)
        assert len(plan.steps) == 3
        assert plan.steps[0].order == 1
        assert plan.steps[2].order == 3

    @pytest.mark.unit
    def test_all_blast_radius_values_accepted(self):
        for br in BlastRadius:
            plan = _make_plan(blast_radius=br)
            assert plan.blast_radius == br

    @pytest.mark.unit
    def test_all_risk_levels_accepted(self):
        for rl in RiskLevel:
            plan = _make_plan(estimated_risk=rl)
            assert plan.estimated_risk == rl

    @pytest.mark.unit
    def test_plan_exports_from_models_init(self):
        from src.models import (
            BlastRadius,
            Precondition,
            RemediationPlan,
            RemediationStep,
            RiskLevel,
        )
        assert BlastRadius is not None
        assert RemediationPlan is not None
        assert RemediationStep is not None
        assert Precondition is not None
        assert RiskLevel is not None
