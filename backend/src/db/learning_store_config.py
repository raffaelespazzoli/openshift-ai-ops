"""Learning Store runtime config persistence (AD-7 layered override).

Simple key-value store for runtime config overrides that take
precedence over Helm/env defaults. Used by the config API and
loaded on startup to apply DB overrides to KnowledgeSettings.
"""

from __future__ import annotations

from datetime import datetime, timezone

import asyncpg

from ..config.logging import Component, get_logger

logger = get_logger(Component.DB)


async def get_config(conn: asyncpg.Connection, key: str) -> str | None:
    """Get a single config value by key. Returns None if not found."""
    row = await conn.fetchrow(
        "SELECT value FROM learning_store_config WHERE key = $1", key
    )
    return row["value"] if row else None


async def set_config(
    conn: asyncpg.Connection, key: str, value: str, actor: str
) -> None:
    """Upsert a config key-value pair with audit metadata."""
    await conn.execute(
        """
        INSERT INTO learning_store_config (key, value, updated_at, updated_by)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by
        """,
        key,
        value,
        datetime.now(timezone.utc),
        actor,
    )


async def get_all_config(conn: asyncpg.Connection) -> dict[str, str]:
    """Return all config overrides as a dict."""
    rows = await conn.fetch("SELECT key, value FROM learning_store_config")
    return {row["key"]: row["value"] for row in rows}
