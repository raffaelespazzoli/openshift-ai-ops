"""Outcome observation — webhook monitoring + resource verification (Story 3.5).

Primary signal: resolved webhook from AlertManager (DB poll).
Corroborating signal: direct resource verification via read-only MCP.
Includes re-fire detection as a post-observation background task.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from ..config.execution_settings import ExecutionSettings, get_execution_settings
from ..config.logging import Component, get_logger
from ..db.connection import get_pool
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.execution import ExecutionLog, OutcomeConfidence, OutcomeResult
from .mcp_client import ReadOnlyMCPClient

logger = get_logger(Component.PIPELINE)


async def observe_outcome(
    incident_id: uuid.UUID,
    artifact: ImmutableDiagnosisArtifact,
    execution_log: ExecutionLog,
    settings: ExecutionSettings | None = None,
    _sleep: object = asyncio.sleep,
) -> OutcomeResult:
    """Observe whether the remediation resolved the problem.

    Primary signal: resolved webhook from AlertManager
    Corroborating signal: direct resource verification via read-only MCP

    outcome_confidence scoring:
    - 1.0: Both webhook resolved AND resource verification passes
    - 0.7: Webhook resolved only
    - 0.5: Resource verification passes only
    - 0.2: Timeout — neither signal received
    """
    config = settings or get_execution_settings()
    observation_start = datetime.now(timezone.utc)

    alert_resolved = False
    resource_verification: dict | None = None

    deadline = observation_start + timedelta(seconds=config.observation_timeout_seconds)
    while datetime.now(timezone.utc) < deadline:
        pool = await get_pool()
        async with pool.acquire() as conn:
            alert_resolved = await _check_alert_resolved(conn, incident_id)

        if alert_resolved:
            break

        await _sleep(config.lock_poll_interval_seconds)

    resource_verification = await _verify_affected_resources(artifact)

    webhook_ok = alert_resolved
    verification_ok = (
        resource_verification is not None
        and resource_verification.get("all_healthy", False)
    )

    if webhook_ok and verification_ok:
        outcome_confidence = OutcomeConfidence.BOTH
    elif webhook_ok:
        outcome_confidence = OutcomeConfidence.WEBHOOK_ONLY
    elif verification_ok:
        outcome_confidence = OutcomeConfidence.VERIFICATION_ONLY
    else:
        outcome_confidence = OutcomeConfidence.TIMEOUT

    resolution_method = (
        "webhook" if webhook_ok else ("verification" if verification_ok else "timeout")
    )

    logger.info(
        "Outcome observation complete",
        extra={
            "incident_id": str(incident_id),
            "alert_resolved": alert_resolved,
            "outcome_confidence": outcome_confidence,
            "resolution_method": resolution_method,
        },
    )

    return OutcomeResult(
        incident_id=incident_id,
        alert_resolved=alert_resolved,
        resolution_method=resolution_method,
        resource_verification=resource_verification,
        outcome_confidence=outcome_confidence,
        refire_detected=False,
        observation_started_at=observation_start,
        observation_completed_at=datetime.now(timezone.utc),
        timeout_seconds=config.observation_timeout_seconds,
    )


async def monitor_for_refire(
    incident_id: uuid.UUID,
    settings: ExecutionSettings | None = None,
    _sleep: object = asyncio.sleep,
) -> bool:
    """Monitor for alert re-fire within the configured window.

    Called after a successful resolution. Runs as a background task.
    If re-fire detected, flags the incident for review.
    """
    config = settings or get_execution_settings()
    deadline = datetime.now(timezone.utc) + timedelta(
        seconds=config.refire_window_seconds
    )

    while datetime.now(timezone.utc) < deadline:
        pool = await get_pool()
        async with pool.acquire() as conn:
            refired = await _check_alert_refired(conn, incident_id)

        if refired:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE outcome_results
                    SET refire_detected = TRUE
                    WHERE incident_id = $1
                    """,
                    incident_id,
                )
            logger.warning(
                "Re-fire detected for resolved incident",
                extra={"incident_id": str(incident_id)},
            )
            return True

        await _sleep(config.lock_poll_interval_seconds)

    return False


async def _check_alert_resolved(
    conn,
    incident_id: uuid.UUID,
) -> bool:
    """Check if ALL alerts for this incident have resolved.

    For correlated incidents (multiple alerts grouped), all alerts
    must resolve for the remediation to be considered successful.
    """
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM alerts WHERE incident_id = $1", incident_id
    )
    resolved = await conn.fetchval(
        "SELECT COUNT(*) FROM alerts WHERE incident_id = $1 AND status = 'resolved'",
        incident_id,
    )
    if total == 0:
        return False  # No alerts to check — can't confirm resolution
    return resolved >= total  # All alerts resolved


async def _check_alert_refired(
    conn,
    incident_id: uuid.UUID,
) -> bool:
    """Check if the alert has re-fired after resolution.

    Looks for new firing alerts after a resolved alert for the same incident.
    """
    row = await conn.fetchrow(
        """
        SELECT EXISTS(
            SELECT 1 FROM alerts a1
            WHERE a1.incident_id = $1
              AND a1.status = 'firing'
              AND a1.created_at > (
                  SELECT MAX(a2.created_at) FROM alerts a2
                  WHERE a2.incident_id = $1 AND a2.status = 'resolved'
              )
        ) AS refired
        """,
        incident_id,
    )
    return row["refired"] if row else False


_DEGRADATION_SIGNALS = (
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
    "OOMKilled",
    "Error",
    "Failed",
    "NotReady",
    "Terminating",
    "Evicted",
    "BackOff",
    "ContainerCannotRun",
)


def _content_indicates_unhealthy(text: str) -> bool:
    """Check MCP response content for degradation signals."""
    lowered = text.lower()
    for signal in _DEGRADATION_SIGNALS:
        if signal.lower() in lowered:
            return True
    return False


async def _verify_affected_resources(
    artifact: ImmutableDiagnosisArtifact,
) -> dict | None:
    """Verify affected resources are healthy via read-only MCP.

    Uses ReadOnlyMCPClient for post-remediation verification (AD-2).
    A resource is considered unhealthy if the MCP response is invalid
    OR contains known degradation keywords (CrashLoopBackOff, OOMKilled, etc.).
    """
    if not artifact.affected_resources:
        return {"all_healthy": True, "resources": []}

    try:
        client = ReadOnlyMCPClient()
        results = []

        for resource in artifact.affected_resources:
            evidence = await client.query(
                tool_name="resources_list",
                arguments={"apiVersion": "v1", "kind": "Pod", "namespace": resource.split("/")[0] if "/" in resource else "default"},
            )
            from ..models.diagnosis import EvidenceArtifact

            if not isinstance(evidence, EvidenceArtifact):
                results.append(
                    {
                        "resource": resource,
                        "healthy": False,
                        "detail": str(evidence)[:200],
                    }
                )
                continue

            content = evidence.result[:2000]
            has_degradation = _content_indicates_unhealthy(content)
            healthy = not has_degradation
            results.append(
                {
                    "resource": resource,
                    "healthy": healthy,
                    "detail": content[:200],
                }
            )

        all_healthy = all(r["healthy"] for r in results)
        return {"all_healthy": all_healthy, "resources": results}

    except Exception:
        logger.warning(
            "Resource verification failed — treating as inconclusive",
            extra={"affected_resources": list(artifact.affected_resources)},
        )
        return None
