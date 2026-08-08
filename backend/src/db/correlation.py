"""Database operations for correlation groups.

All correlation state is persisted in PostgreSQL (NFR-2, survives pod restart).
Operations use transactions for atomicity of group creation + member insert.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg

from ..config.logging import Component, get_logger
from ..models.root_cause_event import CorrelationEvidence

logger = get_logger(Component.PIPELINE)


async def check_dedup(
    conn: asyncpg.Connection | asyncpg.Pool,
    fingerprint: str,
) -> bool:
    """Check if an alert with this fingerprint is already active (not resolved).

    Uses FOR UPDATE SKIP LOCKED to prevent race conditions where two concurrent
    requests both pass the dedup check before either creates an alert row.
    If no row exists to lock, the caller must rely on the unique-ish insert
    serialization (see webhooks.py advisory lock).
    """
    result = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM alerts WHERE fingerprint = $1 AND status = 'firing' FOR UPDATE SKIP LOCKED)",
        fingerprint,
    )
    return result


async def update_dedup_timestamp(
    conn: asyncpg.Connection | asyncpg.Pool,
    fingerprint: str,
) -> None:
    """Update the most recent firing alert's created_at to track last duplicate arrival."""
    await conn.execute(
        """
        UPDATE alerts SET created_at = NOW()
        WHERE id = (
            SELECT id FROM alerts
            WHERE fingerprint = $1 AND status = 'firing'
            ORDER BY created_at DESC
            LIMIT 1
        )
        """,
        fingerprint,
    )


async def get_open_groups(
    conn: asyncpg.Connection | asyncpg.Pool,
    for_update: bool = False,
) -> list[dict]:
    """Fetch all open (unsealed) correlation groups with their member alerts.

    Args:
        for_update: If True, acquires row-level locks on open groups to prevent
            concurrent alerts from creating duplicate groups. Must be called
            within a transaction.
    """
    lock_clause = "FOR UPDATE" if for_update else ""
    groups = await conn.fetch(
        f"""
        SELECT g.id, g.state, g.settling_window_seconds, g.created_at,
               g.last_alert_at, g.max_age_at, g.correlation_evidence
        FROM correlation_groups g
        WHERE g.state = 'open'
        ORDER BY g.created_at DESC
        {lock_clause}
        """
    )

    result = []
    for group in groups:
        members = await conn.fetch(
            """
            SELECT agm.alert_id, agm.incident_id, agm.joined_at,
                   a.fingerprint, a.labels, a.status
            FROM alert_group_members agm
            JOIN alerts a ON a.id = agm.alert_id
            WHERE agm.group_id = $1
            """,
            group["id"],
        )
        group_dict = dict(group)
        group_dict["members"] = [dict(m) for m in members]
        result.append(group_dict)

    return result


async def create_correlation_group(
    conn: asyncpg.Connection | asyncpg.Pool,
    alert_id: uuid.UUID,
    incident_id: uuid.UUID,
    settling_window_seconds: int,
    evidence: CorrelationEvidence | None = None,
) -> uuid.UUID:
    """Create a new correlation group with the given alert as the seed member.

    Returns the new group ID.
    """
    group_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    max_age_at = now + timedelta(seconds=3 * settling_window_seconds)

    evidence_json = json.dumps([evidence.model_dump(mode="json")] if evidence else [])

    await conn.execute(
        """
        INSERT INTO correlation_groups (id, state, settling_window_seconds, created_at, last_alert_at, max_age_at, correlation_evidence)
        VALUES ($1, 'open', $2, $3, $3, $4, $5::jsonb)
        """,
        group_id,
        settling_window_seconds,
        now,
        max_age_at,
        evidence_json,
    )

    await conn.execute(
        """
        INSERT INTO alert_group_members (group_id, alert_id, incident_id, joined_at)
        VALUES ($1, $2, $3, $4)
        """,
        group_id,
        alert_id,
        incident_id,
        now,
    )

    logger.info(
        "Correlation group created",
        extra={
            "group_id": str(group_id),
            "alert_id": str(alert_id),
            "settling_window_seconds": settling_window_seconds,
        },
    )
    return group_id


