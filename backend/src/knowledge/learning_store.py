"""Learning Store query interface — pgvector similarity + temporal decay (AD-20).

Provides read-only access to past Case Records for enriching diagnosis.
The table is populated by Epic 4; this module only queries.
Returns empty list gracefully when no records exist.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import asyncpg

from ..config.knowledge_settings import get_knowledge_settings
from ..config.logging import Component, get_logger
from ..db.case_records import search_similar_cases
from ..knowledge.embeddings import embed_texts
from ..models.case_record import CaseRecordSummary

logger = get_logger(Component.KNOWLEDGE)


def _get_decay_half_life_days() -> float:
    """Get the configured decay half-life from settings (Helm/env-configurable)."""
    return get_knowledge_settings().learning_store_decay_half_life_days


def apply_temporal_decay(
    case: dict,
    current_ocp_version: str = "4",
    decay_half_life_days: float | None = None,
) -> float:
    """Compute effective confidence with temporal decay and version relevance.

    Formula: effective_confidence = base_confidence × decay_factor(age) × version_relevance

    Args:
        case: Dict with 'outcome_confidence', 'created_at', 'ocp_version'.
        current_ocp_version: Current cluster OCP version string.
        decay_half_life_days: Half-life for exponential decay. If None, uses
            the Helm/env-configured value from KnowledgeSettings.

    Returns:
        Effective confidence score (0-1 range, may be slightly above if version matches).
    """
    effective_half_life = (
        decay_half_life_days if decay_half_life_days is not None
        else _get_decay_half_life_days()
    )
    age_days = (datetime.now(timezone.utc) - case["created_at"]).days
    decay_factor = math.exp(-0.693 * age_days / effective_half_life)

    case_major = case["ocp_version"].split(".")[0]
    current_major = current_ocp_version.split(".")[0]
    version_relevance = 1.0 if case_major == current_major else 0.5

    return case["outcome_confidence"] * decay_factor * version_relevance


async def query_learning_store(
    alert_context: str,
    conn: asyncpg.Connection,
    top_k: int = 3,
    similarity_threshold: float = 0.75,
    current_ocp_version: str = "4",
) -> list[CaseRecordSummary]:
    """Query the Learning Store for past cases similar to the current alert context.

    Embeds the alert context, queries pgvector for similar case records,
    applies temporal decay, and returns ranked results.

    Args:
        alert_context: Text describing the current alert/symptoms.
        conn: asyncpg connection with pgvector registered.
        top_k: Maximum results to return.
        similarity_threshold: Minimum cosine similarity.
        current_ocp_version: Current OCP version for relevance weighting.

    Returns:
        List of CaseRecordSummary ranked by effective confidence.
        Returns empty list when no records exist (graceful degradation).

    Raises:
        RuntimeError: If the embedding service returns no vectors.
        Exception: Propagates embedding or DB query failures so callers
            can report them as evidence gaps rather than masking them
            as empty results.
    """
    embeddings = await embed_texts([alert_context])
    if not embeddings:
        raise RuntimeError("Embedding service returned no vectors for alert context")
    query_embedding = embeddings[0]

    cases = await search_similar_cases(
        conn, query_embedding, top_k=top_k, similarity_threshold=similarity_threshold
    )

    if not cases:
        return []

    results = []
    for case in cases:
        effective_conf = apply_temporal_decay(
            case, current_ocp_version=current_ocp_version
        )
        results.append(CaseRecordSummary(
            id=case["id"],
            alert_signature=case["alert_signature"],
            root_cause_code=case["root_cause_code"],
            outcome=case["outcome"],
            outcome_confidence=case["outcome_confidence"],
            ocp_version=case["ocp_version"],
            created_at=case["created_at"],
            similarity=case["similarity"],
            effective_confidence=effective_conf,
        ))

    results.sort(key=lambda r: r.effective_confidence, reverse=True)
    return results
