"""SSE event envelope models and EventBus protocol (AD-21, AD-24).

Defines the SSE event data envelope, dot-notation event name constants,
and the in-process event bus interface contract.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field


class SSEEventData(BaseModel):
    """Payload envelope for all SSE events sent to clients."""

    incident_id: uuid.UUID
    stage: str
    state: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


class BusEvent(BaseModel):
    """Internal representation of an event on the bus."""

    event_name: str
    data: SSEEventData


class EventNames:
    """Dot-notation event name constants (AD-21)."""

    INCIDENT_CREATED = "incident.created"
    INCIDENT_STAGE_CHANGED = "incident.stage_changed"
    INCIDENT_STATE_CHANGED = "incident.state_changed"
    INCIDENT_RESOLVED = "incident.resolved"
    INCIDENT_APPROVAL_DECISION = "incident.approval_decision"


class EventBus(Protocol):
    """In-process asyncio event bus contract (AD-24)."""

    async def emit(self, event_name: str, data: SSEEventData) -> None:
        """Broadcast an event to all subscribers."""
        ...

    async def subscribe(self) -> AsyncIterator[BusEvent]:
        """Create a new subscription returning an async iterator of events."""
        ...

    async def unsubscribe(self, subscriber: Any) -> None:
        """Remove a subscriber and clean up its resources."""
        ...
