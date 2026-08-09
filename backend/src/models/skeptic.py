"""Skeptic challenge/response models for adversarial diagnosis validation (AD-4).

Defines the typed artifacts produced during the Skeptic validation loop:
- SkepticChallenge: adversarial challenge issued by the Skeptic agent
- SkepticRebuttal: individual rebuttal to a specific challenge point
- SkepticResponse: orchestrator's response to a skeptic challenge
- SkepticVerdict: outcome of the full skeptic validation loop
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .diagnosis import DiagnosisObject


class SkepticChallenge(BaseModel):
    """Structured adversarial challenge produced by the Skeptic agent."""

    alternative_hypotheses: list[str] = Field(min_length=1)
    evidence_gap_challenges: list[str] = Field(default_factory=list)
    logical_weaknesses: list[str] = Field(min_length=1)
    overall_assessment: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SkepticRebuttal(BaseModel):
    """Individual rebuttal addressing a specific challenge point."""

    challenge_point: str
    rebuttal: str
    additional_evidence: str = ""


class SkepticResponse(BaseModel):
    """Orchestrator's response to a skeptic challenge."""

    rebuttals: list[SkepticRebuttal]
    revised_diagnosis: DiagnosisObject | None = None
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SkepticVerdict(BaseModel):
    """Outcome of the full skeptic validation loop."""

    passed: bool
    rounds_completed: int = Field(ge=1, le=2)
    original_hash: str = Field(min_length=1)
    final_hash: str = Field(min_length=1)
    challenge_history: list[dict[str, Any]]
    verdict_reasoning: str
