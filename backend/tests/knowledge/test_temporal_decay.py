"""Unit tests for compute_version_relevance() and refined apply_temporal_decay().

Covers AC #1 (effective confidence formula), AC #2 (version relevance),
AC #3 (temporal decay), and AC #5 (ranking by effective confidence).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.config.knowledge_settings import KnowledgeSettings
from src.knowledge.learning_store import apply_temporal_decay, compute_version_relevance


class TestComputeVersionRelevance:
    """Tests for the standalone compute_version_relevance() function."""

    @pytest.mark.unit
    def test_same_major_and_minor_returns_full_weight(self):
        """Same major+minor version returns same_major_weight (1.0)."""
        result = compute_version_relevance("4.15.0", "4.15.0")
        assert result == 1.0

    @pytest.mark.unit
    def test_same_major_one_minor_apart(self):
        """Same major, 1 minor apart: 1.0 - 0.02 = 0.98."""
        result = compute_version_relevance("4.14.0", "4.15.0")
        assert abs(result - 0.98) < 1e-9

    @pytest.mark.unit
    def test_same_major_ten_minors_apart(self):
        """Same major, 10 minors apart: 1.0 - 0.20 = 0.80."""
        result = compute_version_relevance("4.5.0", "4.15.0")
        assert abs(result - 0.80) < 1e-9

    @pytest.mark.unit
    def test_same_major_clamped_to_floor(self):
        """Same major, 30+ minors apart → clamped to different_major_weight floor."""
        result = compute_version_relevance("4.1.0", "4.35.0")
        assert result == 0.5

    @pytest.mark.unit
    def test_different_major_version(self):
        """Different major version returns different_major_weight (0.5)."""
        result = compute_version_relevance("3.11.0", "4.15.0")
        assert result == 0.5

    @pytest.mark.unit
    def test_custom_different_major_weight(self):
        """Custom different_major_weight=0.3 → different major returns 0.3."""
        result = compute_version_relevance(
            "3.11.0", "4.15.0", different_major_weight=0.3
        )
        assert result == 0.3

    @pytest.mark.unit
    def test_custom_minor_penalty(self):
        """Custom minor_penalty_per_version=0.05 → 5 minors apart = 0.75."""
        result = compute_version_relevance(
            "4.10.0", "4.15.0", minor_penalty_per_version=0.05
        )
        assert abs(result - 0.75) < 1e-9

    @pytest.mark.unit
    def test_version_without_minor_component(self):
        """Version strings without minor (e.g. '4' vs '4.15') handled gracefully."""
        result = compute_version_relevance("4", "4.15")
        expected = 1.0 - (0.02 * 15)
        assert abs(result - expected) < 1e-9

    @pytest.mark.unit
    def test_both_versions_major_only(self):
        """Both versions major-only → minor distance is 0 → full weight."""
        result = compute_version_relevance("4", "4")
        assert result == 1.0

    @pytest.mark.unit
    def test_custom_same_major_weight(self):
        """Custom same_major_weight=0.9 used as starting point."""
        result = compute_version_relevance(
            "4.15.0", "4.15.0", same_major_weight=0.9
        )
        assert result == 0.9

    @pytest.mark.unit
    def test_minor_penalty_clamps_to_different_major_floor(self):
        """Minor penalty can't push below different_major_weight floor."""
        result = compute_version_relevance(
            "4.1.0",
            "4.100.0",
            same_major_weight=1.0,
            different_major_weight=0.3,
            minor_penalty_per_version=0.05,
        )
        assert result == 0.3


