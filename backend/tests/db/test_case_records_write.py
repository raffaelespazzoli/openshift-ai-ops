"""Unit + integration tests for case_records write operations (Story 4.1).

Unit tests: persist_case_record, downgrade_case_record, get_case_record_by_incident
with mocked asyncpg connections.

DB integration tests (marked @pytest.mark.db) require testcontainers.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.case_records import (
    downgrade_case_record,
    get_case_record_by_incident,
    persist_case_record,
)
from src.models.case_record import CaseRecord

pytestmark = pytest.mark.unit


def _make_case_record(**overrides) -> CaseRecord:
    defaults = {
        "incident_id": uuid.uuid4(),
        "alert_signature": "KubePodCrashLooping production critical",
        "root_cause_code": "workload/crash-loop",
        "diagnosis_object": {"root_cause_component": "workload"},
        "remediation_plan": {"steps": []},
        "outcome": "success",
        "outcome_confidence": 0.7,
        "outcome_details": {"alert_resolved": True},
        "ocp_version": "4.16",
    }
    defaults.update(overrides)
    return CaseRecord(**defaults)


class TestPersistCaseRecord:
    async def test_persist_with_embedding(self):
        conn = AsyncMock()
        conn.execute = AsyncMock()
        record = _make_case_record()
        embedding = [0.1] * 1536

        result = await persist_case_record(conn, record, embedding)

        assert result == record.id
        conn.execute.assert_called_once()
        call_args = conn.execute.call_args[0]
        assert "INSERT INTO case_records" in call_args[0]
        assert call_args[4] == str(embedding)

    async def test_persist_without_embedding(self):
        conn = AsyncMock()
        conn.execute = AsyncMock()
        record = _make_case_record()

        result = await persist_case_record(conn, record, embedding=None)

        assert result == record.id
        conn.execute.assert_called_once()
        call_args = conn.execute.call_args[0]
        assert call_args[4] is None

    async def test_persist_stores_all_fields(self):
        conn = AsyncMock()
        conn.execute = AsyncMock()
        record = _make_case_record(
            cluster_context={"ocp_version": "4.16"},
            diagnosis_summary="OOM crash loop",
            remediation_summary="Restart pod",
            fast_path_eligible=False,
        )

        await persist_case_record(conn, record)

        call_args = conn.execute.call_args[0]
        assert call_args[1] == record.id
        assert call_args[2] == record.incident_id
        assert call_args[3] == record.alert_signature
        assert call_args[5] == record.root_cause_code
        assert call_args[6] == record.outcome
        assert call_args[7] == record.outcome_confidence
        assert call_args[9] == json.dumps(record.cluster_context)
        assert call_args[10] == record.diagnosis_summary
        assert call_args[11] == record.remediation_summary
        assert call_args[15] == record.fast_path_eligible


class TestDowngradeCaseRecord:
    async def test_downgrade_returns_true_when_updated(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")
        incident_id = uuid.uuid4()

        result = await downgrade_case_record(
            conn, incident_id, new_confidence=0.2, reason="re-fire"
        )

        assert result is True
        conn.execute.assert_called_once()
        call_args = conn.execute.call_args[0]
        assert "UPDATE case_records" in call_args[0]
        assert "fast_path_eligible = FALSE" in call_args[0]
        assert call_args[1] == incident_id
        assert call_args[2] == 0.2

    async def test_downgrade_returns_false_when_no_record(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 0")

        result = await downgrade_case_record(
            conn, uuid.uuid4(), new_confidence=0.2, reason="rollback"
        )

        assert result is False


class TestGetCaseRecordByIncident:
    async def test_returns_dict_when_found(self):
        incident_id = uuid.uuid4()
        fake_row = {
            "id": uuid.uuid4(),
            "incident_id": incident_id,
            "alert_signature": "test",
            "root_cause_code": "workload/crash-loop",
            "outcome": "success",
            "outcome_confidence": 0.7,
            "ocp_version": "4.16",
            "cluster_context": "{}",
            "diagnosis_summary": "",
            "remediation_summary": "",
            "diagnosis_object": "{}",
            "remediation_plan": "{}",
            "outcome_details": "{}",
            "fast_path_eligible": True,
            "created_at": datetime.now(timezone.utc),
        }

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=fake_row)

        result = await get_case_record_by_incident(conn, incident_id)
        assert result is not None
        assert result["incident_id"] == incident_id
        assert result["outcome"] == "success"
        conn.fetchrow.assert_called_once()

    async def test_returns_none_when_not_found(self):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)

        result = await get_case_record_by_incident(conn, uuid.uuid4())
        assert result is None
