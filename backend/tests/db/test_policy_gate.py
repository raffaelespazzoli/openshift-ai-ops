"""DB integration tests for policy gate persistence (Story 3.3).

Tests persist_dry_run_result and persist_policy_decision roundtrip
with testcontainers PostgreSQL.
"""

import uuid
from datetime import datetime, timezone

import pytest

from src.db.policy_gate import (
    load_dry_run_result,
    load_policy_decision,
    persist_dry_run_result,
    persist_policy_decision,
)
from src.models.policy_gate import (
    DryRunResult,
    DryRunStepResult,
    PolicyDecision,
    PolicyDimension,
)


def _make_ids():
    """Create test UUIDs and insert prerequisite rows."""
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


async def _insert_prerequisites(conn, incident_id, plan_id, diagnosis_id):
    """Insert incident and plan rows that dry_run_results/policy_decisions FK to."""
    await conn.execute(
        "INSERT INTO incidents (id, state, created_at) VALUES ($1, 'diagnosed', NOW())",
        incident_id,
    )
    await conn.execute(
        """INSERT INTO immutable_diagnoses (id, incident_id, diagnosis, skeptic_verdict, sealed_at)
        VALUES ($1, $2, '{}', '{}', NOW())""",
        diagnosis_id,
        incident_id,
    )
    await conn.execute(
        """INSERT INTO remediation_plans (id, incident_id, diagnosis_id, plan, blast_radius, estimated_risk, created_at)
        VALUES ($1, $2, $3, '{}', 'workload', 'low', NOW())""",
        plan_id,
        incident_id,
        diagnosis_id,
    )


class TestPersistDryRunResult:
    @pytest.mark.db
    async def test_roundtrip(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        dr = DryRunResult(
            incident_id=incident_id,
            plan_id=plan_id,
            step_results=[
                DryRunStepResult(
                    step_order=1, command="oc apply", success=True, message="ok"
                ),
                DryRunStepResult(
                    step_order=2, command="oc set", success=False,
                    message="denied", error_detail="RBAC",
                ),
            ],
            dry_run_passed=False,
            dry_run_errors=["RBAC"],
        )

        result_id = await persist_dry_run_result(db_conn, dr)
        assert result_id == dr.id

        loaded = await load_dry_run_result(db_conn, incident_id)
        assert loaded is not None
        assert loaded.id == dr.id
        assert loaded.incident_id == incident_id
        assert loaded.dry_run_passed is False
        assert loaded.dry_run_errors == ["RBAC"]
        assert len(loaded.step_results) == 2
        assert loaded.step_results[0].success is True
        assert loaded.step_results[1].success is False

    @pytest.mark.db
    async def test_unique_constraint(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        dr = DryRunResult(
            incident_id=incident_id,
            plan_id=plan_id,
            step_results=[
                DryRunStepResult(
                    step_order=1, command="cmd", success=True, message="ok"
                ),
            ],
            dry_run_passed=True,
            dry_run_errors=[],
        )

        await persist_dry_run_result(db_conn, dr)

        dr2 = DryRunResult(
            incident_id=incident_id,
            plan_id=plan_id,
            step_results=[
                DryRunStepResult(
                    step_order=1, command="cmd2", success=True, message="ok"
                ),
            ],
            dry_run_passed=True,
            dry_run_errors=[],
        )

        with pytest.raises(Exception):
            await persist_dry_run_result(db_conn, dr2)


class TestPersistPolicyDecision:
    @pytest.mark.db
    async def test_roundtrip(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        decision = PolicyDecision(
            incident_id=incident_id,
            plan_id=plan_id,
            dimensions=[
                PolicyDimension(
                    name="severity", value="warning",
                    threshold="info,warning", passed=True,
                ),
                PolicyDimension(
                    name="blast_radius", value="workload",
                    threshold="workload", passed=True,
                ),
                PolicyDimension(
                    name="confidence", value=0.9,
                    threshold=0.8, passed=True,
                ),
            ],
            evidence_complete=True,
            evidence_gaps_empty=True,
            auto_execution_approved=True,
            reasoning="All checks pass",
        )

        result_id = await persist_policy_decision(db_conn, decision)
        assert result_id == decision.id

        loaded = await load_policy_decision(db_conn, incident_id)
        assert loaded is not None
        assert loaded.id == decision.id
        assert loaded.auto_execution_approved is True
        assert loaded.evidence_complete is True
        assert len(loaded.dimensions) == 3
        assert loaded.reasoning == "All checks pass"

    @pytest.mark.db
    async def test_unique_constraint(self, db_conn):
        incident_id, plan_id, diagnosis_id = _make_ids()
        await _insert_prerequisites(db_conn, incident_id, plan_id, diagnosis_id)

        decision = PolicyDecision(
            incident_id=incident_id,
            plan_id=plan_id,
            dimensions=[
                PolicyDimension(
                    name="confidence", value=0.9, threshold=0.8, passed=True
                ),
            ],
            evidence_complete=True,
            evidence_gaps_empty=True,
            auto_execution_approved=True,
            reasoning="Pass",
        )

        await persist_policy_decision(db_conn, decision)

        decision2 = PolicyDecision(
            incident_id=incident_id,
            plan_id=plan_id,
            dimensions=[
                PolicyDimension(
                    name="confidence", value=0.5, threshold=0.8, passed=False
                ),
            ],
            evidence_complete=False,
            evidence_gaps_empty=False,
            auto_execution_approved=False,
            reasoning="Fail",
        )

        with pytest.raises(Exception):
            await persist_policy_decision(db_conn, decision2)
