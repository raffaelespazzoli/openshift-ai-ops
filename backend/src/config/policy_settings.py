"""Policy gate configuration — default-deny matrix (Story 3.3).

Resolves from env vars seeded by Helm values.
Default values enforce default-deny: all remediations require
human approval unless explicitly relaxed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _parse_list(raw: str) -> list[str]:
    """Parse a comma-separated env var into a list of non-empty strings."""
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class PolicyMatrixSettings:
    """Policy gate configuration — default is deny-all (human approval required)."""

    severity_auto_approve: list[str] = field(default_factory=list)
    blast_radius_auto_approve: list[str] = field(default_factory=list)
    confidence_minimum: float = 1.0

    @classmethod
    def from_env(cls) -> PolicyMatrixSettings:
        return cls(
            severity_auto_approve=_parse_list(
                os.environ.get("POLICY_SEVERITY_AUTO_APPROVE", "")
            ),
            blast_radius_auto_approve=_parse_list(
                os.environ.get("POLICY_BLAST_RADIUS_AUTO_APPROVE", "")
            ),
            confidence_minimum=float(
                os.environ.get("POLICY_CONFIDENCE_MINIMUM", "1.0")
            ),
        )


_policy_settings: PolicyMatrixSettings | None = None


def get_policy_matrix_settings() -> PolicyMatrixSettings:
    """Get or create the singleton PolicyMatrixSettings instance."""
    global _policy_settings
    if _policy_settings is None:
        _policy_settings = PolicyMatrixSettings.from_env()
    return _policy_settings


def reset_policy_settings() -> None:
    """Reset cached settings (for testing)."""
    global _policy_settings
    _policy_settings = None
