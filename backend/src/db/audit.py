"""Audit log database write function (AD-25).

Write point #1 for the audit log — called from the API audit middleware.
Write point #2 (pipeline audit hook) is built in later stories.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg

from ..config.logging import Component, get_logger

logger = get_logger(Component.DB)


async def write_audit_log(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    actor: str,
    action: str,
    target_resource: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Write an audit record to the audit_log table.

    When *conn* is a Pool, errors are logged and swallowed (fire-and-forget).
    When *conn* is a Connection (transactional caller), errors re-raise so the
    enclosing transaction can roll back.
    """
    try:
        now = datetime.now(timezone.utc)
        await conn.execute(
            """
            INSERT INTO audit_log (actor, action, target_resource, detail, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            actor,
            action,
            target_resource,
            json.dumps(detail) if detail else None,
            now,
        )
    except Exception:
        if isinstance(conn, asyncpg.Connection):
            raise
        logger.exception(
            "Failed to write audit log — swallowing error",
            extra={
                "actor": actor,
                "action": action,
                "target_resource": target_resource,
            },
        )
