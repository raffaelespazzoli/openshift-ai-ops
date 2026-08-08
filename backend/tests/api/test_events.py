"""SSE integration tests for the event stream endpoint and event bus."""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.api.event_bus import InProcessEventBus, NumberedEvent, get_event_bus, reset_event_bus
from src.api.events import _event_generator
from src.models.events import EventNames, SSEEventData

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _auth_disabled():
    """Disable auth for all tests in this module."""
    with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
        yield


@pytest.fixture(autouse=True)
def _reset_bus():
    """Reset event bus between tests."""
    reset_event_bus()
    yield
    reset_event_bus()


class TestEventBusUnit:
    """Unit tests for the in-process event bus."""

    async def test_emit_to_subscriber(self):
        bus = InProcessEventBus()
        queue = await bus.subscribe()
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        await bus.emit(EventNames.INCIDENT_STAGE_CHANGED, data)
        numbered = queue.get_nowait()
        assert numbered.event.event_name == EventNames.INCIDENT_STAGE_CHANGED
        assert numbered.event.data.incident_id == data.incident_id
        assert numbered.id == 1

    async def test_broadcast_to_multiple_subscribers(self):
        bus = InProcessEventBus()
        q1 = await bus.subscribe()
        q2 = await bus.subscribe()
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        await bus.emit(EventNames.INCIDENT_CREATED, data)
        e1 = q1.get_nowait()
        e2 = q2.get_nowait()
        assert e1.event.event_name == e2.event.event_name
        assert e1.event.data.incident_id == e2.event.data.incident_id

    async def test_unsubscribe_removes_queue(self):
        bus = InProcessEventBus()
        queue = await bus.subscribe()
        assert bus.subscriber_count == 1
        await bus.unsubscribe(queue)
        assert bus.subscriber_count == 0

    async def test_full_queue_drops_event(self):
        bus = InProcessEventBus(max_queue_size=1)
        queue = await bus.subscribe()
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        await bus.emit("test.event", data)
        await bus.emit("test.event", data)
        assert bus.subscriber_count == 0

    async def test_subscriber_count(self):
        bus = InProcessEventBus()
        await bus.subscribe()
        await bus.subscribe()
        assert bus.subscriber_count == 2

    async def test_monotonic_ids_increment(self):
        bus = InProcessEventBus()
        queue = await bus.subscribe()
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        await bus.emit("test.event", data)
        await bus.emit("test.event", data)
        await bus.emit("test.event", data)
        e1 = queue.get_nowait()
        e2 = queue.get_nowait()
        e3 = queue.get_nowait()
        assert e1.id == 1
        assert e2.id == 2
        assert e3.id == 3

    async def test_reconnection_replays_missed_events(self):
        bus = InProcessEventBus()
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        await bus.emit("test.event", data)
        await bus.emit("test.event", data)
        await bus.emit("test.event", data)

        queue = await bus.subscribe(last_event_id=1)
        e1 = queue.get_nowait()
        e2 = queue.get_nowait()
        assert e1.id == 2
        assert e2.id == 3
        assert queue.empty()

    async def test_reconnection_with_no_missed_events(self):
        bus = InProcessEventBus()
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        await bus.emit("test.event", data)

        queue = await bus.subscribe(last_event_id=1)
        assert queue.empty()


