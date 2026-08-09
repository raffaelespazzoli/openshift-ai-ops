"""Unit tests for Learning Store query interface (AC: #2, #3, #6).

Tests temporal decay, version relevance, empty results handling,
and ranked result ordering.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.knowledge.learning_store import apply_temporal_decay, query_learning_store
from src.models.case_record import CaseRecordSummary


class TestApplyTemporalDecay:
    """Tests for the temporal decay formula."""

    @pytest.mark.unit
    def test_recent_same_version_full_confidence(self):
        """Recent case with matching OCP version preserves confidence."""
        case = {
            "outcome_confidence": 0.9,
            "created_at": datetime.now(timezone.utc) - timedelta(days=1),
            "ocp_version": "4.14.5",
        }
        result = apply_temporal_decay(case, current_ocp_version="4.15.0", decay_half_life_days=90.0)
        assert result > 0.85

    @pytest.mark.unit
    def test_old_case_reduced_confidence(self):
        """Old case has significantly reduced confidence via decay."""
        case = {
            "outcome_confidence": 0.9,
            "created_at": datetime.now(timezone.utc) - timedelta(days=180),
            "ocp_version": "4.14.5",
        }
        result = apply_temporal_decay(case, current_ocp_version="4.15.0", decay_half_life_days=90.0)
        assert result < 0.3

    @pytest.mark.unit
    def test_different_major_version_halves_confidence(self):
        """Different OCP major version reduces confidence by half."""
        now = datetime.now(timezone.utc)
        case = {
            "outcome_confidence": 0.9,
            "created_at": now,
            "ocp_version": "3.11.0",
        }
        result = apply_temporal_decay(case, current_ocp_version="4.15.0", decay_half_life_days=90.0)
        # Different major version: 0.9 * 1.0 (no decay, just created) * 0.5
        assert abs(result - 0.45) < 0.05

    @pytest.mark.unit
    def test_half_life_at_90_days(self):
        """At 90 days, decay factor should be approximately 0.5."""
        case = {
            "outcome_confidence": 1.0,
            "created_at": datetime.now(timezone.utc) - timedelta(days=90),
            "ocp_version": "4.14.0",
        }
        result = apply_temporal_decay(case, current_ocp_version="4.15.0", decay_half_life_days=90.0)
        assert abs(result - 0.5) < 0.05

    @pytest.mark.unit
    def test_zero_confidence_stays_zero(self):
        """Zero base confidence remains zero regardless of age."""
        case = {
            "outcome_confidence": 0.0,
            "created_at": datetime.now(timezone.utc),
            "ocp_version": "4.14.0",
        }
        result = apply_temporal_decay(case, current_ocp_version="4.14.0", decay_half_life_days=90.0)
        assert result == 0.0

    @pytest.mark.unit
    def test_uses_configured_half_life_from_settings(self):
        """When decay_half_life_days is None, reads from KnowledgeSettings."""
        case = {
            "outcome_confidence": 1.0,
            "created_at": datetime.now(timezone.utc) - timedelta(days=45),
            "ocp_version": "4.14.0",
        }
        from src.config.knowledge_settings import KnowledgeSettings
        custom_settings = KnowledgeSettings(learning_store_decay_half_life_days=45.0)
        with patch("src.knowledge.learning_store.get_knowledge_settings", return_value=custom_settings):
            result = apply_temporal_decay(case, current_ocp_version="4.15.0")
        # 45-day half-life at 45 days → decay_factor ≈ 0.5
        assert abs(result - 0.5) < 0.05

    @pytest.mark.unit
    def test_custom_half_life_changes_decay_rate(self):
        """A shorter half-life leads to faster decay."""
        case = {
            "outcome_confidence": 1.0,
            "created_at": datetime.now(timezone.utc) - timedelta(days=30),
            "ocp_version": "4.14.0",
        }
        result_short = apply_temporal_decay(case, current_ocp_version="4.14.0", decay_half_life_days=30.0)
        result_long = apply_temporal_decay(case, current_ocp_version="4.14.0", decay_half_life_days=180.0)
        # Shorter half-life = more decay at 30 days
        assert result_short < result_long


class TestQueryLearningStore:
    """Tests for the query_learning_store function."""

    @pytest.mark.unit
    async def test_empty_learning_store_returns_empty_list(self):
        """Empty Learning Store returns empty list gracefully (AC #3)."""
        mock_conn = AsyncMock()
        mock_embedding = [[0.1] * 1536]

        with (
            patch("src.knowledge.learning_store.embed_texts", new_callable=AsyncMock, return_value=mock_embedding),
            patch("src.knowledge.learning_store.search_similar_cases", new_callable=AsyncMock, return_value=[]),
        ):
            results = await query_learning_store("pod crashloop", mock_conn)

        assert results == []

    @pytest.mark.unit
    async def test_returns_ranked_results_with_temporal_decay(self):
        """Learning Store returns results ranked by effective confidence."""
        now = datetime.now(timezone.utc)
        mock_cases = [
            {
                "id": uuid.uuid4(),
                "alert_signature": "KubePodCrashLooping",
                "root_cause_code": "workload/crash-loop-backoff",
                "outcome": "success",
                "outcome_confidence": 0.8,
                "ocp_version": "4.14.5",
                "created_at": now - timedelta(days=30),
                "similarity": 0.92,
            },
            {
                "id": uuid.uuid4(),
                "alert_signature": "KubePodCrashLooping",
                "root_cause_code": "workload/oom-killed",
                "outcome": "success",
                "outcome_confidence": 0.9,
                "ocp_version": "4.14.5",
                "created_at": now - timedelta(days=120),
                "similarity": 0.85,
            },
        ]
        mock_embedding = [[0.1] * 1536]
        mock_conn = AsyncMock()

        with (
            patch("src.knowledge.learning_store.embed_texts", new_callable=AsyncMock, return_value=mock_embedding),
            patch("src.knowledge.learning_store.search_similar_cases", new_callable=AsyncMock, return_value=mock_cases),
        ):
            results = await query_learning_store("pod crashloop", mock_conn)

        assert len(results) == 2
        assert all(isinstance(r, CaseRecordSummary) for r in results)
        # Results should be sorted by effective_confidence descending
        assert results[0].effective_confidence >= results[1].effective_confidence

    @pytest.mark.unit
    async def test_embedding_failure_propagates(self):
        """Embedding failure raises so the caller can report an evidence gap."""
        mock_conn = AsyncMock()

        with (
            patch(
                "src.knowledge.learning_store.embed_texts",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Embedding service down"),
            ),
            pytest.raises(RuntimeError, match="Embedding service down"),
        ):
            await query_learning_store("test", mock_conn)

    @pytest.mark.unit
    async def test_empty_embedding_result_raises(self):
        """Empty embedding result raises RuntimeError (not silently returns [])."""
        mock_conn = AsyncMock()

        with (
            patch(
                "src.knowledge.learning_store.embed_texts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            pytest.raises(RuntimeError, match="no vectors"),
        ):
            await query_learning_store("test", mock_conn)

    @pytest.mark.unit
    async def test_db_query_failure_propagates(self):
        """Database query failure raises so the caller can report an evidence gap."""
        mock_conn = AsyncMock()
        mock_embedding = [[0.1] * 1536]

        with (
            patch("src.knowledge.learning_store.embed_texts", new_callable=AsyncMock, return_value=mock_embedding),
            patch(
                "src.knowledge.learning_store.search_similar_cases",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB connection lost"),
            ),
            pytest.raises(RuntimeError, match="DB connection lost"),
        ):
            await query_learning_store("test", mock_conn)

    @pytest.mark.unit
    async def test_version_relevance_applied_to_results(self):
        """Version relevance reduces confidence for different OCP major versions."""
        now = datetime.now(timezone.utc)
        mock_cases = [
            {
                "id": uuid.uuid4(),
                "alert_signature": "NodeNotReady",
                "root_cause_code": "node/not-ready",
                "outcome": "success",
                "outcome_confidence": 0.9,
                "ocp_version": "3.11.0",
                "created_at": now - timedelta(days=1),
                "similarity": 0.95,
            },
        ]
        mock_embedding = [[0.1] * 1536]
        mock_conn = AsyncMock()

        with (
            patch("src.knowledge.learning_store.embed_texts", new_callable=AsyncMock, return_value=mock_embedding),
            patch("src.knowledge.learning_store.search_similar_cases", new_callable=AsyncMock, return_value=mock_cases),
        ):
            results = await query_learning_store("node not ready", mock_conn, current_ocp_version="4.15.0")

        assert len(results) == 1
        # Different major version (3 vs 4) should halve confidence
        assert results[0].effective_confidence < 0.5
