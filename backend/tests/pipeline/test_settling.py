"""Unit tests for settling window logic.

Tests cover:
- Correct window duration per severity
- Timer reset uses shortest window (min)
- Max age = 3× settling window
- Sealing conditions: window expired OR max age exceeded
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from src.config.settings import reset_correlation_settings
from src.pipeline.settling import (
    calculate_max_age,
    check_group_sealing,
    get_settling_window,
    recalculate_group_window,
)


@pytest.fixture(autouse=True)
def _reset_settings():
    """Reset correlation settings before each test to ensure isolation."""
    reset_correlation_settings()
    yield
    reset_correlation_settings()


class TestGetSettlingWindow:
    """Settling window seconds per severity."""

    @pytest.mark.unit
    def test_critical_window_60s(self):
        assert get_settling_window("critical") == 60

    @pytest.mark.unit
    def test_warning_window_300s(self):
        assert get_settling_window("warning") == 300

    @pytest.mark.unit
    def test_info_window_600s(self):
        assert get_settling_window("info") == 600

    @pytest.mark.unit
    def test_unknown_severity_defaults_to_warning(self):
        assert get_settling_window("unknown") == 300

    @pytest.mark.unit
    def test_custom_values_from_env(self, monkeypatch):
        monkeypatch.setenv("CORRELATION_SETTLING_CRITICAL", "30")
        monkeypatch.setenv("CORRELATION_SETTLING_WARNING", "120")
        monkeypatch.setenv("CORRELATION_SETTLING_INFO", "240")
        reset_correlation_settings()

        assert get_settling_window("critical") == 30
        assert get_settling_window("warning") == 120
        assert get_settling_window("info") == 240


class TestRecalculateGroupWindow:
    """Timer reset: group window = min(current, new alert window)."""

    @pytest.mark.unit
    def test_critical_alert_escalates_warning_group(self):
        """Critical alert joining a warning group drops window to 60s."""
        result = recalculate_group_window(300, "critical")
        assert result == 60

    @pytest.mark.unit
    def test_warning_alert_in_critical_group_keeps_critical(self):
        """Warning alert joining a critical group keeps window at 60s."""
        result = recalculate_group_window(60, "warning")
        assert result == 60

    @pytest.mark.unit
    def test_same_severity_keeps_window(self):
        """Same severity keeps window unchanged."""
        result = recalculate_group_window(300, "warning")
        assert result == 300

    @pytest.mark.unit
    def test_info_alert_in_warning_group(self):
        """Info alert in warning group keeps shorter warning window."""
        result = recalculate_group_window(300, "info")
        assert result == 300


class TestMaxAge:
    """Max age = 3 × settling window."""

    @pytest.mark.unit
    def test_critical_max_age(self):
        result = calculate_max_age(60)
        assert result == timedelta(seconds=180)

    @pytest.mark.unit
    def test_warning_max_age(self):
        result = calculate_max_age(300)
        assert result == timedelta(seconds=900)

    @pytest.mark.unit
    def test_info_max_age(self):
        result = calculate_max_age(600)
        assert result == timedelta(seconds=1800)

    @pytest.mark.unit
    def test_custom_multiplier(self, monkeypatch):
        monkeypatch.setenv("CORRELATION_MAX_AGE_MULTIPLIER", "5")
        reset_correlation_settings()

        result = calculate_max_age(60)
        assert result == timedelta(seconds=300)


class TestCheckGroupSealing:
    """Sealing conditions: settling window expired OR max age exceeded."""

    @pytest.mark.unit
    def test_window_expired_seals(self):
        """Group should seal when settling window has expired."""
        now = datetime.now(timezone.utc)
        last_alert_at = now - timedelta(seconds=120)
        created_at = now - timedelta(seconds=150)

        result = check_group_sealing(last_alert_at, created_at, settling_window_seconds=60, now=now)
        assert result is True

    @pytest.mark.unit
    def test_window_not_expired_does_not_seal(self):
        """Group should NOT seal when settling window is still active."""
        now = datetime.now(timezone.utc)
        last_alert_at = now - timedelta(seconds=10)
        created_at = now - timedelta(seconds=30)

        result = check_group_sealing(last_alert_at, created_at, settling_window_seconds=300, now=now)
        assert result is False

    @pytest.mark.unit
    def test_max_age_exceeded_seals(self):
        """Group should seal when max age (3x window) is exceeded."""
        now = datetime.now(timezone.utc)
        last_alert_at = now - timedelta(seconds=10)
        created_at = now - timedelta(seconds=200)

        result = check_group_sealing(last_alert_at, created_at, settling_window_seconds=60, now=now)
        assert result is True

    @pytest.mark.unit
    def test_max_age_not_exceeded_does_not_seal(self):
        """Group should NOT seal when within max age."""
        now = datetime.now(timezone.utc)
        last_alert_at = now - timedelta(seconds=10)
        created_at = now - timedelta(seconds=100)

        result = check_group_sealing(last_alert_at, created_at, settling_window_seconds=60, now=now)
        assert result is False

    @pytest.mark.unit
    def test_critical_alert_joining_triggers_immediate_seal(self):
        """A group older than 3*60=180s should seal when window drops to 60s."""
        now = datetime.now(timezone.utc)
        last_alert_at = now - timedelta(seconds=5)
        created_at = now - timedelta(seconds=200)

        result = check_group_sealing(last_alert_at, created_at, settling_window_seconds=60, now=now)
        assert result is True
