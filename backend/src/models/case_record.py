"""Case Record summary model — minimal read-only projection (AD-4, AD-20).

This provides a lightweight view of past case records for the Learning Store
query interface. The full Case Record schema (including DiagnosisObject,
RemediationPlan, cluster topology) is Epic 4's responsibility.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
