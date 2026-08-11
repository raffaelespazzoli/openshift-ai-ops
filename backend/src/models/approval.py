"""Human approval workflow models (AD-4, Story 3.4).

Defines typed artifacts for the human-in-the-loop approval/rejection
of remediation plans, and for lightweight policy adjustments.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ApprovalAction = Literal["approved", "rejected"]


class ApprovalRecord(BaseModel):
    """Persisted record of an approval or rejection decision."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    plan_id: uuid.UUID
    action: ApprovalAction
    actor: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RejectionRequest(BaseModel):
    """Request body for rejecting a remediation plan."""

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be blank")
        return v


class ApprovalContext(BaseModel):
    """Full decision context returned to the SRE for an incident awaiting approval."""

    incident_id: uuid.UUID
    state: str
    severity: str | None = None
    diagnosis_summary: dict = Field(default_factory=dict)
    remediation_plan: dict = Field(default_factory=dict)
    skeptic_reviews: list[dict] = Field(default_factory=list)
    dry_run_result: dict | None = None
    blast_radius: str | None = None
    policy_decision: dict | None = None
    queued_at: datetime | None = None
    minimum_review_seconds: int | None = None
    review_time_remaining: float | None = None


class PolicyAdjustmentRequest(BaseModel):
    """Request body for adjusting policy gate thresholds."""

    severity: str
    blast_radius: str
    confidence_minimum: float | None = Field(default=None, ge=0.0, le=1.0)
    new_auto_approve: bool
