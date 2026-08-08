"""SSE event stream endpoint (AD-21).

GET /api/v1/events/stream — Server-Sent Events for real-time pipeline updates.
Uses FastAPI's native EventSourceResponse and ServerSentEvent.
Supports reconnection via Last-Event-ID header with monotonic event IDs.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..config.logging import Component, get_logger
from .auth import UserInfo, get_current_user
from .event_bus import InProcessEventBus, NumberedEvent, get_event_bus

router = APIRouter()
logger = get_logger(Component.API)

_KEEPALIVE_INTERVAL = 15.0  # seconds


async def _event_generator(
    queue: asyncio.Queue[NumberedEvent],
    event_bus: InProcessEventBus,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted events from a subscriber queue.

    Sends keepalive comments every 15s to prevent proxy timeouts.
    Cleans up on client disconnect.
    Uses monotonic event IDs from the bus for reconnection support.
    """
    try:
        while True:
            try:
                numbered = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL)
                data_json = numbered.event.data.model_dump_json()
                yield f"id: {numbered.id}\nevent: {numbered.event.event_name}\ndata: {data_json}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await event_bus.unsubscribe(queue)


def _parse_last_event_id(request: Request) -> int | None:
    """Extract and parse Last-Event-ID header from the request."""
    last_id = request.headers.get("Last-Event-ID") or request.headers.get("last-event-id")
    if last_id is None:
        return None
    try:
        return int(last_id)
    except (ValueError, TypeError):
        return None


@router.get("/api/v1/events/stream")
async def event_stream(
    request: Request,
    user: UserInfo = Depends(get_current_user),
    event_bus: InProcessEventBus = Depends(get_event_bus),
) -> StreamingResponse:
    """Subscribe to real-time SSE events from the pipeline event bus."""
    request.state.user = user

    last_event_id = _parse_last_event_id(request)
    queue = await event_bus.subscribe(last_event_id=last_event_id)

    return StreamingResponse(
        _event_generator(queue, event_bus),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
