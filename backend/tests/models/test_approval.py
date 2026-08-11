"""Unit tests for approval workflow models (Story 3.4).

Tests ApprovalRecord, ApprovalContext, RejectionRequest,
PolicyAdjustmentRequest validation.
"""

import uuid
from datetime import datetime, timezone

import pytest

from src.models.approval import (
    ApprovalContext,
    ApprovalRecord,
    PolicyAdjustmentRequest,
    RejectionRequest,
)


class TestApprovalRecord:
    @pytest.mark.unit
    def test_create_approved_record(self):
        record = ApprovalRecord(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            action="approved",
            actor="sre-user",
        )
        assert record.action == "approved"
        assert record.actor == "sre-user"
        assert record.reason is None
        assert record.id is not None
        assert record.created_at is not None

    @pytest.mark.unit
    def test_create_rejected_record(self):
        record = ApprovalRecord(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            action="rejected",
            actor="sre-user",
            reason="Too risky",
        )
        assert record.action == "rejected"
        assert record.reason == "Too risky"

    @pytest.mark.unit
    def test_invalid_action_rejected(self):
        with pytest.raises(Exception):
            ApprovalRecord(
                incident_id=uuid.uuid4(),
                plan_id=uuid.uuid4(),
                action="cancelled",
                actor="sre-user",
            )

    @pytest.mark.unit
    def test_serialization_roundtrip(self):
        record = ApprovalRecord(
            incident_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            action="approved",
            actor="sre-user",
        )
        data = record.model_dump(mode="json")
        restored = ApprovalRecord.model_validate(data)
        assert restored.id == record.id
        assert restored.action == "approved"


class TestRejectionRequest:
    @pytest.mark.unit
    def test_valid_reason(self):
        req = RejectionRequest(reason="Plan is too risky for production")
        assert req.reason == "Plan is too risky for production"

    @pytest.mark.unit
    def test_empty_reason_rejected(self):
        with pytest.raises(Exception):
            RejectionRequest(reason="")

    @pytest.mark.unit
    def test_blank_reason_rejected(self):
        with pytest.raises(Exception):
            RejectionRequest(reason="   ")

    @pytest.mark.unit
    def test_missing_reason_rejected(self):
        with pytest.raises(Exception):
            RejectionRequest()


class TestApprovalContext:
    @pytest.mark.unit
    def test_create_full_context(self):
        ctx = ApprovalContext(
            incident_id=uuid.uuid4(),
            state="awaiting_approval",
            severity="critical",
            diagnosis_summary={"root_cause": "OOM"},
            remediation_plan={"steps": [{"order": 1}]},
            skeptic_reviews=[{"round_number": 1}],
            dry_run_result={"dry_run_passed": True},
            blast_radius="node",
            policy_decision={"auto_execution_approved": False},
            queued_at=datetime.now(timezone.utc),
            minimum_review_seconds=60,
            review_time_remaining=30.5,
        )
        assert ctx.state == "awaiting_approval"
        assert ctx.blast_radius == "node"
        assert ctx.minimum_review_seconds == 60
        assert ctx.review_time_remaining == 30.5

    @pytest.mark.unit
    def test_create_minimal_context(self):
        ctx = ApprovalContext(
            incident_id=uuid.uuid4(),
            state="awaiting_approval",
        )
        assert ctx.diagnosis_summary == {}
        assert ctx.remediation_plan == {}
        assert ctx.skeptic_reviews == []
        assert ctx.dry_run_result is None
        assert ctx.blast_radius is None

    @pytest.mark.unit
    def test_serialization_roundtrip(self):
        ctx = ApprovalContext(
            incident_id=uuid.uuid4(),
            state="awaiting_approval",
            severity="warning",
            blast_radius="cluster",
        )
        data = ctx.model_dump(mode="json")
        restored = ApprovalContext.model_validate(data)
        assert restored.incident_id == ctx.incident_id
        assert restored.blast_radius == "cluster"


