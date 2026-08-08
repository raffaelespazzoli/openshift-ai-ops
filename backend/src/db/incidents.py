"""Incident and alert persistence functions.

All database writes for incident/alert creation go through this module.
Uses asyncpg and the state machine transition function (AD-19).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import asyncpg

from ..config.logging import Component, get_logger
from ..models.state_machine import initial_state

logger = get_logger(Component.DB)


async def create_incident(
    conn: asyncpg.Connection | asyncpg.Pool,
    severity: str,
) -> dict:
    """Create a new incident in the `received` state.

    Uses the state machine transition function to validate the initial state.
    Returns a dict with the new incident row data.
    """
    state = initial_state()

    incident_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    row = await conn.fetchrow(
        """
        INSERT INTO incidents (id, state, severity, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, state, severity, created_at, updated_at
        """,
        incident_id,
        state.value,
        severity,
        now,
        now,
    )
    logger.info(
        "Incident created",
        extra={
            "incident_id": str(incident_id),
            "severity": severity,
            "state": state.value,
        },
    )
    return dict(row)


async def create_alert(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
    fingerprint: str,
    labels: dict,
    annotations: dict,
    status: str,
    fired_at: datetime,
) -> dict:
    """Persist an alert row linked to an incident.

    Returns a dict with the new alert row data.
    """
    alert_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    row = await conn.fetchrow(
        """
        INSERT INTO alerts (id, incident_id, fingerprint, labels, annotations, status, fired_at, created_at)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
        RETURNING id, incident_id, fingerprint, labels, annotations, status, fired_at, created_at
        """,
        alert_id,
        incident_id,
        fingerprint,
        json.dumps(labels),
        json.dumps(annotations),
        status,
        fired_at,
        now,
    )
    logger.info(
        "Alert persisted",
        extra={
            "alert_id": str(alert_id),
            "incident_id": str(incident_id),
            "fingerprint": fingerprint,
        },
    )
    return dict(row)


async def record_resolved_alert(
    conn: asyncpg.Connection | asyncpg.Pool,
    fingerprint: str,
    resolved_at: datetime,
) -> dict | None:
    """Record resolved status for an alert by fingerprint.

    Looks up the most recent firing alert with the given fingerprint.
    If found, updates its status to resolved and sets resolved_at.
    If no matching alert exists, logs and returns None.
    """
    row = await conn.fetchrow(
        """
        UPDATE alerts
        SET status = 'resolved', resolved_at = $2
        WHERE id = (
            SELECT id FROM alerts
            WHERE fingerprint = $1 AND status = 'firing'
            ORDER BY created_at DESC
            LIMIT 1
        )
        RETURNING id, incident_id, fingerprint, status, resolved_at
        """,
        fingerprint,
        resolved_at,
    )
    if row is None:
        logger.info(
            "Resolved alert has no matching firing alert — skipping",
            extra={"fingerprint": fingerprint},
        )
        return None

    logger.info(
        "Alert resolved",
        extra={
            "alert_id": str(row["id"]),
            "incident_id": str(row["incident_id"]),
            "fingerprint": fingerprint,
        },
    )
    return dict(row)
