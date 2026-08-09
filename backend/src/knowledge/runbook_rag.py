"""Runbook RAG retrieval — pgvector similarity search wrapper (AD-13).

Retrieves the top-k most relevant runbook chunks for a given alert context.
This is path 1 of the dual-path knowledge retrieval (AD-13).
Path 2 (RHOKP via okp-mcp) is Story 2.3.
"""

from __future__ import annotations

import asyncpg

from ..config.knowledge_settings import get_knowledge_settings
from ..config.logging import Component, get_logger
from ..db.runbooks import search_similar
from ..knowledge.embeddings import embed_texts
from ..models.knowledge import RunbookChunk

logger = get_logger(Component.KNOWLEDGE)


async def retrieve_runbook_context(
    alert_context: str,
    conn: asyncpg.Connection,
    top_k: int | None = None,
) -> list[RunbookChunk]:
    """Retrieve relevant runbook chunks for the given alert context.

    Embeds the alert context, performs pgvector similarity search, and
    returns the top-k matching chunks as RunbookChunk objects.

    Args:
        alert_context: Text describing the alert/incident for similarity matching.
        conn: asyncpg connection with pgvector types registered.
        top_k: Override for max results. Uses settings default if None.

    Returns:
        List of RunbookChunk objects ranked by relevance.
    """
    settings = get_knowledge_settings()
    effective_top_k = top_k if top_k is not None else settings.top_k

    embeddings = await embed_texts([alert_context])
    if not embeddings:
        logger.warning("Failed to generate embedding for alert context")
        return []

    query_embedding = embeddings[0]
    results = await search_similar(
        conn,
        query_embedding=query_embedding,
        top_k=effective_top_k,
        similarity_threshold=settings.similarity_threshold,
    )

    chunks = []
    for row in results:
        chunks.append(RunbookChunk(
            id=row["id"],
            source_file=row["source_file"],
            chunk_index=0,
            heading_hierarchy=row.get("heading_hierarchy", []),
            content=row["content"],
            token_count=row.get("token_count", 0),
        ))

    logger.info(
        "Retrieved runbook context",
        extra={"query_length": len(alert_context), "results": len(chunks)},
    )
    return chunks
