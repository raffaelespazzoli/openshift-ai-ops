"""DB integration tests for case_records table (AC: #2, #3).

Tests migration creates table, pgvector queries work, empty table
returns gracefully. Requires testcontainers (pytest -m db).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.db.case_records import search_similar_cases


@pytest.mark.db
class TestCaseRecordsTable:
    """Tests for the case_records table and pgvector queries."""

    async def test_table_created_by_migration(self, db_conn):
        """case_records table exists after migration."""
        result = await db_conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'case_records')"
        )
        assert result is True

    async def test_hnsw_index_exists(self, db_conn):
        """HNSW index exists on alert_signature_embedding column."""
        result = await db_conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'case_records_embedding_idx')"
        )
        assert result is True

    async def test_empty_table_returns_empty_list(self, db_conn):
        """search_similar_cases on empty table returns empty list (AC #3)."""
        from pgvector.asyncpg import register_vector
        await register_vector(db_conn)

        query_embedding = [0.1] * 1536
        results = await search_similar_cases(db_conn, query_embedding)
        assert results == []

    async def test_returns_results_ranked_by_similarity(self, db_conn):
        """search_similar_cases returns results ordered by cosine similarity."""
        from pgvector.asyncpg import register_vector
        await register_vector(db_conn)

        # Insert two case records with different embeddings
        embedding_close = [0.9] + [0.1] * 1535
        embedding_far = [0.1] + [0.9] * 1535

        await db_conn.execute(
            """
            INSERT INTO case_records (id, alert_signature, alert_signature_embedding,
                root_cause_code, outcome, outcome_confidence, ocp_version)
            VALUES ($1, $2, $3::vector, $4, $5, $6, $7)
            """,
            uuid.uuid4(), "KubePodCrashLooping", str(embedding_close),
            "workload/crash-loop-backoff", "success", 0.9, "4.14.5",
        )
        await db_conn.execute(
            """
            INSERT INTO case_records (id, alert_signature, alert_signature_embedding,
                root_cause_code, outcome, outcome_confidence, ocp_version)
            VALUES ($1, $2, $3::vector, $4, $5, $6, $7)
            """,
            uuid.uuid4(), "NodeNotReady", str(embedding_far),
            "node/not-ready", "success", 0.8, "4.14.5",
        )

        query_embedding = [0.85] + [0.1] * 1535
        results = await search_similar_cases(
            db_conn, query_embedding, top_k=5, similarity_threshold=0.0
        )

        assert len(results) >= 1
        # First result should be the closer embedding
        assert results[0]["alert_signature"] == "KubePodCrashLooping"

    async def test_similarity_threshold_filters_results(self, db_conn):
        """Results below similarity threshold are excluded."""
        from pgvector.asyncpg import register_vector
        await register_vector(db_conn)

        # Insert a record with embedding far from query
        embedding_far = [0.0] * 768 + [1.0] * 768
        await db_conn.execute(
            """
            INSERT INTO case_records (id, alert_signature, alert_signature_embedding,
                root_cause_code, outcome, outcome_confidence, ocp_version)
            VALUES ($1, $2, $3::vector, $4, $5, $6, $7)
            """,
            uuid.uuid4(), "DissimilarAlert", str(embedding_far),
            "unknown/unclassified", "failure", 0.5, "4.14.5",
        )

        query_embedding = [1.0] * 768 + [0.0] * 768
        results = await search_similar_cases(
            db_conn, query_embedding, top_k=5, similarity_threshold=0.99
        )

        assert len(results) == 0
