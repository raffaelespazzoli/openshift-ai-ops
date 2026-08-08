"""Unit tests for priority queue scoring, cancellation, and TTL logic.

Tests cover:
- Priority scoring: critical > warning > info at same recency
- Recency: newer events score higher than older events at same severity
- Combined: critical+old vs warning+new ordering
- Parallelism cap: returns None when at capacity
- TTL expiry: items past TTL are identified
- Cancellation: only queued items are cancelled, not processing
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.clients.alertmanager import (
    AlertManagerClient,
    AlertManagerUnreachableError,
)
from src.config.queue_settings import PriorityWeights, QueueSettings, reset_queue_settings
from src.pipeline.priority_queue import calculate_priority_score


@pytest.fixture(autouse=True)
def _reset_settings():
    """Reset cached settings between tests."""
    reset_queue_settings()
    yield
    reset_queue_settings()


class TestPriorityScoring:
    """Priority scoring: severity_weight × recency_factor."""

    def test_critical_outranks_warning_and_info(self):
        """Critical severity should always score higher than warning and info at same time."""
        now = datetime.now(timezone.utc)
        with patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings:
            mock_settings.return_value = QueueSettings()
            score_critical = calculate_priority_score("critical", now)
            score_warning = calculate_priority_score("warning", now)
            score_info = calculate_priority_score("info", now)

        assert score_critical > score_warning > score_info

    def test_warning_outranks_info(self):
        """Warning severity should score higher than info at same time."""
        now = datetime.now(timezone.utc)
        with patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings:
            mock_settings.return_value = QueueSettings()
            score_warning = calculate_priority_score("warning", now)
            score_info = calculate_priority_score("info", now)

        assert score_warning > score_info

    def test_newer_events_score_higher_same_severity(self):
        """More recent events should have higher priority than older ones at same severity."""
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        with patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings:
            mock_settings.return_value = QueueSettings()
            score_new = calculate_priority_score("warning", now)
            score_old = calculate_priority_score("warning", one_hour_ago)

        assert score_new > score_old

    def test_critical_old_beats_warning_new(self):
        """A 30-minute-old critical should beat a brand-new warning."""
        now = datetime.now(timezone.utc)
        thirty_min_ago = now - timedelta(minutes=30)

        with patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings:
            mock_settings.return_value = QueueSettings()
            score_critical_old = calculate_priority_score("critical", thirty_min_ago)
            score_warning_new = calculate_priority_score("warning", now)

        assert score_critical_old > score_warning_new

    def test_recency_decays_over_hours(self):
        """Recency factor should decay: 1h old ≈ 0.5 recency, 2h old ≈ 0.33."""
        now = datetime.now(timezone.utc)
        with patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings:
            mock_settings.return_value = QueueSettings()
            score_now = calculate_priority_score("critical", now)
            score_1h = calculate_priority_score("critical", now - timedelta(hours=1))
            score_2h = calculate_priority_score("critical", now - timedelta(hours=2))

        assert score_now > score_1h > score_2h
        assert score_1h == pytest.approx(score_now / 2.0, rel=0.01)

    def test_unknown_severity_defaults_to_warning_weight(self):
        """Unknown severity should use warning weight as default."""
        now = datetime.now(timezone.utc)
        with patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings:
            mock_settings.return_value = QueueSettings()
            score_unknown = calculate_priority_score("unknown_sev", now)
            score_warning = calculate_priority_score("warning", now)

        assert score_unknown == pytest.approx(score_warning, rel=1e-4)

    def test_configurable_weights(self):
        """Priority weights should be configurable via settings."""
        now = datetime.now(timezone.utc)
        custom_weights = PriorityWeights(critical=200, warning=100, info=20)
        custom_settings = QueueSettings(priority_weights=custom_weights)

        with patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings:
            mock_settings.return_value = custom_settings
            score = calculate_priority_score("critical", now)

        assert score == pytest.approx(200.0, rel=0.01)


class TestCancellationLogic:
    """Cancellation behavior per AD-16."""

    @pytest.mark.asyncio
    async def test_cancel_queued_item_succeeds(self):
        """Cancellation of a queued item should succeed."""
        rce_id = uuid.uuid4()
        incident_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "id": uuid.uuid4(),
            "incident_id": incident_id,
            "root_cause_event_id": rce_id,
            "status": "queued",
        }
        mock_conn.fetchval.return_value = "queued"
        mock_conn.execute.return_value = None

        with patch("src.pipeline.priority_queue.cancel_queued_item", new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = {
                "id": uuid.uuid4(),
                "incident_id": incident_id,
                "root_cause_event_id": rce_id,
            }
            from src.pipeline.priority_queue import cancel_queued_rce
            result = await cancel_queued_rce(mock_conn, rce_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_processing_item_fails(self):
        """Cancellation of a processing item should return False (AD-16)."""
        rce_id = uuid.uuid4()
        mock_conn = AsyncMock()

        with patch("src.pipeline.priority_queue.cancel_queued_item", new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = None
            from src.pipeline.priority_queue import cancel_queued_rce
            result = await cancel_queued_rce(mock_conn, rce_id)

        assert result is False


class _FakeAMClient(AlertManagerClient):
    """Test helper that returns a canned response."""

    def __init__(self, *, firing: bool):
        self._firing = firing

    async def check_alerts_firing(self, fingerprints: list[str]) -> bool:
        return self._firing


class _UnreachableAMClient(AlertManagerClient):
    """Test helper that always raises unreachable."""

    async def check_alerts_firing(self, fingerprints: list[str]) -> bool:
        raise AlertManagerUnreachableError("test")


def _make_expired_item(
    item_id=None, rce_id=None, incident_id=None,
):
    return {
        "id": item_id or uuid.uuid4(),
        "root_cause_event_id": rce_id or uuid.uuid4(),
        "incident_id": incident_id or uuid.uuid4(),
        "priority_score": 100.0,
        "severity": "critical",
        "enqueued_at": datetime.now(timezone.utc) - timedelta(hours=2),
        "ttl_expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
    }


class TestTTLExpiry:
    """TTL verification logic."""

    @pytest.mark.asyncio
    async def test_ttl_expired_alert_not_firing_gets_cancelled(self):
        """TTL-expired items where AlertManager confirms not firing should be cancelled."""
        item_id = uuid.uuid4()
        rce_id = uuid.uuid4()
        incident_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [
            "queued",
        ]
        mock_conn.execute.return_value = None

        with (
            patch("src.pipeline.priority_queue.get_ttl_expired_items", new_callable=AsyncMock) as mock_expired,
            patch("src.pipeline.priority_queue.cancel_queued_item", new_callable=AsyncMock) as mock_cancel,
            patch("src.pipeline.priority_queue.get_rce_alert_fingerprints", new_callable=AsyncMock) as mock_fps,
            patch("src.pipeline.priority_queue.get_rce_incident_ids", new_callable=AsyncMock) as mock_siblings,
        ):
            mock_expired.return_value = [
                _make_expired_item(item_id=item_id, rce_id=rce_id, incident_id=incident_id),
            ]
            mock_fps.return_value = ["fp-abc"]
            mock_cancel.return_value = {"id": item_id, "incident_id": incident_id, "root_cause_event_id": rce_id}
            mock_siblings.return_value = [incident_id]

            from src.pipeline.priority_queue import check_ttl_expired_items
            cancelled = await check_ttl_expired_items(
                mock_conn, alertmanager_client=_FakeAMClient(firing=False),
            )

        assert len(cancelled) == 1
        mock_cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_ttl_expired_alert_still_firing_extends_ttl(self):
        """TTL-expired items where AlertManager says still firing get TTL extended."""
        item_id = uuid.uuid4()
        rce_id = uuid.uuid4()
        incident_id = uuid.uuid4()

        mock_conn = AsyncMock()

        with (
            patch("src.pipeline.priority_queue.get_ttl_expired_items", new_callable=AsyncMock) as mock_expired,
            patch("src.pipeline.priority_queue.get_rce_alert_fingerprints", new_callable=AsyncMock) as mock_fps,
            patch("src.pipeline.priority_queue.extend_ttl", new_callable=AsyncMock) as mock_extend,
            patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings,
        ):
            mock_settings.return_value = QueueSettings()
            mock_expired.return_value = [
                _make_expired_item(item_id=item_id, rce_id=rce_id, incident_id=incident_id),
            ]
            mock_fps.return_value = ["fp-abc"]

            from src.pipeline.priority_queue import check_ttl_expired_items
            cancelled = await check_ttl_expired_items(
                mock_conn, alertmanager_client=_FakeAMClient(firing=True),
            )

        assert len(cancelled) == 0
        mock_extend.assert_called_once()

    @pytest.mark.asyncio
    async def test_ttl_alertmanager_unreachable_keeps_item_in_queue(self):
        """When AlertManager is unreachable, items stay in the queue (fail-safe)."""
        item_id = uuid.uuid4()
        rce_id = uuid.uuid4()
        incident_id = uuid.uuid4()

        mock_conn = AsyncMock()

        with (
            patch("src.pipeline.priority_queue.get_ttl_expired_items", new_callable=AsyncMock) as mock_expired,
            patch("src.pipeline.priority_queue.get_rce_alert_fingerprints", new_callable=AsyncMock) as mock_fps,
            patch("src.pipeline.priority_queue.extend_ttl", new_callable=AsyncMock) as mock_extend,
            patch("src.pipeline.priority_queue.cancel_queued_item", new_callable=AsyncMock) as mock_cancel,
            patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings,
        ):
            mock_settings.return_value = QueueSettings()
            mock_expired.return_value = [
                _make_expired_item(item_id=item_id, rce_id=rce_id, incident_id=incident_id),
            ]
            mock_fps.return_value = ["fp-abc"]

            from src.pipeline.priority_queue import check_ttl_expired_items
            cancelled = await check_ttl_expired_items(
                mock_conn, alertmanager_client=_UnreachableAMClient(),
            )

        assert len(cancelled) == 0
        mock_extend.assert_called_once()
        mock_cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_ttl_stub_client_default_is_fail_safe(self):
        """Default stub client triggers fail-safe (extend TTL, no cancel)."""
        item_id = uuid.uuid4()

        mock_conn = AsyncMock()

        with (
            patch("src.pipeline.priority_queue.get_ttl_expired_items", new_callable=AsyncMock) as mock_expired,
            patch("src.pipeline.priority_queue.get_rce_alert_fingerprints", new_callable=AsyncMock) as mock_fps,
            patch("src.pipeline.priority_queue.extend_ttl", new_callable=AsyncMock) as mock_extend,
            patch("src.pipeline.priority_queue.cancel_queued_item", new_callable=AsyncMock) as mock_cancel,
            patch("src.pipeline.priority_queue.get_queue_settings") as mock_settings,
        ):
            mock_settings.return_value = QueueSettings()
            mock_expired.return_value = [_make_expired_item(item_id=item_id)]
            mock_fps.return_value = ["fp-xyz"]

            from src.pipeline.priority_queue import check_ttl_expired_items
            cancelled = await check_ttl_expired_items(mock_conn)

        assert len(cancelled) == 0
        mock_extend.assert_called_once()
        mock_cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_ttl_dequeue_race_skips_incident_transition(self):
        """If cancel_queued_item returns None (already dequeued), skip incident transitions."""
        item_id = uuid.uuid4()
        rce_id = uuid.uuid4()
        incident_id = uuid.uuid4()

        mock_conn = AsyncMock()

        with (
            patch("src.pipeline.priority_queue.get_ttl_expired_items", new_callable=AsyncMock) as mock_expired,
            patch("src.pipeline.priority_queue.cancel_queued_item", new_callable=AsyncMock) as mock_cancel,
            patch("src.pipeline.priority_queue.get_rce_alert_fingerprints", new_callable=AsyncMock) as mock_fps,
            patch("src.pipeline.priority_queue.get_rce_incident_ids", new_callable=AsyncMock) as mock_siblings,
        ):
            mock_expired.return_value = [
                _make_expired_item(item_id=item_id, rce_id=rce_id, incident_id=incident_id),
            ]
            mock_fps.return_value = ["fp-abc"]
            mock_cancel.return_value = None  # already dequeued

            from src.pipeline.priority_queue import check_ttl_expired_items
            cancelled = await check_ttl_expired_items(
                mock_conn, alertmanager_client=_FakeAMClient(firing=False),
            )

        assert len(cancelled) == 0
        mock_cancel.assert_called_once()
        mock_siblings.assert_not_called()
        mock_conn.fetchval.assert_not_called()


class TestPriorityWeights:
    """PriorityWeights dataclass behavior."""

    def test_get_known_severity(self):
        weights = PriorityWeights()
        assert weights.get("critical") == 100
        assert weights.get("warning") == 50
        assert weights.get("info") == 10

    def test_get_unknown_severity_defaults_to_warning(self):
        weights = PriorityWeights()
        assert weights.get("something_else") == 50

    def test_custom_weights(self):
        weights = PriorityWeights(critical=200, warning=75, info=25)
        assert weights.get("critical") == 200
        assert weights.get("warning") == 75
        assert weights.get("info") == 25
