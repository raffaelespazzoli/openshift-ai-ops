"""Incident list and detail REST endpoints.

GET /api/v1/incidents — paginated list with filters
GET /api/v1/incidents/{incident_id} — full detail with correlated alerts
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from ..config.logging import Component, get_logger, request_id_var
from ..db import get_pool
from ..db.incidents import get_incident_detail, list_incidents
from ..models.api import (
    ERROR_NOT_FOUND,
    ApiError,
    ApiMeta,
    ApiResponse,
)
from .auth import UserInfo, get_current_user

router = APIRouter()
logger = get_logger(Component.API)


@router.get("/api/v1/incidents")
async def list_incidents_endpoint(
    request: Request,
    user: UserInfo = Depends(get_current_user),
    status: list[str] | None = Query(None),
    severity: list[str] | None = Query(None),
    from_time: datetime | None = Query(None),
    to_time: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    """Return a paginated list of incidents with optional filters."""
    request.state.user = user

    pool = await get_pool()
    async with pool.acquire() as conn:
        incidents, total = await list_incidents(
            conn,
            statuses=status,
            severities=severity,
            from_time=from_time,
            to_time=to_time,
            page=page,
            page_size=page_size,
        )

    serialized = []
    for inc in incidents:
        serialized.append({
            "id": str(inc["id"]),
            "state": inc["state"],
            "severity": inc["severity"],
            "created_at": inc["created_at"].isoformat(),
            "updated_at": inc["updated_at"].isoformat(),
        })

    meta = ApiMeta(
        request_id=request_id_var.get() or "",
        page=page,
        page_size=page_size,
        total=total,
    )
    return ApiResponse(data=serialized, meta=meta).model_dump(mode="json")


@router.get("/api/v1/incidents/{incident_id}")
async def get_incident_detail_endpoint(
    request: Request,
    incident_id: uuid.UUID,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Return full incident detail including correlated alerts."""
    request.state.user = user

    pool = await get_pool()
    async with pool.acquire() as conn:
        detail = await get_incident_detail(conn, incident_id)

    if detail is None:
        error = ApiError(
            error="Incident not found",
            code=ERROR_NOT_FOUND,
            detail={"incident_id": str(incident_id)},
        )
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content=error.model_dump(mode="json"))

    alerts_serialized = []
    for alert in detail.get("alerts", []):
        alerts_serialized.append({
            "id": str(alert["id"]),
            "fingerprint": alert["fingerprint"],
            "labels": alert["labels"],
            "annotations": alert["annotations"],
            "status": alert["status"],
            "fired_at": alert["fired_at"].isoformat(),
            "resolved_at": alert["resolved_at"].isoformat() if alert.get("resolved_at") else None,
            "created_at": alert["created_at"].isoformat(),
        })

    data = {
        "id": str(detail["id"]),
        "state": detail["state"],
        "severity": detail["severity"],
        "created_at": detail["created_at"].isoformat(),
        "updated_at": detail["updated_at"].isoformat(),
        "alerts": alerts_serialized,
        "correlation_evidence": detail.get("correlation_evidence", {}),
    }

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(data=data, meta=meta).model_dump(mode="json")
