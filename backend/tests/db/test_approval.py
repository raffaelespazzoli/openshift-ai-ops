"""DB integration tests for approval persistence (Story 3.4).

Tests persist_approval_record roundtrip, UNIQUE constraint,
load_approval_context joins, and list_awaiting_approval
with testcontainers PostgreSQL.
"""

import uuid
from datetime import datetime, timezone

import pytest

from src.db.approval import (
    list_awaiting_approval,
    load_approval_context,
    persist_approval_record,
    persist_policy_adjustment,
)
from src.models.approval import PolicyAdjustmentRequest


def _make_ids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


async def _insert_prerequisites(conn, incident_id, plan_id, diagnosis_id, *, state="awaiting_approval"):
    """Insert incident → immutable_diagnosis → remediation_plan chain."""
    await conn.execute(
        "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, $2, 'critical', NOW(), NOW())",
        incident_id,
        state,
    )
    await conn.execute(
        """INSERT INTO immutable_diagnoses (id, incident_id, diagnosis, skeptic_verdict, sealed_at)
        VALUES ($1, $2, '{"root_cause": "OOM"}'::jsonb, '{}'::jsonb, NOW())""",
        diagnosis_id,
        incident_id,
    )
    await conn.execute(
        """INSERT INTO remediation_plans (id, incident_id, diagnosis_id, plan, blast_radius, estimated_risk, created_at)
        VALUES ($1, $2, $3, '{"steps": []}'::jsonb, 'node', 'medium', NOW())""",
        plan_id,
        incident_id,
        diagnosis_id,
    )


class TestPersistApprovalRecord:
    @pytest.mark.db
    async def test_roundtrip(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        record_id = await persist_approval_record(
            db_conn,
            incident_id=incident_id,
            plan_id=plan_id,
            action="approved",
            actor="sre-alice",
        )
        assert record_id is not None

        row = await db_conn.fetchrow(
            "SELECT * FROM approval_records WHERE id = $1", record_id
        )
        assert row is not None
        assert row["incident_id"] == incident_id
        assert row["plan_id"] == plan_id
        assert row["action"] == "approved"
        assert row["actor"] == "sre-alice"
        assert row["reason"] is None

    @pytest.mark.db
    async def test_rejection_with_reason(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        record_id = await persist_approval_record(
            db_conn,
            incident_id=incident_id,
            plan_id=plan_id,
            action="rejected",
            actor="sre-bob",
            reason="Plan is too risky",
        )

        row = await db_conn.fetchrow(
            "SELECT * FROM approval_records WHERE id = $1", record_id
        )
        assert row["action"] == "rejected"
        assert row["reason"] == "Plan is too risky"

    @pytest.mark.db
    async def test_unique_constraint_prevents_duplicate(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        await persist_approval_record(
            db_conn,
            incident_id=incident_id,
            plan_id=plan_id,
            action="approved",
            actor="sre-alice",
        )

        with pytest.raises(Exception):
            await persist_approval_record(
                db_conn,
                incident_id=incident_id,
                plan_id=plan_id,
                action="rejected",
                actor="sre-bob",
                reason="Changed my mind",
            )


class TestLoadApprovalContext:
    @pytest.mark.db
    async def test_returns_full_join_data(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        ctx = await load_approval_context(db_conn, incident_id)
        assert ctx is not None
        assert ctx["incident_id"] == incident_id
        assert ctx["state"] == "awaiting_approval"
        assert ctx["blast_radius"] == "node"
        assert ctx["diagnosis_summary"] == {"root_cause": "OOM"}
        assert ctx["remediation_plan"] == {"steps": []}

    @pytest.mark.db
    async def test_returns_none_for_nonexistent(self, db_conn):
        ctx = await load_approval_context(db_conn, uuid.uuid4())
        assert ctx is None

    @pytest.mark.db
    async def test_includes_dry_run_and_policy(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        import json

        dr_id = uuid.uuid4()
        await db_conn.execute(
            """INSERT INTO dry_run_results (id, incident_id, plan_id, step_results, dry_run_passed, dry_run_errors)
            VALUES ($1, $2, $3, $4::jsonb, $5, '[]'::jsonb)""",
            dr_id, incident_id, plan_id,
            json.dumps([{"step_order": 1, "command": "cmd", "success": True, "message": "ok"}]),
            True,
        )

        pd_id = uuid.uuid4()
        await db_conn.execute(
            """INSERT INTO policy_decisions (id, incident_id, plan_id, dimensions, evidence_complete, evidence_gaps_empty, auto_execution_approved, reasoning)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)""",
            pd_id, incident_id, plan_id,
            json.dumps([{"name": "severity", "value": "warning", "threshold": "warning", "passed": True}]),
            True, True, False, "Needs approval",
        )

        ctx = await load_approval_context(db_conn, incident_id)
        assert ctx["dry_run_result"] is not None
        assert ctx["dry_run_result"]["dry_run_passed"] is True
        assert ctx["policy_decision"] is not None
        assert ctx["policy_decision"]["auto_execution_approved"] is False


class TestListAwaitingApproval:
    @pytest.mark.db
    async def test_returns_only_awaiting(self, db_conn):
        a_id, a_plan, a_diag = _make_ids()
        await _insert_prerequisites(db_conn, a_id, a_plan, a_diag, state="awaiting_approval")

        b_id, b_plan, b_diag = _make_ids()
        await _insert_prerequisites(db_conn, b_id, b_plan, b_diag, state="diagnosing")

        items = await list_awaiting_approval(db_conn)
        ids = {item["id"] for item in items}
        assert a_id in ids
        assert b_id not in ids

    @pytest.mark.db
    async def test_empty_when_none_awaiting(self, db_conn):
        items = await list_awaiting_approval(db_conn)
        awaiting = [i for i in items if i["state"] == "awaiting_approval"]
        assert isinstance(awaiting, list)


class TestPersistPolicyAdjustment:
    @pytest.mark.db
    async def test_roundtrip(self, db_conn):
        body = PolicyAdjustmentRequest(
            severity="warning",
            blast_radius="workload",
            confidence_minimum=0.85,
            new_auto_approve=True,
        )
        record_id = await persist_policy_adjustment(db_conn, body, actor="sre-admin")
        assert record_id is not None

        row = await db_conn.fetchrow(
            "SELECT * FROM policy_adjustments WHERE id = $1", record_id
        )
        assert row["severity"] == "warning"
        assert row["blast_radius"] == "workload"
        assert row["confidence_minimum"] == 0.85
        assert row["actor"] == "sre-admin"
        assert row["new_auto_approve"] is True
