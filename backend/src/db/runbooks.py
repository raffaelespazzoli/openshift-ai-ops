"""Database operations for runbook chunks — pgvector store/search (AD-13).

All pgvector queries for the runbook_chunks table live here.
Never inline SQL in business logic.
"""

from __future__ import annotations

import uuid

import asyncpg

from ..config.logging import Component, get_logger
from ..models.knowledge import RunbookChunk

logger = get_logger(Component.DB)


async def store_chunks(
    conn: asyncpg.Connection,
    chunks: list[RunbookChunk],
    embeddings: list[list[float]],
) -> int:
    """Insert or upsert runbook chunks with their embeddings.

    Uses ON CONFLICT to update existing chunks (same source_file + chunk_index).

    Args:
        conn: asyncpg connection with pgvector registered.
        chunks: List of RunbookChunk objects to store.
        embeddings: Corresponding embedding vectors.

    Returns:
        Number of chunks stored.
    """
    if not chunks or not embeddings:
        return 0

    count = 0
    for chunk, embedding in zip(chunks, embeddings):
        await conn.execute(
            """
            INSERT INTO runbook_chunks (
                id, source_file, chunk_index, heading_hierarchy,
                content, embedding, token_count, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8)
            ON CONFLICT (source_file, chunk_index) DO UPDATE SET
                heading_hierarchy = EXCLUDED.heading_hierarchy,
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                token_count = EXCLUDED.token_count,
                metadata = EXCLUDED.metadata
            """,
            chunk.id,
            chunk.source_file,
            chunk.chunk_index,
            chunk.heading_hierarchy,
            chunk.content,
            str(embedding),
            chunk.token_count,
            "{}",
        )
        count += 1

    logger.info(
        "Stored runbook chunks",
        extra={"count": count, "source_file": chunks[0].source_file if chunks else ""},
    )
    return count


async def search_similar(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    top_k: int = 5,
    similarity_threshold: float = 0.7,
) -> list[dict]:
    """Search for similar runbook chunks using pgvector cosine distance.

    Args:
        conn: asyncpg connection with pgvector registered.
        query_embedding: The query vector to compare against.
        top_k: Maximum number of results to return.
        similarity_threshold: Minimum similarity score (0-1).

    Returns:
        List of dicts with chunk data and similarity scores, ranked by similarity.
    """
    rows = await conn.fetch(
        """
        SELECT id, source_file, heading_hierarchy, content, token_count,
               1 - (embedding <=> $1::vector) AS similarity
        FROM runbook_chunks
        WHERE 1 - (embedding <=> $1::vector) > $3
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        str(query_embedding),
        top_k,
        similarity_threshold,
    )
    return [dict(row) for row in rows]


async def delete_by_source_file(
    conn: asyncpg.Connection,
    source_file: str,
) -> int:
    """Delete all chunks for a given source file (used during re-ingestion)."""
    result = await conn.execute(
        "DELETE FROM runbook_chunks WHERE source_file = $1",
        source_file,
    )
    count = int(result.split()[-1]) if result else 0
    return count


async def delete_stale_chunks(
    conn: asyncpg.Connection,
    source_file: str,
    keep_count: int,
) -> int:
    """Delete chunks with chunk_index >= keep_count for a source file.

    Used after upserting new chunks to clean up stale indices from a
    previous ingestion that produced more chunks than the current one.
    """
    result = await conn.execute(
        "DELETE FROM runbook_chunks WHERE source_file = $1 AND chunk_index >= $2",
        source_file,
        keep_count,
    )
    count = int(result.split()[-1]) if result else 0
    return count
