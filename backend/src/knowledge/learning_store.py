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


def compute_version_relevance(
    case_ocp_version: str,
    current_ocp_version: str,
    same_major_weight: float = 1.0,
    different_major_weight: float = 0.5,
    minor_penalty_per_version: float = 0.02,
) -> float:
    """Compute version relevance between case and current cluster OCP versions.

    Same major version: starts at same_major_weight, reduced by
    minor_penalty_per_version for each minor version apart, clamped
    to different_major_weight as floor.

    Different major version: returns different_major_weight directly.
    """
    case_parts = case_ocp_version.split(".")
    current_parts = current_ocp_version.split(".")
    case_major = case_parts[0]
    current_major = current_parts[0]

    if case_major != current_major:
        return different_major_weight

    case_minor = int(case_parts[1]) if len(case_parts) > 1 else 0
    current_minor = int(current_parts[1]) if len(current_parts) > 1 else 0
    minor_distance = abs(current_minor - case_minor)

    relevance = same_major_weight - (minor_penalty_per_version * minor_distance)
    return max(relevance, different_major_weight)


def apply_temporal_decay(
    case: dict,
    current_ocp_version: str = "4",
    decay_half_life_days: float | None = None,
) -> float:
    """Compute effective confidence with temporal decay and version relevance.

    Formula: effective_confidence = base_confidence × decay_factor(age)
             × version_relevance(OCP_version_then vs OCP_version_now)

    Args:
        case: Dict with 'outcome_confidence', 'created_at', 'ocp_version'.
        current_ocp_version: Current cluster OCP version string.
        decay_half_life_days: Half-life for exponential decay. If None, uses
            the Helm/env-configured value from KnowledgeSettings.

    Returns:
        Effective confidence score (0-1 range, may be slightly above if version matches).
    """
    settings = get_knowledge_settings()
    effective_half_life = (
        decay_half_life_days if decay_half_life_days is not None
        else settings.learning_store_decay_half_life_days
    )
    effective_half_life = max(effective_half_life, 1.0)
    age_days = (datetime.now(timezone.utc) - case["created_at"]).days
    decay_factor = math.exp(-0.693 * age_days / effective_half_life)

    version_relevance = compute_version_relevance(
        case["ocp_version"],
        current_ocp_version,
        same_major_weight=settings.version_relevance_same_major,
        different_major_weight=settings.version_relevance_different_major,
        minor_penalty_per_version=settings.version_relevance_minor_penalty_per_version,
    )

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
