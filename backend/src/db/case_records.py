"""Database operations for case records — pgvector similarity search (AD-20).

Read-only: this module only queries. Epic 4 implements the write path.
"""

from __future__ import annotations

import asyncpg

from ..config.logging import Component, get_logger

logger = get_logger(Component.DB)


async def search_similar_cases(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    top_k: int = 3,
    similarity_threshold: float = 0.75,
) -> list[dict]:
    """Search for case records similar to the given embedding using cosine distance.

    Args:
        conn: asyncpg connection with pgvector registered.
        query_embedding: The query vector (alert context embedding).
        top_k: Maximum number of results to return.
        similarity_threshold: Minimum similarity score (0-1).

    Returns:
        List of dicts with case record data and similarity scores,
        ranked by similarity. Returns empty list if no records exist.
    """
    rows = await conn.fetch(
        """
        SELECT id, alert_signature, root_cause_code, outcome,
               outcome_confidence, ocp_version, created_at,
               1 - (alert_signature_embedding <=> $1::vector) AS similarity
        FROM case_records
        WHERE 1 - (alert_signature_embedding <=> $1::vector) > $3
        ORDER BY alert_signature_embedding <=> $1::vector
        LIMIT $2
        """,
        str(query_embedding),
        top_k,
        similarity_threshold,
    )
    return [dict(row) for row in rows]
