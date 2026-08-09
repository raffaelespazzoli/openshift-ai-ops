"""LangGraph audit callback — AD-25 write point #2.

Registers a callback that writes internal pipeline state transitions
to the audit_log table. This is the second audit write point (the first
is the API audit middleware).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..config.logging import Component, get_logger
from ..db import get_pool
from ..db.audit import write_audit_log

logger = get_logger(Component.PIPELINE)


async def pipeline_audit_log(
    *,
    incident_id: str,
    stage_name: str,
    state_before: str,
    state_after: str,
) -> None:
    """Write a pipeline stage transition to the audit log (fire-and-forget).

    Args:
        incident_id: The incident UUID being processed.
        stage_name: The graph node name (e.g. 'diagnose', 'finalize').
        state_before: Pipeline state before this node ran.
        state_after: Pipeline state after this node ran.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await write_audit_log(
                conn,
                actor="pipeline",
                action=f"pipeline.stage.{stage_name}",
                target_resource=f"incident/{incident_id}",
                detail={
                    "incident_id": incident_id,
                    "stage": stage_name,
                    "state_before": state_before,
                    "state_after": state_after,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
    except Exception:
        logger.exception(
            "Pipeline audit log write failed — swallowing error",
            extra={"incident_id": incident_id, "stage": stage_name},
        )
