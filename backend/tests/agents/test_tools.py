"""Unit tests for orchestrator tools (AC: #1, #2, #4).

Tests each tool returns correct EvidenceArtifact/EvidenceSource.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.tools import (
    get_orchestrator_tools,
    get_resource_logs,
    query_cluster_resources,
    search_runbooks,
    set_mcp_client,
)
from src.models.diagnosis import EvidenceArtifact, EvidenceGap, EvidenceSource


class TestQueryClusterResources:
    """Tests for the query_cluster_resources tool."""

    @pytest.mark.unit
    async def test_returns_evidence_on_success(self, mock_mcp_client):
        result = await query_cluster_resources.ainvoke({
            "resource_type": "Pod",
            "namespace": "default",
        })
        assert result["type"] == "evidence"
        assert result["source"] == EvidenceSource.MCP_CLUSTER.value

    @pytest.mark.unit
    async def test_returns_evidence_gap_on_timeout(self, mock_mcp_client_timeout):
        from src.config.mcp_settings import MCPSettings

        with patch("src.agents.tools._get_mcp_client") as mock_get:
            from src.pipeline.mcp_client import ReadOnlyMCPClient
            client = ReadOnlyMCPClient(MCPSettings(timeout_seconds=0.01))
            mock_get.return_value = client

            result = await query_cluster_resources.ainvoke({
                "resource_type": "Pod",
                "namespace": "default",
            })

        assert result["type"] == "evidence_gap"
        assert result["source"] == EvidenceSource.MCP_CLUSTER.value

    @pytest.mark.unit
    async def test_uses_get_resource_for_named_queries(self, mock_mcp_client):
        result = await query_cluster_resources.ainvoke({
            "resource_type": "Pod",
            "namespace": "default",
            "name": "my-pod",
        })
        assert result["type"] == "evidence"
        assert "get_resource" in result["query"]


class TestGetResourceLogs:
    """Tests for the get_resource_logs tool."""

    @pytest.mark.unit
    async def test_returns_evidence_with_logs(self, mock_mcp_client):
        result = await get_resource_logs.ainvoke({
            "namespace": "default",
            "pod_name": "test-pod-1",
        })
        assert result["type"] == "evidence"
        assert result["source"] == EvidenceSource.MCP_CLUSTER.value
        assert "OOMKilled" in result["result"]

    @pytest.mark.unit
    async def test_returns_evidence_gap_on_failure(self, mock_mcp_client_error):
        from src.config.mcp_settings import MCPSettings

        with patch("src.agents.tools._get_mcp_client") as mock_get:
            from src.pipeline.mcp_client import ReadOnlyMCPClient
            client = ReadOnlyMCPClient(MCPSettings(max_retries=0))
            mock_get.return_value = client

            result = await get_resource_logs.ainvoke({
                "namespace": "default",
                "pod_name": "nonexistent",
            })

        assert result["type"] == "evidence_gap"


class TestSearchRunbooks:
    """Tests for the search_runbooks tool."""

    @pytest.mark.unit
    async def test_returns_evidence_with_chunks(self):
        """search_runbooks returns runbook evidence via RAG retrieval."""
        from contextlib import asynccontextmanager

        from src.models.knowledge import RunbookChunk

        mock_chunks = [
            RunbookChunk(
                source_file="crashloop.md",
                chunk_index=0,
                heading_hierarchy=["Troubleshooting", "CrashLoopBackOff"],
                content="Check memory limits and OOM events.",
                token_count=10,
            ),
        ]

        mock_conn = AsyncMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool = AsyncMock()
        mock_pool.acquire = mock_acquire

        async def mock_get_pool():
            return mock_pool

        with (
            patch("src.db.connection.get_pool", side_effect=mock_get_pool),
            patch("src.db.get_pool", side_effect=mock_get_pool),
            patch("pgvector.asyncpg.register_vector", new_callable=AsyncMock),
            patch(
                "src.knowledge.runbook_rag.retrieve_runbook_context",
                new_callable=AsyncMock,
                return_value=mock_chunks,
            ),
        ):
            result = await search_runbooks.ainvoke({
                "query": "CrashLoopBackOff pod restart",
            })

        assert result["type"] == "evidence"
        assert result["source"] == EvidenceSource.RUNBOOK.value
        assert len(result["chunks"]) > 0

    @pytest.mark.unit
    async def test_returns_empty_when_no_chunks_found(self):
        """Returns evidence with empty chunks when no matches found."""
        from contextlib import asynccontextmanager

        mock_conn = AsyncMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool = AsyncMock()
        mock_pool.acquire = mock_acquire

        async def mock_get_pool():
            return mock_pool

        with (
            patch("src.db.connection.get_pool", side_effect=mock_get_pool),
            patch("src.db.get_pool", side_effect=mock_get_pool),
            patch("pgvector.asyncpg.register_vector", new_callable=AsyncMock),
            patch(
                "src.knowledge.runbook_rag.retrieve_runbook_context",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await search_runbooks.ainvoke({
                "query": "nonexistent issue",
            })

        assert result["type"] == "evidence"
        assert result["chunks"] == []

    @pytest.mark.unit
    async def test_handles_retrieval_failure_gracefully(self):
        """Returns evidence_gap when RAG retrieval fails."""
        with patch("src.db.get_pool", new_callable=AsyncMock, side_effect=RuntimeError("DB down")):
            result = await search_runbooks.ainvoke({
                "query": "some query",
            })

        assert result["type"] == "evidence_gap"
        assert "failed" in result["reason"].lower()


class TestGetOrchestratorTools:
    """Tests for the tool list getter."""

    @pytest.mark.unit
    def test_returns_three_tools(self):
        tools = get_orchestrator_tools()
        assert len(tools) == 3

    @pytest.mark.unit
    def test_tool_names_correct(self):
        tools = get_orchestrator_tools()
        names = {t.name for t in tools}
        assert "query_cluster_resources" in names
        assert "get_resource_logs" in names
        assert "search_runbooks" in names
