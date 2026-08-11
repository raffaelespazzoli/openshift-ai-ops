"""Dry-run pre-flight and policy gate models (AD-4, Story 3.3).

Defines typed artifacts for cluster-side validation (dry-run)
and the three-dimensional policy matrix evaluation that decides
auto-execution vs. human approval.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class DryRunStepResult(BaseModel):
    """Result of dry-run validation for a single remediation step."""

    step_order: int
    command: str
    success: bool
    message: str
    error_detail: str | None = None


class DryRunResult(BaseModel):
    """Aggregate result of dry-run pre-flight validation against the live cluster."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    plan_id: uuid.UUID
    step_results: list[DryRunStepResult]
    rbac_check_passed: bool
    quota_check_passed: bool
    admission_check_passed: bool
    overall_passed: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


PolicyDimensionName = Literal["severity", "blast_radius", "confidence"]


class PolicyDimension(BaseModel):
    """A single dimension in the policy matrix evaluation."""

    name: PolicyDimensionName
    value: str | float
    threshold: str | float
    passed: bool


class PolicyDecision(BaseModel):
    """Result of the three-dimensional policy gate evaluation."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    plan_id: uuid.UUID
    dimensions: list[PolicyDimension]
    evidence_complete: bool
    evidence_gaps_empty: bool
    auto_execution_approved: bool
    reasoning: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyMatrix(BaseModel):
    """Snapshot of the policy matrix thresholds used for a decision."""

    severity_thresholds: dict
    blast_radius_thresholds: dict
    confidence_threshold: float
