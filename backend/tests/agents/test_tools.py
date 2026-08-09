"""Unit tests for orchestrator tools (AC: #1, #2, #4, #6).

Tests each tool returns correct EvidenceArtifact/EvidenceSource.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.tools import (
    _get_cluster_ocp_version,
    get_orchestrator_tools,
    get_resource_logs,
    get_rhokp_document,
    query_cluster_resources,
    query_past_incidents,
    search_rhokp,
    search_runbooks,
    set_mcp_client,
    set_rhokp_client,
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


class TestSearchRhokp:
    """Tests for the search_rhokp tool."""

    @pytest.mark.unit
    async def test_returns_evidence_on_success(self):
        """search_rhokp returns evidence with source=RHOKP."""
        from src.knowledge.rhokp_client import RHOKPClient

        mock_client = AsyncMock(spec=RHOKPClient)
        mock_client.search_portal = AsyncMock(return_value={
            "success": True,
            "data": [{"id": "doc1", "title": "Node memory pressure guide", "score": 0.9}],
        })
        set_rhokp_client(mock_client)

        try:
            result = await search_rhokp.ainvoke({"queries": ["node memory pressure"]})
            assert result["type"] == "evidence"
            assert result["source"] == EvidenceSource.RHOKP.value
            assert "node memory pressure" in result["query"]
        finally:
            set_rhokp_client(None)

    @pytest.mark.unit
    async def test_returns_evidence_gap_on_failure(self):
        """search_rhokp returns evidence_gap when RHOKP is unavailable."""
        from src.knowledge.rhokp_client import RHOKPClient

        mock_client = AsyncMock(spec=RHOKPClient)
        mock_client.search_portal = AsyncMock(return_value={
            "success": False,
            "evidence_gap": EvidenceGap(
                query="search_portal(['test'])",
                reason="RHOKP query timed out",
                timeout_seconds=30.0,
            ),
        })
        set_rhokp_client(mock_client)

        try:
            result = await search_rhokp.ainvoke({"queries": ["test"]})
            assert result["type"] == "evidence_gap"
            assert result["source"] == EvidenceSource.RHOKP.value
        finally:
            set_rhokp_client(None)

    @pytest.mark.unit
    async def test_supports_multi_query_rank_fusion(self):
        """search_rhokp accepts multiple queries for reciprocal rank fusion (AC #1)."""
        from src.knowledge.rhokp_client import RHOKPClient

        mock_client = AsyncMock(spec=RHOKPClient)
        mock_client.search_portal = AsyncMock(return_value={
            "success": True,
            "data": [{"id": "doc1", "title": "fused results", "score": 0.95}],
        })
        set_rhokp_client(mock_client)

        try:
            queries = [
                "node memory pressure OOM",
                "kubelet eviction threshold",
                "container memory limits exceeded",
            ]
            result = await search_rhokp.ainvoke({"queries": queries})
            assert result["type"] == "evidence"
            assert result["source"] == EvidenceSource.RHOKP.value
            mock_client.search_portal.assert_called_once_with(queries, top_k=5)
            assert "node memory pressure OOM" in result["query"]
            assert "kubelet eviction threshold" in result["query"]
        finally:
            set_rhokp_client(None)


class TestGetRhokpDocument:
    """Tests for the get_rhokp_document tool."""

    @pytest.mark.unit
    async def test_returns_evidence_on_success(self):
        """get_rhokp_document returns evidence with source=RHOKP."""
        from src.knowledge.rhokp_client import RHOKPClient

        mock_client = AsyncMock(spec=RHOKPClient)
        mock_client.get_document = AsyncMock(return_value={
            "success": True,
            "data": {"id": "DOC-123", "title": "Full document", "content": "Body text"},
        })
        set_rhokp_client(mock_client)

        try:
            result = await get_rhokp_document.ainvoke({"doc_id": "DOC-123"})
            assert result["type"] == "evidence"
            assert result["source"] == EvidenceSource.RHOKP.value
        finally:
            set_rhokp_client(None)


class TestQueryPastIncidents:
    """Tests for the query_past_incidents tool."""

    @pytest.mark.unit
    async def test_returns_evidence_with_empty_learning_store(self):
        """query_past_incidents returns evidence with empty cases on fresh deployment."""
        from contextlib import asynccontextmanager

        mock_conn = AsyncMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool = AsyncMock()
        mock_pool.acquire = mock_acquire

        with (
            patch("src.agents.tools._get_cluster_ocp_version", new_callable=AsyncMock, return_value="4.15.2"),
            patch("src.agents.tools._get_db_pool", new_callable=AsyncMock, return_value=mock_pool),
            patch("pgvector.asyncpg.register_vector", new_callable=AsyncMock),
            patch(
                "src.knowledge.learning_store.query_learning_store",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await query_past_incidents.ainvoke({"alert_context": "pod crash"})

        assert result["type"] == "evidence"
        assert result["source"] == EvidenceSource.LEARNING_STORE.value
        assert result["cases"] == []

    @pytest.mark.unit
    async def test_returns_evidence_gap_on_failure(self):
        """query_past_incidents returns evidence_gap when query fails."""
        with (
            patch("src.agents.tools._get_cluster_ocp_version", new_callable=AsyncMock, return_value="4"),
            patch(
                "src.agents.tools._get_db_pool",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB unavailable"),
            ),
        ):
            result = await query_past_incidents.ainvoke({"alert_context": "test"})

        assert result["type"] == "evidence_gap"
        assert result["source"] == EvidenceSource.LEARNING_STORE.value

    @pytest.mark.unit
    async def test_queries_cluster_version_via_mcp(self):
        """query_past_incidents gets live OCP version from MCP and passes to learning store."""
        from contextlib import asynccontextmanager

        mock_conn = AsyncMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool = AsyncMock()
        mock_pool.acquire = mock_acquire

        mock_query_ls = AsyncMock(return_value=[])

        with (
            patch("src.agents.tools._get_cluster_ocp_version", new_callable=AsyncMock, return_value="4.16.1"),
            patch("src.agents.tools._get_db_pool", new_callable=AsyncMock, return_value=mock_pool),
            patch("pgvector.asyncpg.register_vector", new_callable=AsyncMock),
            patch(
                "src.knowledge.learning_store.query_learning_store",
                mock_query_ls,
            ),
        ):
            await query_past_incidents.ainvoke({"alert_context": "pod crash"})

        mock_query_ls.assert_called_once()
        call_kwargs = mock_query_ls.call_args
        assert call_kwargs.kwargs.get("current_ocp_version") == "4.16.1" or \
            (len(call_kwargs.args) > 4 and call_kwargs.args[4] == "4.16.1")


    @pytest.mark.unit
    async def test_passes_configured_similarity_threshold(self):
        """query_past_incidents passes the configured similarity threshold to the learning store."""
        from contextlib import asynccontextmanager

        mock_conn = AsyncMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool = AsyncMock()
        mock_pool.acquire = mock_acquire

        mock_query_ls = AsyncMock(return_value=[])

        with (
            patch("src.agents.tools._get_cluster_ocp_version", new_callable=AsyncMock, return_value="4.15"),
            patch("src.agents.tools._get_db_pool", new_callable=AsyncMock, return_value=mock_pool),
            patch("pgvector.asyncpg.register_vector", new_callable=AsyncMock),
            patch(
                "src.knowledge.learning_store.query_learning_store",
                mock_query_ls,
            ),
            patch(
                "src.config.knowledge_settings.get_knowledge_settings",
                return_value=type("S", (), {"learning_store_similarity_threshold": 0.82})(),
            ),
        ):
            await query_past_incidents.ainvoke({"alert_context": "high cpu"})

        mock_query_ls.assert_called_once()
        call_kwargs = mock_query_ls.call_args
        assert call_kwargs.kwargs.get("similarity_threshold") == 0.82


class TestGetClusterOcpVersion:
    """Tests for _get_cluster_ocp_version helper."""

    @pytest.mark.unit
    async def test_returns_version_from_cluster_version_resource(self):
        """Extracts OCP version from ClusterVersion resource via MCP."""
        cluster_version_json = json.dumps({
            "status": {
                "history": [
                    {"version": "4.16.1", "state": "Completed"},
                    {"version": "4.15.8", "state": "Completed"},
                ],
                "desired": {"version": "4.16.1"},
            }
        })
        mock_artifact = EvidenceArtifact(
            source=EvidenceSource.MCP_CLUSTER,
            query="get_resource({'kind': 'ClusterVersion', 'name': 'version'})",
            result=cluster_version_json,
            timestamp=datetime.now(timezone.utc),
        )
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_artifact)
        set_mcp_client(mock_client)

        try:
            version = await _get_cluster_ocp_version()
            assert version == "4.16.1"
        finally:
            set_mcp_client(None)

    @pytest.mark.unit
    async def test_falls_back_to_desired_version(self):
        """Falls back to desired version when history is empty."""
        cluster_version_json = json.dumps({
            "status": {
                "history": [],
                "desired": {"version": "4.15.0"},
            }
        })
        mock_artifact = EvidenceArtifact(
            source=EvidenceSource.MCP_CLUSTER,
            query="get_resource",
            result=cluster_version_json,
            timestamp=datetime.now(timezone.utc),
        )
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_artifact)
        set_mcp_client(mock_client)

        try:
            version = await _get_cluster_ocp_version()
            assert version == "4.15.0"
        finally:
            set_mcp_client(None)

    @pytest.mark.unit
    async def test_returns_fallback_on_evidence_gap(self):
        """Returns '4' fallback when MCP returns an EvidenceGap."""
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=EvidenceGap(
            query="get_resource",
            reason="MCP timeout",
            timeout_seconds=30.0,
        ))
        set_mcp_client(mock_client)

        try:
            version = await _get_cluster_ocp_version()
            assert version == "4"
        finally:
            set_mcp_client(None)


class TestGetOrchestratorTools:
    """Tests for the tool list getter."""

    @pytest.mark.unit
    def test_returns_six_tools(self):
        tools = get_orchestrator_tools()
        assert len(tools) == 6

    @pytest.mark.unit
    def test_tool_names_correct(self):
        tools = get_orchestrator_tools()
        names = {t.name for t in tools}
        assert "query_cluster_resources" in names
        assert "get_resource_logs" in names
        assert "search_runbooks" in names
        assert "search_rhokp" in names
        assert "get_rhokp_document" in names
        assert "query_past_incidents" in names
