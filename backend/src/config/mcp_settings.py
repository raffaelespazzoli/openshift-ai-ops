"""MCP connection settings for read-only and read-write cluster access clients."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MCPSettings:
    """Configuration for the MCP read-only server connection (AD-2)."""

    url: str = "http://mcp-readonly:8080/mcp"
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_delay_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> MCPSettings:
        return cls(
            url=os.environ.get("MCP_READONLY_URL", "http://mcp-readonly:8080/mcp"),
            timeout_seconds=float(os.environ.get("MCP_TIMEOUT_SECONDS", "30.0")),
            max_retries=int(os.environ.get("MCP_MAX_RETRIES", "2")),
            retry_delay_seconds=float(os.environ.get("MCP_RETRY_DELAY_SECONDS", "1.0")),
        )


@dataclass(frozen=True)
class MCPReadWriteSettings:
    """Configuration for the MCP read-write server connection (AD-2, AD-9).

    The read-write MCP Server is bound to a cluster-admin ServiceAccount
    and supports both query and mutation operations.
    """

    url: str = "http://mcp-readwrite:8080/mcp"
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_delay_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> MCPReadWriteSettings:
        return cls(
            url=os.environ.get("MCP_READWRITE_URL", "http://mcp-readwrite:8080/mcp"),
            timeout_seconds=float(os.environ.get("MCP_READWRITE_TIMEOUT_SECONDS", "30.0")),
            max_retries=int(os.environ.get("MCP_READWRITE_MAX_RETRIES", "2")),
            retry_delay_seconds=float(
                os.environ.get("MCP_READWRITE_RETRY_DELAY_SECONDS", "1.0")
            ),
        )


_mcp_settings: MCPSettings | None = None
_mcp_readwrite_settings: MCPReadWriteSettings | None = None


def get_mcp_settings() -> MCPSettings:
    """Get or create the singleton MCP settings instance."""
    global _mcp_settings
    if _mcp_settings is None:
        _mcp_settings = MCPSettings.from_env()
    return _mcp_settings


def get_mcp_readwrite_settings() -> MCPReadWriteSettings:
    """Get or create the singleton MCP read-write settings instance."""
    global _mcp_readwrite_settings
    if _mcp_readwrite_settings is None:
        _mcp_readwrite_settings = MCPReadWriteSettings.from_env()
    return _mcp_readwrite_settings


def reset_mcp_settings() -> None:
    """Reset cached settings (for testing)."""
    global _mcp_settings, _mcp_readwrite_settings
    _mcp_settings = None
    _mcp_readwrite_settings = None
