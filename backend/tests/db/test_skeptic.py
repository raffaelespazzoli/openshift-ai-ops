"""DB integration tests for skeptic persistence (testcontainers).

Tests persist_skeptic_record and persist_immutable_diagnosis roundtrip.
These tests require a running container runtime (Docker/Podman).
"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from src.db.diagnosis import persist_immutable_diagnosis
from src.db.skeptic import persist_skeptic_record


@pytest.mark.db
class TestPersistSkepticRecord:
    """persist_skeptic_record writes round data to skeptic_reviews table."""

    async def test_persist_single_round(self, db_conn):
        incident_id = await _create_test_incident(db_conn)
        challenge = {"alternative_hypotheses": ["alt"], "overall_assessment": "test"}
        response = {"rebuttals": [], "summary": "defended"}

        record_id = await persist_skeptic_record(
            db_conn,
            incident_id=incident_id,
            round_number=1,
            challenge=challenge,
            response=response,
        )

        assert record_id is not None
        row = await db_conn.fetchrow(
            "SELECT * FROM skeptic_reviews WHERE id = $1", record_id
        )
        assert row is not None
        assert row["incident_id"] == incident_id
        assert row["round_number"] == 1
        stored_challenge = json.loads(row["challenge"])
        assert stored_challenge["alternative_hypotheses"] == ["alt"]

    async def test_persist_with_verdict(self, db_conn):
        incident_id = await _create_test_incident(db_conn)
        verdict = {"passed": True, "rounds_completed": 1}

        record_id = await persist_skeptic_record(
            db_conn,
            incident_id=incident_id,
            round_number=1,
            challenge={"test": True},
            response={"test": True},
            verdict=verdict,
        )

        row = await db_conn.fetchrow(
            "SELECT verdict FROM skeptic_reviews WHERE id = $1", record_id
        )
        stored_verdict = json.loads(row["verdict"])
        assert stored_verdict["passed"] is True

    async def test_unique_constraint_incident_round(self, db_conn):
        incident_id = await _create_test_incident(db_conn)
        await persist_skeptic_record(
            db_conn,
            incident_id=incident_id,
            round_number=1,
            challenge={"test": True},
            response={"test": True},
        )

        with pytest.raises(Exception):
            await persist_skeptic_record(
                db_conn,
                incident_id=incident_id,
                round_number=1,
                challenge={"test": "duplicate"},
                response={"test": "duplicate"},
            )


@pytest.mark.db
class TestPersistImmutableDiagnosis:
    """persist_immutable_diagnosis writes sealed artifact to immutable_diagnoses."""

    async def test_persist_sealed_artifact(self, db_conn):
        incident_id = await _create_test_incident(db_conn)
        diagnosis = {
            "root_cause_code": "workload/crash-loop-backoff",
            "confidence": 0.85,
        }
        verdict = {"passed": True, "rounds_completed": 1}
        sealed_at = datetime.now(timezone.utc)

        record_id = await persist_immutable_diagnosis(
            db_conn,
            incident_id=incident_id,
            diagnosis=diagnosis,
            skeptic_verdict=verdict,
            sealed_at=sealed_at,
        )

        assert record_id is not None
        row = await db_conn.fetchrow(
            "SELECT * FROM immutable_diagnoses WHERE id = $1", record_id
        )
        assert row is not None
        stored_diag = json.loads(row["diagnosis"])
        assert stored_diag["root_cause_code"] == "workload/crash-loop-backoff"

    async def test_unique_constraint_incident(self, db_conn):
        incident_id = await _create_test_incident(db_conn)
        sealed_at = datetime.now(timezone.utc)

        await persist_immutable_diagnosis(
            db_conn,
            incident_id=incident_id,
            diagnosis={"test": True},
            skeptic_verdict={"passed": True},
            sealed_at=sealed_at,
        )

        with pytest.raises(Exception):
            await persist_immutable_diagnosis(
                db_conn,
                incident_id=incident_id,
                diagnosis={"test": "duplicate"},
                skeptic_verdict={"passed": True},
                sealed_at=sealed_at,
            )

    async def test_jsonb_roundtrip(self, db_conn):
        """JSONB roundtrip: persisted and retrieved data matches."""
        incident_id = await _create_test_incident(db_conn)
        diagnosis = {
            "root_cause_code": "node/memory-pressure",
            "confidence": 0.92,
            "causal_chain": ["memory spike", "eviction"],
        }
        verdict = {
            "passed": True,
            "rounds_completed": 2,
            "original_hash": "abc123",
            "final_hash": "def456",
        }
        sealed_at = datetime.now(timezone.utc)

        record_id = await persist_immutable_diagnosis(
            db_conn,
            incident_id=incident_id,
            diagnosis=diagnosis,
            skeptic_verdict=verdict,
            sealed_at=sealed_at,
        )

        row = await db_conn.fetchrow(
            "SELECT diagnosis, skeptic_verdict FROM immutable_diagnoses WHERE id = $1",
            record_id,
        )
        stored_diag = json.loads(row["diagnosis"])
        stored_verdict = json.loads(row["skeptic_verdict"])
        assert stored_diag == diagnosis
        assert stored_verdict == verdict


async def _create_test_incident(conn) -> uuid.UUID:
    """Create a minimal incident for FK references."""
    incident_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO incidents (id, state, severity, title, created_at, updated_at)
        VALUES ($1, 'diagnosing', 'critical', 'Test incident', NOW(), NOW())
        """,
        incident_id,
    )
    return incident_id
