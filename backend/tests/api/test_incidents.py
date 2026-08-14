"""API integration tests for incident endpoints."""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import asyncpg
import pytest

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _auth_disabled():
    """Disable auth for all tests in this module."""
    with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
        yield


@pytest.fixture
async def seeded_incident(db_url, run_migrations):
    """Create a test incident with alerts via a committed connection."""
    conn = await asyncpg.connect(db_url)
    try:
        incident_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        await conn.execute(
            """
            INSERT INTO incidents (id, state, severity, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            incident_id, "received", "critical", now, now,
        )
        alert_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO alerts (id, incident_id, fingerprint, labels, annotations, status, fired_at, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
            """,
            alert_id, incident_id, "fp-abc123",
            '{"alertname": "HighCPU"}', '{"summary": "CPU high"}',
            "firing", now, now,
        )
        yield incident_id
    finally:
        await conn.execute("DELETE FROM alerts WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM incidents WHERE id = $1", incident_id)
        await conn.close()


class TestListIncidents:
    async def test_returns_envelope_format(self, async_client):
        resp = await async_client.get("/api/v1/incidents")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "timestamp" in body["meta"]
        assert "request_id" in body["meta"]

    async def test_pagination_metadata(self, async_client):
        resp = await async_client.get("/api/v1/incidents?page=1&page_size=10")
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["page"] == 1
        assert meta["page_size"] == 10
        assert "total" in meta

    async def test_filter_by_status(self, async_client, seeded_incident):
        resp = await async_client.get("/api/v1/incidents?status=received")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(d["state"] == "received" for d in data)

    async def test_filter_by_severity(self, async_client, seeded_incident):
        resp = await async_client.get("/api/v1/incidents?severity=critical")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(d["severity"] == "critical" for d in data)

    async def test_active_status_maps_to_non_terminal(self, async_client, seeded_incident):
        resp = await async_client.get("/api/v1/incidents?status=active")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1

    async def test_pagination_limits_results(self, async_client, seeded_incident):
        resp = await async_client.get("/api/v1/incidents?page=1&page_size=1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) <= 1

    async def test_page_size_max_200(self, async_client):
        resp = await async_client.get("/api/v1/incidents?page_size=300")
        assert resp.status_code == 422


class TestGetIncidentDetail:
    async def test_returns_full_detail(self, async_client, seeded_incident):
        resp = await async_client.get(f"/api/v1/incidents/{seeded_incident}")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        assert data["id"] == str(seeded_incident)
        assert data["state"] == "received"
        assert data["severity"] == "critical"
        assert "alerts" in data
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["fingerprint"] == "fp-abc123"

    async def test_not_found_returns_404_error_envelope(self, async_client):
        fake_id = uuid.uuid4()
        resp = await async_client.get(f"/api/v1/incidents/{fake_id}")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "Incident not found"
        assert body["code"] == "NOT_FOUND"
        assert "detail" in body

    async def test_invalid_uuid_returns_422(self, async_client):
        resp = await async_client.get("/api/v1/incidents/not-a-uuid")
        assert resp.status_code == 422

    async def test_detail_includes_fast_path_fields(self, async_client, seeded_incident):
        """Incident detail includes fast_path, fast_path_similarity, fast_path_case_record_id."""
        resp = await async_client.get(f"/api/v1/incidents/{seeded_incident}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "fast_path" in data
        assert data["fast_path"] is False
        assert data["fast_path_similarity"] is None
        assert data["fast_path_case_record_id"] is None


class TestListIncidentsFastPath:
    async def test_list_includes_fast_path_flag(self, async_client, seeded_incident):
        """Incident list items include fast_path flag."""
        resp = await async_client.get("/api/v1/incidents?status=received")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        for item in data:
            assert "fast_path" in item
            assert item["fast_path"] is False
