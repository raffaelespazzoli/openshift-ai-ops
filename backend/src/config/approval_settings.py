"""Approval workflow configuration (Story 3.4).

Resolves from env vars seeded by Helm values.
Controls minimum review time enforcement for node/cluster blast radius.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


class ApprovalSettings(BaseModel):
    """Minimum review time configuration for human approval workflow."""

    model_config = {"frozen": True}

    minimum_review_enabled: bool = Field(default=True)
    minimum_review_seconds_node: int = Field(default=60, ge=0)
    minimum_review_seconds_cluster: int = Field(default=60, ge=0)

    @classmethod
    def from_env(cls) -> ApprovalSettings:
        return cls(
            minimum_review_enabled=os.environ.get(
                "APPROVAL_MIN_REVIEW_ENABLED", "true"
            ).lower()
            == "true",
            minimum_review_seconds_node=int(
                os.environ.get("APPROVAL_MIN_REVIEW_NODE", "60")
            ),
            minimum_review_seconds_cluster=int(
                os.environ.get("APPROVAL_MIN_REVIEW_CLUSTER", "60")
            ),
        )


_approval_settings: ApprovalSettings | None = None


def get_approval_settings() -> ApprovalSettings:
    """Get or create the singleton ApprovalSettings instance."""
    global _approval_settings
    if _approval_settings is None:
        _approval_settings = ApprovalSettings.from_env()
    return _approval_settings


def reset_approval_settings() -> None:
    """Reset cached settings (for testing)."""
    global _approval_settings
    _approval_settings = None
