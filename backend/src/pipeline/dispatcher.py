"""Periodic dispatch loop — polls queue and dispatches to diagnosis pipeline (AD-23).

Runs as a FastAPI lifespan background task. On startup, recovers stale items
from a previous pod lifecycle. Then polls on a configurable interval.
"""

from __future__ import annotations

import asyncio

import asyncpg

from ..config.logging import Component, get_logger
from ..config.queue_settings import get_queue_settings
from ..db import get_pool
from ..db.queue import (
    dequeue_next,
    get_rce_incident_ids,
    mark_pipeline_complete,
    recover_stale_items,
)
from ..models.state_machine import IncidentState, transition
from .priority_queue import check_ttl_expired_items

logger = get_logger(Component.PIPELINE)


async def dispatch_to_pipeline(
    item: dict,
    conn: asyncpg.Connection | asyncpg.Pool,
) -> None:
    """Dispatch a dequeued RCE to the diagnosis pipeline.

    STUB: Logs dispatch and immediately marks the pipeline as complete so
    the parallelism cap slot is freed. Story 2.1 will replace this with
    an async LangGraph invocation that calls mark_pipeline_complete on
    terminal states.
    """
    logger.info(
        "Dispatched RCE to diagnosis pipeline",
        extra={
            "incident_id": str(item["incident_id"]),
            "root_cause_event_id": str(item["root_cause_event_id"]),
            "priority_score": item["priority_score"],
        },
    )
    await mark_pipeline_complete(conn, item["id"])


async def _transition_incidents_to_diagnosing(
    conn: asyncpg.Connection | asyncpg.Pool,
    root_cause_event_id,
    primary_incident_id,
) -> None:
    """Transition all incidents for this RCE from queued to diagnosing (AD-19).

    Multi-incident RCEs share one queue row; all sibling incidents must
    transition together.
    """
    incident_ids = await get_rce_incident_ids(conn, root_cause_event_id)
    if not incident_ids:
        incident_ids = [primary_incident_id]

    for incident_id in incident_ids:
        current_state = await conn.fetchval(
            "SELECT state FROM incidents WHERE id = $1", incident_id
        )
        if current_state is None:
            logger.warning(
                "Incident not found for dispatch transition",
                extra={"incident_id": str(incident_id)},
            )
            continue

        current = IncidentState(current_state)
        try:
            new_state = transition(current, IncidentState.DIAGNOSING)
            await conn.execute(
                "UPDATE incidents SET state = $2, updated_at = NOW() WHERE id = $1",
                incident_id,
                new_state.value,
            )
        except Exception:
            logger.warning(
                "Could not transition incident to diagnosing",
                extra={
                    "incident_id": str(incident_id),
                    "current_state": current_state,
                },
            )


async def run_dispatcher() -> None:
    """Background dispatch loop.

    1. On startup: recover stale items from crashed pods (with retry)
    2. Loop: check TTL, check capacity, dequeue, transition, dispatch
    """
    settings = get_queue_settings()

    for attempt in range(1, 6):
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                recovered = await recover_stale_items(conn)
                if recovered:
                    logger.info(
                        "Dispatcher startup: recovered stale items",
                        extra={"recovered_count": recovered},
                    )
            break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Dispatcher startup failed, retrying",
                extra={"attempt": attempt, "max_attempts": 5},
            )
            if attempt == 5:
                logger.error("Dispatcher startup exhausted retries, starting without recovery")
            await asyncio.sleep(min(2 ** attempt, 30))

    logger.info(
        "Dispatcher started",
        extra={"poll_interval": settings.poll_interval_seconds},
    )

    while True:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await check_ttl_expired_items(conn)

                item = await dequeue_next(conn)
                if item:
                    await _transition_incidents_to_diagnosing(
                        conn, item["root_cause_event_id"], item["incident_id"]
                    )
                    await dispatch_to_pipeline(item, conn)
        except asyncio.CancelledError:
            logger.info("Dispatcher shutting down")
            raise
        except Exception:
            logger.exception("Dispatcher error")

        await asyncio.sleep(settings.poll_interval_seconds)
