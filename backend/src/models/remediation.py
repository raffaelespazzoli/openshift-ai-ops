"""Remediation plan models (AD-4, Story 3.1).

Defines the typed artifacts produced by the remediation planner.
RemediationPlan is the structured output from the planner agent —
it describes what to fix, how to roll back, and what preconditions
must be satisfied before execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class BlastRadius(StrEnum):
    WORKLOAD = "workload"
    NAMESPACE = "namespace"
    NODE = "node"
    CLUSTER = "cluster"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RemediationStep(BaseModel):
    """A single step in a remediation or rollback plan."""

    order: int = Field(ge=1)
    description: str
    command: str | None = None
    resource: str
    action: str
    expected_outcome: str


class Precondition(BaseModel):
    """A prerequisite that must be satisfied before remediation execution."""

    type: str  # "rbac" | "quota" | "resource"
    description: str
    requirement: str
    satisfied: bool | None = None


class RemediationPlan(BaseModel):
    """Structured remediation plan produced by the planner agent."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    diagnosis_id: uuid.UUID
    steps: list[RemediationStep] = Field(min_length=1)
    blast_radius: BlastRadius
    rollback_plan: list[RemediationStep] = Field(default_factory=list)
    estimated_risk: RiskLevel
    preconditions: list[Precondition] = Field(default_factory=list)
    plan_summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