class TestSSEGenerator:
    """Tests for the SSE event generator function directly."""

    async def test_event_yields_correct_format(self):
        """Verify the generator yields properly formatted SSE lines."""
        bus = InProcessEventBus()
        queue = await bus.subscribe()
        incident_id = uuid.uuid4()
        data = SSEEventData(
            incident_id=incident_id,
            stage="diagnosing",
            state="active",
            payload={"detail": "test"},
        )
        await bus.emit(EventNames.INCIDENT_STAGE_CHANGED, data)

        gen = _event_generator(queue, bus)
        line = await gen.__anext__()

        assert f"event: {EventNames.INCIDENT_STAGE_CHANGED}" in line
        assert "id: 1" in line
        assert "data:" in line

        data_part = line.split("data: ")[1].split("\n")[0]
        payload = json.loads(data_part)
        assert payload["incident_id"] == str(incident_id)
        assert payload["stage"] == "diagnosing"
        assert payload["state"] == "active"
        assert payload["payload"] == {"detail": "test"}

        await gen.aclose()

    async def test_envelope_contains_all_fields(self):
        """Verify event envelope matches AD-21 specification."""
        bus = InProcessEventBus()
        queue = await bus.subscribe()
        ts = datetime(2026, 8, 8, 14, 0, 0, tzinfo=timezone.utc)
        data = SSEEventData(
            incident_id=uuid.uuid4(),
            stage="executing",
            state="in_progress",
            timestamp=ts,
            payload={"step": 1},
        )
        await bus.emit(EventNames.INCIDENT_STAGE_CHANGED, data)

        gen = _event_generator(queue, bus)
        line = await gen.__anext__()

        data_part = line.split("data: ")[1].split("\n")[0]
        payload = json.loads(data_part)
        assert "incident_id" in payload
        assert "stage" in payload
        assert "state" in payload
        assert "timestamp" in payload
        assert "payload" in payload

        await gen.aclose()

    async def test_multiple_subscribers_receive_broadcast(self):
        """Verify multiple queues each receive the same event."""
        bus = InProcessEventBus()
        q1 = await bus.subscribe()
        q2 = await bus.subscribe()
        incident_id = uuid.uuid4()
        data = SSEEventData(incident_id=incident_id, stage="correlating", state="active")
        await bus.emit(EventNames.INCIDENT_CREATED, data)

        gen1 = _event_generator(q1, bus)
        gen2 = _event_generator(q2, bus)

        line1 = await gen1.__anext__()
        line2 = await gen2.__anext__()

        data1 = json.loads(line1.split("data: ")[1].split("\n")[0])
        data2 = json.loads(line2.split("data: ")[1].split("\n")[0])
        assert data1["incident_id"] == data2["incident_id"] == str(incident_id)

        await gen1.aclose()
        await gen2.aclose()

    async def test_keepalive_on_timeout(self):
        """Verify keepalive comment is sent when no events arrive."""
        bus = InProcessEventBus()
        queue = await bus.subscribe()

        gen = _event_generator(queue, bus)

        import src.api.events as events_mod
        original_interval = events_mod._KEEPALIVE_INTERVAL
        events_mod._KEEPALIVE_INTERVAL = 0.1

        try:
            line = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
            assert line == ": keepalive\n\n"
        finally:
            events_mod._KEEPALIVE_INTERVAL = original_interval
            await gen.aclose()

    async def test_disconnect_unsubscribes(self):
        """Verify generator cleanup unsubscribes from bus."""
        bus = InProcessEventBus()
        queue = await bus.subscribe()
        assert bus.subscriber_count == 1

        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        await bus.emit("test.event", data)

        gen = _event_generator(queue, bus)
        await gen.__anext__()
        await gen.aclose()

        assert bus.subscriber_count == 0

    async def test_sequential_events_have_incrementing_ids(self):
        """Verify event IDs increment sequentially (monotonic from bus)."""
        bus = InProcessEventBus()
        queue = await bus.subscribe()
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        await bus.emit("test.event", data)
        await bus.emit("test.event", data)

        gen = _event_generator(queue, bus)
        line1 = await gen.__anext__()
        line2 = await gen.__anext__()

        assert "id: 1\n" in line1
        assert "id: 2\n" in line2

        await gen.aclose()

    async def test_reconnection_replays_via_generator(self):
        """Verify reconnection with Last-Event-ID replays missed events."""
        bus = InProcessEventBus()
        data = SSEEventData(incident_id=uuid.uuid4(), stage="test", state="active")
        await bus.emit("test.event", data)
        await bus.emit("test.event", data)
        await bus.emit("test.event", data)

        queue = await bus.subscribe(last_event_id=1)
        gen = _event_generator(queue, bus)

        line1 = await gen.__anext__()
        line2 = await gen.__anext__()
        assert "id: 2\n" in line1
        assert "id: 3\n" in line2

        await gen.aclose()


class TestSSEEndpoint:
    """Integration tests for SSE endpoint (non-streaming aspects)."""

    async def test_endpoint_requires_auth(self, async_client):
        """With auth enabled, endpoint should require token."""
        with patch.dict(os.environ, {"AUTH_DISABLED": ""}):
            resp = await async_client.get("/api/v1/events/stream")
            assert resp.status_code == 401
