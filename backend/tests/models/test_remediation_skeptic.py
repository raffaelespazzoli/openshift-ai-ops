"""Unit tests for RemediationSkepticChallenge, RemediationSkepticVerdict,
and RemediationPlan.plan_hash() (Story 3.2).
"""

import copy
import uuid

import pytest
from pydantic import ValidationError

from src.models.remediation import (
    BlastRadius,
    Precondition,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from src.models.remediation_skeptic import (
    RemediationSkepticChallenge,
    RemediationSkepticVerdict,
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


def _make_plan(**overrides) -> RemediationPlan:
    incident_id = overrides.pop("incident_id", uuid.uuid4())
    diagnosis_id = overrides.pop("diagnosis_id", uuid.uuid4())
    defaults = {
        "incident_id": incident_id,
        "diagnosis_id": diagnosis_id,
        "steps": [_make_step()],
        "blast_radius": BlastRadius.WORKLOAD,
        "rollback_plan": [
            _make_step(order=1, description="Rollback step", action="rollback")
        ],
        "estimated_risk": RiskLevel.LOW,
        "preconditions": [
            Precondition(
                type="rbac",
                description="Can delete pods",
                requirement="delete verbs on pods resource",
            )
        ],
        "plan_summary": "Restart the crashing pod",
    }
    defaults.update(overrides)
    return RemediationPlan(**defaults)


class TestRemediationSkepticChallenge:
    """RemediationSkepticChallenge validates field types and constraints."""

    @pytest.mark.unit
    def test_valid_challenge(self):
        c = RemediationSkepticChallenge(
            step_correctness_issues=["Step 1 is redundant"],
            blast_radius_assessment="Blast radius is accurate",
            rollback_feasibility_issues=[],
            precondition_gaps=["Missing quota check"],
            risk_assessment_critique="Risk should be medium, not low",
            overall_verdict="Plan needs minor revisions",
        )
        assert len(c.step_correctness_issues) == 1
        assert c.blast_radius_assessment == "Blast radius is accurate"
        assert c.overall_verdict == "Plan needs minor revisions"

    @pytest.mark.unit
    def test_challenge_lists_default_to_empty(self):
        c = RemediationSkepticChallenge(
            blast_radius_assessment="ok",
            risk_assessment_critique="ok",
            overall_verdict="ok",
        )
        assert c.step_correctness_issues == []
        assert c.rollback_feasibility_issues == []
        assert c.precondition_gaps == []

    @pytest.mark.unit
    def test_challenge_auto_generates_created_at(self):
        c = RemediationSkepticChallenge(
            blast_radius_assessment="ok",
            risk_assessment_critique="ok",
            overall_verdict="ok",
        )
        assert c.created_at is not None
        assert c.created_at.tzinfo is not None

    @pytest.mark.unit
    def test_challenge_json_roundtrip(self):
        c = RemediationSkepticChallenge(
            step_correctness_issues=["issue1"],
            blast_radius_assessment="fine",
            rollback_feasibility_issues=["rollback concern"],
            precondition_gaps=["gap1", "gap2"],
            risk_assessment_critique="too low",
            overall_verdict="needs revision",
        )
        data = c.model_dump(mode="json")
        restored = RemediationSkepticChallenge.model_validate(data)
        assert restored.step_correctness_issues == c.step_correctness_issues
        assert restored.overall_verdict == c.overall_verdict

    @pytest.mark.unit
    def test_challenge_exports_from_models_init(self):
        from src.models import RemediationSkepticChallenge as Exported

        assert Exported is not None


class TestRemediationSkepticVerdict:
    """RemediationSkepticVerdict validates rounds_completed and hash fields."""

    @pytest.mark.unit
    def test_valid_verdict_one_round(self):
        v = RemediationSkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_plan_hash="a" * 64,
            final_plan_hash="a" * 64,
            challenge_history=[{"round": 1}],
            verdict_reasoning="Validated in 1 round",
        )
        assert v.passed is True
        assert v.rounds_completed == 1

    @pytest.mark.unit
    def test_valid_verdict_two_rounds(self):
        v = RemediationSkepticVerdict(
            passed=True,
            rounds_completed=2,
            original_plan_hash="a" * 64,
            final_plan_hash="b" * 64,
            challenge_history=[{"round": 1}, {"round": 2}],
            verdict_reasoning="Validated in 2 rounds",
        )
        assert v.rounds_completed == 2

    @pytest.mark.unit
    def test_rounds_completed_must_be_ge_1(self):
        with pytest.raises(ValidationError):
            RemediationSkepticVerdict(
                passed=True,
                rounds_completed=0,
                original_plan_hash="a" * 64,
                final_plan_hash="a" * 64,
                challenge_history=[],
                verdict_reasoning="bad",
            )

    @pytest.mark.unit
    def test_rounds_completed_must_be_le_2(self):
        with pytest.raises(ValidationError):
            RemediationSkepticVerdict(
                passed=True,
                rounds_completed=3,
                original_plan_hash="a" * 64,
                final_plan_hash="a" * 64,
                challenge_history=[],
                verdict_reasoning="bad",
            )

    @pytest.mark.unit
    def test_original_plan_hash_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            RemediationSkepticVerdict(
                passed=True,
                rounds_completed=1,
                original_plan_hash="",
                final_plan_hash="a" * 64,
                challenge_history=[],
                verdict_reasoning="bad",
            )

    @pytest.mark.unit
    def test_final_plan_hash_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            RemediationSkepticVerdict(
                passed=True,
                rounds_completed=1,
                original_plan_hash="a" * 64,
                final_plan_hash="",
                challenge_history=[],
                verdict_reasoning="bad",
            )

    @pytest.mark.unit
    def test_verdict_json_roundtrip(self):
        v = RemediationSkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_plan_hash="abc123",
            final_plan_hash="abc123",
            challenge_history=[{"round": 1, "detail": "test"}],
            verdict_reasoning="Validated",
        )
        data = v.model_dump(mode="json")
        restored = RemediationSkepticVerdict.model_validate(data)
        assert restored.passed == v.passed
        assert restored.original_plan_hash == v.original_plan_hash

    @pytest.mark.unit
    def test_verdict_exports_from_models_init(self):
        from src.models import RemediationSkepticVerdict as Exported

        assert Exported is not None


