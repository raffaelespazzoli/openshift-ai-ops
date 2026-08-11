"""Remediation skeptic challenge/verdict models (AD-4, Story 3.2).

Defines the typed artifacts produced during the Remediation Skeptic
validation loop — parallel to models/skeptic.py but for plan challenges:
- RemediationSkepticChallenge: adversarial challenge to a remediation plan
- RemediationSkepticVerdict: outcome of the full remediation skeptic loop
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class RemediationSkepticChallenge(BaseModel):
    """Structured adversarial challenge to a Remediation Plan."""

    step_correctness_issues: list[str] = Field(default_factory=list)
    blast_radius_assessment: str
    rollback_feasibility_issues: list[str] = Field(default_factory=list)
    precondition_gaps: list[str] = Field(default_factory=list)
    risk_assessment_critique: str
    overall_verdict: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RemediationSkepticVerdict(BaseModel):
    """Outcome of the full remediation skeptic validation loop."""

    passed: bool
    degraded: bool = False
    verdict_note: str | None = None
    rounds_completed: int = Field(ge=1, le=2)
    original_plan_hash: str = Field(min_length=1)
    final_plan_hash: str = Field(min_length=1)
    challenge_history: list[dict[str, Any]]
    verdict_reasoning: str
