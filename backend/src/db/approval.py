"""Persistence for approval records and approval context (Story 3.4).

Provides persist, load, and list functions for the approval_records
and policy_adjustments tables.
"""

from __future__ import annotations

import json
import uuid

import asyncpg

from ..config.logging import Component, get_logger
from ..models.approval import ApprovalRecord, PolicyAdjustmentRequest

logger = get_logger(Component.DB)


async def persist_approval_record(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    incident_id: uuid.UUID,
    plan_id: uuid.UUID,
    action: str,
    actor: str,
    reason: str | None = None,
) -> uuid.UUID:
    """Persist an approval or rejection record.

    Returns the UUID of the inserted record.
    """
    record_id = uuid.uuid4()
    try:
        await conn.execute(
            """
            INSERT INTO approval_records (id, incident_id, plan_id, action, actor, reason)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            record_id,
            incident_id,
            plan_id,
            action,
            actor,
            reason,
        )
        logger.info(
            "Approval record persisted",
            extra={
                "incident_id": str(incident_id),
                "action": action,
                "actor": actor,
            },
        )
    except Exception:
        logger.exception(
            "Failed to persist approval record",
            extra={"incident_id": str(incident_id)},
        )
        raise

    return record_id


async def load_approval_context(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
) -> dict | None:
    """Load full approval context for an incident.

    Joins: incidents, remediation_plans, immutable_diagnoses,
           dry_run_results, policy_decisions.
    """
    row = await conn.fetchrow(
        """
        SELECT
            i.id, i.state, i.severity, i.created_at, i.updated_at,
            rp.id AS plan_id, rp.plan, rp.blast_radius,
            rp.estimated_risk, rp.created_at AS plan_created_at,
            id.diagnosis, id.skeptic_verdict AS diagnosis_skeptic_verdict,
            id.sealed_at,
            dr.step_results, dr.dry_run_passed, dr.dry_run_errors,
            pd.dimensions, pd.evidence_complete, pd.evidence_gaps_empty,
            pd.auto_execution_approved, pd.reasoning AS policy_reasoning
        FROM incidents i
        LEFT JOIN remediation_plans rp ON rp.incident_id = i.id
        LEFT JOIN immutable_diagnoses id ON id.incident_id = i.id
        LEFT JOIN dry_run_results dr ON dr.incident_id = i.id
        LEFT JOIN policy_decisions pd ON pd.incident_id = i.id
        WHERE i.id = $1
        """,
        incident_id,
    )

    if row is None:
        return None

    skeptic_rows = await conn.fetch(
        """
        SELECT round_number, challenge, response, verdict
        FROM remediation_skeptic_reviews
        WHERE incident_id = $1
        ORDER BY round_number
        """,
        incident_id,
    )

    def _parse_jsonb(val):
        if val is None:
            return None
        if isinstance(val, str):
            return json.loads(val)
        return val

    diagnosis = _parse_jsonb(row["diagnosis"]) or {}
    plan = _parse_jsonb(row["plan"]) or {}
    step_results = _parse_jsonb(row["step_results"])
    dry_run_errors = _parse_jsonb(row.get("dry_run_errors"))
    dimensions = _parse_jsonb(row["dimensions"])

    dry_run_result = None
    if step_results is not None:
        dry_run_result = {
            "step_results": step_results,
            "dry_run_passed": row["dry_run_passed"],
            "dry_run_errors": dry_run_errors or [],
        }

    policy_decision = None
    if dimensions is not None:
        policy_decision = {
            "dimensions": dimensions,
            "evidence_complete": row["evidence_complete"],
            "evidence_gaps_empty": row["evidence_gaps_empty"],
            "auto_execution_approved": row["auto_execution_approved"],
            "reasoning": row["policy_reasoning"],
        }

    skeptic_reviews = []
    for sr in skeptic_rows:
        skeptic_reviews.append({
            "round_number": sr["round_number"],
            "challenge": _parse_jsonb(sr["challenge"]),
            "response": _parse_jsonb(sr["response"]),
            "verdict": _parse_jsonb(sr["verdict"]),
        })

    return {
        "incident_id": row["id"],
        "state": row["state"],
        "severity": row["severity"],
        "diagnosis_summary": diagnosis,
        "remediation_plan": plan,
        "skeptic_reviews": skeptic_reviews,
        "dry_run_result": dry_run_result,
        "blast_radius": row["blast_radius"],
        "policy_decision": policy_decision,
        "queued_at": row["updated_at"],
        "plan_id": row["plan_id"],
    }


async def list_awaiting_approval(
    conn: asyncpg.Connection | asyncpg.Pool,
) -> list[dict]:
    """List all incidents currently in awaiting_approval state."""
    rows = await conn.fetch(
        """
        SELECT i.id, i.state, i.severity, i.created_at, i.updated_at,
               rp.blast_radius
        FROM incidents i
        LEFT JOIN remediation_plans rp ON rp.incident_id = i.id
        WHERE i.state = 'awaiting_approval'
        ORDER BY i.updated_at ASC
        """
    )
    return [
        {
            "id": r["id"],
            "state": r["state"],
            "severity": r["severity"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "blast_radius": r["blast_radius"],
        }
        for r in rows
    ]


async def persist_policy_adjustment(
    conn: asyncpg.Connection | asyncpg.Pool,
    body: PolicyAdjustmentRequest,
    *,
    actor: str,
) -> uuid.UUID:
    """Persist a policy adjustment record."""
    record_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO policy_adjustments (id, severity, blast_radius, confidence, new_auto_approve, actor)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        record_id,
        body.severity,
        body.blast_radius,
        body.confidence,
        body.new_auto_approve,
        actor,
    )
    logger.info(
        "Policy adjustment persisted",
        extra={
            "severity": body.severity,
            "blast_radius": body.blast_radius,
            "actor": actor,
        },
    )
    return record_id