class TestPlanHash:
    """RemediationPlan.plan_hash() is deterministic and content-sensitive."""

    @pytest.mark.unit
    def test_plan_hash_is_deterministic(self):
        plan = _make_plan()
        h1 = plan.plan_hash()
        h2 = plan.plan_hash()
        assert h1 == h2

    @pytest.mark.unit
    def test_plan_hash_is_64_char_hex(self):
        plan = _make_plan()
        h = plan.plan_hash()
        assert len(h) == 64
        int(h, 16)  # raises if not valid hex

    @pytest.mark.unit
    def test_plan_hash_changes_when_steps_modified(self):
        plan1 = _make_plan()
        plan2 = _make_plan(
            steps=[_make_step(description="Different step action")]
        )
        assert plan1.plan_hash() != plan2.plan_hash()

    @pytest.mark.unit
    def test_plan_hash_changes_when_blast_radius_changed(self):
        plan1 = _make_plan(blast_radius=BlastRadius.WORKLOAD)
        plan2 = _make_plan(blast_radius=BlastRadius.CLUSTER)
        assert plan1.plan_hash() != plan2.plan_hash()

    @pytest.mark.unit
    def test_plan_hash_changes_when_rollback_changed(self):
        plan1 = _make_plan()
        plan2 = _make_plan(
            rollback_plan=[
                _make_step(order=1, description="Totally different rollback", action="rollback")
            ]
        )
        assert plan1.plan_hash() != plan2.plan_hash()

    @pytest.mark.unit
    def test_plan_hash_changes_when_risk_changed(self):
        plan1 = _make_plan(estimated_risk=RiskLevel.LOW)
        plan2 = _make_plan(estimated_risk=RiskLevel.HIGH)
        assert plan1.plan_hash() != plan2.plan_hash()

    @pytest.mark.unit
    def test_plan_hash_unchanged_when_only_summary_changes(self):
        plan1 = _make_plan(plan_summary="Summary A")
        plan2 = _make_plan(plan_summary="Summary B")
        assert plan1.plan_hash() == plan2.plan_hash()

    @pytest.mark.unit
    def test_plan_hash_unchanged_when_only_created_at_changes(self):
        from datetime import datetime, timezone, timedelta

        plan1 = _make_plan()
        plan2 = plan1.model_copy(
            update={"created_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}
        )
        assert plan1.plan_hash() == plan2.plan_hash()

    @pytest.mark.unit
    def test_plan_hash_unchanged_when_only_ids_change(self):
        plan1 = _make_plan()
        plan2 = plan1.model_copy(
            update={
                "id": uuid.uuid4(),
                "incident_id": uuid.uuid4(),
                "diagnosis_id": uuid.uuid4(),
            }
        )
        assert plan1.plan_hash() == plan2.plan_hash()
