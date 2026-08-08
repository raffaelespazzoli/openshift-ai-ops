"""Settling window logic and group sealing checks (AD-6).

Settling windows vary by severity: critical alerts get a short window
to minimize response time, while lower-severity alerts get longer windows
to accumulate related alerts before sealing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config.settings import get_correlation_settings


def get_settling_window(severity: str) -> int:
    """Return the settling window in seconds for the given severity.

    Args:
        severity: One of 'critical', 'warning', 'info'.

    Returns:
        Settling window duration in seconds.
    """
    settings = get_correlation_settings()
    windows = {
        "critical": settings.settling_window_critical,
        "warning": settings.settling_window_warning,
        "info": settings.settling_window_info,
    }
    return windows.get(severity, settings.settling_window_warning)


def calculate_max_age(settling_window_seconds: int) -> timedelta:
    """Calculate the max age for a correlation group.

    Max age = max_age_multiplier * settling_window.
    """
    settings = get_correlation_settings()
    return timedelta(seconds=settings.max_age_multiplier * settling_window_seconds)


def recalculate_group_window(current_window: int, new_alert_severity: str) -> int:
    """Recalculate group settling window when a new alert joins.

    The group window becomes min(current_window, new_alert_window).
    A critical alert joining a warning group escalates urgency.
    """
    new_window = get_settling_window(new_alert_severity)
    return min(current_window, new_window)


def check_group_sealing(
    last_alert_at: datetime,
    created_at: datetime,
    settling_window_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Determine if a correlation group should be sealed.

    A group seals when either:
    - The settling window has expired (no new alerts within window), OR
    - The max age has been exceeded (3x settling window from creation)

    Args:
        last_alert_at: Timestamp of the most recent alert joining the group.
        created_at: Timestamp of group creation.
        settling_window_seconds: Current settling window for the group.
        now: Current time (defaults to utcnow, injectable for testing).

    Returns:
        True if the group should be sealed.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    settling_expired = (now - last_alert_at) > timedelta(seconds=settling_window_seconds)

    max_age = calculate_max_age(settling_window_seconds)
    age_exceeded = (now - created_at) > max_age

    return settling_expired or age_exceeded
