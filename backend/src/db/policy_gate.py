"""Persistence for dry-run results and policy decisions (Story 3.3).

Provides persist and load functions for the dry_run_results
and policy_decisions tables.
"""

from __future__ import annotations

import json
import uuid

import asyncpg

from ..config.logging import Component, get_logger
from ..models.policy_gate import DryRunResult, PolicyDecision

logger = get_logger(Component.DB)


async def persist_dry_run_result(
    conn: asyncpg.Connection | asyncpg.Pool,
    result: DryRunResult,
) -> uuid.UUID:
    """Persist a dry-run result to the database.

    Args:
        conn: Database connection or pool.
        result: The DryRunResult to persist.

    Returns:
        The UUID of the inserted record.
    """
    try:
        await conn.execute(
            """
            INSERT INTO dry_run_results
                (id, incident_id, plan_id, step_results,
                 dry_run_passed, dry_run_errors, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb, $7)
            """,
            result.id,
            result.incident_id,
            result.plan_id,
            json.dumps(
                [sr.model_dump(mode="json") for sr in result.step_results],
                default=str,
            ),
            result.dry_run_passed,
            json.dumps(result.dry_run_errors),
            result.created_at,
        )
        logger.info(
            "Dry-run result persisted",
            extra={
                "incident_id": str(result.incident_id),
                "dry_run_passed": result.dry_run_passed,
            },
        )
    except Exception:
        logger.exception(
            "Failed to persist dry-run result",
            extra={"incident_id": str(result.incident_id)},
        )
        raise

    return result.id


async def persist_policy_decision(
    conn: asyncpg.Connection | asyncpg.Pool,
    decision: PolicyDecision,
) -> uuid.UUID:
    """Persist a policy decision to the database.

    Args:
        conn: Database connection or pool.
        decision: The PolicyDecision to persist.

    Returns:
        The UUID of the inserted record.
    """
    try:
        await conn.execute(
            """
            INSERT INTO policy_decisions
                (id, incident_id, plan_id, dimensions,
                 evidence_complete, evidence_gaps_empty,
                 auto_execution_approved, reasoning, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9)
            """,
            decision.id,
            decision.incident_id,
            decision.plan_id,
            json.dumps(
                [d.model_dump(mode="json") for d in decision.dimensions],
                default=str,
            ),
            decision.evidence_complete,
            decision.evidence_gaps_empty,
            decision.auto_execution_approved,
            decision.reasoning,
            decision.created_at,
        )
        logger.info(
            "Policy decision persisted",
            extra={
                "incident_id": str(decision.incident_id),
                "auto_approved": decision.auto_execution_approved,
            },
        )
    except Exception:
        logger.exception(
            "Failed to persist policy decision",
            extra={"incident_id": str(decision.incident_id)},
        )
        raise

    return decision.id


async def load_dry_run_result(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
) -> DryRunResult | None:
    """Load a dry-run result by incident ID."""
    row = await conn.fetchrow(
        "SELECT * FROM dry_run_results WHERE incident_id = $1",
        incident_id,
    )
    if row is None:
        return None

    step_results = row["step_results"]
    if isinstance(step_results, str):
        step_results = json.loads(step_results)

    dry_run_errors = row["dry_run_errors"]
    if isinstance(dry_run_errors, str):
        dry_run_errors = json.loads(dry_run_errors)

    return DryRunResult(
        id=row["id"],
        incident_id=row["incident_id"],
        plan_id=row["plan_id"],
        step_results=step_results,
        dry_run_passed=row["dry_run_passed"],
        dry_run_errors=dry_run_errors or [],
        created_at=row["created_at"],
    )


async def load_policy_decision(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
) -> PolicyDecision | None:
    """Load a policy decision by incident ID."""
    row = await conn.fetchrow(
        "SELECT * FROM policy_decisions WHERE incident_id = $1",
        incident_id,
    )
    if row is None:
        return None

    dimensions = row["dimensions"]
    if isinstance(dimensions, str):
        dimensions = json.loads(dimensions)

    return PolicyDecision(
        id=row["id"],
        incident_id=row["incident_id"],
        plan_id=row["plan_id"],
        dimensions=dimensions,
        evidence_complete=row["evidence_complete"],
        evidence_gaps_empty=row["evidence_gaps_empty"],
        auto_execution_approved=row["auto_execution_approved"],
        reasoning=row["reasoning"],
        created_at=row["created_at"],
    )
