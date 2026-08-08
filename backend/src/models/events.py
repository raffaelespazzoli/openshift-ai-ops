"""Event bus interface shape (AD-24).

Stub defining the emit/subscribe contract for later implementation.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Protocol

type EventHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus(Protocol):
    """In-process asyncio event bus contract."""

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Emit an event to all subscribers of the given type."""
        ...

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for events of the given type."""
        ...
