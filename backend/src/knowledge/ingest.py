"""Runbook ingestion pipeline — chunk, embed, upsert to pgvector (AD-13).

CLI/startup entrypoint that scans the runbooks/ directory, chunks markdown
files, generates embeddings, and upserts into the runbook_chunks table.
Runbooks are bundled at container build time; refresh = image rebuild.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from ..config.knowledge_settings import get_knowledge_settings
from ..config.logging import Component, get_logger
from ..db.runbooks import delete_stale_chunks, store_chunks
from ..knowledge.chunker import chunk_markdown
from ..knowledge.embeddings import embed_texts

logger = get_logger(Component.KNOWLEDGE)


async def ingest_runbooks(
    conn: asyncpg.Connection,
    runbooks_dir: str | Path | None = None,
    batch_size: int = 20,
) -> dict[str, int]:
    """Ingest all markdown runbooks from the given directory.

    Scans for .md files, chunks them, generates embeddings, and upserts
    into pgvector. Existing chunks for re-ingested files are replaced.

    Args:
        conn: asyncpg connection with pgvector types registered.
        runbooks_dir: Path to the runbooks directory. Uses settings default if None.
        batch_size: Number of chunks to embed in one API call.

    Returns:
        Dict with ingestion stats: files_processed, chunks_created, errors.
    """
    settings = get_knowledge_settings()
    directory = Path(runbooks_dir) if runbooks_dir else Path(settings.runbooks_directory)

    stats = {"files_processed": 0, "chunks_created": 0, "errors": 0}

    if not directory.exists():
        logger.warning(
            "Runbooks directory not found",
            extra={"directory": str(directory)},
        )
        return stats

    md_files = sorted(directory.glob("**/*.md"))
    if not md_files:
        logger.info(
            "No markdown files found in runbooks directory",
            extra={"directory": str(directory)},
        )
        return stats

    logger.info(
        "Starting runbook ingestion",
        extra={"directory": str(directory), "file_count": len(md_files)},
    )

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            relative_path = str(md_file.relative_to(directory))

            chunks = chunk_markdown(
                content=content,
                source_file=relative_path,
                max_tokens=settings.chunk_max_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )

            if not chunks:
                continue

            all_embeddings: list[list[float]] = []
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                texts = [c.content for c in batch]
                embeddings = await embed_texts(texts)
                all_embeddings.extend(embeddings)

            async with conn.transaction():
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i:i + batch_size]
                    batch_embeddings = all_embeddings[i:i + batch_size]
                    await store_chunks(conn, batch, batch_embeddings)
                await delete_stale_chunks(conn, relative_path, len(chunks))

            stats["files_processed"] += 1
            stats["chunks_created"] += len(chunks)

            logger.info(
                "Ingested runbook file",
                extra={
                    "file": relative_path,
                    "chunks": len(chunks),
                },
            )
        except Exception:
            stats["errors"] += 1
            logger.exception(
                "Failed to ingest runbook file",
                extra={"file": str(md_file)},
            )

    logger.info("Runbook ingestion complete", extra=stats)
    return stats


async def run_ingest_cli() -> None:
    """CLI entrypoint for standalone runbook ingestion."""
    from ..db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        from pgvector.asyncpg import register_vector
        await register_vector(conn)
        stats = await ingest_runbooks(conn)

    print(f"Ingestion complete: {stats}")


if __name__ == "__main__":
    asyncio.run(run_ingest_cli())
