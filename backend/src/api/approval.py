"""Human approval workflow REST endpoints (Story 3.4).

GET  /api/v1/incidents/{incident_id}/approval  — full approval context
POST /api/v1/incidents/{incident_id}/approve   — approve remediation plan
POST /api/v1/incidents/{incident_id}/reject    — reject remediation plan
GET  /api/v1/incidents/awaiting-approval       — list awaiting incidents
POST /api/v1/policy/adjust                     — adjust policy thresholds
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..config.approval_settings import ApprovalSettings, get_approval_settings
from ..config.logging import Component, get_logger, request_id_var
from ..db import get_pool, write_audit_log
from ..db.approval import (
    list_awaiting_approval,
    load_approval_context,
    persist_approval_record,
    persist_policy_adjustment,
)
from ..models.api import (
    ERROR_CONFLICT,
    ERROR_NOT_FOUND,
    ApiError,
    ApiMeta,
    ApiResponse,
)
from ..models.approval import (
    ApprovalContext,
    PolicyAdjustmentRequest,
    RejectionRequest,
)
from ..models.events import EventNames, SSEEventData
from ..models.remediation import BlastRadius
from ..models.state_machine import IncidentState, transition
from .auth import UserInfo, get_current_user
from .event_bus import get_event_bus

router = APIRouter()
logger = get_logger(Component.API)


def _get_minimum_review_seconds(
    blast_radius: str | None, settings: ApprovalSettings
) -> int | None:
    """Return the minimum review seconds for a blast radius, or None if disabled."""
    if not settings.minimum_review_enabled:
        return None

    if blast_radius == BlastRadius.NODE.value:
        return settings.minimum_review_seconds_node
    elif blast_radius == BlastRadius.CLUSTER.value:
        return settings.minimum_review_seconds_cluster

    return None


def _review_time_elapsed(
    queued_at: datetime, blast_radius: str | None, settings: ApprovalSettings
) -> tuple[bool, float | None]:
    """Check if the minimum review time has elapsed.

    Returns (elapsed: bool, remaining_seconds: float | None).
    """
    min_seconds = _get_minimum_review_seconds(blast_radius, settings)
    if min_seconds is None:
        return True, None

    elapsed = (datetime.now(timezone.utc) - queued_at).total_seconds()
    remaining = max(0.0, min_seconds - elapsed)
    return elapsed >= min_seconds, remaining if remaining > 0 else None


@router.get("/api/v1/incidents/awaiting-approval")
async def list_awaiting_approval_endpoint(
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """List all incidents currently awaiting human approval."""
    request.state.user = user

    pool = await get_pool()
    async with pool.acquire() as conn:
        items = await list_awaiting_approval(conn)

    serialized = []
    for item in items:
        serialized.append({
            "id": str(item["id"]),
            "state": item["state"],
            "severity": item["severity"],
            "blast_radius": item["blast_radius"],
            "created_at": item["created_at"].isoformat(),
            "updated_at": item["updated_at"].isoformat(),
        })

    meta = ApiMeta(
        request_id=request_id_var.get() or "",
        total=len(serialized),
    )
    return ApiResponse(data=serialized, meta=meta).model_dump(mode="json")


@router.get("/api/v1/incidents/{incident_id}/approval")
async def get_approval_context_endpoint(
    request: Request,
    incident_id: uuid.UUID,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Return full approval context for an incident awaiting approval."""
    request.state.user = user

    pool = await get_pool()
    async with pool.acquire() as conn:
        ctx_data = await load_approval_context(conn, incident_id)

    if ctx_data is None:
        error = ApiError(
            error="Incident not found",
            code=ERROR_NOT_FOUND,
            detail={"incident_id": str(incident_id)},
        )
        return JSONResponse(status_code=404, content=error.model_dump(mode="json"))

    if (
        ctx_data.get("state") == IncidentState.AWAITING_APPROVAL.value
        and not ctx_data.get("remediation_plan")
    ):
        error = ApiError(
            error="Approval context incomplete: no remediation plan found",
            code="INTERNAL_ERROR",
            detail={"incident_id": str(incident_id)},
        )
        return JSONResponse(status_code=500, content=error.model_dump(mode="json"))

    settings = get_approval_settings()
    blast_radius = ctx_data.get("blast_radius")
    min_review = _get_minimum_review_seconds(blast_radius, settings)

    queued_at = ctx_data.get("queued_at")
    review_remaining = None
    if queued_at is not None and min_review is not None:
        elapsed = (datetime.now(timezone.utc) - queued_at).total_seconds()
        remaining = max(0.0, min_review - elapsed)
        review_remaining = remaining if remaining > 0 else None

    ctx = ApprovalContext(
        incident_id=ctx_data["incident_id"],
        state=ctx_data["state"],
        severity=ctx_data.get("severity"),
        diagnosis_summary=ctx_data["diagnosis_summary"],
        remediation_plan=ctx_data["remediation_plan"],
        skeptic_reviews=ctx_data.get("skeptic_reviews", []),
        dry_run_result=ctx_data["dry_run_result"],
        blast_radius=blast_radius,
        policy_decision=ctx_data["policy_decision"],
        queued_at=queued_at,
        minimum_review_seconds=min_review,
        review_time_remaining=review_remaining,
    )

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(
        data=ctx.model_dump(mode="json"), meta=meta
    ).model_dump(mode="json")


