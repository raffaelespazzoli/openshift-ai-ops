"""DB integration tests for remediation skeptic persistence (testcontainers).

Tests persist_remediation_skeptic_record roundtrip, multiple rounds,
and JSONB integrity. These tests require a running container runtime.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from src.db.remediation_skeptic import persist_remediation_skeptic_record


@pytest.mark.db
class TestPersistRemediationSkepticRecord:
    """persist_remediation_skeptic_record writes round data to remediation_skeptic_reviews."""

    async def test_persist_single_round(self, db_conn):
        incident_id = await _create_test_incident(db_conn)
        challenge = {
            "step_correctness_issues": ["issue1"],
            "blast_radius_assessment": "accurate",
            "overall_verdict": "minor revisions needed",
        }
        response = {
            "plan_summary": "revised plan",
            "steps": [{"order": 1, "description": "fix"}],
        }

        record_id = await persist_remediation_skeptic_record(
            db_conn,
            incident_id=incident_id,
            round_number=1,
            challenge=challenge,
            response=response,
        )

        assert record_id is not None
        row = await db_conn.fetchrow(
            "SELECT * FROM remediation_skeptic_reviews WHERE id = $1", record_id
        )
        assert row is not None
        assert row["incident_id"] == incident_id
        assert row["round_number"] == 1
        stored_challenge = json.loads(row["challenge"])
        assert stored_challenge["step_correctness_issues"] == ["issue1"]

    async def test_persist_with_verdict(self, db_conn):
        incident_id = await _create_test_incident(db_conn)
        verdict = {"passed": True, "rounds_completed": 1}

        record_id = await persist_remediation_skeptic_record(
            db_conn,
            incident_id=incident_id,
            round_number=1,
            challenge={"test": True},
            response={"test": True},
            verdict=verdict,
        )

        row = await db_conn.fetchrow(
            "SELECT verdict FROM remediation_skeptic_reviews WHERE id = $1",
            record_id,
        )
        stored_verdict = json.loads(row["verdict"])
        assert stored_verdict["passed"] is True

    async def test_multiple_rounds_same_incident(self, db_conn):
        """Multiple rounds for the same incident persist without constraint violation."""
        incident_id = await _create_test_incident(db_conn)

        id1 = await persist_remediation_skeptic_record(
            db_conn,
            incident_id=incident_id,
            round_number=1,
            challenge={"round": 1},
            response={"round": 1},
        )
        id2 = await persist_remediation_skeptic_record(
            db_conn,
            incident_id=incident_id,
            round_number=2,
            challenge={"round": 2},
            response={"round": 2},
            verdict={"passed": True, "rounds_completed": 2},
        )

        assert id1 != id2
        count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM remediation_skeptic_reviews WHERE incident_id = $1",
            incident_id,
        )
        assert count == 2

    async def test_jsonb_roundtrip(self, db_conn):
        """JSONB roundtrip: persisted and retrieved data matches originals."""
        incident_id = await _create_test_incident(db_conn)
        challenge = {
            "step_correctness_issues": ["issue A", "issue B"],
            "blast_radius_assessment": "under-estimated",
            "rollback_feasibility_issues": ["no rollback for step 2"],
            "precondition_gaps": ["missing quota check"],
            "risk_assessment_critique": "should be medium",
            "overall_verdict": "plan needs revision",
        }
        response = {
            "steps": [
                {"order": 1, "description": "revised step"},
            ],
            "blast_radius": "namespace",
            "estimated_risk": "medium",
            "plan_summary": "Revised plan addressing skeptic concerns",
        }

        record_id = await persist_remediation_skeptic_record(
            db_conn,
            incident_id=incident_id,
            round_number=1,
            challenge=challenge,
            response=response,
        )

        row = await db_conn.fetchrow(
            "SELECT challenge, response FROM remediation_skeptic_reviews WHERE id = $1",
            record_id,
        )
        stored_challenge = json.loads(row["challenge"])
        stored_response = json.loads(row["response"])
        assert stored_challenge == challenge
        assert stored_response == response


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
