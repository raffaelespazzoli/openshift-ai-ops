"""Case Record models (AD-4, AD-20).

CaseRecordSummary: lightweight read-only projection for Learning Store queries.
CaseRecord: full persistence model with diagnosis, plan, and outcome detail.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


class CaseRecordSummary(BaseModel):
    """Minimal Case Record projection for Learning Store similarity queries."""

    id: uuid.UUID
    alert_signature: str
    root_cause_code: str
    outcome: str
    outcome_confidence: float = Field(ge=0.0, le=1.0)
    ocp_version: str
    created_at: datetime
    similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    effective_confidence: float = Field(default=0.0, ge=0.0)


class CaseRecord(BaseModel):
    """Full Case Record for Learning Store persistence (AD-4, AD-20)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    alert_signature: str
    root_cause_code: str
    diagnosis_object: dict
    remediation_plan: dict
    outcome: str
    outcome_confidence: float = Field(ge=0.0, le=1.0)
    outcome_details: dict
    ocp_version: str
    cluster_context: dict = Field(default_factory=dict)
    diagnosis_summary: str = ""
    remediation_summary: str = ""
    fast_path_eligible: bool = True
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("outcome")
    @classmethod
    def _validate_outcome(cls, v: str) -> str:
        if v not in ("success", "failure"):
            raise ValueError(f"outcome must be 'success' or 'failure', got: {v!r}")
        return v
