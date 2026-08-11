"""Execution, outcome, and rollback persistence (Story 3.5).

Provides persist/load functions for execution_logs, outcome_results,
and rollback_records tables.
"""

from __future__ import annotations

import json
import uuid

import asyncpg

from ..config.logging import Component, get_logger
from ..models.execution import ExecutionLog, OutcomeResult, RollbackRecord

logger = get_logger(Component.DB)


async def persist_execution_log(
    conn: asyncpg.Connection,
    log: ExecutionLog,
) -> None:
    """Insert an execution log record."""
    await conn.execute(
        """
        INSERT INTO execution_logs (id, incident_id, plan_id, steps, mcp_calls,
                                    started_at, completed_at, status)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
        """,
        log.id,
        log.incident_id,
        log.plan_id,
        json.dumps([s.model_dump(mode="json") for s in log.steps]),
        json.dumps(log.mcp_calls),
        log.started_at,
        log.completed_at,
        log.status,
    )


async def load_execution_log(
    conn: asyncpg.Connection,
    incident_id: uuid.UUID,
) -> ExecutionLog | None:
    """Load execution log for an incident."""
    row = await conn.fetchrow(
        "SELECT * FROM execution_logs WHERE incident_id = $1",
        incident_id,
    )
    if row is None:
        return None
    return ExecutionLog(
        id=row["id"],
        incident_id=row["incident_id"],
        plan_id=row["plan_id"],
        steps=json.loads(row["steps"]),
        mcp_calls=json.loads(row["mcp_calls"]) if row["mcp_calls"] else [],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        status=row["status"],
    )


async def persist_outcome_result(
    conn: asyncpg.Connection,
    result: OutcomeResult,
) -> None:
    """Insert an outcome result record."""
    await conn.execute(
        """
        INSERT INTO outcome_results (id, incident_id, alert_resolved, resolution_method,
                                     resource_verification, outcome_confidence,
                                     refire_detected, observation_started_at,
                                     observation_completed_at, timeout_seconds)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10)
        """,
        result.id,
        result.incident_id,
        result.alert_resolved,
        result.resolution_method,
        json.dumps(result.resource_verification) if result.resource_verification else None,
        result.outcome_confidence,
        result.refire_detected,
        result.observation_started_at,
        result.observation_completed_at,
        result.timeout_seconds,
    )


async def load_outcome_result(
    conn: asyncpg.Connection,
    incident_id: uuid.UUID,
) -> OutcomeResult | None:
    """Load outcome result for an incident."""
    row = await conn.fetchrow(
        "SELECT * FROM outcome_results WHERE incident_id = $1",
        incident_id,
    )
    if row is None:
        return None
    return OutcomeResult(
        id=row["id"],
        incident_id=row["incident_id"],
        alert_resolved=row["alert_resolved"],
        resolution_method=row["resolution_method"],
        resource_verification=(
            json.loads(row["resource_verification"])
            if row["resource_verification"]
            else None
        ),
        outcome_confidence=row["outcome_confidence"],
        refire_detected=row["refire_detected"],
        observation_started_at=row["observation_started_at"],
        observation_completed_at=row["observation_completed_at"],
        timeout_seconds=row["timeout_seconds"],
    )


async def persist_rollback_record(
    conn: asyncpg.Connection,
    record: RollbackRecord,
) -> None:
    """Insert a rollback record."""
    await conn.execute(
        """
        INSERT INTO rollback_records (id, incident_id, plan_id, actor,
                                      steps_executed, success, created_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
        """,
        record.id,
        record.incident_id,
        record.plan_id,
        record.actor,
        json.dumps([s.model_dump(mode="json") for s in record.steps_executed]),
        record.success,
        record.created_at,
    )


async def load_rollback_records(
    conn: asyncpg.Connection,
    incident_id: uuid.UUID,
) -> list[RollbackRecord]:
    """Load all rollback records for an incident."""
    rows = await conn.fetch(
        "SELECT * FROM rollback_records WHERE incident_id = $1 ORDER BY created_at",
        incident_id,
    )
    return [
        RollbackRecord(
            id=row["id"],
            incident_id=row["incident_id"],
            plan_id=row["plan_id"],
            actor=row["actor"],
            steps_executed=json.loads(row["steps_executed"]) if row["steps_executed"] else [],
            success=row["success"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
