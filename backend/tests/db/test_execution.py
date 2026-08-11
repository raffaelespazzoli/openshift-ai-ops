"""DB integration tests for execution persistence (Story 3.5).

Tests: persist_execution_log, persist_outcome_result, persist_rollback_record roundtrip.
"""

import json
import uuid
from datetime import datetime, timezone

import asyncpg
import pytest

from src.db.execution import (
    load_execution_log,
    load_outcome_result,
    load_rollback_records,
    persist_execution_log,
    persist_outcome_result,
    persist_rollback_record,
)
from src.models.execution import (
    ExecutionLog,
    ExecutionStepLog,
    OutcomeResult,
    RollbackRecord,
)

pytestmark = pytest.mark.db


async def _seed_incident_and_plan(conn):
    """Insert minimal incident + plan for FK references."""
    incident_id = uuid.uuid4()
    diagnosis_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    await conn.execute(
        "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, 'executing', 'critical', $2, $3)",
        incident_id, now, now,
    )
    await conn.execute(
        """INSERT INTO immutable_diagnoses (id, incident_id, diagnosis, skeptic_verdict, sealed_at)
        VALUES ($1, $2, '{"root_cause": "test"}'::jsonb, '{}'::jsonb, NOW())""",
        diagnosis_id, incident_id,
    )
    await conn.execute(
        """INSERT INTO remediation_plans (id, incident_id, diagnosis_id, plan, blast_radius, estimated_risk, created_at)
        VALUES ($1, $2, $3, '{"steps": []}'::jsonb, 'workload', 'low', NOW())""",
        plan_id, incident_id, diagnosis_id,
    )
    return incident_id, plan_id, diagnosis_id


class TestPersistExecutionLog:
    """persist_execution_log roundtrip."""

    async def test_roundtrip(self, db_conn):
        incident_id, plan_id, _ = await _seed_incident_and_plan(db_conn)

        log = ExecutionLog(
            incident_id=incident_id,
            plan_id=plan_id,
            steps=[
                ExecutionStepLog(
                    step_order=1,
                    command="kubectl apply",
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    success=True,
                    output="applied",
                ),
            ],
            mcp_calls=[{"tool": "apply_resource", "step_order": 1}],
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            status="completed",
        )

        await persist_execution_log(db_conn, log)
        loaded = await load_execution_log(db_conn, incident_id)

        assert loaded is not None
        assert loaded.id == log.id
        assert loaded.incident_id == incident_id
        assert loaded.status == "completed"
        assert len(loaded.steps) == 1
        assert loaded.steps[0].command == "kubectl apply"


class TestPersistOutcomeResult:
    """persist_outcome_result roundtrip."""

    async def test_roundtrip(self, db_conn):
        incident_id, _, _ = await _seed_incident_and_plan(db_conn)

        result = OutcomeResult(
            incident_id=incident_id,
            alert_resolved=True,
            resolution_method="webhook",
            resource_verification={"all_healthy": True},
            outcome_confidence=0.7,
            refire_detected=False,
            observation_started_at=datetime.now(timezone.utc),
            observation_completed_at=datetime.now(timezone.utc),
            timeout_seconds=300,
        )

        await persist_outcome_result(db_conn, result)
        loaded = await load_outcome_result(db_conn, incident_id)

        assert loaded is not None
        assert loaded.id == result.id
        assert loaded.alert_resolved is True
        assert loaded.outcome_confidence == 0.7
        assert loaded.resource_verification == {"all_healthy": True}


class TestPersistRollbackRecord:
    """persist_rollback_record roundtrip."""

    async def test_roundtrip(self, db_conn):
        incident_id, plan_id, _ = await _seed_incident_and_plan(db_conn)

        record = RollbackRecord(
            incident_id=incident_id,
            plan_id=plan_id,
            actor="sre-admin",
            steps_executed=[
                ExecutionStepLog(
                    step_order=1,
                    command="kubectl rollback",
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    success=True,
                    output="rolled back",
                ),
            ],
            success=True,
        )

        await persist_rollback_record(db_conn, record)
        loaded = await load_rollback_records(db_conn, incident_id)

        assert len(loaded) == 1
        assert loaded[0].id == record.id
        assert loaded[0].actor == "sre-admin"
        assert loaded[0].success is True

    async def test_multiple_rollbacks_same_incident(self, db_conn):
        incident_id, plan_id, _ = await _seed_incident_and_plan(db_conn)

        for i in range(2):
            record = RollbackRecord(
                incident_id=incident_id,
                plan_id=plan_id,
                actor=f"user-{i}",
                success=True,
            )
            await persist_rollback_record(db_conn, record)

        loaded = await load_rollback_records(db_conn, incident_id)
        assert len(loaded) == 2
