"""Integration tests for runbook ingestion (AC: #3).

Tests end-to-end ingest of sample runbook files.
"""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge.ingest import ingest_runbooks


def _make_conn_with_transaction() -> AsyncMock:
    """Create a mock asyncpg connection that supports conn.transaction()."""
    conn = AsyncMock()

    @asynccontextmanager
    async def _fake_transaction():
        yield

    conn.transaction = _fake_transaction
    return conn


SAMPLE_RUNBOOK_1 = """# CrashLoopBackOff Troubleshooting

## Symptoms

Pod enters CrashLoopBackOff state repeatedly.

## Diagnosis

1. Check pod events
2. Check container logs for OOM kills

## Resolution

Increase memory limits or fix application memory leak.
"""

SAMPLE_RUNBOOK_2 = """# Node Not Ready

## Symptoms

Node shows NotReady condition.

## Diagnosis

Check kubelet status and node conditions.
"""


class TestIngestRunbooks:
    """Tests for the ingest_runbooks function."""

    @pytest.mark.unit
    async def test_ingests_markdown_files(self):
        """Ingest processes all .md files in directory."""
        mock_embedding = [0.1] * 1536

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "crashloop.md").write_text(SAMPLE_RUNBOOK_1)
            Path(tmpdir, "node-ready.md").write_text(SAMPLE_RUNBOOK_2)

            with (
                patch(
                    "src.knowledge.ingest.embed_texts",
                    new_callable=AsyncMock,
                    return_value=[mock_embedding] * 20,
                ),
                patch(
                    "src.knowledge.ingest.store_chunks",
                    new_callable=AsyncMock,
                    return_value=5,
                ),
                patch(
                    "src.knowledge.ingest.delete_stale_chunks",
                    new_callable=AsyncMock,
                    return_value=0,
                ),
            ):
                conn = _make_conn_with_transaction()
                stats = await ingest_runbooks(conn, runbooks_dir=tmpdir)

        assert stats["files_processed"] == 2
        assert stats["chunks_created"] > 0
        assert stats["errors"] == 0

    @pytest.mark.unit
    async def test_returns_zero_stats_for_missing_directory(self):
        """Non-existent directory returns zero stats."""
        conn = _make_conn_with_transaction()
        stats = await ingest_runbooks(conn, runbooks_dir="/nonexistent/path")
        assert stats["files_processed"] == 0
        assert stats["chunks_created"] == 0

    @pytest.mark.unit
    async def test_returns_zero_stats_for_empty_directory(self):
        """Empty directory returns zero stats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = _make_conn_with_transaction()
            stats = await ingest_runbooks(conn, runbooks_dir=tmpdir)
        assert stats["files_processed"] == 0
        assert stats["chunks_created"] == 0

    @pytest.mark.unit
    async def test_handles_embedding_failure_gracefully(self):
        """Files that fail to embed are counted as errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "failing.md").write_text(SAMPLE_RUNBOOK_1)

            with patch(
                    "src.knowledge.ingest.embed_texts",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("Embedding API down"),
            ):
                conn = _make_conn_with_transaction()
                stats = await ingest_runbooks(conn, runbooks_dir=tmpdir)

        assert stats["errors"] == 1

    @pytest.mark.unit
    async def test_cleans_up_stale_chunks_after_upsert(self):
        """Re-ingestion upserts first, then deletes stale chunks."""
        mock_embedding = [0.1] * 1536

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.md").write_text(SAMPLE_RUNBOOK_1)

            with (
                patch(
                    "src.knowledge.ingest.embed_texts",
                    new_callable=AsyncMock,
                    return_value=[mock_embedding] * 20,
                ),
                patch(
                    "src.knowledge.ingest.store_chunks",
                    new_callable=AsyncMock,
                    return_value=3,
                ),
                patch(
                    "src.knowledge.ingest.delete_stale_chunks",
                    new_callable=AsyncMock,
                    return_value=2,
                ) as mock_cleanup,
            ):
                conn = _make_conn_with_transaction()
                await ingest_runbooks(conn, runbooks_dir=tmpdir)

        mock_cleanup.assert_called_once()
        call_args = mock_cleanup.call_args
        assert call_args[0][1] == "test.md"
        assert call_args[0][2] > 0

    @pytest.mark.unit
    async def test_processes_nested_subdirectories(self):
        """Glob finds .md files in nested directories."""
        mock_embedding = [0.1] * 1536

        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir, "alerts", "node")
            subdir.mkdir(parents=True)
            Path(subdir, "memory.md").write_text(SAMPLE_RUNBOOK_2)

            with (
                patch(
                    "src.knowledge.ingest.embed_texts",
                    new_callable=AsyncMock,
                    return_value=[mock_embedding] * 20,
                ),
                patch(
                    "src.knowledge.ingest.store_chunks",
                    new_callable=AsyncMock,
                    return_value=2,
                ),
                patch(
                    "src.knowledge.ingest.delete_stale_chunks",
                    new_callable=AsyncMock,
                    return_value=0,
                ),
            ):
                conn = _make_conn_with_transaction()
                stats = await ingest_runbooks(conn, runbooks_dir=tmpdir)

        assert stats["files_processed"] == 1
