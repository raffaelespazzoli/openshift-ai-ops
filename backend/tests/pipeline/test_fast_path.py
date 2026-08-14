"""Unit tests for fast-path check and runner (Story 4.3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipeline.fast_path import (
    FastPathMatch,
    _build_replayed_plan,
    _build_synthetic_artifact,
    check_fast_path,
    run_fast_path_pipeline,
)

pytestmark = pytest.mark.unit


def _make_item(alerts=None, incident_id=None, queue_item_id=None, severity="warning"):
    return {
        "id": queue_item_id or uuid.uuid4(),
        "incident_id": incident_id or uuid.uuid4(),
        "root_cause_event_id": uuid.uuid4(),
        "priority_score": 100,
        "severity": severity,
        "alerts": alerts or [
            {
                "name": "HighMemory",
                "labels": {"namespace": "default", "severity": "warning"},
                "annotations": {"summary": "Pod memory high"},
            }
        ],
    }


def _make_case_record_row(similarity=0.95, ocp_version="4.16"):
    return {
        "id": uuid.uuid4(),
        "alert_signature": "HighMemory default warning Pod memory high",
        "root_cause_code": "node/memory-pressure",
        "outcome": "success",
        "outcome_confidence": 0.9,
        "ocp_version": ocp_version,
        "created_at": datetime.now(timezone.utc),
        "diagnosis_object": {
            "id": str(uuid.uuid4()),
            "incident_id": str(uuid.uuid4()),
            "root_cause_component": "node",
            "failure_mode": "memory-pressure",
            "root_cause_code": "node/memory-pressure",
            "causal_chain": ["memory exhaustion", "OOM kill"],
            "affected_resources": ["pod/app-1"],
            "evidence": [],
            "evidence_gaps": [],
            "confidence": 0.92,
            "agent_summary": "Memory pressure",
            "skeptic_verdict": {"outcome": "approved", "source": "original"},
            "sealed_at": datetime.now(timezone.utc).isoformat(),
        },
        "remediation_plan": {
            "id": str(uuid.uuid4()),
            "incident_id": str(uuid.uuid4()),
            "diagnosis_id": str(uuid.uuid4()),
            "steps": [
                {
                    "order": 1,
                    "description": "Increase memory limit",
                    "command": "kubectl set resources",
                    "resource": "deployment/app",
                    "action": "patch",
                    "expected_outcome": "Memory limit increased",
                }
            ],
            "blast_radius": "workload",
            "rollback_plan": [],
            "estimated_risk": "low",
            "preconditions": [],
            "plan_summary": "Increase memory limits",
        },
        "similarity": similarity,
    }


def _make_match(similarity=0.95) -> FastPathMatch:
    row = _make_case_record_row(similarity)
    return FastPathMatch(
        case_record_id=row["id"],
        alert_signature=row["alert_signature"],
        root_cause_code=row["root_cause_code"],
        similarity=similarity,
        effective_confidence=0.88,
        ocp_version=row["ocp_version"],
        diagnosis_object=row["diagnosis_object"],
        remediation_plan=row["remediation_plan"],
    )


class TestCheckFastPath:
    """Tests for check_fast_path()."""

    @pytest.fixture
    def conn(self):
        return AsyncMock()

    async def test_match_found_above_threshold(self, conn):
        """Valid match above threshold returns FastPathMatch."""
        row = _make_case_record_row(similarity=0.95)
        item = _make_item()

        with (
            patch("src.pipeline.fast_path.embed_texts", new_callable=AsyncMock) as mock_embed,
            patch("src.pipeline.fast_path.search_fast_path_candidates", new_callable=AsyncMock) as mock_search,
            patch("src.pipeline.fast_path.apply_temporal_decay") as mock_decay,
        ):
            mock_embed.return_value = [[0.1] * 1536]
            mock_search.return_value = [row]
            mock_decay.return_value = 0.88

            result = await check_fast_path(item, conn)

        assert result is not None
        assert isinstance(result, FastPathMatch)
        assert result.case_record_id == row["id"]
        assert result.similarity == 0.95
        assert result.effective_confidence == 0.88

    async def test_no_match_returns_none(self, conn):
        """No candidates above threshold returns None."""
        item = _make_item()

        with (
            patch("src.pipeline.fast_path.embed_texts", new_callable=AsyncMock) as mock_embed,
            patch("src.pipeline.fast_path.search_fast_path_candidates", new_callable=AsyncMock) as mock_search,
        ):
            mock_embed.return_value = [[0.1] * 1536]
            mock_search.return_value = []

            result = await check_fast_path(item, conn)

        assert result is None

    async def test_empty_alerts_returns_none(self, conn):
        """Item with no alerts returns None."""
        item = _make_item(alerts=[])
        result = await check_fast_path(item, conn)
        assert result is None

    async def test_multiple_candidates_returns_best_effective_confidence(self, conn):
        """Multiple candidates: returns highest effective_confidence."""
        row1 = _make_case_record_row(similarity=0.93)
        row2 = _make_case_record_row(similarity=0.97)
        item = _make_item()

        with (
            patch("src.pipeline.fast_path.embed_texts", new_callable=AsyncMock) as mock_embed,
            patch("src.pipeline.fast_path.search_fast_path_candidates", new_callable=AsyncMock) as mock_search,
            patch("src.pipeline.fast_path.apply_temporal_decay") as mock_decay,
        ):
            mock_embed.return_value = [[0.1] * 1536]
            mock_search.return_value = [row1, row2]
            mock_decay.side_effect = [0.70, 0.92]

            result = await check_fast_path(item, conn)

        assert result is not None
        assert result.effective_confidence == 0.92
        assert result.case_record_id == row2["id"]

    async def test_embedding_failure_returns_none(self, conn):
        """Embedding generation failure returns None (non-fatal)."""
        item = _make_item()

        with patch("src.pipeline.fast_path.embed_texts", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = Exception("Embedding service down")

            result = await check_fast_path(item, conn)

        assert result is None

    async def test_db_query_failure_returns_none(self, conn):
        """DB query failure returns None (non-fatal)."""
        item = _make_item()

        with (
            patch("src.pipeline.fast_path.embed_texts", new_callable=AsyncMock) as mock_embed,
            patch("src.pipeline.fast_path.search_fast_path_candidates", new_callable=AsyncMock) as mock_search,
        ):
            mock_embed.return_value = [[0.1] * 1536]
            mock_search.side_effect = Exception("Connection reset")

            result = await check_fast_path(item, conn)

        assert result is None

    async def test_empty_embedding_result_returns_none(self, conn):
        """Embedding service returning empty list returns None."""
        item = _make_item()

        with patch("src.pipeline.fast_path.embed_texts", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = []

            result = await check_fast_path(item, conn)

        assert result is None


class TestRunFastPathPipeline:
    """Tests for run_fast_path_pipeline()."""

    @pytest.fixture
    def mock_pool(self):
        conn = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=False)

        pool = MagicMock()
        pool.acquire.return_value = ctx
        return pool, conn

    async def test_success_path_transitions_to_awaiting_approval(self, mock_pool):
        """Success: QUEUED → DIAGNOSED → PLANNING → AWAITING_APPROVAL."""
        pool, conn = mock_pool
        item = _make_item()
        match = _make_match()

        with (
            patch("src.pipeline.fast_path.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("src.pipeline.fast_path.transition_incident_state", new_callable=AsyncMock, return_value=True),
            patch("src.pipeline.fast_path.persist_immutable_diagnosis", new_callable=AsyncMock, return_value=uuid.uuid4()),
            patch("src.pipeline.fast_path.persist_remediation_plan", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.record_fast_path", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.persist_dry_run_result", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.persist_policy_decision", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.mark_pipeline_complete", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.pipeline_audit_log", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.run_dry_run_preflight", new_callable=AsyncMock) as mock_dry,
            patch("src.pipeline.fast_path.evaluate_policy_gate", new_callable=AsyncMock) as mock_policy,
            patch("src.pipeline.fast_path._emit_stage_event"),
        ):
            mock_dry.return_value = MagicMock(dry_run_passed=True)
            mock_policy.return_value = MagicMock(auto_execution_approved=False)

            result = await run_fast_path_pipeline(item, match)

        assert result is True

    async def test_success_path_auto_approve(self, mock_pool):
        """Auto-approve path: PLANNING → EXECUTING."""
        pool, conn = mock_pool
        item = _make_item()
        match = _make_match()

        with (
            patch("src.pipeline.fast_path.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("src.pipeline.fast_path.transition_incident_state", new_callable=AsyncMock, return_value=True),
            patch("src.pipeline.fast_path.persist_immutable_diagnosis", new_callable=AsyncMock, return_value=uuid.uuid4()),
            patch("src.pipeline.fast_path.persist_remediation_plan", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.record_fast_path", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.persist_dry_run_result", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.persist_policy_decision", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.mark_pipeline_complete", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.pipeline_audit_log", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.run_dry_run_preflight", new_callable=AsyncMock) as mock_dry,
            patch("src.pipeline.fast_path.evaluate_policy_gate", new_callable=AsyncMock) as mock_policy,
            patch("src.pipeline.fast_path._emit_stage_event"),
        ):
            mock_dry.return_value = MagicMock(dry_run_passed=True)
            mock_policy.return_value = MagicMock(auto_execution_approved=True)

            result = await run_fast_path_pipeline(item, match)

        assert result is True

    async def test_state_transition_failure_returns_false(self, mock_pool):
        """Failed QUEUED→DIAGNOSED transition returns False."""
        pool, conn = mock_pool
        item = _make_item()
        match = _make_match()

        with (
            patch("src.pipeline.fast_path.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("src.pipeline.fast_path.transition_incident_state", new_callable=AsyncMock, return_value=False),
            patch("src.pipeline.fast_path._emit_stage_event"),
        ):
            result = await run_fast_path_pipeline(item, match)

        assert result is False

    async def test_artifact_persistence_failure_returns_false(self, mock_pool):
        """Artifact persistence failure returns False."""
        pool, conn = mock_pool
        item = _make_item()
        match = _make_match()

        with (
            patch("src.pipeline.fast_path.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("src.pipeline.fast_path.transition_incident_state", new_callable=AsyncMock, return_value=True),
            patch("src.pipeline.fast_path.persist_immutable_diagnosis", new_callable=AsyncMock, side_effect=Exception("DB error")),
            patch("src.pipeline.fast_path._emit_stage_event"),
        ):
            result = await run_fast_path_pipeline(item, match)

        assert result is False

    async def test_queue_item_marked_complete(self, mock_pool):
        """Queue item is marked complete on successful fast-path."""
        pool, conn = mock_pool
        item = _make_item()
        match = _make_match()

        with (
            patch("src.pipeline.fast_path.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("src.pipeline.fast_path.transition_incident_state", new_callable=AsyncMock, return_value=True),
            patch("src.pipeline.fast_path.persist_immutable_diagnosis", new_callable=AsyncMock, return_value=uuid.uuid4()),
            patch("src.pipeline.fast_path.persist_remediation_plan", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.record_fast_path", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.persist_dry_run_result", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.persist_policy_decision", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.mark_pipeline_complete", new_callable=AsyncMock) as mock_complete,
            patch("src.pipeline.fast_path.pipeline_audit_log", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.run_dry_run_preflight", new_callable=AsyncMock) as mock_dry,
            patch("src.pipeline.fast_path.evaluate_policy_gate", new_callable=AsyncMock) as mock_policy,
            patch("src.pipeline.fast_path._emit_stage_event"),
        ):
            mock_dry.return_value = MagicMock(dry_run_passed=True)
            mock_policy.return_value = MagicMock(auto_execution_approved=False)

            await run_fast_path_pipeline(item, match)

        mock_complete.assert_called_once_with(conn, item["id"])

    async def test_fast_path_metadata_recorded(self, mock_pool):
        """Fast-path metadata is recorded on the incident."""
        pool, conn = mock_pool
        item = _make_item()
        match = _make_match(similarity=0.96)

        with (
            patch("src.pipeline.fast_path.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("src.pipeline.fast_path.transition_incident_state", new_callable=AsyncMock, return_value=True),
            patch("src.pipeline.fast_path.persist_immutable_diagnosis", new_callable=AsyncMock, return_value=uuid.uuid4()),
            patch("src.pipeline.fast_path.persist_remediation_plan", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.record_fast_path", new_callable=AsyncMock) as mock_record,
            patch("src.pipeline.fast_path.persist_dry_run_result", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.persist_policy_decision", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.mark_pipeline_complete", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.pipeline_audit_log", new_callable=AsyncMock),
            patch("src.pipeline.fast_path.run_dry_run_preflight", new_callable=AsyncMock) as mock_dry,
            patch("src.pipeline.fast_path.evaluate_policy_gate", new_callable=AsyncMock) as mock_policy,
            patch("src.pipeline.fast_path._emit_stage_event"),
        ):
            mock_dry.return_value = MagicMock(dry_run_passed=True)
            mock_policy.return_value = MagicMock(auto_execution_approved=False)

            await run_fast_path_pipeline(item, match)

        mock_record.assert_called_once_with(
            conn, item["incident_id"], match.case_record_id, 0.96
        )


class TestBuildSyntheticArtifact:
    """Tests for _build_synthetic_artifact()."""

    def test_creates_valid_immutable_artifact(self):
        match = _make_match()
        incident_id = uuid.uuid4()

        artifact = _build_synthetic_artifact(match, incident_id)

        assert artifact.incident_id == incident_id
        assert artifact.root_cause_component == "node"
        assert artifact.failure_mode == "memory-pressure"
        assert artifact.sealed_at is not None

    def test_preserves_skeptic_verdict(self):
        match = _make_match()
        incident_id = uuid.uuid4()

        artifact = _build_synthetic_artifact(match, incident_id)

        assert artifact.skeptic_verdict is not None

    def test_assigns_new_id(self):
        match = _make_match()
        incident_id = uuid.uuid4()
        original_id = match.diagnosis_object["id"]

        artifact = _build_synthetic_artifact(match, incident_id)

        assert str(artifact.id) != original_id

    def test_preserves_original_diagnosis_object_id(self):
        match = _make_match()
        incident_id = uuid.uuid4()
        original_id = match.diagnosis_object["id"]

        artifact = _build_synthetic_artifact(match, incident_id)

        assert str(artifact.diagnosis_object_id) == original_id
        assert artifact.diagnosis_object_id != artifact.id


class TestBuildReplayedPlan:
    """Tests for _build_replayed_plan()."""

    def test_creates_valid_plan(self):
        match = _make_match()
        incident_id = uuid.uuid4()
        diagnosis_id = uuid.uuid4()

        plan = _build_replayed_plan(match, incident_id, diagnosis_id)

        assert plan.incident_id == incident_id
        assert plan.diagnosis_id == diagnosis_id
        assert len(plan.steps) == 1
        assert plan.blast_radius.value == "workload"

    def test_clears_manifest_path_from_steps(self):
        match = _make_match()
        match.remediation_plan["steps"][0]["manifest_path"] = "/tmp/old.yaml"
        match.remediation_plan["steps"][0]["manifest_generation_failed"] = True
        incident_id = uuid.uuid4()
        diagnosis_id = uuid.uuid4()

        plan = _build_replayed_plan(match, incident_id, diagnosis_id)

        assert plan.steps[0].manifest_path is None
        assert plan.steps[0].manifest_generation_failed is False

    def test_assigns_new_id(self):
        match = _make_match()
        original_id = match.remediation_plan["id"]
        incident_id = uuid.uuid4()
        diagnosis_id = uuid.uuid4()

        plan = _build_replayed_plan(match, incident_id, diagnosis_id)

        assert str(plan.id) != original_id


class TestDispatcherIntegration:
    """Tests for fast-path integration in dispatcher dispatch loop."""

    async def test_fast_path_match_skips_diagnosis(self):
        """When fast-path match found, diagnosis dispatch is not called."""
        from src.pipeline.dispatcher import _run_fast_path_task

        item = _make_item()
        match = _make_match()

        with patch("src.pipeline.fast_path.run_fast_path_pipeline", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = True
            await _run_fast_path_task(item, match)

        mock_run.assert_called_once_with(item, match)

    async def test_fast_path_check_exception_is_non_fatal(self):
        """Fast-path check exception does not crash the dispatcher loop."""
        from src.pipeline.fast_path import check_fast_path

        item = _make_item()
        conn = AsyncMock()

        with patch("src.pipeline.fast_path.build_alert_signature", side_effect=RuntimeError("boom")):
            result = await check_fast_path(item, conn)

        assert result is None
