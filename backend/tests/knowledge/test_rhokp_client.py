"""Unit tests for RHOKP MCP client (AC: #1, #6).

Tests search_portal, get_document, and timeout → EvidenceGap behavior.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.config.rhokp_settings import RHOKPSettings
from src.knowledge.rhokp_client import RHOKPClient
from src.models.diagnosis import EvidenceGap


class TestRHOKPClientSearchPortal:
    """Tests for RHOKPClient.search_portal()."""

    @pytest.mark.unit
    async def test_search_portal_returns_structured_data_on_success(self):
        """search_portal returns success with parsed structured data."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        mock_json = '[{"id": "doc1", "title": "Node memory pressure", "score": 0.95}, {"id": "doc2", "title": "OOM Kill investigation", "score": 0.88}]'

        with patch.object(client, "_call_tool", new_callable=AsyncMock, return_value=mock_json):
            result = await client.search_portal(["node memory pressure"], top_k=3)

        assert result["success"] is True
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 2
        assert result["data"][0]["id"] == "doc1"
        assert result["data"][0]["score"] == 0.95

    @pytest.mark.unit
    async def test_search_portal_uses_settings_top_k(self):
        """search_portal uses settings default top_k when not specified."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", top_k=10)
        client = RHOKPClient(settings=settings)

        call_args = {}

        async def capture_call(tool_name, arguments):
            call_args.update(arguments)
            return '[]'

        with patch.object(client, "_call_tool", side_effect=capture_call):
            await client.search_portal(["test query"])

        assert call_args["rows"] == 10

    @pytest.mark.unit
    async def test_search_portal_timeout_produces_evidence_gap(self):
        """search_portal timeout produces EvidenceGap (not exception)."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", timeout_seconds=0.01)
        client = RHOKPClient(settings=settings)

        async def slow_call(tool_name, arguments):
            await asyncio.sleep(100)
            return "never reached"

        with patch.object(client, "_call_tool", side_effect=slow_call):
            result = await client.search_portal(["test"])

        assert result["success"] is False
        assert isinstance(result["evidence_gap"], EvidenceGap)
        assert "timed out" in result["evidence_gap"].reason
        assert result["evidence_gap"].timeout_seconds == 0.01

    @pytest.mark.unit
    async def test_search_portal_connection_error_produces_evidence_gap(self):
        """search_portal connection failure produces EvidenceGap."""
        settings = RHOKPSettings(url="http://mock:8000/mcp")
        client = RHOKPClient(settings=settings)

        with patch.object(
            client, "_call_tool", new_callable=AsyncMock,
            side_effect=ConnectionError("Connection refused"),
        ):
            result = await client.search_portal(["test"])

        assert result["success"] is False
        assert isinstance(result["evidence_gap"], EvidenceGap)
        assert "failed" in result["evidence_gap"].reason


    @pytest.mark.unit
    async def test_search_portal_normalizes_dict_with_results_key(self):
        """search_portal normalizes a dict with 'results' key to list[dict]."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        mock_json = '{"results": [{"id": "doc1", "score": 0.9}]}'

        with patch.object(client, "_call_tool", new_callable=AsyncMock, return_value=mock_json):
            result = await client.search_portal(["test"])

        assert result["success"] is True
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "doc1"

    @pytest.mark.unit
    async def test_search_portal_normalizes_plain_list(self):
        """search_portal returns plain list as-is when MCP returns a JSON array."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        mock_json = '[{"id": "a"}, {"id": "b"}]'

        with patch.object(client, "_call_tool", new_callable=AsyncMock, return_value=mock_json):
            result = await client.search_portal(["test"])

        assert result["success"] is True
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 2

    @pytest.mark.unit
    async def test_search_portal_normalizes_non_json_to_list(self):
        """search_portal wraps non-JSON text into a single-element list[dict]."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        with patch.object(client, "_call_tool", new_callable=AsyncMock, return_value="plain text"):
            result = await client.search_portal(["test"])

        assert result["success"] is True
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 1
        assert result["data"][0]["raw_content"] == "plain text"


class TestRHOKPClientGetDocument:
    """Tests for RHOKPClient.get_document()."""

    @pytest.mark.unit
    async def test_get_document_returns_structured_data_on_success(self):
        """get_document returns parsed structured dict."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        mock_json = '{"id": "DOC-12345", "title": "Memory troubleshooting", "passages": [{"text": "Check OOM events", "score": 0.92}]}'

        with patch.object(client, "_call_tool", new_callable=AsyncMock, return_value=mock_json):
            result = await client.get_document("DOC-12345")

        assert result["success"] is True
        assert isinstance(result["data"], dict)
        assert result["data"]["id"] == "DOC-12345"
        assert result["data"]["passages"][0]["score"] == 0.92

    @pytest.mark.unit
    async def test_non_json_response_wrapped_in_dict(self):
        """Non-JSON MCP response is wrapped in a structured dict with raw_content."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", timeout_seconds=5.0)
        client = RHOKPClient(settings=settings)

        mock_plain_text = "This is plain text, not JSON"

        with patch.object(client, "_call_tool", new_callable=AsyncMock, return_value=mock_plain_text):
            result = await client.get_document("DOC-99999")

        assert result["success"] is True
        assert isinstance(result["data"], dict)
        assert result["data"]["raw_content"] == mock_plain_text

    @pytest.mark.unit
    async def test_get_document_timeout_produces_evidence_gap(self):
        """get_document timeout produces EvidenceGap."""
        settings = RHOKPSettings(url="http://mock:8000/mcp", timeout_seconds=0.01)
        client = RHOKPClient(settings=settings)

        async def slow_call(tool_name, arguments):
            await asyncio.sleep(100)
            return "never reached"

        with patch.object(client, "_call_tool", side_effect=slow_call):
            result = await client.get_document("DOC-12345")

        assert result["success"] is False
        assert isinstance(result["evidence_gap"], EvidenceGap)
        assert "timed out" in result["evidence_gap"].reason
        assert result["evidence_gap"].timeout_seconds == 0.01

    @pytest.mark.unit
    async def test_get_document_passes_correct_arguments(self):
        """get_document passes doc_id as 'id' argument to MCP tool."""
        settings = RHOKPSettings(url="http://mock:8000/mcp")
        client = RHOKPClient(settings=settings)

        captured_args = {}

        async def capture_call(tool_name, arguments):
            captured_args["tool"] = tool_name
            captured_args["args"] = arguments
            return '{"id": "MY-DOC-ID", "content": "text"}'

        with patch.object(client, "_call_tool", side_effect=capture_call):
            await client.get_document("MY-DOC-ID")

        assert captured_args["tool"] == "get_document"
        assert captured_args["args"] == {"id": "MY-DOC-ID"}
