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
    recover_stale_items,
)
from ..models.state_machine import IncidentState, transition
from .priority_queue import check_ttl_expired_items

logger = get_logger(Component.PIPELINE)

_inflight_tasks: set[asyncio.Task] = set()
_inflight_items: dict[asyncio.Task, dict] = {}

MAX_TRANSITION_RETRIES = 3
_transition_retry_counts: dict[str, int] = {}


def _task_done(task: asyncio.Task) -> None:
    """Cleanup callback when a pipeline task completes normally."""
    _inflight_tasks.discard(task)
    _inflight_items.pop(task, None)


async def dispatch_to_pipeline(
    item: dict,
    conn: asyncpg.Connection | asyncpg.Pool,
) -> None:
    """Dispatch a dequeued RCE to the diagnosis pipeline.

    Fires the LangGraph diagnosis graph as an asyncio task so the
    dispatcher loop continues polling without blocking. The pipeline
    task calls mark_pipeline_complete on terminal states.

    Tasks are tracked in _inflight_tasks so shutdown_pipeline_tasks()
    can cancel/await them during application shutdown.
    """
    logger.info(
        "Dispatched RCE to diagnosis pipeline",
        extra={
            "incident_id": str(item["incident_id"]),
            "root_cause_event_id": str(item["root_cause_event_id"]),
            "priority_score": item["priority_score"],
        },
    )
    task = asyncio.create_task(_run_pipeline_task(item))
    _inflight_tasks.add(task)
    _inflight_items[task] = item
    task.add_done_callback(_task_done)


async def shutdown_pipeline_tasks(timeout: float = 10.0) -> None:
    """Cancel in-flight pipeline tasks and reset their queue items for immediate re-processing.

    Called during FastAPI lifespan shutdown. After cancelling tasks, resets
    interrupted queue rows from 'processing' to 'queued' and associated
    incidents from 'diagnosing' to 'queued' so they are immediately
    re-processable on restart (AC #3) without waiting for the stale timeout.
    """
    if not _inflight_tasks:
        return

    tasks = list(_inflight_tasks)
    items = [_inflight_items[t] for t in tasks if t in _inflight_items]
    logger.info(
        "Shutting down in-flight pipeline tasks",
        extra={"task_count": len(tasks)},
    )

    for t in tasks:
        t.cancel()

    done, pending = await asyncio.wait(tasks, timeout=timeout)
    if pending:
        logger.warning(
            "Pipeline tasks did not finish within timeout — proceeding with reset",
            extra={"timed_out_count": len(pending)},
        )
    for t in done:
        exc = t.exception() if not t.cancelled() else None
        if exc is not None:
            logger.warning("Pipeline task error during shutdown", extra={"error": str(exc)})

    if items:
        await _reset_interrupted_items(items)


