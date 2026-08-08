"""Integration tests for the correlation engine with real PostgreSQL.

Uses testcontainers for a real PostgreSQL database.
Tests verify full correlation flow, dedup, group sealing, state transitions.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.db.correlation import (
    add_alert_to_group,
    check_dedup,
    create_correlation_group,
    get_groups_to_seal,
    get_open_groups,
    seal_group,
)
from src.db.incidents import create_alert, create_incident
from src.models.root_cause_event import CorrelationEvidence, CorrelationLayer
from src.models.state_machine import IncidentState
from src.pipeline.correlator import process_alert_for_correlation, seal_expired_groups


async def _create_test_alert(
    conn,
    fingerprint: str = "test-fp",
    labels: dict | None = None,
    severity: str = "warning",
) -> tuple[dict, dict]:
    """Helper: create an incident + alert pair for testing."""
    incident = await create_incident(conn, severity=severity)
    alert = await create_alert(
        conn,
        incident_id=incident["id"],
        fingerprint=fingerprint,
        labels=labels or {"alertname": "TestAlert", "namespace": "default"},
        annotations={"summary": "test"},
        status="firing",
        fired_at=datetime.now(timezone.utc),
    )
    return incident, alert


class TestDedupIntegration:
    """Dedup prevents duplicate incident creation in DB."""

    @pytest.mark.db
    async def test_dedup_detects_existing_firing_alert(self, db_conn):
        """check_dedup returns True for an existing firing alert."""
        _, alert = await _create_test_alert(db_conn, fingerprint="dedup-test-001")

        result = await check_dedup(db_conn, "dedup-test-001")
        assert result is True

    @pytest.mark.db
    async def test_dedup_returns_false_for_new_fingerprint(self, db_conn):
        """check_dedup returns False for a never-seen fingerprint."""
        result = await check_dedup(db_conn, "brand-new-fingerprint")
        assert result is False

    @pytest.mark.db
    async def test_dedup_returns_false_for_resolved_alert(self, db_conn):
        """Resolved alerts should not block new alerts with same fingerprint."""
        _, alert = await _create_test_alert(db_conn, fingerprint="resolved-fp")
        await db_conn.execute(
            "UPDATE alerts SET status = 'resolved' WHERE id = $1", alert["id"]
        )

        result = await check_dedup(db_conn, "resolved-fp")
        assert result is False


class TestCorrelationGroupLifecycle:
    """Full correlation group lifecycle: create, add members, seal."""

    @pytest.mark.db
    async def test_create_group_with_seed_alert(self, db_conn):
        """Creating a group should persist group + member."""
        incident, alert = await _create_test_alert(db_conn)
        group_id = await create_correlation_group(
            db_conn, alert["id"], incident["id"], settling_window_seconds=300
        )

        groups = await get_open_groups(db_conn)
        assert len(groups) == 1
        assert groups[0]["id"] == group_id
        assert groups[0]["settling_window_seconds"] == 300
        assert len(groups[0]["members"]) == 1

    @pytest.mark.db
    async def test_add_alert_to_existing_group(self, db_conn):
        """Adding an alert updates group and adds member."""
        inc1, alert1 = await _create_test_alert(db_conn, fingerprint="first")
        group_id = await create_correlation_group(
            db_conn, alert1["id"], inc1["id"], settling_window_seconds=300
        )

        inc2, alert2 = await _create_test_alert(db_conn, fingerprint="second")
        evidence = CorrelationEvidence(
            layer=CorrelationLayer.NAMESPACE_TEMPORAL,
            alert_ids=[alert2["id"]],
            reasoning="Same namespace within window",
            dimension_data={"namespace": "default"},
        )
        await add_alert_to_group(db_conn, group_id, alert2["id"], inc2["id"], 300, evidence)

        groups = await get_open_groups(db_conn)
        assert len(groups) == 1
        assert len(groups[0]["members"]) == 2

    @pytest.mark.db
    async def test_seal_group_produces_root_cause_event(self, db_conn):
        """Sealing a group sets state=sealed and links incidents."""
        inc1, alert1 = await _create_test_alert(db_conn, fingerprint="seal-test-1")
        group_id = await create_correlation_group(
            db_conn, alert1["id"], inc1["id"], settling_window_seconds=60
        )

        sealed = await seal_group(db_conn, group_id)

        assert sealed["state"] == "sealed"
        assert sealed["sealed_at"] is not None
        assert alert1["id"] in sealed["alert_ids"]
        assert inc1["id"] in sealed["incident_ids"]

        inc_row = await db_conn.fetchrow(
            "SELECT root_cause_event_id FROM incidents WHERE id = $1", inc1["id"]
        )
        assert inc_row["root_cause_event_id"] == group_id


class TestStateTransitions:
    """State transitions: received → correlating → queued."""

    @pytest.mark.db
    async def test_correlation_transitions_to_correlating(self, db_conn):
        """process_alert_for_correlation transitions incident to correlating."""
        incident, alert = await _create_test_alert(
            db_conn, fingerprint="state-test-1", labels={"alertname": "X", "namespace": "ns1"}
        )

        await process_alert_for_correlation(
            db_conn,
            alert_id=alert["id"],
            incident_id=incident["id"],
            fingerprint="state-test-1",
            labels={"alertname": "X", "namespace": "ns1"},
            severity="warning",
        )

        state = await db_conn.fetchval(
            "SELECT state FROM incidents WHERE id = $1", incident["id"]
        )
        assert state == "correlating"

    @pytest.mark.db
    async def test_sealing_transitions_to_queued(self, db_conn):
        """Sealing a group transitions its incidents to queued state."""
        inc1, alert1 = await _create_test_alert(
            db_conn, fingerprint="seal-state-1", labels={"alertname": "A", "namespace": "ns-seal"}
        )

        await process_alert_for_correlation(
            db_conn,
            alert_id=alert1["id"],
            incident_id=inc1["id"],
            fingerprint="seal-state-1",
            labels={"alertname": "A", "namespace": "ns-seal"},
            severity="critical",
        )

        await db_conn.execute(
            """
            UPDATE correlation_groups
            SET last_alert_at = created_at - interval '120 seconds'
            WHERE state = 'open'
            """
        )

        sealed_count = await seal_expired_groups(db_conn)
        assert sealed_count >= 1

        state = await db_conn.fetchval(
            "SELECT state FROM incidents WHERE id = $1", inc1["id"]
        )
        assert state == "queued"


class TestSettlingWindowIntegration:
    """Settling window timer resets and max age sealing."""

    @pytest.mark.db
    async def test_settling_window_timer_resets(self, db_conn):
        """New alert joining a group resets last_alert_at."""
        inc1, alert1 = await _create_test_alert(
            db_conn, fingerprint="timer-1", labels={"alertname": "T1", "namespace": "ns-timer"}
        )
        group_id = await create_correlation_group(
            db_conn, alert1["id"], inc1["id"], settling_window_seconds=300
        )

        initial_last_alert = await db_conn.fetchval(
            "SELECT last_alert_at FROM correlation_groups WHERE id = $1", group_id
        )

        await asyncio.sleep(0.05)

        inc2, alert2 = await _create_test_alert(
            db_conn, fingerprint="timer-2", labels={"alertname": "T2", "namespace": "ns-timer"}
        )
        evidence = CorrelationEvidence(
            layer=CorrelationLayer.NAMESPACE_TEMPORAL,
            alert_ids=[alert2["id"]],
            reasoning="Same namespace",
        )
        await add_alert_to_group(db_conn, group_id, alert2["id"], inc2["id"], 300, evidence)

        new_last_alert = await db_conn.fetchval(
            "SELECT last_alert_at FROM correlation_groups WHERE id = $1", group_id
        )
        assert new_last_alert > initial_last_alert

    @pytest.mark.db
    async def test_max_age_sealing(self, db_conn):
        """Groups exceeding max age (3x window) should seal even if window hasn't expired."""
        inc1, alert1 = await _create_test_alert(
            db_conn, fingerprint="maxage-1", labels={"alertname": "M1", "namespace": "ns-max"}
        )
        group_id = await create_correlation_group(
            db_conn, alert1["id"], inc1["id"], settling_window_seconds=60
        )

        await db_conn.execute(
            "UPDATE incidents SET state = 'correlating' WHERE id = $1", inc1["id"]
        )

        await db_conn.execute(
            """
            UPDATE correlation_groups
            SET created_at = NOW() - interval '200 seconds',
                max_age_at = NOW() - interval '10 seconds',
                last_alert_at = NOW() - interval '5 seconds'
            WHERE id = $1
            """,
            group_id,
        )

        sealed_count = await seal_expired_groups(db_conn)
        assert sealed_count == 1

        group_state = await db_conn.fetchval(
            "SELECT state FROM correlation_groups WHERE id = $1", group_id
        )
        assert group_state == "sealed"


