"""Unit tests for execution models (Story 3.5).

Tests ExecutionLog, ExecutionStepLog, OutcomeResult, RollbackRecord validation.
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.execution import (
    ExecutionLog,
    ExecutionStepLog,
    OutcomeConfidence,
    OutcomeResult,
    RollbackRecord,
)

pytestmark = pytest.mark.unit


class TestExecutionStepLog:
    def test_valid_step_log(self):
        step = ExecutionStepLog(
            step_order=1,
            command="kubectl apply -f fix.yaml",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            success=True,
            output="applied",
        )
        assert step.step_order == 1
        assert step.success is True

    def test_step_order_must_be_positive(self):
        with pytest.raises(ValidationError):
            ExecutionStepLog(
                step_order=0,
                command="cmd",
                started_at=datetime.now(timezone.utc),
                success=True,
            )

    def test_step_with_error(self):
        step = ExecutionStepLog(
            step_order=2,
            command="kubectl delete pod",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            success=False,
            error="timeout",
        )
        assert step.success is False
        assert step.error == "timeout"


class TestExecutionLog:
    def test_valid_execution_log(self):
        log = ExecutionLog(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            steps=[],
            status="running",
        )
        assert log.status == "running"
        assert log.id is not None

    def test_status_must_be_valid(self):
        with pytest.raises(ValidationError):
            ExecutionLog(
                incident_id=uuid.uuid4(),
                plan_id=uuid.uuid4(),
                status="invalid_status",
            )

    def test_status_completed(self):
        log = ExecutionLog(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            status="completed",
        )
        assert log.status == "completed"

    def test_status_failed(self):
        log = ExecutionLog(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            status="failed",
        )
        assert log.status == "failed"


class TestOutcomeResult:
    def test_valid_outcome(self):
        result = OutcomeResult(
            incident_id=uuid.uuid4(),
            alert_resolved=True,
            resolution_method="webhook",
            outcome_confidence=0.7,
        )
        assert result.alert_resolved is True
        assert result.outcome_confidence == 0.7

    def test_confidence_must_be_between_0_and_1(self):
        with pytest.raises(ValidationError):
            OutcomeResult(
                incident_id=uuid.uuid4(),
                alert_resolved=True,
                outcome_confidence=1.5,
            )

    def test_confidence_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            OutcomeResult(
                incident_id=uuid.uuid4(),
                alert_resolved=False,
                outcome_confidence=-0.1,
            )

    def test_confidence_boundary_values(self):
        result_zero = OutcomeResult(
            incident_id=uuid.uuid4(),
            alert_resolved=False,
            outcome_confidence=0.0,
        )
        assert result_zero.outcome_confidence == 0.0

        result_one = OutcomeResult(
            incident_id=uuid.uuid4(),
            alert_resolved=True,
            outcome_confidence=1.0,
        )
        assert result_one.outcome_confidence == 1.0

    def test_refire_detected_default_false(self):
        result = OutcomeResult(
            incident_id=uuid.uuid4(),
            alert_resolved=True,
            outcome_confidence=0.7,
        )
        assert result.refire_detected is False


class TestOutcomeConfidence:
    def test_confidence_constants(self):
        assert OutcomeConfidence.BOTH == 1.0
        assert OutcomeConfidence.WEBHOOK_ONLY == 0.7
        assert OutcomeConfidence.VERIFICATION_ONLY == 0.5
        assert OutcomeConfidence.TIMEOUT == 0.2


class TestRollbackRecord:
    def test_valid_rollback_record(self):
        record = RollbackRecord(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            actor="admin@example.com",
            success=True,
        )
        assert record.actor == "admin@example.com"
        assert record.success is True

    def test_actor_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            RollbackRecord(
                incident_id=uuid.uuid4(),
                plan_id=uuid.uuid4(),
                actor="",
                success=True,
            )

    def test_rollback_with_steps(self):
        step = ExecutionStepLog(
            step_order=1,
            command="kubectl rollback",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            success=True,
            output="rolled back",
        )
        record = RollbackRecord(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            actor="sre-user",
            steps_executed=[step],
            success=True,
        )
        assert len(record.steps_executed) == 1
