"""Database operations for the priority queue (AD-23).

All queue state is persisted in PostgreSQL (NFR-2, survives pod restart).
Uses SELECT FOR UPDATE SKIP LOCKED for concurrent dequeue safety.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg

from ..config.logging import Component, get_logger
from ..config.queue_settings import get_queue_settings

logger = get_logger(Component.DB)


async def insert_queue_item(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    root_cause_event_id: uuid.UUID,
    incident_id: uuid.UUID,
    priority_score: float,
    severity: str,
    ttl_expires_at: datetime,
) -> dict:
    """Insert a new item into the priority queue with status='queued'."""
    item_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    row = await conn.fetchrow(
        """
        INSERT INTO priority_queue
            (id, root_cause_event_id, incident_id, priority_score, severity,
             status, enqueued_at, ttl_expires_at)
        VALUES ($1, $2, $3, $4, $5, 'queued', $6, $7)
        RETURNING *
        """,
        item_id,
        root_cause_event_id,
        incident_id,
        priority_score,
        severity,
        now,
        ttl_expires_at,
    )
    logger.info(
        "Queue item inserted",
        extra={
            "queue_item_id": str(item_id),
            "incident_id": str(incident_id),
            "priority_score": priority_score,
            "severity": severity,
        },
    )
    return dict(row)


async def dequeue_next(
    conn: asyncpg.Connection | asyncpg.Pool,
) -> dict | None:
    """Atomically claim the highest-priority queued item.

    Uses a single CTE that checks the parallelism cap, selects the next
    item with FOR UPDATE SKIP LOCKED, updates it to 'processing', and
    inserts into active_pipelines — all in one statement to prevent races
    between the cap check and the claim.
    """
    settings = get_queue_settings()

    row = await conn.fetchrow(
        """
        WITH lock_gate AS (
            SELECT pg_advisory_xact_lock(42)
        ),
        cap_check AS (
            SELECT COUNT(*) AS cnt
            FROM active_pipelines, lock_gate
            WHERE completed_at IS NULL
        ),
        next_item AS (
            SELECT pq.id
            FROM priority_queue pq
            CROSS JOIN cap_check cc
            WHERE pq.status = 'queued' AND cc.cnt < $1
            ORDER BY pq.priority_score DESC, pq.enqueued_at ASC
            FOR UPDATE OF pq SKIP LOCKED
            LIMIT 1
        ),
        claimed AS (
            UPDATE priority_queue
            SET status = 'processing', dequeued_at = NOW()
            FROM next_item
            WHERE priority_queue.id = next_item.id
            RETURNING priority_queue.*
        ),
        pipeline_track AS (
            INSERT INTO active_pipelines (id, queue_item_id, incident_id, started_at)
            SELECT gen_random_uuid(), claimed.id, claimed.incident_id, NOW()
            FROM claimed
        )
        SELECT * FROM claimed
        """,
        settings.parallelism_cap,
    )
    if row is None:
        return None

    result = dict(row)
    logger.info(
        "Queue item dequeued",
        extra={
            "queue_item_id": str(result["id"]),
            "incident_id": str(result["incident_id"]),
            "priority_score": result["priority_score"],
        },
    )
    return result


async def cancel_queued_item(
    conn: asyncpg.Connection | asyncpg.Pool,
    root_cause_event_id: uuid.UUID,
) -> dict | None:
    """Cancel a queued item by RCE ID. Only cancels if status is 'queued'.

    Returns the cancelled row or None if the item was not in 'queued' status
    (e.g. already processing or completed).
    """
    row = await conn.fetchrow(
        """
        UPDATE priority_queue
        SET status = 'cancelled'
        WHERE root_cause_event_id = $1 AND status = 'queued'
        RETURNING *
        """,
        root_cause_event_id,
    )
    if row:
        logger.info(
            "Queue item cancelled",
            extra={
                "queue_item_id": str(row["id"]),
                "root_cause_event_id": str(root_cause_event_id),
            },
        )
    return dict(row) if row else None


async def mark_pipeline_complete(
    conn: asyncpg.Connection | asyncpg.Pool,
    queue_item_id: uuid.UUID,
) -> None:
    """Mark a queue item and its active_pipeline entry as completed."""
    await conn.execute(
        """
        UPDATE priority_queue
        SET status = 'completed', completed_at = NOW()
        WHERE id = $1
        """,
        queue_item_id,
    )

    await conn.execute(
        """
        UPDATE active_pipelines
        SET completed_at = NOW()
        WHERE queue_item_id = $1 AND completed_at IS NULL
        """,
        queue_item_id,
    )

    logger.info(
        "Pipeline completed",
        extra={"queue_item_id": str(queue_item_id)},
    )


async def get_ttl_expired_items(
    conn: asyncpg.Connection | asyncpg.Pool,
) -> list[dict]:
    """Find queued items whose TTL has expired."""
    rows = await conn.fetch(
        """
        SELECT id, root_cause_event_id, incident_id, priority_score, severity,
               enqueued_at, ttl_expires_at
        FROM priority_queue
        WHERE status = 'queued' AND ttl_expires_at <= NOW()
        """
    )
    return [dict(r) for r in rows]


async def extend_ttl(
    conn: asyncpg.Connection | asyncpg.Pool,
    queue_item_id: uuid.UUID,
    new_ttl_expires_at: datetime,
) -> None:
    """Extend the TTL for a queue item (alert still firing)."""
    await conn.execute(
        "UPDATE priority_queue SET ttl_expires_at = $2 WHERE id = $1",
        queue_item_id,
        new_ttl_expires_at,
    )


async def recover_stale_items(
    conn: asyncpg.Connection | asyncpg.Pool,
) -> int:
    """Reset items stuck in 'processing' from a previous pod lifecycle.

    Returns the number of items recovered.
    """
    settings = get_queue_settings()
    timeout = settings.stale_processing_timeout_seconds

    recovered_rows = await conn.fetch(
        """
        UPDATE priority_queue
        SET status = 'queued', dequeued_at = NULL
        WHERE status = 'processing'
          AND dequeued_at < NOW() - make_interval(secs => $1::double precision)
        RETURNING incident_id, root_cause_event_id
        """,
        float(timeout),
    )
    recovered = len(recovered_rows)

    if recovered > 0:
        all_incident_ids: set[uuid.UUID] = set()
        for row in recovered_rows:
            all_incident_ids.add(row["incident_id"])
            sibling_ids = await get_rce_incident_ids(conn, row["root_cause_event_id"])
            all_incident_ids.update(sibling_ids)

        await conn.execute(
            """
            UPDATE incidents
            SET state = 'queued', updated_at = NOW()
            WHERE id = ANY($1::uuid[])
              AND state = 'diagnosing'
            """,
            list(all_incident_ids),
        )

    await conn.execute(
        """
        DELETE FROM active_pipelines
        WHERE completed_at IS NULL
          AND started_at < NOW() - make_interval(secs => $1::double precision)
        """,
        float(timeout),
    )

    if recovered > 0:
        logger.info(
            "Recovered stale processing items",
            extra={"recovered_count": recovered},
        )
    return recovered


async def check_alert_still_firing(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
) -> bool:
    """Check if at least one alert in the incident is still firing (MVP approach)."""
    return await conn.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM alerts
            WHERE incident_id = $1 AND status = 'firing'
        )
        """,
        incident_id,
    )


