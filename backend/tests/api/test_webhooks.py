"""Tests for the AlertManager webhook endpoint.

Covers:
- Task 5 (unit): 200 for valid, 400 for invalid, structured error format
- Task 6 (db integration): firing webhook creates incident + alert rows, resolved handling
- Task 7 (api): concurrent response time validation (500ms SLA)
"""

from __future__ import annotations

import asyncio
import json

import pytest


def _valid_alert(**overrides) -> dict:
    base = {
        "status": "firing",
        "labels": {"alertname": "NodeMemoryPressure", "node": "worker-1", "severity": "warning"},
        "annotations": {"summary": "Node worker-1 is under memory pressure"},
        "startsAt": "2026-08-08T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "http://prometheus:9090/graph",
        "fingerprint": "abc123def456",
    }
    base.update(overrides)
    return base


def _valid_webhook(**overrides) -> dict:
    base = {
        "version": "4",
        "groupKey": '{alertname="NodeMemoryPressure"}',
        "status": "firing",
        "receiver": "webhook",
        "alerts": [_valid_alert()],
        "groupLabels": {"alertname": "NodeMemoryPressure"},
        "commonLabels": {"alertname": "NodeMemoryPressure", "severity": "warning"},
        "commonAnnotations": {"summary": "Node under memory pressure"},
        "externalURL": "http://alertmanager:9093",
        "truncatedAlerts": 0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Task 5: API unit tests — endpoint returns correct status codes
# ---------------------------------------------------------------------------


class TestWebhookEndpointUnit:
    @pytest.mark.api
    async def test_valid_firing_payload_returns_200(self, async_client):
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=_valid_webhook(alerts=[_valid_alert(fingerprint="a00f1e000200")]),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"

    @pytest.mark.api
    async def test_valid_resolved_payload_returns_200(self, async_client):
        payload = _valid_webhook(
            status="resolved",
            alerts=[_valid_alert(status="resolved", fingerprint="b00e50000200")],
        )
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

    @pytest.mark.api
    async def test_malformed_payload_returns_400(self, async_client):
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json={"bad": "payload"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Invalid webhook payload"
        assert data["code"] == "INVALID_PAYLOAD"
        assert "validation_errors" in data["detail"]

    @pytest.mark.api
    async def test_missing_version_returns_400(self, async_client):
        payload = _valid_webhook()
        del payload["version"]
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=payload,
        )
        assert response.status_code == 400

    @pytest.mark.api
    async def test_wrong_version_returns_400(self, async_client):
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=_valid_webhook(version="3"),
        )
        assert response.status_code == 400

    @pytest.mark.api
    async def test_empty_alerts_returns_400(self, async_client):
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=_valid_webhook(alerts=[]),
        )
        assert response.status_code == 400

    @pytest.mark.api
    async def test_invalid_json_returns_400(self, async_client):
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            content=b"not json at all",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "INVALID_PAYLOAD"

    @pytest.mark.api
    async def test_error_response_structure(self, async_client):
        """Error response must match {error, code, detail} format with sanitized errors."""
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json={"version": "4"},
        )
        assert response.status_code == 400
        data = response.json()
        assert set(data.keys()) == {"error", "code", "detail"}
        errors = data["detail"]["validation_errors"]
        assert isinstance(errors, list)
        for err in errors:
            assert set(err.keys()) == {"field", "message"}
            assert "type" not in err

    @pytest.mark.api
    async def test_mixed_status_payload_accepted(self, async_client):
        alerts = [
            _valid_alert(status="firing", fingerprint="c00f1ed00001"),
            _valid_alert(status="resolved", fingerprint="c00e50d00002"),
        ]
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=_valid_webhook(alerts=alerts),
        )
        assert response.status_code == 200

    @pytest.mark.api
    async def test_request_id_header_present(self, async_client):
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=_valid_webhook(alerts=[_valid_alert(fingerprint="d00e01d00003")]),
        )
        assert "x-request-id" in response.headers


# ---------------------------------------------------------------------------
# Task 6: DB integration tests — verify persistence
# ---------------------------------------------------------------------------


