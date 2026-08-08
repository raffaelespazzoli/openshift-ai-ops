"""Alert model — represents an AlertManager alert."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class AlertStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"


class Alert(BaseModel):
    """Represents a single alert from AlertManager."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID | None = None
    fingerprint: str
    labels: dict = Field(default_factory=dict)
    annotations: dict = Field(default_factory=dict)
    status: AlertStatus
    fired_at: datetime
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
