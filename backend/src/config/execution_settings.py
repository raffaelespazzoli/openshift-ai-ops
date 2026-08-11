"""Execution pipeline configuration (Story 3.5).

Resolves from env vars seeded by Helm values.
Controls observation timeout, cooldown period, re-fire window,
and lock poll interval.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


class ExecutionSettings(BaseModel):
    """Execution pipeline timing configuration."""

    model_config = {"frozen": True}

    observation_timeout_seconds: int = Field(default=300, ge=1)
    cooldown_seconds: int = Field(default=60, ge=0)
    refire_window_seconds: int = Field(default=600, ge=0)
    lock_poll_interval_seconds: int = Field(default=5, ge=1)

    @classmethod
    def from_env(cls) -> ExecutionSettings:
        return cls(
            observation_timeout_seconds=int(
                os.environ.get("EXECUTION_OBSERVATION_TIMEOUT", "300")
            ),
            cooldown_seconds=int(
                os.environ.get("EXECUTION_COOLDOWN_SECONDS", "60")
            ),
            refire_window_seconds=int(
                os.environ.get("EXECUTION_REFIRE_WINDOW", "600")
            ),
            lock_poll_interval_seconds=int(
                os.environ.get("EXECUTION_LOCK_POLL_INTERVAL", "5")
            ),
        )


_execution_settings: ExecutionSettings | None = None


def get_execution_settings() -> ExecutionSettings:
    """Get or create the singleton ExecutionSettings instance."""
    global _execution_settings
    if _execution_settings is None:
        _execution_settings = ExecutionSettings.from_env()
    return _execution_settings


def reset_execution_settings() -> None:
    """Reset cached settings (for testing)."""
    global _execution_settings
    _execution_settings = None
