"""Unit tests for AlertManager webhook payload models."""

import pytest
from pydantic import ValidationError

from src.models.webhook import AlertManagerAlert, AlertManagerWebhook


def _valid_alert(**overrides) -> dict:
    base = {
        "status": "firing",
        "labels": {"alertname": "NodeMemoryPressure", "severity": "warning"},
        "annotations": {"summary": "Node under memory pressure"},
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


class TestAlertManagerAlert:
    @pytest.mark.unit
    def test_valid_firing_alert_parses(self):
        alert = AlertManagerAlert(**_valid_alert())
        assert alert.status == "firing"
        assert alert.fingerprint == "abc123def456"
        assert alert.labels["alertname"] == "NodeMemoryPressure"

    @pytest.mark.unit
    def test_valid_resolved_alert_parses(self):
        alert = AlertManagerAlert(**_valid_alert(status="resolved"))
        assert alert.status == "resolved"

    @pytest.mark.unit
    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            AlertManagerAlert(**_valid_alert(status="pending"))

    @pytest.mark.unit
    def test_empty_fingerprint_rejected(self):
        with pytest.raises(ValidationError):
            AlertManagerAlert(**_valid_alert(fingerprint="  "))

    @pytest.mark.unit
    def test_non_hex_fingerprint_rejected(self):
        with pytest.raises(ValidationError):
            AlertManagerAlert(**_valid_alert(fingerprint="not-hex-xyz!"))

    @pytest.mark.unit
    def test_missing_fingerprint_rejected(self):
        data = _valid_alert()
        del data["fingerprint"]
        with pytest.raises(ValidationError):
            AlertManagerAlert(**data)

    @pytest.mark.unit
    def test_missing_labels_rejected(self):
        data = _valid_alert()
        del data["labels"]
        with pytest.raises(ValidationError):
            AlertManagerAlert(**data)

    @pytest.mark.unit
    def test_missing_annotations_rejected(self):
        data = _valid_alert()
        del data["annotations"]
        with pytest.raises(ValidationError):
            AlertManagerAlert(**data)

    @pytest.mark.unit
    def test_missing_starts_at_rejected(self):
        data = _valid_alert()
        del data["startsAt"]
        with pytest.raises(ValidationError):
            AlertManagerAlert(**data)


class TestAlertManagerWebhook:
    @pytest.mark.unit
    def test_valid_webhook_parses(self):
        webhook = AlertManagerWebhook(**_valid_webhook())
        assert webhook.version == "4"
        assert webhook.status == "firing"
        assert len(webhook.alerts) == 1
        assert webhook.alerts[0].fingerprint == "abc123def456"

    @pytest.mark.unit
    def test_wrong_version_rejected(self):
        with pytest.raises(ValidationError):
            AlertManagerWebhook(**_valid_webhook(version="3"))

    @pytest.mark.unit
    def test_empty_alerts_rejected(self):
        with pytest.raises(ValidationError):
            AlertManagerWebhook(**_valid_webhook(alerts=[]))

    @pytest.mark.unit
    def test_missing_required_fields_rejected(self):
        for field in (
            "version", "groupKey", "status", "receiver", "externalURL",
            "groupLabels", "commonLabels", "commonAnnotations",
        ):
            data = _valid_webhook()
            del data[field]
            with pytest.raises(ValidationError):
                AlertManagerWebhook(**data)

    @pytest.mark.unit
    def test_mixed_status_payload(self):
        alerts = [
            _valid_alert(status="firing", fingerprint="aaa"),
            _valid_alert(status="resolved", fingerprint="bbb"),
        ]
        webhook = AlertManagerWebhook(**_valid_webhook(alerts=alerts))
        assert len(webhook.alerts) == 2
        assert webhook.alerts[0].status == "firing"
        assert webhook.alerts[1].status == "resolved"

    @pytest.mark.unit
    def test_default_truncated_alerts(self):
        data = _valid_webhook()
        del data["truncatedAlerts"]
        webhook = AlertManagerWebhook(**data)
        assert webhook.truncated_alerts == 0

    @pytest.mark.unit
    def test_severity_derivation_from_labels(self):
        alert = AlertManagerAlert(**_valid_alert())
        severity = alert.labels.get("severity", "warning")
        assert severity == "warning"

    @pytest.mark.unit
    def test_severity_default_when_missing(self):
        alert = AlertManagerAlert(**_valid_alert(labels={"alertname": "Test"}))
        severity = alert.labels.get("severity", "warning")
        assert severity == "warning"