class TestWebhookPersistence:
    @pytest.mark.db
    async def test_firing_webhook_creates_incident_row(self, async_client, db_conn):
        """A firing webhook should create an incident in received state."""
        fp = "db01c000000a"
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=_valid_webhook(alerts=[_valid_alert(fingerprint=fp)]),
        )
        assert response.status_code == 200

        await asyncio.sleep(0.5)

        rows = await db_conn.fetch(
            "SELECT i.* FROM incidents i JOIN alerts a ON a.incident_id = i.id WHERE a.fingerprint = $1",
            fp,
        )
        assert len(rows) >= 1
        assert rows[0]["state"] == "received"

    @pytest.mark.db
    async def test_multiple_firing_alerts_create_separate_incidents(self, async_client, db_conn):
        """Each firing alert in a batch must create its own incident."""
        fp1 = "db0a1e0000a1"
        fp2 = "db0a1e0000a2"
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=_valid_webhook(alerts=[
                _valid_alert(fingerprint=fp1),
                _valid_alert(fingerprint=fp2),
            ]),
        )
        assert response.status_code == 200

        await asyncio.sleep(0.5)

        for fp in (fp1, fp2):
            rows = await db_conn.fetch(
                "SELECT i.id FROM incidents i JOIN alerts a ON a.incident_id = i.id WHERE a.fingerprint = $1",
                fp,
            )
            assert len(rows) == 1

        inc1 = await db_conn.fetchval(
            "SELECT i.id FROM incidents i JOIN alerts a ON a.incident_id = i.id WHERE a.fingerprint = $1",
            fp1,
        )
        inc2 = await db_conn.fetchval(
            "SELECT i.id FROM incidents i JOIN alerts a ON a.incident_id = i.id WHERE a.fingerprint = $1",
            fp2,
        )
        assert inc1 != inc2

    @pytest.mark.db
    async def test_firing_webhook_creates_alert_row(self, async_client, db_conn):
        """A firing webhook should persist an alert with correct fields."""
        fp = "db0a1e000002"
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=_valid_webhook(alerts=[_valid_alert(fingerprint=fp)]),
        )
        assert response.status_code == 200

        await asyncio.sleep(0.5)

        rows = await db_conn.fetch(
            "SELECT * FROM alerts WHERE fingerprint = $1", fp
        )
        assert len(rows) >= 1
        alert = rows[0]
        assert alert["fingerprint"] == fp
        assert alert["status"] == "firing"
        labels = alert["labels"] if isinstance(alert["labels"], dict) else json.loads(alert["labels"])
        annotations = alert["annotations"] if isinstance(alert["annotations"], dict) else json.loads(alert["annotations"])
        assert labels["alertname"] == "NodeMemoryPressure"
        assert "summary" in annotations
        assert alert["fired_at"] is not None
        assert alert["incident_id"] is not None

    @pytest.mark.db
    async def test_incident_severity_persisted(self, async_client, db_conn):
        """Incident severity should be derived from alert labels."""
        fp = "db05e9000003"
        payload = _valid_webhook(
            alerts=[_valid_alert(
                labels={"alertname": "Crash", "severity": "critical"},
                fingerprint=fp,
            )],
        )
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=payload,
        )
        assert response.status_code == 200

        await asyncio.sleep(0.5)

        rows = await db_conn.fetch(
            "SELECT i.* FROM incidents i JOIN alerts a ON a.incident_id = i.id WHERE a.fingerprint = $1",
            fp,
        )
        assert len(rows) >= 1
        assert rows[0]["severity"] == "critical"

    @pytest.mark.db
    async def test_resolved_webhook_updates_alert(self, async_client, db_conn):
        """Resolved alert should update existing firing alert's status."""
        fp = "ae501e00fe50"
        firing_payload = _valid_webhook(
            alerts=[_valid_alert(fingerprint=fp)],
        )
        await async_client.post("/api/v1/webhooks/alertmanager", json=firing_payload)
        await asyncio.sleep(0.5)

        resolved_payload = _valid_webhook(
            status="resolved",
            alerts=[_valid_alert(
                status="resolved",
                fingerprint=fp,
                endsAt="2026-08-08T11:00:00Z",
            )],
        )
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=resolved_payload,
        )
        assert response.status_code == 200
        await asyncio.sleep(0.5)

        rows = await db_conn.fetch(
            "SELECT * FROM alerts WHERE fingerprint = $1 ORDER BY created_at DESC",
            fp,
        )
        assert len(rows) >= 1
        resolved_row = [r for r in rows if r["status"] == "resolved"]
        assert len(resolved_row) >= 1
        assert resolved_row[0]["resolved_at"] is not None

    @pytest.mark.db
    async def test_resolved_without_matching_firing_is_skipped(self, async_client, db_conn):
        """Resolved alert with no matching firing alert should not error."""
        fp = "00fa1ce00000"
        payload = _valid_webhook(
            status="resolved",
            alerts=[_valid_alert(status="resolved", fingerprint=fp)],
        )
        response = await async_client.post(
            "/api/v1/webhooks/alertmanager",
            json=payload,
        )
        assert response.status_code == 200
        await asyncio.sleep(0.5)

        rows = await db_conn.fetch(
            "SELECT * FROM alerts WHERE fingerprint = $1", fp
        )
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# Task 7: Response time validation — 500ms SLA under concurrent load
# ---------------------------------------------------------------------------


class TestWebhookPerformance:
    @pytest.mark.api
    async def test_concurrent_webhooks_within_500ms(self, async_client):
        """10 concurrent webhooks should all respond within 500ms."""

        async def send_webhook(idx: int):
            payload = _valid_webhook(
                alerts=[_valid_alert(fingerprint=f"e0e0e5{idx:06x}")],
            )
            loop = asyncio.get_event_loop()
            start = loop.time()
            response = await async_client.post(
                "/api/v1/webhooks/alertmanager",
                json=payload,
            )
            elapsed_ms = (loop.time() - start) * 1000
            return response.status_code, elapsed_ms

        results = await asyncio.gather(*(send_webhook(i) for i in range(10)))

        for status_code, elapsed_ms in results:
            assert status_code == 200, f"Expected 200, got {status_code}"
            assert elapsed_ms < 500, f"Response took {elapsed_ms:.1f}ms, exceeds 500ms SLA"
