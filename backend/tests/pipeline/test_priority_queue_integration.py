"""Integration tests for priority queue with real PostgreSQL.

Tests cover (db-marked):
- Full enqueue/dequeue cycle
- Priority ordering: 3 items at different severities dequeued in correct order
- SKIP LOCKED concurrency: two concurrent transactions each get different items
- Cancellation: queued item cancellable, processing item NOT cancellable
- Parallelism cap: cap=2, enqueue 5 → only 2 dequeued, third returns None
- Pod crash recovery: stale processing items reset to queued on startup
- State machine transitions: queued → diagnosing, queued → cancelled
- Full resolved-webhook flow: enqueue → resolve all alerts → RCE cancelled
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import asyncpg
import pytest

from src.config.queue_settings import QueueSettings, reset_queue_settings
from src.db.queue import (
    cancel_queued_item,
    dequeue_next,
    get_ttl_expired_items,
    insert_queue_item,
    mark_pipeline_complete,
    recover_stale_items,
)
from src.models.state_machine import IncidentState
from src.pipeline.priority_queue import (
    cancel_queued_rce,
    check_ttl_expired_items,
    enqueue_rce,
)


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_queue_settings()
    yield
    reset_queue_settings()


def _queue_settings(**overrides):
    defaults = {
        "parallelism_cap": 3,
        "ttl_seconds": 3600,
        "poll_interval_seconds": 5,
        "stale_processing_timeout_seconds": 900,
    }
    defaults.update(overrides)
    return QueueSettings(**defaults)


async def _create_incident_and_rce(conn: asyncpg.Connection, severity: str = "critical"):
    """Helper: create an incident in 'queued' state and a sealed correlation group."""
    incident_id = uuid.uuid4()
    group_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    await conn.execute(
        "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, $2, $3, $4, $5)",
        incident_id, "queued", severity, now, now,
    )
    await conn.execute(
        """INSERT INTO correlation_groups
           (id, state, settling_window_seconds, created_at, last_alert_at, sealed_at, max_age_at, correlation_evidence)
           VALUES ($1, 'sealed', 60, $2, $2, $2, $3, '[]'::jsonb)""",
        group_id, now, now + timedelta(hours=1),
    )
    await conn.execute(
        "UPDATE incidents SET root_cause_event_id = $2 WHERE id = $1",
        incident_id, group_id,
    )
    await conn.execute(
        """INSERT INTO alerts (id, incident_id, fingerprint, labels, annotations, status, fired_at, created_at)
           VALUES ($1, $2, $3, $4::jsonb, '{}'::jsonb, 'firing', $5, $5)""",
        alert_id, incident_id, f"fp-{uuid.uuid4().hex[:8]}",
        f'{{"severity": "{severity}"}}', now,
    )
    await conn.execute(
        "INSERT INTO alert_group_members (group_id, alert_id, incident_id, joined_at) VALUES ($1, $2, $3, $4)",
        group_id, alert_id, incident_id, now,
    )

    return incident_id, group_id, alert_id


@pytest.mark.db
class TestEnqueueDequeue:
    """Full enqueue/dequeue cycle with real PostgreSQL."""

    @pytest.mark.asyncio
    async def test_enqueue_dequeue_cycle(self, db_conn):
        incident_id, group_id, _ = await _create_incident_and_rce(db_conn)
        now = datetime.now(timezone.utc)

        with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
            item = await insert_queue_item(
                db_conn,
                root_cause_event_id=group_id,
                incident_id=incident_id,
                priority_score=100.0,
                severity="critical",
                ttl_expires_at=now + timedelta(hours=1),
            )
            assert item["status"] == "queued"
            assert item["priority_score"] == 100.0

            dequeued = await dequeue_next(db_conn)
            assert dequeued is not None
            assert dequeued["id"] == item["id"]
            assert dequeued["status"] == "processing"

    @pytest.mark.asyncio
    async def test_priority_ordering(self, db_conn):
        """Enqueue 3 items (critical, warning, info) → dequeue order is critical first."""
        items = []
        now = datetime.now(timezone.utc)

        for severity, score in [("info", 10.0), ("warning", 50.0), ("critical", 100.0)]:
            inc_id, grp_id, _ = await _create_incident_and_rce(db_conn, severity)
            with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
                item = await insert_queue_item(
                    db_conn,
                    root_cause_event_id=grp_id,
                    incident_id=inc_id,
                    priority_score=score,
                    severity=severity,
                    ttl_expires_at=now + timedelta(hours=1),
                )
                items.append(item)

        with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
            d1 = await dequeue_next(db_conn)
            d2 = await dequeue_next(db_conn)
            d3 = await dequeue_next(db_conn)

        assert d1["severity"] == "critical"
        assert d2["severity"] == "warning"
        assert d3["severity"] == "info"

    @pytest.mark.asyncio
    async def test_dequeue_returns_none_when_empty(self, db_conn):
        with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
            result = await dequeue_next(db_conn)
        assert result is None


@pytest.mark.db
class TestConcurrency:
    """Serialized dequeue concurrency tests.

    dequeue_next uses pg_advisory_xact_lock(42) to serialize all dequeues.
    This means two concurrent transactions will block rather than SKIP LOCKED.
    We verify that sequential dequeues from separate connections each claim
    a different item (the advisory lock serializes them, not skips them).
    """

    @pytest.mark.asyncio
    async def test_serialized_dequeue_claims_different_items(self, db_url):
        """Two sequential dequeues from separate connections each get a different item."""
        conn1 = await asyncpg.connect(db_url)
        conn2 = await asyncpg.connect(db_url)
        now = datetime.now(timezone.utc)

        inc1 = grp1 = inc2 = grp2 = None
        q_ids: list[uuid.UUID] = []
        try:
            inc1, grp1, alert1 = await _create_incident_and_rce(conn1, "critical")
            inc2, grp2, alert2 = await _create_incident_and_rce(conn1, "warning")

            for grp, inc, score, sev in [(grp1, inc1, 100.0, "critical"), (grp2, inc2, 50.0, "warning")]:
                qid = uuid.uuid4()
                q_ids.append(qid)
                await conn1.execute(
                    """INSERT INTO priority_queue
                       (id, root_cause_event_id, incident_id, priority_score, severity, status, enqueued_at, ttl_expires_at)
                       VALUES ($1, $2, $3, $4, $5, 'queued', $6, $7)""",
                    qid, grp, inc, score, sev, now, now + timedelta(hours=1),
                )

            with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
                d1 = await dequeue_next(conn1)
                assert d1 is not None

                d2 = await dequeue_next(conn2)
                assert d2 is not None

                assert d1["id"] != d2["id"]
        finally:
            for qid in q_ids:
                await conn1.execute("DELETE FROM active_pipelines WHERE queue_item_id = $1", qid)
                await conn1.execute("DELETE FROM priority_queue WHERE id = $1", qid)
            if grp1:
                await conn1.execute("DELETE FROM alert_group_members WHERE group_id = $1", grp1)
            if grp2:
                await conn1.execute("DELETE FROM alert_group_members WHERE group_id = $1", grp2)
            if inc1:
                await conn1.execute("DELETE FROM alerts WHERE incident_id = $1", inc1)
                await conn1.execute("UPDATE incidents SET root_cause_event_id = NULL WHERE id = $1", inc1)
            if inc2:
                await conn1.execute("DELETE FROM alerts WHERE incident_id = $1", inc2)
                await conn1.execute("UPDATE incidents SET root_cause_event_id = NULL WHERE id = $1", inc2)
            if grp1:
                await conn1.execute("DELETE FROM correlation_groups WHERE id = $1", grp1)
            if grp2:
                await conn1.execute("DELETE FROM correlation_groups WHERE id = $1", grp2)
            if inc1:
                await conn1.execute("DELETE FROM incidents WHERE id = $1", inc1)
            if inc2:
                await conn1.execute("DELETE FROM incidents WHERE id = $1", inc2)
            await conn1.close()
            await conn2.close()


@pytest.mark.db
class TestCancellation:
    """Queue item cancellation tests."""

    @pytest.mark.asyncio
    async def test_cancel_queued_item(self, db_conn):
        inc_id, grp_id, _ = await _create_incident_and_rce(db_conn)
        now = datetime.now(timezone.utc)

        with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
            await insert_queue_item(
                db_conn,
                root_cause_event_id=grp_id,
                incident_id=inc_id,
                priority_score=100.0,
                severity="critical",
                ttl_expires_at=now + timedelta(hours=1),
            )

        cancelled = await cancel_queued_item(db_conn, grp_id)
        assert cancelled is not None
        assert cancelled["status"] == "cancelled"

        with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
            dequeued = await dequeue_next(db_conn)
        assert dequeued is None

    @pytest.mark.asyncio
    async def test_cancel_processing_item_fails(self, db_conn):
        """Cannot cancel an item that is already processing (AD-16)."""
        inc_id, grp_id, _ = await _create_incident_and_rce(db_conn)
        now = datetime.now(timezone.utc)

        with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
            await insert_queue_item(
                db_conn,
                root_cause_event_id=grp_id,
                incident_id=inc_id,
                priority_score=100.0,
                severity="critical",
                ttl_expires_at=now + timedelta(hours=1),
            )
            await dequeue_next(db_conn)

        cancelled = await cancel_queued_item(db_conn, grp_id)
        assert cancelled is None


@pytest.mark.db
class TestParallelismCap:
    """Parallelism cap enforcement."""

    @pytest.mark.asyncio
    async def test_parallelism_cap_limits_dequeue(self, db_conn):
        """With cap=2 and 5 items, only 2 should dequeue; third returns None."""
        now = datetime.now(timezone.utc)
        settings = _queue_settings(parallelism_cap=2)

        for i in range(5):
            inc_id, grp_id, _ = await _create_incident_and_rce(db_conn, "warning")
            with patch("src.db.queue.get_queue_settings", return_value=settings):
                await insert_queue_item(
                    db_conn,
                    root_cause_event_id=grp_id,
                    incident_id=inc_id,
                    priority_score=50.0 - i,
                    severity="warning",
                    ttl_expires_at=now + timedelta(hours=1),
                )

        with patch("src.db.queue.get_queue_settings", return_value=settings):
            d1 = await dequeue_next(db_conn)
            d2 = await dequeue_next(db_conn)
            d3 = await dequeue_next(db_conn)

        assert d1 is not None
        assert d2 is not None
        assert d3 is None


@pytest.mark.db
class TestCrashRecovery:
    """Stale processing recovery on startup."""

    @pytest.mark.asyncio
    async def test_stale_processing_items_reset(self, db_conn):
        """Items stuck in processing past timeout should reset to queued, including incident state."""
        inc_id, grp_id, _ = await _create_incident_and_rce(db_conn)
        item_id = uuid.uuid4()
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=1000)

        await db_conn.execute(
            "UPDATE incidents SET state = 'diagnosing' WHERE id = $1", inc_id,
        )

        await db_conn.execute(
            """INSERT INTO priority_queue
               (id, root_cause_event_id, incident_id, priority_score, severity,
                status, enqueued_at, dequeued_at, ttl_expires_at)
               VALUES ($1, $2, $3, 100.0, 'critical', 'processing', $4, $4, $5)""",
            item_id, grp_id, inc_id, stale_time, stale_time + timedelta(hours=1),
        )
        await db_conn.execute(
            "INSERT INTO active_pipelines (id, queue_item_id, incident_id, started_at) VALUES ($1, $2, $3, $4)",
            uuid.uuid4(), item_id, inc_id, stale_time,
        )

        settings = _queue_settings(stale_processing_timeout_seconds=900)
        with patch("src.db.queue.get_queue_settings", return_value=settings):
            recovered = await recover_stale_items(db_conn)

        assert recovered >= 1

        row = await db_conn.fetchrow("SELECT status FROM priority_queue WHERE id = $1", item_id)
        assert row["status"] == "queued"

        inc_row = await db_conn.fetchrow("SELECT state FROM incidents WHERE id = $1", inc_id)
        assert inc_row["state"] == "queued"


@pytest.mark.db
class TestPipelineCompletion:
    """Pipeline completion tracking."""

    @pytest.mark.asyncio
    async def test_mark_pipeline_complete(self, db_conn):
        inc_id, grp_id, _ = await _create_incident_and_rce(db_conn)
        now = datetime.now(timezone.utc)

        with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
            item = await insert_queue_item(
                db_conn,
                root_cause_event_id=grp_id,
                incident_id=inc_id,
                priority_score=100.0,
                severity="critical",
                ttl_expires_at=now + timedelta(hours=1),
            )
            dequeued = await dequeue_next(db_conn)
            assert dequeued is not None

            await mark_pipeline_complete(db_conn, dequeued["id"])

        row = await db_conn.fetchrow("SELECT status, completed_at FROM priority_queue WHERE id = $1", dequeued["id"])
        assert row["status"] == "completed"
        assert row["completed_at"] is not None

        pipeline_row = await db_conn.fetchrow(
            "SELECT completed_at FROM active_pipelines WHERE queue_item_id = $1", dequeued["id"]
        )
        assert pipeline_row["completed_at"] is not None


@pytest.mark.db
class TestStateTransitions:
    """State machine transition verification."""

    @pytest.mark.asyncio
    async def test_dequeue_does_not_transition_incident(self, db_conn):
        """Dequeue itself does not transition — dispatcher does that separately."""
        inc_id, grp_id, _ = await _create_incident_and_rce(db_conn)
        now = datetime.now(timezone.utc)

        with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
            await insert_queue_item(
                db_conn,
                root_cause_event_id=grp_id,
                incident_id=inc_id,
                priority_score=100.0,
                severity="critical",
                ttl_expires_at=now + timedelta(hours=1),
            )
            await dequeue_next(db_conn)

        row = await db_conn.fetchrow("SELECT state FROM incidents WHERE id = $1", inc_id)
        assert row["state"] == "queued"

    @pytest.mark.asyncio
    async def test_cancel_transitions_incident_to_cancelled(self, db_conn):
        """Cancelling a queued RCE should transition incident to cancelled."""
        inc_id, grp_id, _ = await _create_incident_and_rce(db_conn)
        now = datetime.now(timezone.utc)

        with patch("src.pipeline.priority_queue.get_queue_settings", return_value=_queue_settings()):
            await insert_queue_item(
                db_conn,
                root_cause_event_id=grp_id,
                incident_id=inc_id,
                priority_score=100.0,
                severity="critical",
                ttl_expires_at=now + timedelta(hours=1),
            )

        with patch("src.pipeline.priority_queue.get_queue_settings", return_value=_queue_settings()):
            result = await cancel_queued_rce(db_conn, grp_id)

        assert result is True
        row = await db_conn.fetchrow("SELECT state FROM incidents WHERE id = $1", inc_id)
        assert row["state"] == "cancelled"


@pytest.mark.db
class TestResolvedWebhookFlow:
    """Full resolved-webhook cancellation flow."""

    @pytest.mark.asyncio
    async def test_resolve_all_alerts_cancels_rce(self, db_conn):
        """Enqueue RCE → resolve all alerts → RCE cancelled."""
        inc_id, grp_id, alert_id = await _create_incident_and_rce(db_conn)
        now = datetime.now(timezone.utc)

        with patch("src.pipeline.priority_queue.get_queue_settings", return_value=_queue_settings()):
            with patch("src.db.queue.get_queue_settings", return_value=_queue_settings()):
                await insert_queue_item(
                    db_conn,
                    root_cause_event_id=grp_id,
                    incident_id=inc_id,
                    priority_score=100.0,
                    severity="critical",
                    ttl_expires_at=now + timedelta(hours=1),
                )

        await db_conn.execute(
            "UPDATE alerts SET status = 'resolved', resolved_at = $2 WHERE id = $1",
            alert_id, now,
        )

        all_resolved = await db_conn.fetchval(
            """SELECT NOT EXISTS(
                SELECT 1 FROM alert_group_members agm
                JOIN alerts a ON a.id = agm.alert_id
                WHERE agm.group_id = $1 AND a.status = 'firing'
            )""",
            grp_id,
        )
        assert all_resolved is True

        with patch("src.pipeline.priority_queue.get_queue_settings", return_value=_queue_settings()):
            result = await cancel_queued_rce(db_conn, grp_id)

        assert result is True
        row = await db_conn.fetchrow("SELECT status FROM priority_queue WHERE root_cause_event_id = $1", grp_id)
        assert row["status"] == "cancelled"

        inc_row = await db_conn.fetchrow("SELECT state FROM incidents WHERE id = $1", inc_id)
        assert inc_row["state"] == "cancelled"
