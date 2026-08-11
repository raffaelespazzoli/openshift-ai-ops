"""Global remediation lock via PostgreSQL row-level lock (AD-18, Story 3.5).

Single-row table `remediation_locks`. Lock acquired via SELECT FOR UPDATE NOWAIT.
Lock is tied to the connection — pod crash auto-releases via PostgreSQL semantics.
"""

from __future__ import annotations

import uuid

import asyncpg

from ..config.logging import Component, get_logger

logger = get_logger(Component.DB)


async def acquire_remediation_lock(
    conn: asyncpg.Connection,
    incident_id: uuid.UUID,
) -> bool:
    """Acquire the global remediation lock (AD-18).

    Uses SELECT FOR UPDATE NOWAIT — fails immediately if another
    connection holds the lock. The lock is held as long as the
    connection's transaction remains open.

    Returns True if lock acquired, False if lock is held by another.
    """
    try:
        await conn.execute(
            """
            UPDATE remediation_locks
            SET locked_by = $1, locked_at = NOW(), incident_id = $1
            WHERE id = 'global'
            """,
            incident_id,
        )
        await conn.fetchrow(
            "SELECT * FROM remediation_locks WHERE id = 'global' FOR UPDATE NOWAIT"
        )
        return True
    except asyncpg.exceptions.LockNotAvailableError:
        return False


async def release_remediation_lock(conn: asyncpg.Connection) -> None:
    """Release the global remediation lock by clearing metadata.

    The actual row-level lock is released when the transaction
    commits/rolls back or the connection closes.
    """
    await conn.execute(
        """
        UPDATE remediation_locks
        SET locked_by = NULL, locked_at = NULL, incident_id = NULL
        WHERE id = 'global'
        """
    )


async def is_lock_held(conn: asyncpg.Connection) -> bool:
    """Check if the global lock is currently held (informational only).

    This is a non-blocking check — does NOT attempt to acquire the lock.
    """
    row = await conn.fetchrow(
        "SELECT locked_by FROM remediation_locks WHERE id = 'global'"
    )
    return row is not None and row["locked_by"] is not None
