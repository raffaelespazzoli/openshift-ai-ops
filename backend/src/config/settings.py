"""Application settings loaded from environment variables.

Correlation settings are Helm-configurable via environment variables
injected from charts/openshift-ai-ops/values.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CorrelationSettings:
    """Settling window and sealing configuration (AD-6)."""

    settling_window_critical: int = 60
    settling_window_warning: int = 300
    settling_window_info: int = 600
    max_age_multiplier: int = 3
    sealing_check_interval_seconds: int = 10

    @classmethod
    def from_env(cls) -> CorrelationSettings:
        return cls(
            settling_window_critical=int(
                os.environ.get("CORRELATION_SETTLING_CRITICAL", "60")
            ),
            settling_window_warning=int(
                os.environ.get("CORRELATION_SETTLING_WARNING", "300")
            ),
            settling_window_info=int(
                os.environ.get("CORRELATION_SETTLING_INFO", "600")
            ),
            max_age_multiplier=int(
                os.environ.get("CORRELATION_MAX_AGE_MULTIPLIER", "3")
            ),
            sealing_check_interval_seconds=int(
                os.environ.get("CORRELATION_SEALING_INTERVAL", "10")
            ),
        )


_correlation_settings: CorrelationSettings | None = None


def get_correlation_settings() -> CorrelationSettings:
    """Get or create the singleton correlation settings instance."""
    global _correlation_settings
    if _correlation_settings is None:
        _correlation_settings = CorrelationSettings.from_env()
    return _correlation_settings


def reset_correlation_settings() -> None:
    """Reset cached settings (for testing)."""
    global _correlation_settings
    _correlation_settings = None
