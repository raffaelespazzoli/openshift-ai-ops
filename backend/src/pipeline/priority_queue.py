"""Priority queue logic — scoring, enqueue, cancel, TTL (AD-23).

All queue state persists to PostgreSQL (NFR-2). No in-memory data structures.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import asyncpg

from ..config.logging import Component, get_logger
from ..config.queue_settings import get_queue_settings
from ..clients.alertmanager import (
    AlertManagerClient,
    AlertManagerUnreachableError,
    create_alertmanager_client,
)
from ..db.queue import (
    cancel_queued_item,
    check_rce_alerts_still_firing,
    extend_ttl,
    get_rce_alert_fingerprints,
    get_rce_incident_ids,
    get_ttl_expired_items,
    insert_queue_item,
)
from ..models.state_machine import IncidentState, transition

logger = get_logger(Component.PIPELINE)


def calculate_priority_score(severity: str, sealed_at: datetime) -> float:
    """Compute priority score: severity_weight x recency_factor.

    Higher score = dequeued first. Critical always outranks warning/info
    unless extremely old. Recency decays over hours.
    """
    settings = get_queue_settings()
    weight = settings.priority_weights.get(severity)
    age_seconds = (datetime.now(timezone.utc) - sealed_at).total_seconds()
    recency = 1.0 / (1.0 + age_seconds / 3600)
    return weight * recency


async def enqueue_rce(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    root_cause_event_id: uuid.UUID,
    incident_id: uuid.UUID,
    severity: str,
    sealed_at: datetime,
) -> uuid.UUID:
    """Enqueue a sealed Root-Cause Event for diagnosis.

    Calculates priority score and TTL, inserts into the priority queue.
    Verifies the incident is already in 'queued' state (set by correlator).

    Returns the queue item ID.
    """
    settings = get_queue_settings()

    priority_score = calculate_priority_score(severity, sealed_at)
    ttl_expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.ttl_seconds)

    current_state = await conn.fetchval(
        "SELECT state FROM incidents WHERE id = $1", incident_id
    )
    if current_state and current_state != IncidentState.QUEUED.value:
        logger.warning(
            "Incident not in expected queued state for enqueue",
            extra={
                "incident_id": str(incident_id),
                "actual_state": current_state,
            },
        )

    item = await insert_queue_item(
        conn,
        root_cause_event_id=root_cause_event_id,
        incident_id=incident_id,
        priority_score=priority_score,
        severity=severity,
        ttl_expires_at=ttl_expires_at,
    )

    logger.info(
        "RCE enqueued for diagnosis",
        extra={
            "root_cause_event_id": str(root_cause_event_id),
            "incident_id": str(incident_id),
            "priority_score": priority_score,
            "severity": severity,
        },
    )
    return item["id"]


async def cancel_queued_rce(
    conn: asyncpg.Connection | asyncpg.Pool,
    root_cause_event_id: uuid.UUID,
) -> bool:
    """Attempt to cancel a queued RCE. Only succeeds if status is 'queued'.

    On cancellation, transitions ALL incidents tied to this RCE to 'cancelled'.
    Multi-incident RCEs share one queue row; sibling incidents are discovered
    via alert_group_members.

    If the item is already 'processing', returns False (AD-16: freshness
    gate handles this at execution time).
    """
    cancelled = await cancel_queued_item(conn, root_cause_event_id)
    if cancelled is None:
        return False

    incident_ids = await get_rce_incident_ids(conn, root_cause_event_id)
    if not incident_ids:
        incident_ids = [cancelled["incident_id"]]

    for incident_id in incident_ids:
        current_state = await conn.fetchval(
            "SELECT state FROM incidents WHERE id = $1", incident_id
        )
        if current_state:
            current = IncidentState(current_state)
            try:
                new_state = transition(current, IncidentState.CANCELLED)
                await conn.execute(
                    "UPDATE incidents SET state = $2, updated_at = NOW() WHERE id = $1",
                    incident_id,
                    new_state.value,
                )
                logger.info(
                    "Incident cancelled via resolved webhook",
                    extra={
                        "incident_id": str(incident_id),
                        "root_cause_event_id": str(root_cause_event_id),
                    },
                )
            except Exception:
                logger.warning(
                    "Could not transition incident to cancelled",
                    extra={
                        "incident_id": str(incident_id),
                        "current_state": current_state,
                    },
                )

    return True


async def check_ttl_expired_items(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    alertmanager_client: AlertManagerClient | None = None,
) -> list[uuid.UUID]:
    """Check for TTL-expired queue items and handle them.

    For each expired item the AlertManager API is consulted first (AC5).
    If AlertManager is unreachable the item stays in the queue (fail-safe).
    If AlertManager confirms the alert is no longer firing the item is
    cancelled — but only if ``cancel_queued_item`` succeeds (guards against
    a concurrent dequeue race).
    """
    settings = get_queue_settings()
    expired_items = await get_ttl_expired_items(conn)
    cancelled_ids: list[uuid.UUID] = []

    if alertmanager_client is None:
        alertmanager_client = create_alertmanager_client()

    for item in expired_items:
        rce_id = item["root_cause_event_id"]

        # AC5: verify against AlertManager API before cancelling
        try:
            fingerprints = await get_rce_alert_fingerprints(conn, rce_id)
            still_firing = await alertmanager_client.check_alerts_firing(fingerprints)
        except AlertManagerUnreachableError:
            new_ttl = datetime.now(timezone.utc) + timedelta(seconds=settings.ttl_seconds)
            await extend_ttl(conn, item["id"], new_ttl)
            logger.warning(
                "AlertManager unreachable during TTL check; keeping item in queue (fail-safe)",
                extra={
                    "queue_item_id": str(item["id"]),
                    "root_cause_event_id": str(rce_id),
                },
            )
            continue

        if still_firing:
            new_ttl = datetime.now(timezone.utc) + timedelta(seconds=settings.ttl_seconds)
            await extend_ttl(conn, item["id"], new_ttl)
            logger.info(
                "TTL extended for queue item (alert still firing per AlertManager)",
                extra={
                    "queue_item_id": str(item["id"]),
                    "incident_id": str(item["incident_id"]),
                },
            )
            continue

        # AlertManager confirms alert is no longer firing — attempt cancel.
        # If cancel_queued_item returns None the item was already dequeued
        # by another worker; skip incident transitions to avoid the race.
        cancelled = await cancel_queued_item(conn, rce_id)
        if cancelled is None:
            logger.info(
                "TTL cancel skipped — item already dequeued/cancelled",
                extra={
                    "queue_item_id": str(item["id"]),
                    "root_cause_event_id": str(rce_id),
                },
            )
            continue

        incident_ids = await get_rce_incident_ids(conn, rce_id)
        if not incident_ids:
            incident_ids = [item["incident_id"]]

        for incident_id in incident_ids:
            current_state = await conn.fetchval(
                "SELECT state FROM incidents WHERE id = $1",
                incident_id,
            )
            if current_state:
                current = IncidentState(current_state)
                try:
                    new_state = transition(current, IncidentState.CANCELLED)
                    await conn.execute(
                        "UPDATE incidents SET state = $2, updated_at = NOW() WHERE id = $1",
                        incident_id,
                        new_state.value,
                    )
                except Exception:
                    logger.warning(
                        "Could not transition TTL-expired incident to cancelled",
                        extra={"incident_id": str(incident_id)},
                    )

        cancelled_ids.append(item["id"])
        logger.info(
            "TTL-expired queue item cancelled (alert no longer firing)",
            extra={
                "queue_item_id": str(item["id"]),
                "incident_id": str(item["incident_id"]),
            },
        )

    return cancelled_ids
