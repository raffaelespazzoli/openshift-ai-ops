"""Read-only MCP client wrapper with timeout → EvidenceGap (AD-2, AD-15).

Connects to the kubernetes-mcp-server via Streamable HTTP transport.
All queries are read-only (server enforces --read-only flag).
Timeouts produce EvidenceGap objects instead of raising exceptions,
ensuring the diagnosis pipeline continues with partial evidence.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..config.logging import Component, get_logger
from ..config.mcp_settings import MCPSettings, get_mcp_settings
from ..models.diagnosis import EvidenceArtifact, EvidenceGap, EvidenceSource

logger = get_logger(Component.PIPELINE)


class ReadOnlyMCPClient:
    """Client for querying the cluster via the read-only MCP Server."""

    def __init__(self, settings: MCPSettings | None = None) -> None:
        self._settings = settings or get_mcp_settings()

    async def query(
        self,
        tool_name: str,
        arguments: dict,
        timeout: float | None = None,
    ) -> EvidenceArtifact | EvidenceGap:
        """Execute an MCP tool call, returning evidence or an evidence gap on timeout.

        Args:
            tool_name: The MCP tool to invoke (e.g. 'resources_list', 'resources_get', 'pods_log').
            arguments: Arguments to pass to the tool.
            timeout: Override timeout in seconds. Uses settings default if None.

        Returns:
            EvidenceArtifact on success, EvidenceGap on timeout or connection failure.
        """
        effective_timeout = timeout if timeout is not None else self._settings.timeout_seconds
        last_error: Exception | None = None

        for attempt in range(1, self._settings.max_retries + 2):
            try:
                result = await asyncio.wait_for(
                    self._call_tool(tool_name, arguments),
                    timeout=effective_timeout,
                )
                return EvidenceArtifact(
                    source=EvidenceSource.MCP_CLUSTER,
                    query=f"{tool_name}({arguments})",
                    result=str(result),
                    timestamp=datetime.now(timezone.utc),
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "MCP query timed out",
                    extra={
                        "tool": tool_name,
                        "timeout": effective_timeout,
                        "attempt": attempt,
                    },
                )
                return EvidenceGap(
                    query=f"{tool_name}({arguments})",
                    reason="MCP query timed out",
                    timeout_seconds=effective_timeout,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "MCP query failed, retrying",
                    extra={
                        "tool": tool_name,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                if attempt <= self._settings.max_retries:
                    await asyncio.sleep(self._settings.retry_delay_seconds)

        return EvidenceGap(
            query=f"{tool_name}({arguments})",
            reason=f"MCP query failed after {self._settings.max_retries + 1} attempts: {last_error}",
        )

    async def _call_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute the actual MCP tool call via Streamable HTTP transport."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(self._settings.url) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                contents = []
                for block in result.content:
                    if hasattr(block, "text"):
                        contents.append(block.text)
                    else:
                        contents.append(str(block))
                return "\n".join(contents)