class TestCorrelationEvidence:
    """Correlation evidence persisted correctly."""

    @pytest.mark.db
    async def test_evidence_persisted_as_jsonb(self, db_conn):
        """Evidence should be stored as JSONB and retrievable."""
        inc1, alert1 = await _create_test_alert(
            db_conn, fingerprint="evidence-1", labels={"alertname": "E1", "namespace": "ns-ev"}
        )
        group_id = await create_correlation_group(
            db_conn, alert1["id"], inc1["id"], settling_window_seconds=300
        )

        inc2, alert2 = await _create_test_alert(
            db_conn, fingerprint="evidence-2", labels={"alertname": "E2", "namespace": "ns-ev"}
        )
        evidence = CorrelationEvidence(
            layer=CorrelationLayer.NAMESPACE_TEMPORAL,
            alert_ids=[alert2["id"]],
            reasoning="Same namespace 'ns-ev' within settling window",
            dimension_data={"namespace": "ns-ev"},
        )
        await add_alert_to_group(db_conn, group_id, alert2["id"], inc2["id"], 300, evidence)

        row = await db_conn.fetchrow(
            "SELECT correlation_evidence FROM correlation_groups WHERE id = $1", group_id
        )
        evidence_list = row["correlation_evidence"]
        if isinstance(evidence_list, str):
            evidence_list = json.loads(evidence_list)

        assert len(evidence_list) >= 1
        last_evidence = evidence_list[-1]
        assert last_evidence["layer"] == "namespace_temporal"
        assert last_evidence["reasoning"] == "Same namespace 'ns-ev' within settling window"
