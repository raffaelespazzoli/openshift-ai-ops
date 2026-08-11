"""Rollback API endpoint (Story 3.5).

POST /api/v1/incidents/{incident_id}/rollback — execute the rollback plan.
Rollback is human-triggered ONLY. The system never auto-rolls back.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..config.logging import Component, get_logger, request_id_var
from ..db import get_pool, write_audit_log
from ..db.execution import persist_rollback_record
from ..db.remediation_lock import acquire_remediation_lock, release_remediation_lock
from ..models.api import ERROR_CONFLICT, ERROR_NOT_FOUND, ApiError, ApiMeta, ApiResponse
from ..models.execution import ExecutionStepLog, RollbackRecord
from ..models.remediation import RemediationPlan, RemediationStep
from ..models.state_machine import IncidentState
from .auth import UserInfo, get_current_user

router = APIRouter()
logger = get_logger(Component.API)


@router.post("/api/v1/incidents/{incident_id}/rollback")
async def trigger_rollback(
    request: Request,
    incident_id: uuid.UUID,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Trigger rollback of a completed remediation.

    Executes the rollback_plan from the RemediationPlan.
    Rollback is always a failure signal for the Learning Store.
    """
    request.state.user = user

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state FROM incidents WHERE id = $1", incident_id
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

        state = IncidentState(row["state"])
        if state not in (IncidentState.RESOLVED, IncidentState.FAILED):
            error = ApiError(
                error="Can only roll back completed remediations",
                code=ERROR_CONFLICT,
                detail={
                    "incident_id": str(incident_id),
                    "current_state": state.value,
                },
            )
            return JSONResponse(
                status_code=409, content=error.model_dump(mode="json")
            )

        plan_row = await conn.fetchrow(
            "SELECT id, plan FROM remediation_plans WHERE incident_id = $1",
            incident_id,
        )

        if plan_row is None:
            error = ApiError(
                error="No remediation plan found",
                code=ERROR_NOT_FOUND,
                detail={"incident_id": str(incident_id)},
            )
            return JSONResponse(
                status_code=404, content=error.model_dump(mode="json")
            )

        import json as _json

        plan_data = plan_row["plan"]
        if isinstance(plan_data, str):
            plan_data = _json.loads(plan_data)
        plan = RemediationPlan.model_validate(plan_data)
        plan_id = plan_row["id"]

        if not plan.rollback_plan:
            error = ApiError(
                error="No rollback steps available in the remediation plan",
                code=ERROR_CONFLICT,
                detail={"incident_id": str(incident_id)},
            )
            return JSONResponse(
                status_code=409, content=error.model_dump(mode="json")
            )

        exec_row = await conn.fetchrow(
            "SELECT id, status FROM execution_logs WHERE incident_id = $1",
            incident_id,
        )
        if exec_row is None:
            error = ApiError(
                error="No execution record found — remediation was never executed",
                code=ERROR_CONFLICT,
                detail={"incident_id": str(incident_id)},
            )
            return JSONResponse(
                status_code=409, content=error.model_dump(mode="json")
            )

    from ..pipeline.mcp_readwrite_client import ReadWriteMCPClient

    async with pool.acquire() as lock_conn:
        async with lock_conn.transaction():
            locked = await acquire_remediation_lock(lock_conn, incident_id)
            if not locked:
                error = ApiError(
                    error="Another remediation is currently executing. Retry later.",
                    code=ERROR_CONFLICT,
                    detail={"incident_id": str(incident_id)},
                )
                return JSONResponse(
                    status_code=409, content=error.model_dump(mode="json")
                )

            mcp_client = ReadWriteMCPClient()
            rollback_steps = await _execute_rollback(plan.rollback_plan, mcp_client)

            record = RollbackRecord(
                incident_id=incident_id,
                plan_id=plan_id,
                actor=user.username,
                steps_executed=rollback_steps,
                success=all(s.success for s in rollback_steps),
            )

            await persist_rollback_record(lock_conn, record)
            await write_audit_log(
                lock_conn,
                actor=user.username,
                action="api.remediation.rollback",
                target_resource=str(incident_id),
                detail={
                    "plan_id": str(plan_id),
                    "success": record.success,
                    "steps_executed": len(rollback_steps),
                },
            )

            await release_remediation_lock(lock_conn)

    try:
        from ..api.event_bus import get_event_bus
        from ..models.events import EventNames, SSEEventData

        bus = get_event_bus()
        await bus.emit(
            EventNames.INCIDENT_STAGE_CHANGED,
            SSEEventData(
                incident_id=incident_id,
                stage="rollback",
                state="completed" if record.success else "failed",
                payload={},
            ),
        )
    except Exception:
        logger.warning(
            "Failed to emit rollback SSE event",
            extra={"incident_id": str(incident_id)},
        )

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(
        data={"status": "rollback_completed", "success": record.success},
        meta=meta,
    ).model_dump(mode="json")


async def _execute_rollback(
    steps: list[RemediationStep],
    mcp_client,
) -> list[ExecutionStepLog]:
    """Execute rollback steps via read-write MCP."""
    step_logs: list[ExecutionStepLog] = []

    for step in steps:
        if step.command is None:
            step_logs.append(
                ExecutionStepLog(
                    step_order=step.order,
                    command="(informational)",
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    success=True,
                    output="Informational rollback step",
                )
            )
            continue

        step_start = datetime.now(timezone.utc)
        try:
            result = await mcp_client.execute(
                tool_name="apply_resource",
                arguments={"command": step.command},
            )
            step_logs.append(
                ExecutionStepLog(
                    step_order=step.order,
                    command=step.command,
                    started_at=step_start,
                    completed_at=datetime.now(timezone.utc),
                    success=True,
                    output=result,
                )
            )
        except Exception as e:
            step_logs.append(
                ExecutionStepLog(
                    step_order=step.order,
                    command=step.command,
                    started_at=step_start,
                    completed_at=datetime.now(timezone.utc),
                    success=False,
                    output="",
                    error=str(e),
                )
            )
            break

    return step_logs
