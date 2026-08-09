"""Skeptic review persistence — AD-25 write point for skeptic audit trail.

Persists full challenge/response/verdict JSON to a dedicated skeptic_reviews
table for structured querying, and writes audit_log entries for each round.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg

from ..config.logging import Component, get_logger
from .audit import write_audit_log

logger = get_logger(Component.DB)


async def persist_skeptic_record(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    incident_id: str | uuid.UUID,
    round_number: int,
    challenge: dict[str, Any],
    response: dict[str, Any],
    verdict: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Persist a single skeptic challenge/response round to skeptic_reviews.

    Also writes an audit_log entry for the round completion.

    Args:
        conn: Database connection or pool.
        incident_id: The incident UUID.
        round_number: The round number (1 or 2).
        challenge: The SkepticChallenge dict.
        response: The SkepticResponse dict.
        verdict: The SkepticVerdict dict (optional, set after final round).

    Returns:
        The UUID of the inserted skeptic_reviews record.
    """
    record_id = uuid.uuid4()
    incident_uuid = uuid.UUID(str(incident_id)) if isinstance(incident_id, str) else incident_id

    try:
        await conn.execute(
            """
            INSERT INTO skeptic_reviews (id, incident_id, round_number, challenge, response, verdict, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7)
            """,
            record_id,
            incident_uuid,
            round_number,
            json.dumps(challenge, default=str),
            json.dumps(response, default=str),
            json.dumps(verdict, default=str) if verdict else None,
            datetime.now(timezone.utc),
        )

        await write_audit_log(
            conn,
            actor="pipeline",
            action="pipeline.skeptic.round_complete",
            target_resource=f"incident/{incident_uuid}",
            detail={
                "round_number": round_number,
                "incident_id": str(incident_uuid),
                "challenge_summary": challenge.get("overall_assessment", ""),
                "response_summary": response.get("summary", ""),
            },
        )

        logger.info(
            "Skeptic record persisted",
            extra={
                "incident_id": str(incident_uuid),
                "round_number": round_number,
                "record_id": str(record_id),
            },
        )

    except Exception:
        logger.exception(
            "Failed to persist skeptic record",
            extra={
                "incident_id": str(incident_uuid),
                "round_number": round_number,
            },
        )
        raise

    return record_id