class TestApplyTemporalDecayWithConfigurableWeights:
    """Tests for refined apply_temporal_decay() using configurable settings."""

    @pytest.mark.unit
    def test_backward_compatible_same_version_recent(self):
        """Recent case with same major version preserves high confidence (backward compat)."""
        case = {
            "outcome_confidence": 0.9,
            "created_at": datetime.now(timezone.utc) - timedelta(days=1),
            "ocp_version": "4.14.5",
        }
        result = apply_temporal_decay(case, current_ocp_version="4.15.0", decay_half_life_days=90.0)
        assert result > 0.85

    @pytest.mark.unit
    def test_backward_compatible_different_major(self):
        """Different major version still reduces confidence (backward compat)."""
        case = {
            "outcome_confidence": 0.9,
            "created_at": datetime.now(timezone.utc),
            "ocp_version": "3.11.0",
        }
        result = apply_temporal_decay(case, current_ocp_version="4.15.0", decay_half_life_days=90.0)
        assert abs(result - 0.45) < 0.05

    @pytest.mark.unit
    def test_custom_different_major_weight_via_settings(self):
        """Custom version_relevance_different_major=0.3 gives lower score."""
        case = {
            "outcome_confidence": 0.9,
            "created_at": datetime.now(timezone.utc),
            "ocp_version": "3.11.0",
        }
        custom_settings = KnowledgeSettings(
            version_relevance_different_major=0.3,
            learning_store_decay_half_life_days=90.0,
        )
        with patch("src.knowledge.learning_store.get_knowledge_settings", return_value=custom_settings):
            result = apply_temporal_decay(case, current_ocp_version="4.15.0")
        assert abs(result - 0.27) < 0.05

    @pytest.mark.unit
    def test_minor_penalty_applied_through_settings(self):
        """Minor version penalty reduces score for same-major cases."""
        case = {
            "outcome_confidence": 1.0,
            "created_at": datetime.now(timezone.utc),
            "ocp_version": "4.5.0",
        }
        custom_settings = KnowledgeSettings(
            version_relevance_same_major=1.0,
            version_relevance_minor_penalty_per_version=0.02,
            learning_store_decay_half_life_days=90.0,
        )
        with patch("src.knowledge.learning_store.get_knowledge_settings", return_value=custom_settings):
            result = apply_temporal_decay(case, current_ocp_version="4.15.0")
        # 10 minors apart: version_relevance = 1.0 - 0.2 = 0.8
        assert abs(result - 0.8) < 0.05

    @pytest.mark.unit
    def test_decay_factor_unchanged(self):
        """Exponential half-life formula still works correctly."""
        case = {
            "outcome_confidence": 1.0,
            "created_at": datetime.now(timezone.utc) - timedelta(days=90),
            "ocp_version": "4.15.0",
        }
        result = apply_temporal_decay(case, current_ocp_version="4.15.0", decay_half_life_days=90.0)
        assert abs(result - 0.5) < 0.05

    @pytest.mark.unit
    def test_explicit_half_life_overrides_settings(self):
        """Explicit decay_half_life_days parameter takes precedence over settings."""
        case = {
            "outcome_confidence": 1.0,
            "created_at": datetime.now(timezone.utc) - timedelta(days=30),
            "ocp_version": "4.15.0",
        }
        custom_settings = KnowledgeSettings(learning_store_decay_half_life_days=180.0)
        with patch("src.knowledge.learning_store.get_knowledge_settings", return_value=custom_settings):
            result = apply_temporal_decay(
                case, current_ocp_version="4.15.0", decay_half_life_days=30.0
            )
        assert abs(result - 0.5) < 0.05

    @pytest.mark.unit
    def test_settings_half_life_used_when_none(self):
        """When decay_half_life_days=None, uses settings value."""
        case = {
            "outcome_confidence": 1.0,
            "created_at": datetime.now(timezone.utc) - timedelta(days=45),
            "ocp_version": "4.15.0",
        }
        custom_settings = KnowledgeSettings(learning_store_decay_half_life_days=45.0)
        with patch("src.knowledge.learning_store.get_knowledge_settings", return_value=custom_settings):
            result = apply_temporal_decay(case, current_ocp_version="4.15.0")
        assert abs(result - 0.5) < 0.05
