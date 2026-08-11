"""API integration tests for approval workflow endpoints (Story 3.4).

Tests approve, reject, approval context retrieval, awaiting list,
minimum review time enforcement, and policy adjustment.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import asyncpg
import pytest

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _auth_disabled():
    with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
        yield


@pytest.fixture(autouse=True)
def _disable_min_review():
    """Disable minimum review time by default; individual tests can override."""
    with patch.dict(os.environ, {"APPROVAL_MIN_REVIEW_ENABLED": "false"}):
        from src.config.approval_settings import reset_approval_settings
        reset_approval_settings()
        yield
        reset_approval_settings()


async def _seed_full_chain(db_url, *, state="awaiting_approval", blast_radius="workload"):
    """Insert incident → diagnosis → plan chain via a committed connection."""
    conn = await asyncpg.connect(db_url)
    try:
        incident_id = uuid.uuid4()
        diagnosis_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        await conn.execute(
            "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, $2, 'critical', $3, $4)",
            incident_id, state, now, now,
        )
        await conn.execute(
            """INSERT INTO immutable_diagnoses (id, incident_id, diagnosis, skeptic_verdict, sealed_at)
            VALUES ($1, $2, '{"root_cause": "OOM"}'::jsonb, '{}'::jsonb, NOW())""",
            diagnosis_id, incident_id,
        )
        await conn.execute(
            """INSERT INTO remediation_plans (id, incident_id, diagnosis_id, plan, blast_radius, estimated_risk, created_at)
            VALUES ($1, $2, $3, '{"steps": [{"order": 1}]}'::jsonb, $4, 'medium', NOW())""",
            plan_id, incident_id, diagnosis_id, blast_radius,
        )
        return incident_id, plan_id, diagnosis_id
    finally:
        await conn.close()


async def _cleanup(db_url, incident_id, plan_id, diagnosis_id):
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("DELETE FROM approval_records WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM dry_run_results WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM policy_decisions WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM remediation_skeptic_reviews WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM remediation_plans WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM immutable_diagnoses WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM incidents WHERE id = $1", incident_id)
    finally:
        await conn.close()


@pytest.fixture
async def awaiting_incident(db_url, run_migrations):
    incident_id, plan_id, diagnosis_id = await _seed_full_chain(db_url)
    yield incident_id, plan_id, diagnosis_id
    await _cleanup(db_url, incident_id, plan_id, diagnosis_id)


@pytest.fixture
async def diagnosing_incident(db_url, run_migrations):
    incident_id, plan_id, diagnosis_id = await _seed_full_chain(db_url, state="diagnosing")
    yield incident_id, plan_id, diagnosis_id
    await _cleanup(db_url, incident_id, plan_id, diagnosis_id)


@pytest.fixture
async def node_incident(db_url, run_migrations):
    incident_id, plan_id, diagnosis_id = await _seed_full_chain(
        db_url, blast_radius="node"
    )
    yield incident_id, plan_id, diagnosis_id
    await _cleanup(db_url, incident_id, plan_id, diagnosis_id)


class TestGetApprovalContext:
    async def test_returns_context_for_awaiting_incident(
        self, async_client, awaiting_incident
    ):
        incident_id, _, _ = awaiting_incident
        resp = await async_client.get(f"/api/v1/incidents/{incident_id}/approval")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        assert data["incident_id"] == str(incident_id)
        assert data["state"] == "awaiting_approval"
        assert "diagnosis_summary" in data
        assert "remediation_plan" in data

    async def test_returns_404_for_nonexistent(self, async_client):
        fake_id = uuid.uuid4()
        resp = await async_client.get(f"/api/v1/incidents/{fake_id}/approval")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "NOT_FOUND"


class TestApproveRemediation:
    async def test_approve_success(self, async_client, awaiting_incident):
        incident_id, _, _ = awaiting_incident
        resp = await async_client.post(f"/api/v1/incidents/{incident_id}/approve")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "approved"
        assert body["data"]["new_state"] == "executing"

    async def test_approve_wrong_state_returns_409(
        self, async_client, diagnosing_incident
    ):
        incident_id, _, _ = diagnosing_incident
        resp = await async_client.post(f"/api/v1/incidents/{incident_id}/approve")
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "CONFLICT"
        assert "current_state" in body["detail"]

    async def test_approve_nonexistent_returns_404(self, async_client):
        fake_id = uuid.uuid4()
        resp = await async_client.post(f"/api/v1/incidents/{fake_id}/approve")
        assert resp.status_code == 404

    async def test_approve_already_approved_returns_409(
        self, async_client, awaiting_incident
    ):
        incident_id, _, _ = awaiting_incident
        resp1 = await async_client.post(f"/api/v1/incidents/{incident_id}/approve")
        assert resp1.status_code == 200

        resp2 = await async_client.post(f"/api/v1/incidents/{incident_id}/approve")
        assert resp2.status_code == 409

    async def test_approve_too_early_returns_409(self, async_client, node_incident):
        incident_id, _, _ = node_incident

        with patch.dict(os.environ, {"APPROVAL_MIN_REVIEW_ENABLED": "true", "APPROVAL_MIN_REVIEW_NODE": "99999"}):
            from src.config.approval_settings import reset_approval_settings
            reset_approval_settings()

            resp = await async_client.post(f"/api/v1/incidents/{incident_id}/approve")
            assert resp.status_code == 409
            body = resp.json()
            assert body["code"] == "CONFLICT"
            assert "review_time_remaining" in body["detail"]

            reset_approval_settings()


class TestRejectRemediation:
    async def test_reject_success(self, async_client, awaiting_incident):
        incident_id, _, _ = awaiting_incident
        resp = await async_client.post(
            f"/api/v1/incidents/{incident_id}/reject",
            json={"reason": "Too risky for production"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "rejected"
        assert body["data"]["new_state"] == "failed"

    async def test_reject_missing_reason_returns_422(
        self, async_client, awaiting_incident
    ):
        incident_id, _, _ = awaiting_incident
        resp = await async_client.post(
            f"/api/v1/incidents/{incident_id}/reject",
            json={},
        )
        assert resp.status_code == 422

    async def test_reject_empty_reason_returns_422(
        self, async_client, awaiting_incident
    ):
        incident_id, _, _ = awaiting_incident
        resp = await async_client.post(
            f"/api/v1/incidents/{incident_id}/reject",
            json={"reason": "   "},
        )
        assert resp.status_code == 422

    async def test_reject_wrong_state_returns_409(
        self, async_client, diagnosing_incident
    ):
        incident_id, _, _ = diagnosing_incident
        resp = await async_client.post(
            f"/api/v1/incidents/{incident_id}/reject",
            json={"reason": "Testing wrong state"},
        )
        assert resp.status_code == 409


class TestListAwaitingApproval:
    async def test_returns_awaiting_incidents(self, async_client, awaiting_incident):
        incident_id, _, _ = awaiting_incident
        resp = await async_client.get("/api/v1/incidents/awaiting-approval")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        ids = [item["id"] for item in body["data"]]
        assert str(incident_id) in ids

    async def test_does_not_include_non_awaiting(
        self, async_client, diagnosing_incident
    ):
        incident_id, _, _ = diagnosing_incident
        resp = await async_client.get("/api/v1/incidents/awaiting-approval")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["data"]]
        assert str(incident_id) not in ids

    async def test_returns_count_in_meta(self, async_client, awaiting_incident):
        resp = await async_client.get("/api/v1/incidents/awaiting-approval")
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert "total" in meta


class TestPolicyAdjust:
    async def test_adjust_success(self, async_client, run_migrations):
        resp = await async_client.post(
            "/api/v1/policy/adjust",
            json={
                "severity": "warning",
                "blast_radius": "workload",
                "confidence_minimum": 0.85,
                "new_auto_approve": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "adjusted"

    async def test_adjust_without_confidence_minimum(self, async_client, run_migrations):
        resp = await async_client.post(
            "/api/v1/policy/adjust",
            json={
                "severity": "critical",
                "blast_radius": "node",
                "new_auto_approve": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "adjusted"

    async def test_adjust_creates_audit_log(self, async_client, db_url, run_migrations):
        resp = await async_client.post(
            "/api/v1/policy/adjust",
            json={
                "severity": "critical",
                "blast_radius": "cluster",
                "confidence_minimum": 0.95,
                "new_auto_approve": False,
            },
        )
        assert resp.status_code == 200

        conn = await asyncpg.connect(db_url)
        try:
            row = await conn.fetchrow(
                "SELECT * FROM audit_log WHERE action = 'api.policy.adjusted' ORDER BY created_at DESC LIMIT 1"
            )
            assert row is not None
            assert row["actor"] == "dev-user"
            assert row["target_resource"] == "policy_matrix"
        finally:
            await conn.close()


async def _seed_incident_no_plan(db_url, *, state="awaiting_approval"):
    """Insert an incident with NO remediation plan (orphaned)."""
    conn = await asyncpg.connect(db_url)
    try:
        incident_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        await conn.execute(
            "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, $2, 'critical', $3, $4)",
            incident_id, state, now, now,
        )
        return incident_id
    finally:
        await conn.close()


async def _cleanup_no_plan(db_url, incident_id):
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("DELETE FROM incidents WHERE id = $1", incident_id)
    finally:
        await conn.close()


@pytest.fixture
async def orphan_incident(db_url, run_migrations):
    incident_id = await _seed_incident_no_plan(db_url)
    yield incident_id
    await _cleanup_no_plan(db_url, incident_id)


class TestMissingPlanGuard:
    """Verify 409 when an incident has no remediation plan."""

    async def test_approve_missing_plan_returns_409(
        self, async_client, orphan_incident
    ):
        incident_id = orphan_incident
        resp = await async_client.post(f"/api/v1/incidents/{incident_id}/approve")
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "CONFLICT"
        assert "No remediation plan" in body["error"]

    async def test_reject_missing_plan_returns_409(
        self, async_client, orphan_incident
    ):
        incident_id = orphan_incident
        resp = await async_client.post(
            f"/api/v1/incidents/{incident_id}/reject",
            json={"reason": "Testing missing plan"},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "CONFLICT"
        assert "No remediation plan" in body["error"]


class TestApproveRejectFullFlow:
    """Full integration flow: seed → approve → verify state."""

    async def test_approve_transitions_to_executing(
        self, async_client, db_url, awaiting_incident
    ):
        incident_id, _, _ = awaiting_incident
        resp = await async_client.post(f"/api/v1/incidents/{incident_id}/approve")
        assert resp.status_code == 200

        conn = await asyncpg.connect(db_url)
        try:
            row = await conn.fetchrow("SELECT state FROM incidents WHERE id = $1", incident_id)
            assert row["state"] == "executing"
        finally:
            await conn.close()

    async def test_reject_transitions_to_failed(
        self, async_client, db_url, awaiting_incident
    ):
        incident_id, _, _ = awaiting_incident
        resp = await async_client.post(
            f"/api/v1/incidents/{incident_id}/reject",
            json={"reason": "Not appropriate"},
        )
        assert resp.status_code == 200

        conn = await asyncpg.connect(db_url)
        try:
            row = await conn.fetchrow("SELECT state FROM incidents WHERE id = $1", incident_id)
            assert row["state"] == "failed"
        finally:
            await conn.close()

    async def test_approve_creates_audit_log(
        self, async_client, db_url, awaiting_incident
    ):
        incident_id, _, _ = awaiting_incident
        await async_client.post(f"/api/v1/incidents/{incident_id}/approve")

        conn = await asyncpg.connect(db_url)
        try:
            row = await conn.fetchrow(
                "SELECT * FROM audit_log WHERE action = 'api.remediation.approved' AND target_resource = $1",
                str(incident_id),
            )
            assert row is not None
            assert row["actor"] == "dev-user"
        finally:
            await conn.close()
