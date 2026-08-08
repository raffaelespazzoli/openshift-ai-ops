"""RootCauseEvent model — sealed correlation group artifact (AD-4, AD-5).

A RootCauseEvent represents a group of correlated alerts that have been
sealed into a single actionable unit for the diagnosis pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class CorrelationLayer(StrEnum):
    DEDUP = "dedup"
    NAMESPACE_TEMPORAL = "namespace_temporal"
    LABEL_TEMPORAL = "label_temporal"
    SUBSYSTEM_DEPENDENCY = "subsystem_dependency"
    LEARNING_STORE_COOCCURRENCE = "learning_store_cooccurrence"


class CorrelationEvidence(BaseModel):
    """Evidence for why alerts were grouped together."""

    layer: CorrelationLayer
    alert_ids: list[uuid.UUID]
    reasoning: str
    dimension_data: dict = Field(default_factory=dict)


class RootCauseEvent(BaseModel):
    """A sealed correlation group — the artifact produced by the triage stage."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    alert_ids: list[uuid.UUID] = Field(default_factory=list)
    correlation_evidence: list[CorrelationEvidence] = Field(default_factory=list)
    sealed: bool = False
    sealed_at: datetime | None = None
    settling_window_seconds: int = 300
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    max_age_at: datetime | None = None
