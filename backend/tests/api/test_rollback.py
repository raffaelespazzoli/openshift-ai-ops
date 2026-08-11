"""API tests for the rollback endpoint (Story 3.5).

Tests: rollback success; wrong state → 409; no rollback plan → 409; unauthenticated → 401.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _auth_disabled():
    with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
        yield


async def _seed_executed_incident(db_url, *, state="resolved", include_rollback=True):
    """Insert incident → diagnosis → plan → execution chain."""
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

        rollback_steps = (
            [{"order": 1, "description": "Undo", "command": "kubectl delete", "resource": "pod/x", "action": "delete", "expected_outcome": "Deleted"}]
            if include_rollback
            else []
        )
        plan_data = json.dumps({
            "id": str(plan_id),
            "incident_id": str(incident_id),
            "diagnosis_id": str(diagnosis_id),
            "steps": [{"order": 1, "description": "Fix", "command": "kubectl apply", "resource": "pod/x", "action": "apply", "expected_outcome": "Fixed"}],
            "blast_radius": "workload",
            "rollback_plan": rollback_steps,
            "estimated_risk": "low",
            "preconditions": [],
            "plan_summary": "Fix it",
        })

        await conn.execute(
            """INSERT INTO remediation_plans (id, incident_id, diagnosis_id, plan, blast_radius, estimated_risk, created_at)
            VALUES ($1, $2, $3, $4::jsonb, 'workload', 'low', NOW())""",
            plan_id, incident_id, diagnosis_id, plan_data,
        )

        exec_id = uuid.uuid4()
        exec_steps = json.dumps([{"step_order": 1, "command": "kubectl apply", "started_at": now.isoformat(), "completed_at": now.isoformat(), "success": True, "output": "applied"}])
        await conn.execute(
            """INSERT INTO execution_logs (id, incident_id, plan_id, steps, mcp_calls, started_at, completed_at, status)
            VALUES ($1, $2, $3, $4::jsonb, '[]'::jsonb, $5, $6, 'completed')""",
            exec_id, incident_id, plan_id, exec_steps, now, now,
        )

        return incident_id, plan_id, diagnosis_id
    finally:
        await conn.close()


async def _cleanup(db_url, incident_id):
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("DELETE FROM rollback_records WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM execution_logs WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM outcome_results WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM approval_records WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM remediation_plans WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM immutable_diagnoses WHERE incident_id = $1", incident_id)
        await conn.execute("DELETE FROM incidents WHERE id = $1", incident_id)
    finally:
        await conn.close()


class TestRollbackSuccess:
    """POST /api/v1/incidents/{id}/rollback — success cases."""

    async def test_rollback_resolved_incident(self, async_client, db_url, run_migrations):
        incident_id, plan_id, diagnosis_id = await _seed_executed_incident(
            db_url, state="resolved"
        )
        try:
            with (
                patch("src.api.rollback.ReadWriteMCPClient") as MockMCP,
                patch("src.api.rollback.acquire_remediation_lock", new_callable=AsyncMock, return_value=True),
                patch("src.api.rollback.release_remediation_lock", new_callable=AsyncMock),
            ):
                mock_instance = AsyncMock()
                mock_instance.execute = AsyncMock(return_value="rolled back")
                MockMCP.return_value = mock_instance

                resp = await async_client.post(
                    f"/api/v1/incidents/{incident_id}/rollback"
                )

            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["status"] == "rollback_completed"
            assert body["data"]["success"] is True
        finally:
            await _cleanup(db_url, incident_id)

    async def test_rollback_failed_incident(self, async_client, db_url, run_migrations):
        incident_id, plan_id, diagnosis_id = await _seed_executed_incident(
            db_url, state="failed"
        )
        try:
            with (
                patch("src.api.rollback.ReadWriteMCPClient") as MockMCP,
                patch("src.api.rollback.acquire_remediation_lock", new_callable=AsyncMock, return_value=True),
                patch("src.api.rollback.release_remediation_lock", new_callable=AsyncMock),
            ):
                mock_instance = AsyncMock()
                mock_instance.execute = AsyncMock(return_value="rolled back")
                MockMCP.return_value = mock_instance

                resp = await async_client.post(
                    f"/api/v1/incidents/{incident_id}/rollback"
                )

            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["success"] is True
        finally:
            await _cleanup(db_url, incident_id)


class TestRollbackConflict:
    """POST /api/v1/incidents/{id}/rollback — conflict cases."""

    async def test_rollback_wrong_state_409(self, async_client, db_url, run_migrations):
        incident_id, plan_id, diagnosis_id = await _seed_executed_incident(
            db_url, state="executing"
        )
        try:
            resp = await async_client.post(
                f"/api/v1/incidents/{incident_id}/rollback"
            )
            assert resp.status_code == 409
            body = resp.json()
            assert body["code"] == "CONFLICT"
        finally:
            await _cleanup(db_url, incident_id)

    async def test_rollback_no_plan_409(self, async_client, db_url, run_migrations):
        incident_id, plan_id, diagnosis_id = await _seed_executed_incident(
            db_url, state="resolved", include_rollback=False
        )
        try:
            resp = await async_client.post(
                f"/api/v1/incidents/{incident_id}/rollback"
            )
            assert resp.status_code == 409
            body = resp.json()
            assert "rollback" in body["error"].lower()
        finally:
            await _cleanup(db_url, incident_id)


class TestRollbackNotFound:
    """POST /api/v1/incidents/{id}/rollback — 404 cases."""

    async def test_rollback_nonexistent_incident_404(self, async_client, run_migrations):
        fake_id = uuid.uuid4()
        resp = await async_client.post(
            f"/api/v1/incidents/{fake_id}/rollback"
        )
        assert resp.status_code == 404


class TestRollbackAuth:
    """POST /api/v1/incidents/{id}/rollback — authentication required."""

    async def test_rollback_unauthenticated_401(self, async_client, db_url, run_migrations):
        incident_id, plan_id, diagnosis_id = await _seed_executed_incident(
            db_url, state="resolved"
        )
        try:
            with patch.dict(os.environ, {"AUTH_DISABLED": "false"}):
                resp = await async_client.post(
                    f"/api/v1/incidents/{incident_id}/rollback"
                )
            assert resp.status_code == 401
        finally:
            await _cleanup(db_url, incident_id)
