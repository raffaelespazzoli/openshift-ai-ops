"""Database operations for case records — pgvector similarity search + write (AD-20).

Read path: search_similar_cases (Epic 2).
Write path: persist_case_record, downgrade_case_record, get_case_record_by_incident (Story 4.1).
"""

from __future__ import annotations

import json
import uuid

import asyncpg

from ..config.logging import Component, get_logger
from ..models.case_record import CaseRecord

logger = get_logger(Component.DB)


async def search_similar_cases(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    top_k: int = 3,
    similarity_threshold: float = 0.75,
) -> list[dict]:
    """Search for case records similar to the given embedding using cosine distance.

    Args:
        conn: asyncpg connection with pgvector registered.
        query_embedding: The query vector (alert context embedding).
        top_k: Maximum number of results to return.
        similarity_threshold: Minimum similarity score (0-1).

    Returns:
        List of dicts with case record data and similarity scores,
        ranked by similarity. Returns empty list if no records exist.
    """
    rows = await conn.fetch(
        """
        SELECT id, alert_signature, root_cause_code, outcome,
               outcome_confidence, ocp_version, created_at,
               1 - (alert_signature_embedding <=> $1::vector) AS similarity
        FROM case_records
        WHERE 1 - (alert_signature_embedding <=> $1::vector) > $3
        ORDER BY alert_signature_embedding <=> $1::vector
        LIMIT $2
        """,
        str(query_embedding),
        top_k,
        similarity_threshold,
    )
    return [dict(row) for row in rows]


async def persist_case_record(
    conn: asyncpg.Connection,
    case_record: CaseRecord,
    embedding: list[float] | None = None,
) -> uuid.UUID:
    """Insert a full case record with optional vector embedding.

    Args:
        conn: asyncpg connection.
        case_record: The CaseRecord to persist.
        embedding: Optional 1536-dimension embedding vector.

    Returns:
        The UUID of the persisted case record.
    """
    embedding_str = str(embedding) if embedding else None

    await conn.execute(
        """
        INSERT INTO case_records (
            id, incident_id, alert_signature, alert_signature_embedding,
            root_cause_code, outcome, outcome_confidence, ocp_version,
            cluster_context, diagnosis_summary, remediation_summary,
            diagnosis_object, remediation_plan, outcome_details,
            fast_path_eligible, created_at
        ) VALUES (
            $1, $2, $3, $4::vector,
            $5, $6, $7, $8,
            $9, $10, $11,
            $12, $13, $14,
            $15, $16
        )
        """,
        case_record.id,
        case_record.incident_id,
        case_record.alert_signature,
        embedding_str,
        case_record.root_cause_code,
        case_record.outcome,
        case_record.outcome_confidence,
        case_record.ocp_version,
        json.dumps(case_record.cluster_context),
        case_record.diagnosis_summary,
        case_record.remediation_summary,
        json.dumps(case_record.diagnosis_object),
        json.dumps(case_record.remediation_plan),
        json.dumps(case_record.outcome_details),
        case_record.fast_path_eligible,
        case_record.created_at,
    )

    logger.info(
        "Case record persisted",
        extra={
            "case_record_id": str(case_record.id),
            "incident_id": str(case_record.incident_id),
            "has_embedding": embedding is not None,
        },
    )
    return case_record.id


async def downgrade_case_record(
    conn: asyncpg.Connection,
    incident_id: uuid.UUID,
    new_confidence: float,
    reason: str,
) -> bool:
    """Downgrade a case record's confidence and revoke fast-path eligibility.

    Used when an alert re-fires or a rollback is triggered.

    Args:
        conn: asyncpg connection.
        incident_id: The incident whose case record to downgrade.
        new_confidence: The new (lower) outcome_confidence value.
        reason: Reason for the downgrade (logged, not persisted).

    Returns:
        True if a record was updated, False if no record found.
    """
    result = await conn.execute(
        """
        UPDATE case_records
        SET outcome_confidence = $2,
            fast_path_eligible = FALSE
        WHERE incident_id = $1
        """,
        incident_id,
        new_confidence,
    )
    updated = result.split()[-1] != "0"

    if updated:
        logger.info(
            "Case record downgraded",
            extra={
                "incident_id": str(incident_id),
                "new_confidence": new_confidence,
                "reason": reason,
            },
        )
    else:
        logger.info(
            "No case record found for downgrade",
            extra={"incident_id": str(incident_id)},
        )

    return updated


async def search_fast_path_candidates(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    threshold: float = 0.90,
    top_k: int = 3,
) -> list[dict]:
    """Search for fast-path-eligible case records above the similarity threshold.

    Filters for successful outcomes with fast_path_eligible = TRUE.
    Returns full diagnosis_object and remediation_plan for replay.

    Args:
        conn: asyncpg connection with pgvector registered.
        query_embedding: The query vector (alert signature embedding).
        threshold: Minimum cosine similarity for fast-path eligibility.
        top_k: Maximum number of candidates to return.

    Returns:
        List of dicts with case record data and similarity scores,
        ordered by similarity (best match first).
    """
    rows = await conn.fetch(
        """
        SELECT id, alert_signature, root_cause_code, outcome,
               outcome_confidence, ocp_version, created_at,
               diagnosis_object, remediation_plan,
               1 - (alert_signature_embedding <=> $1::vector) AS similarity
        FROM case_records
        WHERE fast_path_eligible = TRUE
          AND outcome = 'success'
          AND alert_signature_embedding IS NOT NULL
          AND diagnosis_object IS NOT NULL
          AND remediation_plan IS NOT NULL
          AND 1 - (alert_signature_embedding <=> $1::vector) > $2
        ORDER BY alert_signature_embedding <=> $1::vector
        LIMIT $3
        """,
        str(query_embedding),
        threshold,
        top_k,
    )
    return [dict(row) for row in rows]


async def get_case_record_by_incident(
    conn: asyncpg.Connection,
    incident_id: uuid.UUID,
) -> dict | None:
    """Look up a case record by incident ID.

    Args:
        conn: asyncpg connection.
        incident_id: The incident ID to search for.

    Returns:
        Dict of case record data, or None if not found.
    """
    row = await conn.fetchrow(
        """
        SELECT id, incident_id, alert_signature, root_cause_code,
               outcome, outcome_confidence, ocp_version, cluster_context,
               diagnosis_summary, remediation_summary, diagnosis_object,
               remediation_plan, outcome_details, fast_path_eligible,
               created_at
        FROM case_records
        WHERE incident_id = $1
        """,
        incident_id,
    )
    return dict(row) if row else None
