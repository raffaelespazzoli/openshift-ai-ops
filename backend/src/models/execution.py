"""Execution, outcome, and rollback models (AD-4, Story 3.5).

Defines the typed artifacts produced during remediation execution,
outcome observation, and rollback operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


class ExecutionStepLog(BaseModel):
    """Log entry for a single executed remediation step."""

    step_order: int = Field(ge=1)
    command: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool
    output: str = ""
    error: str | None = None


class ExecutionLog(BaseModel):
    """Complete execution log for a remediation plan."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    plan_id: uuid.UUID
    steps: list[ExecutionStepLog] = Field(default_factory=list)
    mcp_calls: list[dict] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    status: str = "running"

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        allowed = ("running", "completed", "failed")
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got: {v!r}")
        return v


class OutcomeResult(BaseModel):
    """Result of post-execution outcome observation."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    alert_resolved: bool
    resolution_method: str = "timeout"
    resource_verification: dict | None = None
    outcome_confidence: float = Field(ge=0.0, le=1.0)
    refire_detected: bool = False
    observation_started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    observation_completed_at: datetime | None = None
    timeout_seconds: int = 300


class OutcomeConfidence:
    """Outcome confidence scoring constants."""

    BOTH = 1.0
    WEBHOOK_ONLY = 0.7
    VERIFICATION_ONLY = 0.5
    TIMEOUT = 0.2


class RollbackRecord(BaseModel):
    """Record of a human-triggered rollback operation."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    plan_id: uuid.UUID
    actor: str = Field(min_length=1)
    steps_executed: list[ExecutionStepLog] = Field(default_factory=list)
    success: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
