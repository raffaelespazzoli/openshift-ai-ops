"""In-process asyncio event bus implementation (AD-24).

Uses asyncio.Queue per subscriber for broadcast fan-out.
No external broker — single-process model.
Maintains a bounded replay buffer for SSE reconnection support.
"""

from __future__ import annotations

import asyncio
import itertools
from collections import deque

from ..config.logging import Component, get_logger
from ..models.events import BusEvent, SSEEventData

logger = get_logger(Component.API)

_REPLAY_BUFFER_SIZE = 1024


class NumberedEvent:
    """An event with a monotonic sequence ID for reconnection support."""

    __slots__ = ("id", "event")

    def __init__(self, event_id: int, event: BusEvent) -> None:
        self.id = event_id
        self.event = event


class InProcessEventBus:
    """Asyncio-based event bus using per-subscriber queues."""

    def __init__(self, max_queue_size: int = 256, replay_buffer_size: int = _REPLAY_BUFFER_SIZE) -> None:
        self._subscribers: set[asyncio.Queue[NumberedEvent]] = set()
        self._max_queue_size = max_queue_size
        self._id_counter = itertools.count(1)
        self._replay_buffer: deque[NumberedEvent] = deque(maxlen=replay_buffer_size)

    async def emit(self, event_name: str, data: SSEEventData) -> None:
        """Broadcast an event to all subscriber queues.

        Drops events for slow subscribers (full queue) with a warning log
        rather than applying backpressure to the emitter.
        """
        event = BusEvent(event_name=event_name, data=data)
        numbered = NumberedEvent(event_id=next(self._id_counter), event=event)
        self._replay_buffer.append(numbered)

        dead_queues: list[asyncio.Queue[NumberedEvent]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(numbered)
            except asyncio.QueueFull:
                dead_queues.append(queue)
                logger.warning(
                    "Dropping event for slow subscriber — queue full",
                    extra={"event_name": event_name},
                )
        for q in dead_queues:
            self._subscribers.discard(q)

    async def subscribe(self, last_event_id: int | None = None) -> asyncio.Queue[NumberedEvent]:
        """Create a new subscriber queue and register it.

        If last_event_id is provided, replays buffered events that occurred
        after that ID into the new queue before live events start flowing.
        """
        queue: asyncio.Queue[NumberedEvent] = asyncio.Queue(maxsize=self._max_queue_size)

        if last_event_id is not None:
            for numbered in self._replay_buffer:
                if numbered.id > last_event_id:
                    try:
                        queue.put_nowait(numbered)
                    except asyncio.QueueFull:
                        break

        self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[NumberedEvent]) -> None:
        """Remove a subscriber queue from the active set."""
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        """Current number of active subscribers."""
        return len(self._subscribers)


_event_bus: InProcessEventBus | None = None


def get_event_bus() -> InProcessEventBus:
    """FastAPI dependency returning the singleton event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = InProcessEventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the singleton (for testing)."""
    global _event_bus
    _event_bus = None
