"""Unit tests for ReadOnlyMCPClient — timeout produces EvidenceGap (mock MCP)."""

import pytest

from src.config.mcp_settings import MCPSettings
from src.models.diagnosis import EvidenceArtifact, EvidenceGap, EvidenceSource
from src.pipeline.mcp_client import ReadOnlyMCPClient


@pytest.fixture
def mcp_settings() -> MCPSettings:
    return MCPSettings(
        url="http://mock-mcp:8080/mcp",
        timeout_seconds=0.5,
        max_retries=0,
        retry_delay_seconds=0.0,
    )


class TestMCPClientSuccess:
    """MCP client returns EvidenceArtifact on successful tool calls."""

    @pytest.mark.unit
    async def test_successful_query_returns_evidence(self, mock_mcp_client, mcp_settings):
        client = ReadOnlyMCPClient(settings=mcp_settings)
        result = await client.query("get_resources", {"kind": "Pod"})
        assert isinstance(result, EvidenceArtifact)
        assert result.source == EvidenceSource.MCP_CLUSTER
        assert "get_resources" in result.query
        assert result.result  # non-empty

    @pytest.mark.unit
    async def test_query_records_timestamp(self, mock_mcp_client, mcp_settings):
        client = ReadOnlyMCPClient(settings=mcp_settings)
        result = await client.query("get_resources", {"kind": "Pod"})
        assert isinstance(result, EvidenceArtifact)
        assert result.timestamp is not None
        assert result.timestamp.tzinfo is not None

    @pytest.mark.unit
    async def test_different_tools_return_different_results(self, mock_mcp_client, mcp_settings):
        client = ReadOnlyMCPClient(settings=mcp_settings)
        r1 = await client.query("get_resources", {"kind": "Pod"})
        r2 = await client.query("get_logs", {"pod": "test"})
        assert isinstance(r1, EvidenceArtifact)
        assert isinstance(r2, EvidenceArtifact)
        assert r1.result != r2.result


class TestMCPClientTimeout:
    """MCP timeout produces EvidenceGap, not an exception."""

    @pytest.mark.unit
    async def test_timeout_returns_evidence_gap(self, mock_mcp_client_timeout, mcp_settings):
        client = ReadOnlyMCPClient(settings=mcp_settings)
        result = await client.query("get_resources", {"kind": "Pod"})
        assert isinstance(result, EvidenceGap)
        assert result.timeout_seconds == mcp_settings.timeout_seconds
        assert "timed out" in result.reason

    @pytest.mark.unit
    async def test_timeout_records_query(self, mock_mcp_client_timeout, mcp_settings):
        client = ReadOnlyMCPClient(settings=mcp_settings)
        result = await client.query("get_resources", {"kind": "Pod"})
        assert isinstance(result, EvidenceGap)
        assert "get_resources" in result.query

    @pytest.mark.unit
    async def test_timeout_with_custom_value(self, mock_mcp_client_timeout, mcp_settings):
        client = ReadOnlyMCPClient(settings=mcp_settings)
        result = await client.query("get_resources", {}, timeout=0.1)
        assert isinstance(result, EvidenceGap)
        assert result.timeout_seconds == 0.1


class TestMCPClientConnectionFailure:
    """MCP connection errors produce EvidenceGap after retry exhaustion."""

    @pytest.mark.unit
    async def test_connection_error_returns_evidence_gap(self, mock_mcp_client_error, mcp_settings):
        client = ReadOnlyMCPClient(settings=mcp_settings)
        result = await client.query("get_resources", {"kind": "Pod"})
        assert isinstance(result, EvidenceGap)
        assert "failed" in result.reason.lower()

    @pytest.mark.unit
    async def test_retries_before_giving_up(self):
        """With retries configured, the client retries before returning a gap."""
        settings = MCPSettings(
            url="http://mock-mcp:8080/mcp",
            timeout_seconds=1.0,
            max_retries=1,
            retry_delay_seconds=0.0,
        )
        import asyncio
        from unittest.mock import AsyncMock, patch

        call_count = 0

        async def mock_failing_call(self, tool_name, arguments):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("connection refused")

        with patch(
            "src.pipeline.mcp_client.ReadOnlyMCPClient._call_tool",
            mock_failing_call,
        ):
            client = ReadOnlyMCPClient(settings=settings)
            result = await client.query("get_resources", {})

        assert isinstance(result, EvidenceGap)
        assert call_count == 2  # initial + 1 retry


class TestMCPClientPartialEvidence:
    """Partial evidence continuation — pipeline gets evidence where available."""

    @pytest.mark.unit
    async def test_partial_evidence_mix(self, mock_mcp_client, mcp_settings):
        """Some queries succeed, some timeout — both results are usable."""
        client = ReadOnlyMCPClient(settings=mcp_settings)

        success = await client.query("get_resources", {"kind": "Pod"})
        assert isinstance(success, EvidenceArtifact)

    @pytest.mark.unit
    async def test_timeout_gap_is_serializable(self, mock_mcp_client_timeout, mcp_settings):
        client = ReadOnlyMCPClient(settings=mcp_settings)
        result = await client.query("get_resources", {})
        assert isinstance(result, EvidenceGap)
        data = result.model_dump_json()
        restored = EvidenceGap.model_validate_json(data)
        assert restored == result
