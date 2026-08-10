"""Read-write MCP client for remediation cluster access (AD-2, AD-9).

Connects to the kubernetes-mcp-server via Streamable HTTP transport.
Unlike the read-only client, this targets the MCP server bound to the
cluster-admin ServiceAccount — full read/write access to the cluster.

Returns raw string results (not EvidenceArtifact — that is diagnosis-side only).
Timeouts raise exceptions (no EvidenceGap concept on the write side).
"""

from __future__ import annotations

import asyncio

from ..config.logging import Component, get_logger
from ..config.mcp_settings import MCPReadWriteSettings, get_mcp_readwrite_settings

logger = get_logger(Component.PIPELINE)


class ReadWriteMCPClient:
    """Client for querying/mutating the cluster via the read-write MCP Server (AD-2)."""

    def __init__(self, settings: MCPReadWriteSettings | None = None) -> None:
        self._settings = settings or get_mcp_readwrite_settings()

    async def query(
        self,
        tool_name: str,
        arguments: dict,
        timeout: float | None = None,
    ) -> str:
        """Execute an MCP tool call, returning the raw result string.

        Raises on timeout (no EvidenceGap concept on the write side).

        Args:
            tool_name: The MCP tool to invoke (e.g. 'get_resources', 'describe_resource').
            arguments: Arguments to pass to the tool.
            timeout: Override timeout in seconds. Uses settings default if None.

        Returns:
            Raw string result from the MCP tool.

        Raises:
            TimeoutError: If the query exceeds the timeout.
            ConnectionError: If all retry attempts fail.
        """
        effective_timeout = timeout if timeout is not None else self._settings.timeout_seconds
        last_error: Exception | None = None

        for attempt in range(1, self._settings.max_retries + 2):
            try:
                result = await asyncio.wait_for(
                    self._call_tool(tool_name, arguments),
                    timeout=effective_timeout,
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(
                    "MCP read-write query timed out",
                    extra={
                        "tool": tool_name,
                        "timeout": effective_timeout,
                        "attempt": attempt,
                    },
                )
                raise TimeoutError(
                    f"MCP read-write query '{tool_name}' timed out after {effective_timeout}s"
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "MCP read-write query failed, retrying",
                    extra={
                        "tool": tool_name,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                if attempt <= self._settings.max_retries:
                    await asyncio.sleep(self._settings.retry_delay_seconds)

        raise ConnectionError(
            f"MCP read-write query '{tool_name}' failed after "
            f"{self._settings.max_retries + 1} attempts: {last_error}"
        )

    async def execute(
        self,
        tool_name: str,
        arguments: dict,
        timeout: float | None = None,
    ) -> str:
        """Execute a mutation via MCP. Used by Story 3.5 (execution), not this story.

        Same interface as query() — separated semantically for audit clarity.
        """
        return await self.query(tool_name, arguments, timeout=timeout)

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