class TestPolicyAdjustmentRequest:
    @pytest.mark.unit
    def test_valid_adjustment(self):
        req = PolicyAdjustmentRequest(
            severity="warning",
            blast_radius="workload",
            confidence_minimum=0.85,
            new_auto_approve=True,
        )
        assert req.severity == "warning"
        assert req.blast_radius == "workload"
        assert req.confidence_minimum == 0.85
        assert req.new_auto_approve is True

    @pytest.mark.unit
    def test_confidence_minimum_optional(self):
        req = PolicyAdjustmentRequest(
            severity="critical",
            blast_radius="node",
            new_auto_approve=False,
        )
        assert req.confidence_minimum is None
        assert req.severity == "critical"
        assert req.blast_radius == "node"

    @pytest.mark.unit
    def test_confidence_out_of_range(self):
        with pytest.raises(Exception):
            PolicyAdjustmentRequest(
                severity="warning",
                blast_radius="workload",
                confidence_minimum=1.5,
                new_auto_approve=True,
            )

    @pytest.mark.unit
    def test_confidence_negative_rejected(self):
        with pytest.raises(Exception):
            PolicyAdjustmentRequest(
                severity="warning",
                blast_radius="workload",
                confidence_minimum=-0.1,
                new_auto_approve=True,
            )


class TestMinimumReviewTimeLogic:
    """Unit tests for the minimum review time helper functions."""

    @pytest.mark.unit
    def test_elapsed_returns_true(self):
        from src.api.approval import _review_time_elapsed
        from src.config.approval_settings import ApprovalSettings

        settings = ApprovalSettings(
            minimum_review_enabled=True,
            minimum_review_seconds_node=60,
            minimum_review_seconds_cluster=60,
        )
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        elapsed, remaining = _review_time_elapsed(past, "node", settings)
        assert elapsed is True
        assert remaining is None

    @pytest.mark.unit
    def test_not_elapsed_returns_false(self):
        from src.api.approval import _review_time_elapsed
        from src.config.approval_settings import ApprovalSettings

        settings = ApprovalSettings(
            minimum_review_enabled=True,
            minimum_review_seconds_node=99999,
            minimum_review_seconds_cluster=99999,
        )
        recent = datetime.now(timezone.utc)
        elapsed, remaining = _review_time_elapsed(recent, "node", settings)
        assert elapsed is False
        assert remaining is not None
        assert remaining > 0

    @pytest.mark.unit
    def test_disabled_always_elapsed(self):
        from src.api.approval import _review_time_elapsed
        from src.config.approval_settings import ApprovalSettings

        settings = ApprovalSettings(minimum_review_enabled=False)
        recent = datetime.now(timezone.utc)
        elapsed, remaining = _review_time_elapsed(recent, "node", settings)
        assert elapsed is True
        assert remaining is None

    @pytest.mark.unit
    def test_workload_blast_radius_always_elapsed(self):
        from src.api.approval import _review_time_elapsed
        from src.config.approval_settings import ApprovalSettings

        settings = ApprovalSettings(
            minimum_review_enabled=True,
            minimum_review_seconds_node=60,
            minimum_review_seconds_cluster=60,
        )
        recent = datetime.now(timezone.utc)
        elapsed, remaining = _review_time_elapsed(recent, "workload", settings)
        assert elapsed is True
        assert remaining is None

    @pytest.mark.unit
    def test_namespace_blast_radius_always_elapsed(self):
        from src.api.approval import _review_time_elapsed
        from src.config.approval_settings import ApprovalSettings

        settings = ApprovalSettings(
            minimum_review_enabled=True,
            minimum_review_seconds_node=60,
            minimum_review_seconds_cluster=60,
        )
        recent = datetime.now(timezone.utc)
        elapsed, remaining = _review_time_elapsed(recent, "namespace", settings)
        assert elapsed is True
        assert remaining is None

    @pytest.mark.unit
    def test_cluster_blast_radius_enforced(self):
        from src.api.approval import _review_time_elapsed
        from src.config.approval_settings import ApprovalSettings

        settings = ApprovalSettings(
            minimum_review_enabled=True,
            minimum_review_seconds_node=60,
            minimum_review_seconds_cluster=120,
        )
        recent = datetime.now(timezone.utc)
        elapsed, remaining = _review_time_elapsed(recent, "cluster", settings)
        assert elapsed is False
        assert remaining is not None
        assert remaining > 0