async def add_alert_to_group(
    conn: asyncpg.Connection | asyncpg.Pool,
    group_id: uuid.UUID,
    alert_id: uuid.UUID,
    incident_id: uuid.UUID,
    new_window: int,
    evidence: CorrelationEvidence,
) -> None:
    """Add an alert to an existing correlation group.

    Updates the group's last_alert_at, recalculates settling window,
    and appends correlation evidence.
    """
    now = datetime.now(timezone.utc)

    await conn.execute(
        """
        INSERT INTO alert_group_members (group_id, alert_id, incident_id, joined_at)
        VALUES ($1, $2, $3, $4)
        """,
        group_id,
        alert_id,
        incident_id,
        now,
    )

    new_max_age_at = await conn.fetchval(
        "SELECT created_at FROM correlation_groups WHERE id = $1", group_id
    )
    new_max_age_at = new_max_age_at + timedelta(seconds=3 * new_window)

    await conn.execute(
        """
        UPDATE correlation_groups
        SET last_alert_at = $2,
            settling_window_seconds = $3,
            max_age_at = $4,
            correlation_evidence = correlation_evidence || $5::jsonb
        WHERE id = $1
        """,
        group_id,
        now,
        new_window,
        new_max_age_at,
        json.dumps([evidence.model_dump(mode="json")]),
    )

    logger.info(
        "Alert added to correlation group",
        extra={
            "group_id": str(group_id),
            "alert_id": str(alert_id),
            "new_window": new_window,
            "layer": evidence.layer.value,
        },
    )


async def get_groups_to_seal(
    conn: asyncpg.Connection | asyncpg.Pool,
) -> list[dict]:
    """Find open groups that should be sealed (settling expired or max age exceeded)."""
    now = datetime.now(timezone.utc)
    groups = await conn.fetch(
        """
        SELECT id, settling_window_seconds, created_at, last_alert_at, max_age_at
        FROM correlation_groups
        WHERE state = 'open'
          AND (
            ($1 - last_alert_at) > (settling_window_seconds * interval '1 second')
            OR $1 > max_age_at
          )
        """,
        now,
    )
    return [dict(g) for g in groups]


async def seal_group(
    conn: asyncpg.Connection | asyncpg.Pool,
    group_id: uuid.UUID,
) -> dict:
    """Seal a correlation group and return its final state.

    Updates group state to 'sealed' and sets sealed_at timestamp.
    Returns group data including all member alert_ids and incident_ids.
    """
    now = datetime.now(timezone.utc)

    await conn.execute(
        """
        UPDATE correlation_groups
        SET state = 'sealed', sealed_at = $2
        WHERE id = $1
        """,
        group_id,
        now,
    )

    members = await conn.fetch(
        """
        SELECT alert_id, incident_id
        FROM alert_group_members
        WHERE group_id = $1
        """,
        group_id,
    )

    await conn.execute(
        """
        UPDATE incidents
        SET root_cause_event_id = $1
        WHERE id = ANY($2::uuid[])
        """,
        group_id,
        [m["incident_id"] for m in members],
    )

    group = await conn.fetchrow(
        """
        SELECT id, state, settling_window_seconds, created_at, last_alert_at,
               sealed_at, max_age_at, correlation_evidence
        FROM correlation_groups
        WHERE id = $1
        """,
        group_id,
    )

    logger.info(
        "Correlation group sealed",
        extra={
            "group_id": str(group_id),
            "member_count": len(members),
        },
    )

    result = dict(group)
    result["alert_ids"] = [m["alert_id"] for m in members]
    result["incident_ids"] = [m["incident_id"] for m in members]
    return result