async def _reset_interrupted_items(items: list[dict]) -> None:
    """Reset queue items interrupted by shutdown to 'queued' for immediate re-processing.

    Resets queue rows and associated incident states via the canonical state
    machine (AD-19) so the dispatcher picks them up promptly on restart
    instead of waiting for stale recovery.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            queue_item_ids = [item["id"] for item in items]

            await conn.execute(
                """
                UPDATE priority_queue
                SET status = 'queued', dequeued_at = NULL
                WHERE id = ANY($1::uuid[])
                  AND status = 'processing'
                """,
                queue_item_ids,
            )

            await conn.execute(
                """
                DELETE FROM active_pipelines
                WHERE queue_item_id = ANY($1::uuid[])
                  AND completed_at IS NULL
                """,
                queue_item_ids,
            )

            all_incident_ids: set = set()
            for item in items:
                all_incident_ids.add(item["incident_id"])
                sibling_ids = await get_rce_incident_ids(conn, item["root_cause_event_id"])
                all_incident_ids.update(sibling_ids)

            reset_count = 0
            for iid in all_incident_ids:
                current_state_val = await conn.fetchval(
                    "SELECT state FROM incidents WHERE id = $1", iid
                )
                if current_state_val is None:
                    continue
                try:
                    current = IncidentState(current_state_val)
                    new_state = transition(current, IncidentState.QUEUED)
                    await conn.execute(
                        "UPDATE incidents SET state = $2, updated_at = NOW() WHERE id = $1",
                        iid,
                        new_state.value,
                    )
                    reset_count += 1
                except Exception:
                    logger.warning(
                        "Could not reset incident via state machine — skipping",
                        extra={
                            "incident_id": str(iid),
                            "current_state": current_state_val,
                        },
                    )

            logger.info(
                "Reset interrupted queue items for immediate re-processing",
                extra={
                    "queue_item_count": len(queue_item_ids),
                    "incident_count": reset_count,
                },
            )
    except Exception:
        logger.warning(
            "Failed to reset interrupted queue items during shutdown "
            "— stale recovery will handle them on next startup",
        )


async def _run_pipeline_task(item: dict) -> None:
    """Wrapper for run_diagnosis_pipeline that catches all errors."""
    from .runner import run_diagnosis_pipeline

    try:
        await run_diagnosis_pipeline(item)
    except asyncio.CancelledError:
        logger.info(
            "Pipeline task cancelled during shutdown",
            extra={"incident_id": str(item["incident_id"])},
        )
        raise
    except Exception:
        logger.exception(
            "Pipeline task crashed unexpectedly",
            extra={"incident_id": str(item["incident_id"])},
        )


async def _transition_incidents_to_diagnosing(
    conn: asyncpg.Connection | asyncpg.Pool,
    root_cause_event_id,
    primary_incident_id,
) -> bool:
    """Transition all incidents for this RCE from queued to diagnosing (AD-19).

    Multi-incident RCEs share one queue row; all sibling incidents must
    transition together atomically. Wraps ALL sibling transitions in a
    single DB transaction so they either all succeed or all roll back —
    preventing partial writes that leave some siblings stuck in diagnosing.

    Returns True only when all transitions succeed;
    False means dispatch must NOT proceed.
    """
    incident_ids = await get_rce_incident_ids(conn, root_cause_event_id)
    if not incident_ids:
        incident_ids = [primary_incident_id]

    try:
        async with conn.transaction():
            for incident_id in incident_ids:
                current_state = await conn.fetchval(
                    "SELECT state FROM incidents WHERE id = $1", incident_id
                )
                if current_state is None:
                    raise ValueError(
                        f"Incident {incident_id} not found during dispatch transition"
                    )

                current = IncidentState(current_state)
                new_state = transition(current, IncidentState.DIAGNOSING)
                await conn.execute(
                    "UPDATE incidents SET state = $2, updated_at = NOW() WHERE id = $1",
                    incident_id,
                    new_state.value,
                )
    except Exception:
        logger.warning(
            "Could not transition incidents to diagnosing — transaction rolled back",
            extra={
                "root_cause_event_id": str(root_cause_event_id),
                "incident_count": len(incident_ids),
            },
        )
        return False

    return True


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
                    success = await _transition_incidents_to_diagnosing(
                        conn, item["root_cause_event_id"], item["incident_id"]
                    )
                    if success:
                        item_key = str(item["id"])
                        _transition_retry_counts.pop(item_key, None)
                        await dispatch_to_pipeline(item, conn)
                    else:
                        item_key = str(item["id"])
                        _transition_retry_counts[item_key] = (
                            _transition_retry_counts.get(item_key, 0) + 1
                        )
                        if _transition_retry_counts[item_key] >= MAX_TRANSITION_RETRIES:
                            _transition_retry_counts.pop(item_key, None)
                            await _mark_item_failed(conn, item["id"])
                        else:
                            await _requeue_failed_transition(conn, item["id"])
        except asyncio.CancelledError:
            logger.info("Dispatcher shutting down")
            raise
        except Exception:
            logger.exception("Dispatcher error")

        await asyncio.sleep(settings.poll_interval_seconds)


async def _requeue_failed_transition(
    conn: asyncpg.Connection | asyncpg.Pool,
    queue_item_id,
) -> None:
    """Reset a queue item to 'queued' after a failed state transition.

    This prevents items from being stuck in 'processing' when the
    queued→diagnosing persistence fails.
    """
    await conn.execute(
        """
        UPDATE priority_queue
        SET status = 'queued', dequeued_at = NULL
        WHERE id = $1 AND status = 'processing'
        """,
        queue_item_id,
    )
    await conn.execute(
        """
        DELETE FROM active_pipelines
        WHERE queue_item_id = $1 AND completed_at IS NULL
        """,
        queue_item_id,
    )
    logger.info(
        "Re-queued item after failed diagnosing transition",
        extra={"queue_item_id": str(queue_item_id)},
    )


async def _mark_item_failed(
    conn: asyncpg.Connection | asyncpg.Pool,
    queue_item_id,
) -> None:
    """Permanently mark a queue item as failed after exhausting transition retries.

    Prevents permanent failures (missing incidents, invalid sibling states)
    from hot-looping the same queue item indefinitely.
    """
    await conn.execute(
        """
        UPDATE priority_queue
        SET status = 'failed', completed_at = NOW()
        WHERE id = $1 AND status = 'processing'
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
    logger.error(
        "Queue item marked as failed after exhausting transition retries",
        extra={
            "queue_item_id": str(queue_item_id),
            "max_retries": MAX_TRANSITION_RETRIES,
        },
    )
