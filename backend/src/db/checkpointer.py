"""LangGraph AsyncPostgresSaver factory and lifecycle (AD-3).

The checkpointer uses psycopg (v3), NOT asyncpg. This is a SEPARATE
connection pool to the SAME PostgreSQL instance. The langgraph_*
tables are a black box — never query them from application code.
"""

from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ..config.logging import Component, get_logger
from .connection import get_db_url

logger = get_logger(Component.DB)

_checkpointer: AsyncPostgresSaver | None = None
_psycopg_pool: AsyncConnectionPool | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Get or create the singleton AsyncPostgresSaver.

    Creates a psycopg3 AsyncConnectionPool (separate from the asyncpg
    application pool) and wraps it in an AsyncPostgresSaver.
    """
    global _checkpointer, _psycopg_pool
    if _checkpointer is not None:
        return _checkpointer

    conninfo = get_db_url()

    _psycopg_pool = AsyncConnectionPool(
        conninfo=conninfo,
        kwargs={"autocommit": True, "row_factory": dict_row},
        min_size=1,
        max_size=3,
    )
    await _psycopg_pool.open()

    _checkpointer = AsyncPostgresSaver(_psycopg_pool)
    return _checkpointer


async def setup_checkpointer() -> AsyncPostgresSaver:
    """Initialize the checkpointer and create langgraph_* tables.

    Must be called once during application startup (lifespan).
    """
    checkpointer = await get_checkpointer()
    await checkpointer.setup()
    logger.info("LangGraph checkpointer tables initialized")
    return checkpointer


async def close_checkpointer() -> None:
    """Shut down the checkpointer and its connection pool."""
    global _checkpointer, _psycopg_pool
    if _psycopg_pool is not None:
        await _psycopg_pool.close()
        _psycopg_pool = None
    _checkpointer = None