@router.post("/api/v1/incidents/{incident_id}/approve")
async def approve_remediation(
    request: Request,
    incident_id: uuid.UUID,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Approve a remediation plan for execution.

    Validates:
    - Incident is in awaiting_approval state
    - Minimum review time has elapsed (for node/cluster blast radius)

    On success: transitions to executing, records approval, emits SSE event.
    """
    request.state.user = user
    settings = get_approval_settings()
    plan_id: uuid.UUID | None = None

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT i.state, i.updated_at, rp.id AS plan_id, rp.blast_radius
                FROM incidents i
                LEFT JOIN remediation_plans rp ON rp.incident_id = i.id
                WHERE i.id = $1
                FOR UPDATE OF i
                """,
                incident_id,
            )

            if row is None:
                error = ApiError(
                    error="Incident not found",
                    code=ERROR_NOT_FOUND,
                    detail={"incident_id": str(incident_id)},
                )
                return JSONResponse(
                    status_code=404, content=error.model_dump(mode="json")
                )

            if row["state"] != IncidentState.AWAITING_APPROVAL.value:
                error = ApiError(
                    error="Incident is not awaiting approval",
                    code=ERROR_CONFLICT,
                    detail={
                        "incident_id": str(incident_id),
                        "current_state": row["state"],
                    },
                )
                return JSONResponse(
                    status_code=409, content=error.model_dump(mode="json")
                )

            plan_id = row["plan_id"]
            if plan_id is None:
                error = ApiError(
                    error="No remediation plan found for this incident",
                    code=ERROR_CONFLICT,
                    detail={"incident_id": str(incident_id)},
                )
                return JSONResponse(
                    status_code=409, content=error.model_dump(mode="json")
                )

            blast_radius = row["blast_radius"]
            elapsed, remaining = _review_time_elapsed(
                row["updated_at"], blast_radius, settings
            )
            if not elapsed:
                error = ApiError(
                    error="Minimum review time has not elapsed",
                    code=ERROR_CONFLICT,
                    detail={
                        "incident_id": str(incident_id),
                        "review_time_remaining": remaining,
                    },
                )
                return JSONResponse(
                    status_code=409, content=error.model_dump(mode="json")
                )

            new_state = transition(
                IncidentState.AWAITING_APPROVAL, IncidentState.EXECUTING
            )
            await conn.execute(
                "UPDATE incidents SET state = $1, updated_at = NOW() WHERE id = $2",
                new_state.value,
                incident_id,
            )

            await persist_approval_record(
                conn,
                incident_id=incident_id,
                plan_id=plan_id,
                action="approved",
                actor=user.username,
            )

    try:
        bus = get_event_bus()
        await bus.emit(
            EventNames.INCIDENT_STATE_CHANGED,
            SSEEventData(
                incident_id=incident_id,
                stage="approval",
                state="executing",
            ),
        )
        await bus.emit(
            EventNames.INCIDENT_APPROVAL_DECISION,
            SSEEventData(
                incident_id=incident_id,
                stage="approval",
                state="executing",
                payload={"action": "approved", "actor": user.username},
            ),
        )
    except Exception:
        logger.warning(
            "Failed to emit SSE event after approval",
            extra={"incident_id": str(incident_id)},
        )

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(
        data={"status": "approved", "new_state": "executing"}, meta=meta
    ).model_dump(mode="json")


