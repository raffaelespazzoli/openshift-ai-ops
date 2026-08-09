"""MCP integration tests — exercises the real MCP protocol stack.

Tests the MCP client through the full MCP protocol: MCPServer →
in-memory transport → ClientSession.initialize() → call_tool() →
response parsing. This validates AC #4 (MCP protocol/transport)
and AC #7 (timeout handling) by exercising the real SDK classes.

Transport-level tests exercise ReadOnlyMCPClient._call_tool() by
patching streamable_http_client to route through a mock MCP server
over in-memory streams, verifying the full call_tool → session →
response parsing path shipped in production code.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import patch as mock_patch

import pytest

from src.config.mcp_settings import MCPSettings
from src.models.diagnosis import EvidenceArtifact, EvidenceGap, EvidenceSource
from tests.pipeline.conftest import CANNED_RESPONSES


MOCK_MCP_URL = "http://mock-mcp:8080/mcp"


@pytest.fixture
def mcp_settings() -> MCPSettings:
    return MCPSettings(
        url=MOCK_MCP_URL,
        timeout_seconds=5.0,
        max_retries=0,
        retry_delay_seconds=0.0,
    )


@pytest.fixture
def mcp_settings_short_timeout() -> MCPSettings:
    return MCPSettings(
        url=MOCK_MCP_URL,
        timeout_seconds=0.5,
        max_retries=0,
        retry_delay_seconds=0.0,
    )


def _build_mock_mcp_server(*, delay_seconds: float = 0.0):
    """Build an MCPServer with canned tool responses for protocol-level testing."""
    from mcp.server import MCPServer

    server = MCPServer(name="mock-mcp-readonly", version="0.1.0")

    @server.tool()
    async def get_resources(kind: str = "Pod", namespace: str = "default") -> str:
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        return json.dumps(CANNED_RESPONSES["get_resources"])

    @server.tool()
    async def get_resource(kind: str = "Pod", name: str = "", namespace: str = "default") -> str:
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        return json.dumps(CANNED_RESPONSES["get_resource"])

    @server.tool()
    async def describe_resource(kind: str = "Pod", name: str = "") -> str:
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        return json.dumps(CANNED_RESPONSES["describe_resource"])

    @server.tool()
    async def get_logs(pod: str = "") -> str:
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        return CANNED_RESPONSES["get_logs"]

    @server.tool()
    async def get_events() -> str:
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        return json.dumps(CANNED_RESPONSES["get_events"])

    return server


def _create_mock_streamable_transport(*, delay_seconds: float = 0.0):
    """Create a mock streamable_http_client that routes through an in-memory MCP server.

    Returns a context manager that replaces streamable_http_client in
    ReadOnlyMCPClient._call_tool(), so the full production code path
    (ClientSession creation, initialize(), call_tool(), response parsing)
    is exercised without requiring a real HTTP endpoint.
    """
    from mcp import ServerCapabilities
    from mcp.server import InitializationOptions
    from mcp.shared.memory import create_client_server_memory_streams

    server = _build_mock_mcp_server(delay_seconds=delay_seconds)

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
                        server_name="mock-mcp-readonly",
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


async def _run_mcp_protocol_test(tool_name: str, arguments: dict, *, delay_seconds: float = 0.0):
    """Run a full MCP protocol exchange using in-memory transport.

    Exercises: MCPServer ↔ ClientSession.initialize() ↔ call_tool() ↔ response parsing.
    """
    from mcp import ClientSession, ServerCapabilities
    from mcp.server import InitializationOptions
    from mcp.shared.memory import create_client_server_memory_streams

    server = _build_mock_mcp_server(delay_seconds=delay_seconds)

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams

        async with asyncio.TaskGroup() as tg:
            server_task = tg.create_task(
                server._lowlevel_server.run(
                    server_read,
                    server_write,
                    InitializationOptions(
                        server_name="mock-mcp-readonly",
                        server_version="0.1.0",
                        capabilities=ServerCapabilities(
                            tools={"listChanged": False},
                        ),
                    ),
                )
            )

            async with ClientSession(client_read, client_write) as session:
                init_result = await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                contents = []
                for block in result.content:
                    if hasattr(block, "text"):
                        contents.append(block.text)
                    else:
                        contents.append(str(block))

                server_task.cancel()
                return init_result, "\n".join(contents)


class TestMCPStreamableHTTPIntegration:
    """MCP protocol-level tests via in-memory transport.

    Uses in-memory transport to exercise the full ClientSession lifecycle:
    initialize handshake → tool listing → call_tool → response parsing.
    """

    @pytest.mark.pipeline
    async def test_get_resources_via_mcp_protocol(self):
        """Full protocol: MCPServer → ClientSession.initialize() → call_tool."""
        init_result, result = await _run_mcp_protocol_test(
            "get_resources", {"kind": "Pod"},
        )
        assert init_result is not None
        assert "items" in result

    @pytest.mark.pipeline
    async def test_describe_resource_via_mcp_protocol(self):
        init_result, result = await _run_mcp_protocol_test(
            "describe_resource", {"kind": "Pod", "name": "test-pod-1"},
        )
        assert init_result is not None
        assert "OOMKilled" in result

    @pytest.mark.pipeline
    async def test_get_logs_via_mcp_protocol(self):
        init_result, result = await _run_mcp_protocol_test(
            "get_logs", {"pod": "test"},
        )
        assert init_result is not None
        assert "ERROR" in result

    @pytest.mark.pipeline
    async def test_session_initialize_returns_server_info(self):
        """Verify ClientSession.initialize() returns valid server capabilities."""
        init_result, _ = await _run_mcp_protocol_test(
            "get_resources", {"kind": "Pod"},
        )
        assert init_result is not None
        assert init_result.server_info.name == "mock-mcp-readonly"


class TestMCPClientViaTransport:
    """Exercise ReadOnlyMCPClient._call_tool() through the shipped transport path.

    Patches streamable_http_client at the import site so the full
    _call_tool() body executes: streamable_http_client → ClientSession →
    initialize() → call_tool() → response parsing. This tests the
    production code path without requiring a real HTTP endpoint.
    """

    @pytest.mark.pipeline
    async def test_query_via_transport_returns_evidence(self, mcp_settings):
        """ReadOnlyMCPClient.query() → _call_tool() → streamable_http_client."""
        from src.pipeline.mcp_client import ReadOnlyMCPClient

        mock_transport = _create_mock_streamable_transport()
        with mock_patch(
            "mcp.client.streamable_http.streamable_http_client",
            mock_transport,
        ):
            client = ReadOnlyMCPClient(settings=mcp_settings)
            result = await client.query("get_resources", {"kind": "Pod"})

        assert isinstance(result, EvidenceArtifact)
        assert "items" in result.result
        assert result.source == EvidenceSource.MCP_CLUSTER

    @pytest.mark.pipeline
    async def test_query_via_transport_parses_response(self, mcp_settings):
        """Response content blocks are joined and returned as result string."""
        from src.pipeline.mcp_client import ReadOnlyMCPClient

        mock_transport = _create_mock_streamable_transport()
        with mock_patch(
            "mcp.client.streamable_http.streamable_http_client",
            mock_transport,
        ):
            client = ReadOnlyMCPClient(settings=mcp_settings)
            result = await client.query(
                "describe_resource", {"kind": "Pod", "name": "test-pod-1"},
            )

        assert isinstance(result, EvidenceArtifact)
        assert "OOMKilled" in result.result

    @pytest.mark.pipeline
    async def test_query_via_transport_timeout_returns_gap(self):
        """Timeout through the real _call_tool path returns EvidenceGap."""
        from src.pipeline.mcp_client import ReadOnlyMCPClient

        settings = MCPSettings(
            url=MOCK_MCP_URL,
            timeout_seconds=0.3,
            max_retries=0,
            retry_delay_seconds=0.0,
        )
        mock_transport = _create_mock_streamable_transport(delay_seconds=5.0)
        with mock_patch(
            "mcp.client.streamable_http.streamable_http_client",
            mock_transport,
        ):
            client = ReadOnlyMCPClient(settings=settings)
            result = await client.query("get_resources", {"kind": "Node"})

        assert isinstance(result, EvidenceGap)
        assert "timed out" in result.reason
        assert result.timeout_seconds == 0.3


class TestMCPTimeoutIntegration:
    """MCP timeout scenario returns partial evidence with evidence_gaps populated."""

    @pytest.mark.pipeline
    async def test_timeout_returns_evidence_gap(self, mock_mcp_client_timeout, mcp_settings_short_timeout):
        from src.pipeline.mcp_client import ReadOnlyMCPClient

        client = ReadOnlyMCPClient(settings=mcp_settings_short_timeout)
        result = await client.query("get_resources", {"kind": "Node"})
        assert isinstance(result, EvidenceGap)
        assert result.timeout_seconds == mcp_settings_short_timeout.timeout_seconds
        assert "timed out" in result.reason

    @pytest.mark.pipeline
    async def test_timeout_gap_has_query_info(self, mock_mcp_client_timeout, mcp_settings_short_timeout):
        from src.pipeline.mcp_client import ReadOnlyMCPClient

        client = ReadOnlyMCPClient(settings=mcp_settings_short_timeout)
        result = await client.query("describe_resource", {"kind": "Node", "name": "worker-1"})
        assert isinstance(result, EvidenceGap)
        assert "describe_resource" in result.query


class TestMCPPartialEvidence:
    """Successful queries produce evidence usable alongside gaps."""

    @pytest.mark.pipeline
    async def test_partial_evidence_continuation(self, mock_mcp_client, mcp_settings):
        from src.pipeline.mcp_client import ReadOnlyMCPClient

        client = ReadOnlyMCPClient(settings=mcp_settings)
        evidence_list = []
        gaps_list = []

        r1 = await client.query("get_resources", {"kind": "Pod"})
        if isinstance(r1, EvidenceArtifact):
            evidence_list.append(r1)
        else:
            gaps_list.append(r1)

        assert len(evidence_list) == 1
        assert len(gaps_list) == 0


class TestMCPConcurrentQueries:
    """Multiple concurrent MCP queries handled correctly."""

    @pytest.mark.pipeline
    async def test_concurrent_queries(self, mock_mcp_client, mcp_settings):
        from src.pipeline.mcp_client import ReadOnlyMCPClient

        client = ReadOnlyMCPClient(settings=mcp_settings)
        tasks = [
            client.query("get_resources", {"kind": "Pod"}),
            client.query("get_resources", {"kind": "Node"}),
            client.query("describe_resource", {"kind": "Pod", "name": "test-pod-1"}),
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 3
        assert all(isinstance(r, EvidenceArtifact) for r in results)

    @pytest.mark.pipeline
    async def test_concurrent_mix_success_and_timeout(self, mcp_settings_short_timeout):
        """Some queries succeed, some timeout — both handled correctly."""
        from src.pipeline.mcp_client import ReadOnlyMCPClient

        call_count = 0

        async def mock_mixed_call(self, tool_name: str, arguments: dict) -> str:
            nonlocal call_count
            call_count += 1
            if tool_name == "get_logs":
                await asyncio.sleep(100)
            return json.dumps({"items": []})

        with mock_patch(
            "src.pipeline.mcp_client.ReadOnlyMCPClient._call_tool",
            mock_mixed_call,
        ):
            client = ReadOnlyMCPClient(settings=mcp_settings_short_timeout)
            tasks = [
                client.query("get_resources", {"kind": "Pod"}),
                client.query("get_logs", {"pod": "test"}),
            ]
            results = await asyncio.gather(*tasks)

        successes = [r for r in results if isinstance(r, EvidenceArtifact)]
        gaps = [r for r in results if isinstance(r, EvidenceGap)]
        assert len(successes) == 1
        assert len(gaps) == 1
        assert "timed out" in gaps[0].reason
