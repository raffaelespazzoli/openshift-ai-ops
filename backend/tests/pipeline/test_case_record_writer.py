"""Unit tests for case_record_writer (Story 4.1).

Tests create_case_record: success path, failure path, embedding failure,
missing data, and build_alert_signature determinism.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipeline.case_record_writer import build_alert_signature, create_case_record

pytestmark = pytest.mark.unit


class _AsyncCtx:
    def __init__(self, val):
        self._val = val

    async def __aenter__(self):
        return self._val

    async def __aexit__(self, *args):
        pass


def _mock_pool(conn):
    pool = MagicMock()
    pool.acquire.return_value = _AsyncCtx(conn)
    return pool


def _make_alerts():
    return [
        {
            "name": "KubePodCrashLooping",
            "status": "firing",
            "labels": '{"namespace": "production", "severity": "critical"}',
            "annotations": '{"summary": "Pod is crash looping"}',
            "fingerprint": "abc123",
        }
    ]


def _make_diagnosis():
    return {
        "root_cause_component": "workload",
        "failure_mode": "crash-loop",
        "root_cause_code": "workload/crash-loop",
        "agent_summary": "Pod crash loop due to OOM",
    }


def _make_outcome(resolved=True, refire=False):
    return {
        "alert_resolved": resolved,
        "resolution_method": "webhook" if resolved else "timeout",
        "resource_verification": None,
        "outcome_confidence": 0.7 if resolved else 0.2,
        "refire_detected": refire,
    }


def _make_plan():
    return {
        "steps": [{"order": 1, "description": "Apply fix"}],
        "plan_summary": "Restart crashing pod",
    }


def _setup_conn(
    alerts=None,
    diagnosis=None,
    plan=None,
    outcome=None,
    rollback_exists=False,
):
    conn = AsyncMock()

    async def _fetch(query, *args):
        if "FROM alerts" in query:
            return alerts or []
        return []

    async def _fetchrow(query, *args):
        if "FROM immutable_diagnoses" in query:
            if diagnosis is None:
                return None
            return {"diagnosis": diagnosis}
        if "FROM remediation_plans" in query:
            if plan is None:
                return None
            return {"plan": plan}
        if "FROM outcome_results" in query:
            if outcome is None:
                return None
            return outcome
        return None

    async def _fetchval(query, *args):
        if "rollback_records" in query:
            return rollback_exists
        return None

    conn.fetch = _fetch
    conn.fetchrow = _fetchrow
    conn.fetchval = _fetchval
    conn.execute = AsyncMock()
    return conn


class TestBuildAlertSignature:
    def test_deterministic_sorted_output(self):
        alerts = [
            {"name": "B-Alert", "labels": {"namespace": "ns1", "severity": "warning"},
             "annotations": {"summary": "B summary"}},
            {"name": "A-Alert", "labels": {"namespace": "ns2", "severity": "critical"},
             "annotations": {"summary": "A summary"}},
        ]
        result = build_alert_signature(alerts)
        assert result.startswith("A-Alert")
        assert "B-Alert" in result

    def test_same_input_same_output(self):
        alerts = [
            {"name": "Alert1", "labels": {}, "annotations": {}},
        ]
        assert build_alert_signature(alerts) == build_alert_signature(alerts)

    def test_empty_alerts(self):
        assert build_alert_signature([]) == ""

    def test_missing_fields_handled(self):
        alerts = [{"name": "X"}]
        result = build_alert_signature(alerts)
        assert "X" in result


class TestCreateCaseRecordSuccess:
    async def test_success_path_creates_record(self):
        alerts = _make_alerts()
        diagnosis = _make_diagnosis()
        outcome = _make_outcome(resolved=True)
        plan = _make_plan()
        conn = _setup_conn(
            alerts=alerts,
            diagnosis=diagnosis,
            plan=plan,
            outcome=outcome,
        )
        pool = _mock_pool(conn)
        mock_embedding = [0.1] * 1536

        with patch(
            "src.pipeline.case_record_writer.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            with patch(
                "src.knowledge.embeddings.embed_texts",
                new_callable=AsyncMock,
                return_value=[mock_embedding],
            ):
                with patch(
                    "src.pipeline.case_record_writer.persist_case_record",
                    new_callable=AsyncMock,
                ) as mock_persist:
                    incident_id = uuid.uuid4()
                    result = await create_case_record(incident_id)

                    assert result is not None
                    assert result.outcome == "success"
                    assert result.fast_path_eligible is True
                    assert result.incident_id == incident_id
                    mock_persist.assert_called_once()
                    persist_args = mock_persist.call_args
                    assert persist_args[0][2] == mock_embedding


class TestCreateCaseRecordFailure:
    async def test_failure_outcome_not_fast_path_eligible(self):
        conn = _setup_conn(
            alerts=_make_alerts(),
            diagnosis=_make_diagnosis(),
            plan=_make_plan(),
            outcome=_make_outcome(resolved=False),
        )
        pool = _mock_pool(conn)

        with patch(
            "src.pipeline.case_record_writer.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            with patch(
                "src.knowledge.embeddings.embed_texts",
                new_callable=AsyncMock,
                return_value=[[0.1] * 1536],
            ):
                with patch(
                    "src.pipeline.case_record_writer.persist_case_record",
                    new_callable=AsyncMock,
                ):
                    result = await create_case_record(uuid.uuid4())

                    assert result is not None
                    assert result.outcome == "failure"
                    assert result.fast_path_eligible is False

    async def test_rollback_present_not_fast_path_eligible(self):
        conn = _setup_conn(
            alerts=_make_alerts(),
            diagnosis=_make_diagnosis(),
            plan=_make_plan(),
            outcome=_make_outcome(resolved=True),
            rollback_exists=True,
        )
        pool = _mock_pool(conn)

        with patch(
            "src.pipeline.case_record_writer.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            with patch(
                "src.knowledge.embeddings.embed_texts",
                new_callable=AsyncMock,
                return_value=[[0.1] * 1536],
            ):
                with patch(
                    "src.pipeline.case_record_writer.persist_case_record",
                    new_callable=AsyncMock,
                ):
                    result = await create_case_record(uuid.uuid4())

                    assert result is not None
                    assert result.fast_path_eligible is False


class TestCreateCaseRecordEmbeddingFailure:
    async def test_persists_without_vector_on_embedding_failure(self):
        conn = _setup_conn(
            alerts=_make_alerts(),
            diagnosis=_make_diagnosis(),
            plan=_make_plan(),
            outcome=_make_outcome(resolved=True),
        )
        pool = _mock_pool(conn)

        with patch(
            "src.pipeline.case_record_writer.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            with patch(
                "src.knowledge.embeddings.embed_texts",
                new_callable=AsyncMock,
                side_effect=Exception("embedding service down"),
            ):
                with patch(
                    "src.pipeline.case_record_writer.persist_case_record",
                    new_callable=AsyncMock,
                ) as mock_persist:
                    result = await create_case_record(uuid.uuid4())

                    assert result is not None
                    assert result.outcome == "success"
                    mock_persist.assert_called_once()
                    persist_args = mock_persist.call_args
                    assert persist_args[0][2] is None


class TestCreateCaseRecordMissingData:
    async def test_missing_diagnosis_returns_none(self):
        conn = _setup_conn(
            alerts=_make_alerts(),
            diagnosis=None,
            plan=_make_plan(),
            outcome=_make_outcome(resolved=True),
        )
        pool = _mock_pool(conn)

        with patch(
            "src.pipeline.case_record_writer.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            result = await create_case_record(uuid.uuid4())
            assert result is None

    async def test_missing_outcome_returns_none(self):
        conn = _setup_conn(
            alerts=_make_alerts(),
            diagnosis=_make_diagnosis(),
            plan=_make_plan(),
            outcome=None,
        )
        pool = _mock_pool(conn)

        with patch(
            "src.pipeline.case_record_writer.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            result = await create_case_record(uuid.uuid4())
            assert result is None

    async def test_persist_failure_returns_none(self):
        conn = _setup_conn(
            alerts=_make_alerts(),
            diagnosis=_make_diagnosis(),
            plan=_make_plan(),
            outcome=_make_outcome(resolved=True),
        )
        pool = _mock_pool(conn)

        with patch(
            "src.pipeline.case_record_writer.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            with patch(
                "src.knowledge.embeddings.embed_texts",
                new_callable=AsyncMock,
                return_value=[[0.1] * 1536],
            ):
                with patch(
                    "src.pipeline.case_record_writer.persist_case_record",
                    new_callable=AsyncMock,
                    side_effect=Exception("DB down"),
                ):
                    result = await create_case_record(uuid.uuid4())
                    assert result is None


class TestCreateCaseRecordRefireDetected:
    async def test_refire_detected_not_fast_path_eligible(self):
        conn = _setup_conn(
            alerts=_make_alerts(),
            diagnosis=_make_diagnosis(),
            plan=_make_plan(),
            outcome=_make_outcome(resolved=True, refire=True),
        )
        pool = _mock_pool(conn)

        with patch(
            "src.pipeline.case_record_writer.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            with patch(
                "src.knowledge.embeddings.embed_texts",
                new_callable=AsyncMock,
                return_value=[[0.1] * 1536],
            ):
                with patch(
                    "src.pipeline.case_record_writer.persist_case_record",
                    new_callable=AsyncMock,
                ):
                    result = await create_case_record(uuid.uuid4())

                    assert result is not None
                    assert result.fast_path_eligible is False