@router.post("/api/v1/incidents/{incident_id}/reject")
async def reject_remediation(
    request: Request,
    incident_id: uuid.UUID,
    body: RejectionRequest,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Reject a remediation plan.

    Requires a reason explaining the rejection.
    Transitions incident to failed state.
    """
    request.state.user = user
    plan_id: uuid.UUID | None = None

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT i.state, rp.id AS plan_id
                FROM incidents i
                LEFT JOIN remediation_plans rp ON rp.incident_id = i.id
                WHERE i.id = $1
                FOR UPDATE OF i
                """,
                incident_id,
            )

            if row is None:
                error = ApiError(
                    error="Incident not found",
                    code=ERROR_NOT_FOUND,
                    detail={"incident_id": str(incident_id)},
                )
                return JSONResponse(
                    status_code=404, content=error.model_dump(mode="json")
                )

            if row["state"] != IncidentState.AWAITING_APPROVAL.value:
                error = ApiError(
                    error="Incident is not awaiting approval",
                    code=ERROR_CONFLICT,
                    detail={
                        "incident_id": str(incident_id),
                        "current_state": row["state"],
                    },
                )
                return JSONResponse(
                    status_code=409, content=error.model_dump(mode="json")
                )

            plan_id = row["plan_id"]
            if plan_id is None:
                error = ApiError(
                    error="No remediation plan found for this incident",
                    code=ERROR_CONFLICT,
                    detail={"incident_id": str(incident_id)},
                )
                return JSONResponse(
                    status_code=409, content=error.model_dump(mode="json")
                )

            new_state = transition(
                IncidentState.AWAITING_APPROVAL, IncidentState.FAILED
            )
            await conn.execute(
                "UPDATE incidents SET state = $1, updated_at = NOW() WHERE id = $2",
                new_state.value,
                incident_id,
            )

            await persist_approval_record(
                conn,
                incident_id=incident_id,
                plan_id=plan_id,
                action="rejected",
                actor=user.username,
                reason=body.reason,
            )

    try:
        bus = get_event_bus()
        await bus.emit(
            EventNames.INCIDENT_STATE_CHANGED,
            SSEEventData(
                incident_id=incident_id,
                stage="approval",
                state="failed",
            ),
        )
        await bus.emit(
            EventNames.INCIDENT_APPROVAL_DECISION,
            SSEEventData(
                incident_id=incident_id,
                stage="approval",
                state="failed",
                payload={
                    "action": "rejected",
                    "actor": user.username,
                    "reason": body.reason,
                },
            ),
        )
    except Exception:
        logger.warning(
            "Failed to emit SSE event after rejection",
            extra={"incident_id": str(incident_id)},
        )

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(
        data={"status": "rejected", "new_state": "failed"}, meta=meta
    ).model_dump(mode="json")


@router.post("/api/v1/policy/adjust")
async def adjust_policy(
    request: Request,
    body: PolicyAdjustmentRequest,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Adjust policy gate thresholds for a specific combination.

    Lightweight foundation for Story 6.4's full runtime configuration API.
    Persists to DB and audit-logs the change.
    """
    request.state.user = user

    pool = await get_pool()
    async with pool.acquire() as conn:
        await persist_policy_adjustment(conn, body, actor=user.username)
        await write_audit_log(
            conn,
            actor=user.username,
            action="api.policy.adjusted",
            target_resource="policy_matrix",
            detail=body.model_dump(mode="json"),
        )

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(
        data={"status": "adjusted"}, meta=meta
    ).model_dump(mode="json")
