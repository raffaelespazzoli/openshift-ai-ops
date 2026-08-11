"""Step-by-step execution engine via read-write MCP (AD-2, Story 3.5).

Executes remediation plan steps sequentially using the ReadWriteMCPClient.
On step failure, stops and returns partial log. Steps without a command
are logged as informational.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..config.logging import Component, get_logger
from ..models.execution import ExecutionLog, ExecutionStepLog
from ..models.remediation import RemediationPlan
from .mcp_readwrite_client import ReadWriteMCPClient

logger = get_logger(Component.PIPELINE)


async def execute_remediation(
    plan: RemediationPlan,
    mcp_client: ReadWriteMCPClient,
) -> ExecutionLog:
    """Execute a remediation plan step-by-step via the read-write MCP Server.

    Executes steps sequentially. On step failure, stops and returns
    partial log. Steps without a command are logged as informational.
    """
    step_logs: list[ExecutionStepLog] = []
    mcp_calls: list[dict] = []
    started_at = datetime.now(timezone.utc)

    logger.info(
        "Starting remediation execution",
        extra={
            "incident_id": str(plan.incident_id),
            "plan_id": str(plan.id),
            "step_count": len(plan.steps),
        },
    )

    for step in plan.steps:
        if step.command is None:
            step_logs.append(
                ExecutionStepLog(
                    step_order=step.order,
                    command="(informational)",
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    success=True,
                    output="Informational step — no command to execute",
                )
            )
            continue

        step_start = datetime.now(timezone.utc)
        try:
            result = await mcp_client.execute(
                tool_name="apply_resource",
                arguments={"command": step.command},
            )
            mcp_calls.append(
                {
                    "step_order": step.order,
                    "tool": "apply_resource",
                    "arguments": {"command": step.command},
                    "result": result[:500],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
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
            logger.warning(
                "Execution step failed",
                extra={
                    "incident_id": str(plan.incident_id),
                    "step_order": step.order,
                    "error": str(e),
                },
            )
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

    status = "completed" if all(s.success for s in step_logs) else "failed"

    logger.info(
        "Remediation execution finished",
        extra={
            "incident_id": str(plan.incident_id),
            "status": status,
            "steps_executed": len(step_logs),
        },
    )

    return ExecutionLog(
        incident_id=plan.incident_id,
        plan_id=plan.id,
        steps=step_logs,
        mcp_calls=mcp_calls,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        status=status,
    )
