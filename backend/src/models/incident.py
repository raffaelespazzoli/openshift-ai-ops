"""Incident model — the core domain entity."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from .state_machine import IncidentState


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Incident(BaseModel):
    """Represents an operational incident tracked through the pipeline."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    state: IncidentState = IncidentState.RECEIVED
    severity: Severity | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
