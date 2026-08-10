"""DB integration tests for remediation plan persistence (Story 3.1).

Tests persist_remediation_plan roundtrip, unique constraint on incident_id,
and load_immutable_artifact retrieval. Requires testcontainers.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from src.db.remediation import load_immutable_artifact, persist_remediation_plan
from src.models.remediation import (
    BlastRadius,
    Precondition,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)


def _make_plan(incident_id=None, diagnosis_id=None) -> RemediationPlan:
    return RemediationPlan(
        incident_id=incident_id or uuid.uuid4(),
        diagnosis_id=diagnosis_id or uuid.uuid4(),
        steps=[
            RemediationStep(
                order=1,
                description="Increase memory limit",
                command="kubectl set resources deploy/app --limits=memory=512Mi",
                resource="deployment/app",
                action="patch",
                expected_outcome="Pod restarts with higher memory",
            ),
        ],
        blast_radius=BlastRadius.WORKLOAD,
        rollback_plan=[
            RemediationStep(
                order=1,
                description="Revert memory limit",
                command="kubectl set resources deploy/app --limits=memory=256Mi",
                resource="deployment/app",
                action="patch",
                expected_outcome="Pod reverts to original memory",
            ),
        ],
        estimated_risk=RiskLevel.LOW,
        preconditions=[
            Precondition(
                type="rbac",
                description="Can patch deployments",
                requirement="patch on deployments",
                satisfied=True,
            ),
        ],
        plan_summary="Fix OOM crash loop by increasing memory limit",
    )


async def _insert_incident(conn, incident_id: uuid.UUID) -> None:
    """Insert a minimal incident row for FK satisfaction."""
    await conn.execute(
        """
        INSERT INTO incidents (id, state, severity, created_at, updated_at)
        VALUES ($1, 'diagnosed', 'critical', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """,
        incident_id,
    )


async def _insert_immutable_diagnosis(
    conn, incident_id: uuid.UUID, diagnosis_id: uuid.UUID | None = None
) -> uuid.UUID:
    """Insert an immutable_diagnoses row for load_immutable_artifact tests."""
    did = diagnosis_id or uuid.uuid4()
    diagnosis = {
        "id": str(did),
        "incident_id": str(incident_id),
        "root_cause_component": "workload",
        "failure_mode": "crash-loop-backoff",
        "root_cause_code": "workload/crash-loop-backoff",
        "causal_chain": ["Pod CrashLoopBackOff", "OOM killed"],
        "affected_resources": ["pod/test-pod"],
        "evidence": [
            {
                "source": "mcp_cluster",
                "query": "get_resources",
                "result": "{}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "evidence_gaps": [],
        "confidence": 0.85,
        "agent_summary": "OOM crash loop",
        "coverage_gaps": [],
        "alternative_hypotheses": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    skeptic_verdict = {
        "passed": True,
        "rounds_completed": 1,
        "original_hash": "a" * 64,
        "final_hash": "a" * 64,
        "challenge_history": [{"round": 1}],
        "verdict_reasoning": "validated",
    }
    await conn.execute(
        """
        INSERT INTO immutable_diagnoses (id, incident_id, diagnosis, skeptic_verdict, sealed_at, created_at)
        VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6)
        """,
        did,
        incident_id,
        json.dumps(diagnosis, default=str),
        json.dumps(skeptic_verdict, default=str),
        datetime.now(timezone.utc),
        datetime.now(timezone.utc),
    )
    return did


class TestPersistRemediationPlan:
    """persist_remediation_plan writes plan to remediation_plans table."""

    @pytest.mark.db
    async def test_persist_roundtrip(self, db_conn):
        incident_id = uuid.uuid4()
        await _insert_incident(db_conn, incident_id)

        plan = _make_plan(incident_id=incident_id)
        result_id = await persist_remediation_plan(db_conn, plan)

        assert result_id == plan.id

        row = await db_conn.fetchrow(
            "SELECT * FROM remediation_plans WHERE id = $1", plan.id
        )
        assert row is not None
        assert row["incident_id"] == incident_id
        assert row["blast_radius"] == "workload"
        assert row["estimated_risk"] == "low"

    @pytest.mark.db
    async def test_jsonb_plan_roundtrip(self, db_conn):
        incident_id = uuid.uuid4()
        await _insert_incident(db_conn, incident_id)

        plan = _make_plan(incident_id=incident_id)
        await persist_remediation_plan(db_conn, plan)

        row = await db_conn.fetchrow(
            "SELECT plan FROM remediation_plans WHERE incident_id = $1",
            incident_id,
        )
        plan_data = json.loads(row["plan"])
        restored = RemediationPlan.model_validate(plan_data)
        assert restored.blast_radius == plan.blast_radius
        assert len(restored.steps) == len(plan.steps)
        assert restored.plan_summary == plan.plan_summary

    @pytest.mark.db
    async def test_unique_constraint_on_incident_id(self, db_conn):
        incident_id = uuid.uuid4()
        await _insert_incident(db_conn, incident_id)

        plan1 = _make_plan(incident_id=incident_id)
        await persist_remediation_plan(db_conn, plan1)

        plan2 = _make_plan(incident_id=incident_id)
        with pytest.raises(Exception):
            await persist_remediation_plan(db_conn, plan2)


class TestLoadImmutableArtifact:
    """load_immutable_artifact retrieves and reconstructs ImmutableDiagnosisArtifact."""

    @pytest.mark.db
    async def test_load_artifact_success(self, db_conn):
        incident_id = uuid.uuid4()
        await _insert_incident(db_conn, incident_id)
        await _insert_immutable_diagnosis(db_conn, incident_id)

        artifact = await load_immutable_artifact(db_conn, incident_id)

        assert artifact.incident_id == incident_id
        assert artifact.root_cause_code == "workload/crash-loop-backoff"
        assert artifact.confidence == 0.85

    @pytest.mark.db
    async def test_load_artifact_not_found_raises(self, db_conn):
        missing_id = uuid.uuid4()
        with pytest.raises(ValueError, match="No immutable diagnosis found"):
            await load_immutable_artifact(db_conn, missing_id)

    @pytest.mark.db
    async def test_artifact_is_frozen(self, db_conn):
        incident_id = uuid.uuid4()
        await _insert_incident(db_conn, incident_id)
        await _insert_immutable_diagnosis(db_conn, incident_id)

        artifact = await load_immutable_artifact(db_conn, incident_id)

        with pytest.raises(Exception):
            artifact.root_cause_code = "node/memory-pressure"
