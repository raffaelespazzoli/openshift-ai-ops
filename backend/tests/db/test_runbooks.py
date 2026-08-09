"""Database integration tests for runbook chunks — pgvector (AC: #3).

Tests store and retrieve operations via testcontainers PostgreSQL + pgvector.
These tests require Docker/Podman. Run with: pytest -m db
"""

from __future__ import annotations

import uuid

import pytest

from src.db.runbooks import delete_by_source_file, search_similar, store_chunks
from src.models.knowledge import RunbookChunk


def _make_chunk(
    source_file: str = "test.md",
    chunk_index: int = 0,
    content: str = "Test content",
) -> RunbookChunk:
    return RunbookChunk(
        source_file=source_file,
        chunk_index=chunk_index,
        heading_hierarchy=["Section", "Subsection"],
        content=content,
        token_count=len(content) // 4,
    )


def _make_embedding(dim: int = 1536, val: float = 0.1) -> list[float]:
    return [val] * dim


@pytest.mark.db
class TestStoreChunks:
    """Tests for storing runbook chunks with embeddings."""

    async def test_store_single_chunk(self, db_conn):
        chunk = _make_chunk()
        embedding = _make_embedding()
        count = await store_chunks(db_conn, [chunk], [embedding])
        assert count == 1

    async def test_store_multiple_chunks(self, db_conn):
        chunks = [_make_chunk(chunk_index=i, content=f"Content {i}") for i in range(3)]
        embeddings = [_make_embedding(val=0.1 * (i + 1)) for i in range(3)]
        count = await store_chunks(db_conn, chunks, embeddings)
        assert count == 3

    async def test_upsert_updates_existing(self, db_conn):
        chunk1 = _make_chunk(content="Original")
        await store_chunks(db_conn, [chunk1], [_make_embedding()])

        chunk2 = _make_chunk(content="Updated")
        await store_chunks(db_conn, [chunk2], [_make_embedding(val=0.2)])

        row = await db_conn.fetchrow(
            "SELECT content FROM runbook_chunks WHERE source_file = $1 AND chunk_index = $2",
            "test.md", 0,
        )
        assert row["content"] == "Updated"


@pytest.mark.db
class TestSearchSimilar:
    """Tests for pgvector similarity search."""

    async def test_returns_results_ranked_by_similarity(self, db_conn):
        chunks = [
            _make_chunk(chunk_index=0, content="CrashLoopBackOff troubleshooting"),
            _make_chunk(chunk_index=1, content="Node disk pressure guide"),
            _make_chunk(chunk_index=2, content="Network DNS resolution failures"),
        ]
        embeddings = [
            _make_embedding(val=0.9),
            _make_embedding(val=0.5),
            _make_embedding(val=0.1),
        ]
        await store_chunks(db_conn, chunks, embeddings)

        query_embedding = _make_embedding(val=0.9)
        results = await search_similar(db_conn, query_embedding, top_k=3, similarity_threshold=0.0)
        assert len(results) > 0
        similarities = [r["similarity"] for r in results]
        assert similarities == sorted(similarities, reverse=True)

    async def test_respects_similarity_threshold(self, db_conn):
        chunks = [_make_chunk(chunk_index=0, content="Test")]
        embeddings = [_make_embedding(val=0.1)]
        await store_chunks(db_conn, chunks, embeddings)

        query = _make_embedding(val=0.9)
        results = await search_similar(db_conn, query, top_k=5, similarity_threshold=0.99)
        assert len(results) == 0 or all(r["similarity"] > 0.99 for r in results)

    async def test_respects_top_k_limit(self, db_conn):
        chunks = [_make_chunk(chunk_index=i, content=f"Chunk {i}") for i in range(10)]
        embeddings = [_make_embedding(val=0.1 * (i + 1)) for i in range(10)]
        await store_chunks(db_conn, chunks, embeddings)

        query = _make_embedding(val=0.5)
        results = await search_similar(db_conn, query, top_k=3, similarity_threshold=0.0)
        assert len(results) <= 3


@pytest.mark.db
class TestDeleteBySourceFile:
    """Tests for deleting chunks by source file."""

    async def test_deletes_all_chunks_for_file(self, db_conn):
        chunks = [_make_chunk(chunk_index=i) for i in range(3)]
        embeddings = [_make_embedding() for _ in range(3)]
        await store_chunks(db_conn, chunks, embeddings)

        deleted = await delete_by_source_file(db_conn, "test.md")
        assert deleted == 3

    async def test_does_not_delete_other_files(self, db_conn):
        chunks_a = [_make_chunk(source_file="a.md", chunk_index=0)]
        chunks_b = [_make_chunk(source_file="b.md", chunk_index=0)]
        await store_chunks(db_conn, chunks_a, [_make_embedding()])
        await store_chunks(db_conn, chunks_b, [_make_embedding()])

        await delete_by_source_file(db_conn, "a.md")

        count = await db_conn.fetchval(
            "SELECT count(*) FROM runbook_chunks WHERE source_file = $1", "b.md"
        )
        assert count == 1
