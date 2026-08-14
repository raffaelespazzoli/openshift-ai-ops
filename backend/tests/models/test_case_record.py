"""Unit tests for CaseRecord model (Story 4.1).

Tests validation of outcome, outcome_confidence, fast_path_eligible defaults,
and CaseRecordSummary backward compatibility.
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.case_record import CaseRecord, CaseRecordSummary

pytestmark = pytest.mark.unit


class TestCaseRecord:
    def _make_record(self, **overrides) -> CaseRecord:
        defaults = {
            "incident_id": uuid.uuid4(),
            "alert_signature": "KubePodCrashLooping ns severity critical",
            "root_cause_code": "workload/crash-loop",
            "diagnosis_object": {"root_cause_component": "workload"},
            "remediation_plan": {"steps": []},
            "outcome": "success",
            "outcome_confidence": 0.7,
            "outcome_details": {"alert_resolved": True},
            "ocp_version": "4.16",
        }
        defaults.update(overrides)
        return CaseRecord(**defaults)

    def test_valid_success_record(self):
        record = self._make_record(outcome="success", outcome_confidence=1.0)
        assert record.outcome == "success"
        assert record.outcome_confidence == 1.0
        assert record.id is not None

    def test_valid_failure_record(self):
        record = self._make_record(outcome="failure", outcome_confidence=0.2)
        assert record.outcome == "failure"
        assert record.outcome_confidence == 0.2

    def test_outcome_must_be_success_or_failure(self):
        with pytest.raises(ValidationError, match="outcome must be 'success' or 'failure'"):
            self._make_record(outcome="partial")

    def test_outcome_rejects_empty_string(self):
        with pytest.raises(ValidationError):
            self._make_record(outcome="")

    def test_outcome_confidence_must_be_between_0_and_1(self):
        with pytest.raises(ValidationError):
            self._make_record(outcome_confidence=1.5)

    def test_outcome_confidence_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            self._make_record(outcome_confidence=-0.1)

    def test_outcome_confidence_boundary_zero(self):
        record = self._make_record(outcome_confidence=0.0)
        assert record.outcome_confidence == 0.0

    def test_outcome_confidence_boundary_one(self):
        record = self._make_record(outcome_confidence=1.0)
        assert record.outcome_confidence == 1.0

    def test_fast_path_eligible_defaults_true(self):
        record = self._make_record()
        assert record.fast_path_eligible is True

    def test_fast_path_eligible_explicit_false(self):
        record = self._make_record(fast_path_eligible=False)
        assert record.fast_path_eligible is False

    def test_cluster_context_defaults_empty(self):
        record = self._make_record()
        assert record.cluster_context == {}

    def test_diagnosis_summary_defaults_empty(self):
        record = self._make_record()
        assert record.diagnosis_summary == ""

    def test_remediation_summary_defaults_empty(self):
        record = self._make_record()
        assert record.remediation_summary == ""

    def test_created_at_auto_generated(self):
        record = self._make_record()
        assert isinstance(record.created_at, datetime)
        assert record.created_at.tzinfo is not None

    def test_id_auto_generated(self):
        record = self._make_record()
        assert isinstance(record.id, uuid.UUID)

    def test_custom_id_accepted(self):
        custom_id = uuid.uuid4()
        record = self._make_record(id=custom_id)
        assert record.id == custom_id


class TestCaseRecordSummary:
    """Ensure existing CaseRecordSummary model still works."""

    def test_summary_model_unchanged(self):
        summary = CaseRecordSummary(
            id=uuid.uuid4(),
            alert_signature="test alert",
            root_cause_code="node/memory-pressure",
            outcome="success",
            outcome_confidence=0.9,
            ocp_version="4.16",
            created_at=datetime.now(timezone.utc),
        )
        assert summary.similarity == 0.0
        assert summary.effective_confidence == 0.0
