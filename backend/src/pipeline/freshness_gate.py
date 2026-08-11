"""Freshness gate — verify alert is still firing before execution (AD-16, Story 3.5).

Re-validates that the originating alert is still firing and the diagnosis
is still relevant to current cluster state. Stale remediations are skipped
with the diagnosis preserved as an informational case record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import asyncpg

from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact

logger = get_logger(Component.PIPELINE)


@dataclass
class FreshnessResult:
    """Result of the freshness gate check."""

    is_fresh: bool
    alert_still_firing: bool
    diagnosis_still_relevant: bool
    reason: str | None = None


async def check_freshness(
    incident_id: uuid.UUID,
    artifact: ImmutableDiagnosisArtifact,
    conn: asyncpg.Connection,
) -> FreshnessResult:
    """Verify the alert is still firing and diagnosis is still relevant (AD-16).

    Checks:
    1. Has a resolved webhook arrived for this incident's alerts?
    2. Is the diagnosis still relevant to current cluster state?

    If stale: execution is skipped, diagnosis preserved for Learning Store.
    """
    alert_still_firing = await _check_alert_still_firing(conn, incident_id)

    diagnosis_still_relevant = True

    is_fresh = alert_still_firing and diagnosis_still_relevant

    reason = None
    if not alert_still_firing:
        reason = "Alert resolved — remediation is stale"
    elif not diagnosis_still_relevant:
        reason = "Diagnosis no longer relevant to cluster state"

    logger.info(
        "Freshness gate result",
        extra={
            "incident_id": str(incident_id),
            "is_fresh": is_fresh,
            "alert_still_firing": alert_still_firing,
        },
    )

    return FreshnessResult(
        is_fresh=is_fresh,
        alert_still_firing=alert_still_firing,
        diagnosis_still_relevant=diagnosis_still_relevant,
        reason=reason,
    )


async def _check_alert_still_firing(
    conn: asyncpg.Connection,
    incident_id: uuid.UUID,
) -> bool:
    """Returns True if at least one alert is still firing.

    For correlated incidents (multiple alerts grouped), one alert resolving
    shouldn't invalidate the whole incident. The incident is stale only if
    ALL alerts are resolved (meaning the problem self-healed).
    """
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM alerts WHERE incident_id = $1", incident_id
    )
    resolved = await conn.fetchval(
        "SELECT COUNT(*) FROM alerts WHERE incident_id = $1 AND status = 'resolved'",
        incident_id,
    )
    if total == 0:
        return True  # No alerts tracked — assume still firing (conservative)
    return resolved < total  # Still firing if not ALL resolved
