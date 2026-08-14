"""Immutable diagnosis artifact persistence (AD-2 RBAC Airlock).

Persists the sealed ImmutableDiagnosisArtifact to the immutable_diagnoses
table. This is the handoff object for Epic 3 — the remediation planner
reads from this table.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg

from ..config.logging import Component, get_logger

logger = get_logger(Component.DB)


async def persist_immutable_diagnosis(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    incident_id: str | uuid.UUID,
    diagnosis: dict[str, Any],
    skeptic_verdict: dict[str, Any],
    sealed_at: datetime,
) -> uuid.UUID:
    """Persist a sealed immutable diagnosis artifact.

    Args:
        conn: Database connection or pool.
        incident_id: The incident UUID.
        diagnosis: The sealed DiagnosisObject dict (JSONB).
        skeptic_verdict: The SkepticVerdict dict (JSONB).
        sealed_at: Timestamp when the artifact was sealed.

    Returns:
        The UUID of the inserted record.
    """
    record_id = uuid.uuid4()
    incident_uuid = uuid.UUID(str(incident_id)) if isinstance(incident_id, str) else incident_id
    diagnosis_object_id = diagnosis.get("id")
    diag_obj_uuid = uuid.UUID(str(diagnosis_object_id)) if diagnosis_object_id else None

    try:
        await conn.execute(
            """
            INSERT INTO immutable_diagnoses
                (id, incident_id, diagnosis_object_id, diagnosis, skeptic_verdict, sealed_at, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7)
            """,
            record_id,
            incident_uuid,
            diag_obj_uuid,
            json.dumps(diagnosis, default=str),
            json.dumps(skeptic_verdict, default=str),
            sealed_at,
            datetime.now(timezone.utc),
        )

        logger.info(
            "Immutable diagnosis persisted",
            extra={
                "incident_id": str(incident_uuid),
                "record_id": str(record_id),
            },
        )

    except Exception:
        logger.exception(
            "Failed to persist immutable diagnosis",
            extra={"incident_id": str(incident_uuid)},
        )
        raise

    return record_id
