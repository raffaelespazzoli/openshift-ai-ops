"""Step-by-step execution engine via read-write MCP (AD-2, Story 3.5).

Executes remediation plan steps sequentially using the ReadWriteMCPClient.
On step failure, stops and returns partial log. Steps without a command
are logged as informational.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..config.logging import Component, get_logger
from ..models.execution import ExecutionLog, ExecutionStepLog
from ..models.remediation import RemediationPlan, RemediationStep
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

        execution_path, arguments = _resolve_execution_args(step)

        if execution_path == "manifest_missing":
            logger.warning(
                "Manifest file not found for step",
                extra={
                    "incident_id": str(plan.incident_id),
                    "step_order": step.order,
                    "manifest_path": step.manifest_path,
                },
            )
            step_logs.append(
                ExecutionStepLog(
                    step_order=step.order,
                    command=step.command or "",
                    started_at=step_start,
                    completed_at=datetime.now(timezone.utc),
                    success=False,
                    output="",
                    error=f"Manifest file not found: {step.manifest_path}",
                )
            )
            break

        try:
            result = await mcp_client.execute(
                tool_name="apply_resource",
                arguments=arguments,
            )
            mcp_calls.append(
                {
                    "step_order": step.order,
                    "tool": "apply_resource",
                    "arguments": arguments,
                    "result": result[:500],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "execution_path": execution_path,
                }
            )
            logger.info(
                "Execution step completed",
                extra={
                    "incident_id": str(plan.incident_id),
                    "step_order": step.order,
                    "execution_path": execution_path,
                },
            )
            step_logs.append(
                ExecutionStepLog(
                    step_order=step.order,
                    command=step.command or "",
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
                    "execution_path": execution_path,
                },
            )
            step_logs.append(
                ExecutionStepLog(
                    step_order=step.order,
                    command=step.command or "",
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


def _resolve_execution_args(
    step: RemediationStep,
) -> tuple[str, dict]:
    """Determine execution path (manifest vs command) and MCP arguments.

    Returns:
        A tuple of (execution_path, arguments). If ``execution_path`` is
        ``"manifest_missing"``, the caller should treat the step as failed.
    """
    if step.manifest_path:
        manifest_file = Path(step.manifest_path)
        if not manifest_file.is_file():
            return "manifest_missing", {}
        manifest_content = manifest_file.read_text()
        return "manifest", {"manifest": manifest_content}
    return "command", {"command": step.command}
