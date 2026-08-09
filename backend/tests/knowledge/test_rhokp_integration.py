"""Integration tests for RHOKP client Streamable HTTP transport (AC: #1, Task 10.3).

Tests RHOKPClient._call_tool() through the full MCP protocol stack using
in-memory transport: MCPServer → ClientSession.initialize() → call_tool() →
response parsing.  Unlike the unit tests in test_rhokp_client.py, these tests
never patch _call_tool() — they exercise the real production code path.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import patch as mock_patch

import pytest

from src.config.rhokp_settings import RHOKPSettings
from src.knowledge.rhokp_client import RHOKPClient

MOCK_OKP_URL = "http://mock-okp:8000/mcp"

CANNED_SEARCH_RESULTS = {
    "results": [
        {"id": "doc-1", "title": "Node troubleshooting", "score": 0.95},
        {"id": "doc-2", "title": "Memory pressure guide", "score": 0.87},
    ]
}

CANNED_DOCUMENT = {
    "id": "DOC-123",
    "title": "Troubleshooting Node Memory Pressure",
    "passages": [
        {"text": "Check kubelet memory thresholds", "score": 0.95},
        {"text": "Eviction signals and soft limits", "score": 0.88},
    ],
}


def _build_okp_mcp_server(*, delay_seconds: float = 0.0):
    """Build an in-memory MCP server mimicking the okp-mcp tools."""
    from mcp.server import MCPServer

    server = MCPServer(name="RHEL OKP Knowledge Base", version="0.1.0")

    @server.tool()
    async def search_portal(queries: list[str] | None = None, rows: int = 5) -> str:
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        return json.dumps(CANNED_SEARCH_RESULTS)

    @server.tool()
    async def get_document(id: str = "") -> str:
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        return json.dumps(CANNED_DOCUMENT)

    return server


def _create_okp_mock_transport(*, delay_seconds: float = 0.0):
    """Create a mock streamable_http_client routing through an in-memory okp-mcp server.

    Replaces streamable_http_client at the import site so
    RHOKPClient._call_tool() exercises the full production path:
    streamable_http_client → ClientSession → initialize() → call_tool() →
    response parsing — without requiring a real HTTP endpoint.
    """
    from mcp import ServerCapabilities
    from mcp.server import InitializationOptions
    from mcp.shared.memory import create_client_server_memory_streams

    server = _build_okp_mcp_server(delay_seconds=delay_seconds)

    @asynccontextmanager
    async def mock_streamable_http_client(url, **kwargs):
        async with create_client_server_memory_streams() as (
            client_streams,
            server_streams,
        ):
            client_read, client_write = client_streams
            server_read, server_write = server_streams

            server_task = asyncio.create_task(
                server._lowlevel_server.run(
                    server_read,
                    server_write,
                    InitializationOptions(
                        server_name="RHEL OKP Knowledge Base",
                        server_version="0.1.0",
                        capabilities=ServerCapabilities(
                            tools={"listChanged": False},
                        ),
                    ),
                )
            )
            try:
                yield client_read, client_write
            finally:
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass

    return mock_streamable_http_client


class TestRHOKPTransportIntegration:
    """RHOKP client integration tests exercising the MCP transport layer.

    These tests patch streamable_http_client (not _call_tool) so the full
    production code path — session creation, MCP initialize handshake,
    call_tool, and response parsing — is exercised.
    """

    @pytest.mark.pipeline
    async def test_search_portal_via_transport(self):
        """search_portal through real MCP transport returns structured search results."""
        settings = RHOKPSettings(url=MOCK_OKP_URL, timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        mock_transport = _create_okp_mock_transport()
        with mock_patch(
            "mcp.client.streamable_http.streamable_http_client",
            mock_transport,
        ):
            result = await client.search_portal(
                ["node not ready", "memory pressure"],
                top_k=5,
            )

        assert result["success"] is True
        data = result["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == "doc-1"

    @pytest.mark.pipeline
    async def test_get_document_via_transport(self):
        """get_document through real MCP transport returns structured document data."""
        settings = RHOKPSettings(url=MOCK_OKP_URL, timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        mock_transport = _create_okp_mock_transport()
        with mock_patch(
            "mcp.client.streamable_http.streamable_http_client",
            mock_transport,
        ):
            result = await client.get_document("DOC-123")

        assert result["success"] is True
        data = result["data"]
        assert isinstance(data, dict)
        assert data["id"] == "DOC-123"
        assert len(data["passages"]) == 2

    @pytest.mark.pipeline
    async def test_mcp_initialize_returns_server_info(self):
        """MCP initialize handshake returns correct server name."""
        from mcp import ClientSession, ServerCapabilities
        from mcp.server import InitializationOptions
        from mcp.shared.memory import create_client_server_memory_streams

        server = _build_okp_mcp_server()

        async with create_client_server_memory_streams() as (
            client_streams,
            server_streams,
        ):
            client_read, client_write = client_streams
            server_read, server_write = server_streams

            server_task = asyncio.create_task(
                server._lowlevel_server.run(
                    server_read,
                    server_write,
                    InitializationOptions(
                        server_name="RHEL OKP Knowledge Base",
                        server_version="0.1.0",
                        capabilities=ServerCapabilities(
                            tools={"listChanged": False},
                        ),
                    ),
                )
            )

            try:
                async with ClientSession(client_read, client_write) as session:
                    init_result = await session.initialize()
                    assert init_result.server_info.name == "RHEL OKP Knowledge Base"
            finally:
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.pipeline
    async def test_timeout_via_transport_returns_evidence_gap(self):
        """Timeout through the real transport path returns EvidenceGap."""
        settings = RHOKPSettings(url=MOCK_OKP_URL, timeout_seconds=0.3)
        client = RHOKPClient(settings=settings)

        mock_transport = _create_okp_mock_transport(delay_seconds=5.0)
        with mock_patch(
            "mcp.client.streamable_http.streamable_http_client",
            mock_transport,
        ):
            result = await client.search_portal(["test query"])

        assert result["success"] is False
        assert result["evidence_gap"].timeout_seconds == 0.3
        assert "timed out" in result["evidence_gap"].reason

    @pytest.mark.pipeline
    async def test_sequential_calls_via_transport(self):
        """Multiple sequential calls through real transport succeed."""
        settings = RHOKPSettings(url=MOCK_OKP_URL, timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        mock_transport = _create_okp_mock_transport()
        with mock_patch(
            "mcp.client.streamable_http.streamable_http_client",
            mock_transport,
        ):
            r1 = await client.search_portal(["query1"])
            r2 = await client.get_document("doc1")

        assert r1["success"] is True
        assert r2["success"] is True
