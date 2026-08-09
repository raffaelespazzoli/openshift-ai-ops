"""RHOKP connection settings for the okp-mcp MCP Server (AD-13 path 2)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RHOKPSettings:
    """Configuration for the RHOKP knowledge base via okp-mcp."""

    url: str = "http://okp-mcp:8000/mcp"
    timeout_seconds: float = 30.0
    top_k: int = 5

    @classmethod
    def from_env(cls) -> RHOKPSettings:
        return cls(
            url=os.environ.get("RHOKP_MCP_URL", "http://okp-mcp:8000/mcp"),
            timeout_seconds=float(os.environ.get("RHOKP_TIMEOUT_SECONDS", "30.0")),
            top_k=int(os.environ.get("RHOKP_TOP_K", "5")),
        )


_rhokp_settings: RHOKPSettings | None = None


def get_rhokp_settings() -> RHOKPSettings:
    """Get or create the singleton RHOKP settings instance."""
    global _rhokp_settings
    if _rhokp_settings is None:
        _rhokp_settings = RHOKPSettings.from_env()
    return _rhokp_settings


def reset_rhokp_settings() -> None:
    """Reset cached settings (for testing)."""
    global _rhokp_settings
    _rhokp_settings = None
