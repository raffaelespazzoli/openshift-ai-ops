"""Unit tests for runbook RAG retrieval (AC: #4).

Tests retrieval returns ranked chunks by similarity (mock embedding + mock DB).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.knowledge.runbook_rag import retrieve_runbook_context
from src.models.knowledge import RunbookChunk


class TestRetrieveRunbookContext:
    """Tests for the retrieve_runbook_context function."""

    @pytest.mark.unit
    async def test_returns_ranked_chunks(self):
        """Retrieval returns chunks ranked by similarity."""
        mock_embedding = [0.1] * 1536
        mock_results = [
            {
                "id": uuid.uuid4(),
                "source_file": "crashloop.md",
                "heading_hierarchy": ["Troubleshooting"],
                "content": "Check container restart count",
                "token_count": 10,
                "similarity": 0.95,
            },
            {
                "id": uuid.uuid4(),
                "source_file": "node-pressure.md",
                "heading_hierarchy": ["Diagnosis"],
                "content": "Node memory usage high",
                "token_count": 8,
                "similarity": 0.82,
            },
        ]

        with (
            patch(
                "src.knowledge.runbook_rag.embed_texts",
                new_callable=AsyncMock,
                return_value=[mock_embedding],
            ),
            patch(
                "src.knowledge.runbook_rag.search_similar",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
        ):
            conn = AsyncMock()
            chunks = await retrieve_runbook_context("CrashLoopBackOff pod", conn)

        assert len(chunks) == 2
        assert chunks[0].source_file == "crashloop.md"
        assert chunks[1].source_file == "node-pressure.md"

    @pytest.mark.unit
    async def test_returns_empty_on_no_matches(self):
        """Returns empty list when no chunks match threshold."""
        mock_embedding = [0.1] * 1536

        with (
            patch(
                "src.knowledge.runbook_rag.embed_texts",
                new_callable=AsyncMock,
                return_value=[mock_embedding],
            ),
            patch(
                "src.knowledge.runbook_rag.search_similar",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            conn = AsyncMock()
            chunks = await retrieve_runbook_context("completely unrelated", conn)

        assert chunks == []

    @pytest.mark.unit
    async def test_returns_empty_on_embedding_failure(self):
        """Returns empty list when embedding generation fails."""
        with patch(
            "src.knowledge.runbook_rag.embed_texts",
            new_callable=AsyncMock,
            return_value=[],
        ):
            conn = AsyncMock()
            chunks = await retrieve_runbook_context("any query", conn)

        assert chunks == []

    @pytest.mark.unit
    async def test_uses_configured_top_k(self):
        """Passes configured top_k to search_similar."""
        mock_embedding = [0.1] * 1536

        with (
            patch(
                "src.knowledge.runbook_rag.embed_texts",
                new_callable=AsyncMock,
                return_value=[mock_embedding],
            ),
            patch(
                "src.knowledge.runbook_rag.search_similar",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_search,
        ):
            conn = AsyncMock()
            await retrieve_runbook_context("test", conn, top_k=3)

        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs[1]["top_k"] == 3 or call_kwargs.kwargs.get("top_k") == 3

    @pytest.mark.unit
    async def test_returns_runbook_chunk_objects(self):
        """Results are proper RunbookChunk instances."""
        mock_embedding = [0.1] * 1536
        mock_results = [
            {
                "id": uuid.uuid4(),
                "source_file": "test.md",
                "heading_hierarchy": ["H1", "H2"],
                "content": "test content",
                "token_count": 5,
                "similarity": 0.9,
            },
        ]

        with (
            patch(
                "src.knowledge.runbook_rag.embed_texts",
                new_callable=AsyncMock,
                return_value=[mock_embedding],
            ),
            patch(
                "src.knowledge.runbook_rag.search_similar",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
        ):
            conn = AsyncMock()
            chunks = await retrieve_runbook_context("test", conn)

        assert len(chunks) == 1
        assert isinstance(chunks[0], RunbookChunk)
        assert chunks[0].content == "test content"
        assert chunks[0].heading_hierarchy == ["H1", "H2"]
