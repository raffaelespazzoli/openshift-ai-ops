"""Queue configuration loaded from environment variables.

Priority queue settings are Helm-configurable via environment variables
injected from charts/openshift-ai-ops/values.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PriorityWeights:
    """Severity-to-weight mapping for priority scoring."""

    critical: int = 100
    warning: int = 50
    info: int = 10

    def get(self, severity: str) -> int:
        """Look up the weight for a severity, defaulting to warning weight."""
        return {
            "critical": self.critical,
            "warning": self.warning,
            "info": self.info,
        }.get(severity, self.warning)


@dataclass(frozen=True)
class QueueSettings:
    """Priority queue and dispatcher configuration."""

    parallelism_cap: int = 3
    ttl_seconds: int = 3600
    poll_interval_seconds: int = 5
    stale_processing_timeout_seconds: int = 900
    priority_weights: PriorityWeights = field(default_factory=PriorityWeights)

    @classmethod
    def from_env(cls) -> QueueSettings:
        return cls(
            parallelism_cap=int(
                os.environ.get("QUEUE_PARALLELISM_CAP", "3")
            ),
            ttl_seconds=int(
                os.environ.get("QUEUE_TTL_SECONDS", "3600")
            ),
            poll_interval_seconds=int(
                os.environ.get("QUEUE_POLL_INTERVAL_SECONDS", "5")
            ),
            stale_processing_timeout_seconds=int(
                os.environ.get("QUEUE_STALE_PROCESSING_TIMEOUT_SECONDS", "900")
            ),
            priority_weights=PriorityWeights(
                critical=int(os.environ.get("QUEUE_PRIORITY_WEIGHT_CRITICAL", "100")),
                warning=int(os.environ.get("QUEUE_PRIORITY_WEIGHT_WARNING", "50")),
                info=int(os.environ.get("QUEUE_PRIORITY_WEIGHT_INFO", "10")),
            ),
        )


_queue_settings: QueueSettings | None = None


def get_queue_settings() -> QueueSettings:
    """Get or create the singleton queue settings instance."""
    global _queue_settings
    if _queue_settings is None:
        _queue_settings = QueueSettings.from_env()
    return _queue_settings


def reset_queue_settings() -> None:
    """Reset cached settings (for testing)."""
    global _queue_settings
    _queue_settings = None