async def check_rce_alerts_still_firing(
    conn: asyncpg.Connection | asyncpg.Pool,
    root_cause_event_id: uuid.UUID,
) -> bool:
    """Check if any alert across ALL incidents in the RCE is still firing.

    Queries via alert_group_members so multi-incident RCEs are fully covered.
    Falls back to False if the group has no members (defensive).
    """
    return await conn.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM alert_group_members agm
            JOIN alerts a ON a.id = agm.alert_id
            WHERE agm.group_id = $1 AND a.status = 'firing'
        )
        """,
        root_cause_event_id,
    )


async def get_active_pipeline_count(
    conn: asyncpg.Connection | asyncpg.Pool,
) -> int:
    """Count currently active (non-completed) pipelines."""
    return await conn.fetchval(
        "SELECT COUNT(*) FROM active_pipelines WHERE completed_at IS NULL"
    )


async def get_rce_incident_ids(
    conn: asyncpg.Connection | asyncpg.Pool,
    root_cause_event_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Get all incident IDs associated with a root cause event (correlation group)."""
    rows = await conn.fetch(
        "SELECT DISTINCT incident_id FROM alert_group_members WHERE group_id = $1",
        root_cause_event_id,
    )
    return [r["incident_id"] for r in rows]


async def get_rce_alert_fingerprints(
    conn: asyncpg.Connection | asyncpg.Pool,
    root_cause_event_id: uuid.UUID,
) -> list[str]:
    """Get all alert fingerprints associated with a root cause event."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT a.fingerprint
        FROM alert_group_members agm
        JOIN alerts a ON a.id = agm.alert_id
        WHERE agm.group_id = $1
        """,
        root_cause_event_id,
    )
    return [r["fingerprint"] for r in rows]
