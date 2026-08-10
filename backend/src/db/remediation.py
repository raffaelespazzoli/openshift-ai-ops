"""Remediation plan persistence and artifact loading (AD-2, Story 3.1).

Persists RemediationPlan to the remediation_plans table and loads
ImmutableDiagnosisArtifact from immutable_diagnoses for the RBAC
Airlock handoff.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import asyncpg

from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.remediation import RemediationPlan

logger = get_logger(Component.DB)


async def persist_remediation_plan(
    conn: asyncpg.Connection | asyncpg.Pool,
    plan: RemediationPlan,
) -> uuid.UUID:
    """Persist a remediation plan to the database.

    Args:
        conn: Database connection or pool.
        plan: The RemediationPlan to persist.

    Returns:
        The UUID of the inserted record.
    """
    try:
        await conn.execute(
            """
            INSERT INTO remediation_plans
                (id, incident_id, diagnosis_id, plan, blast_radius, estimated_risk, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
            """,
            plan.id,
            plan.incident_id,
            plan.diagnosis_id,
            json.dumps(plan.model_dump(mode="json"), default=str),
            plan.blast_radius.value,
            plan.estimated_risk.value,
            plan.created_at,
        )

        logger.info(
            "Remediation plan persisted",
            extra={
                "incident_id": str(plan.incident_id),
                "plan_id": str(plan.id),
                "blast_radius": plan.blast_radius.value,
                "risk_level": plan.estimated_risk.value,
            },
        )

    except Exception:
        logger.exception(
            "Failed to persist remediation plan",
            extra={"incident_id": str(plan.incident_id)},
        )
        raise

    return plan.id


async def load_immutable_artifact(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
) -> ImmutableDiagnosisArtifact:
    """Load the sealed diagnosis artifact for remediation planning.

    This is the RBAC Airlock crossing point. The artifact is read-only.

    Args:
        conn: Database connection or pool.
        incident_id: The incident UUID.

    Returns:
        The frozen ImmutableDiagnosisArtifact.

    Raises:
        ValueError: If no immutable diagnosis exists for the incident.
    """
    row = await conn.fetchrow(
        "SELECT id, diagnosis, skeptic_verdict, sealed_at "
        "FROM immutable_diagnoses WHERE incident_id = $1",
        incident_id,
    )
    if row is None:
        raise ValueError(f"No immutable diagnosis found for incident {incident_id}")

    diag_dict = row["diagnosis"]
    if isinstance(diag_dict, str):
        diag_dict = json.loads(diag_dict)

    # Use the row UUID as the artifact id so downstream FKs
    # (e.g. remediation_plans.diagnosis_id) reference the correct PK.
    diag_dict["id"] = str(row["id"])

    skeptic_verdict = row["skeptic_verdict"]
    if isinstance(skeptic_verdict, str):
        skeptic_verdict = json.loads(skeptic_verdict)

    diag_dict["skeptic_verdict"] = skeptic_verdict
    diag_dict["sealed_at"] = row["sealed_at"]
    return ImmutableDiagnosisArtifact.model_validate(diag_dict)
