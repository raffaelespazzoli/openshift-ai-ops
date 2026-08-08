"""AlertManager webhook receiver endpoint.

Receives AlertManager v4 webhook payloads, validates them via Pydantic,
acknowledges with HTTP 200 immediately, and offloads persistence to
BackgroundTasks to meet the 500ms SLA.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..config.logging import Component, get_logger
from ..db import create_alert, create_incident, get_pool, record_resolved_alert
from ..models.webhook import AlertManagerWebhook, WebhookAlertStatus

router = APIRouter()
logger = get_logger(Component.API)

_VALID_SEVERITIES = frozenset({"critical", "warning", "info"})


def _severity_for_alert(alert) -> str:
    """Derive severity from a single alert's labels."""
    sev = alert.labels.get("severity", "warning")
    if sev not in _VALID_SEVERITIES:
        sev = "warning"
    return sev


async def _process_webhook(payload: AlertManagerWebhook) -> None:
    """Background task: persist alerts and create incidents.

    Each firing alert creates its own incident (no batching).
    Story 1.2 handles dedup/correlation — this story must not collapse alerts.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        for alert in payload.alerts:
            if alert.status == WebhookAlertStatus.FIRING:
                severity = _severity_for_alert(alert)
                incident = await create_incident(conn, severity=severity)
                await create_alert(
                    conn,
                    incident_id=incident["id"],
                    fingerprint=alert.fingerprint,
                    labels=dict(alert.labels),
                    annotations=dict(alert.annotations),
                    status=alert.status.value,
                    fired_at=alert.starts_at,
                )
            elif alert.status == WebhookAlertStatus.RESOLVED:
                await record_resolved_alert(
                    conn,
                    fingerprint=alert.fingerprint,
                    resolved_at=alert.ends_at,
                )


@router.post("/api/v1/webhooks/alertmanager")
async def receive_alertmanager_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Receive an AlertManager v4 webhook payload.

    Validates the payload, returns HTTP 200 immediately, and offloads
    persistence to a background task.
    """
    request_details = {
        "method": request.method,
        "path": str(request.url.path),
        "client_host": request.client.host if request.client else "unknown",
    }

    try:
        body = await request.json()
    except Exception:
        logger.warning(
            "Webhook payload is not valid JSON",
            extra={"component": "api", **request_details},
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid webhook payload",
                "code": "INVALID_PAYLOAD",
                "detail": {"validation_errors": ["Request body is not valid JSON"]},
            },
        )

    if not isinstance(body, dict):
        logger.warning(
            "Webhook payload is not a JSON object",
            extra={"component": "api", "body_type": type(body).__name__, **request_details},
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid webhook payload",
                "code": "INVALID_PAYLOAD",
                "detail": {"validation_errors": ["Request body must be a JSON object"]},
            },
        )

    try:
        payload = AlertManagerWebhook(**body)
    except ValidationError as exc:
        sanitized_errors = []
        for err in exc.errors():
            sanitized_errors.append({
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": "invalid value",
            })
        logger.warning(
            "Malformed webhook payload rejected",
            extra={
                "component": "api",
                "validation_error_count": len(sanitized_errors),
                "validation_fields": [e["field"] for e in sanitized_errors],
                **request_details,
            },
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid webhook payload",
                "code": "INVALID_PAYLOAD",
                "detail": {"validation_errors": sanitized_errors},
            },
        )

    background_tasks.add_task(_process_webhook, payload)
    return JSONResponse(status_code=200, content={"status": "accepted"})
