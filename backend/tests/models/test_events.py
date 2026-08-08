"""Unit tests for SSE event models and event bus interface."""

import uuid
from datetime import datetime, timezone

import pytest

from src.models.events import BusEvent, EventNames, SSEEventData


pytestmark = pytest.mark.unit


class TestSSEEventData:
    def test_required_fields(self):
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        assert data.incident_id is not None
        assert data.stage == "correlating"
        assert data.state == "active"
        assert data.timestamp is not None
        assert data.payload == {}

    def test_all_fields(self):
        inc_id = uuid.uuid4()
        ts = datetime(2026, 8, 8, 14, 30, 0, tzinfo=timezone.utc)
        data = SSEEventData(
            incident_id=inc_id,
            stage="diagnosing",
            state="in_progress",
            timestamp=ts,
            payload={"key": "value"},
        )
        assert data.incident_id == inc_id
        assert data.stage == "diagnosing"
        assert data.state == "in_progress"
        assert data.timestamp == ts
        assert data.payload == {"key": "value"}

    def test_serialization_json(self):
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        json_str = data.model_dump_json()
        assert "incident_id" in json_str
        assert "timestamp" in json_str
        assert "stage" in json_str
        assert "state" in json_str

    def test_stage_and_state_required(self):
        with pytest.raises(Exception):
            SSEEventData(incident_id=uuid.uuid4())


class TestBusEvent:
    def test_bus_event_structure(self):
        data = SSEEventData(incident_id=uuid.uuid4(), stage="correlating", state="active")
        event = BusEvent(event_name="incident.created", data=data)
        assert event.event_name == "incident.created"
        assert event.data == data


class TestEventNames:
    def test_dot_notation_format(self):
        assert "." in EventNames.INCIDENT_CREATED
        assert "." in EventNames.INCIDENT_STAGE_CHANGED
        assert "." in EventNames.INCIDENT_STATE_CHANGED
        assert "." in EventNames.INCIDENT_RESOLVED

    def test_names_defined(self):
        assert EventNames.INCIDENT_CREATED == "incident.created"
        assert EventNames.INCIDENT_STAGE_CHANGED == "incident.stage_changed"
        assert EventNames.INCIDENT_STATE_CHANGED == "incident.state_changed"
        assert EventNames.INCIDENT_RESOLVED == "incident.resolved"
