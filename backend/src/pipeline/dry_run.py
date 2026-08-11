"""Dry-run pre-flight executor (AD-2, Story 3.3).

Validates each remediation step against the live API server via
the read-write MCP Server's ``apply_resource`` tool with
``--dry-run=server``. The server-side dry-run validates RBAC,
quota, and admission webhooks in a single pass without persisting
changes.
"""

from __future__ import annotations

from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.policy_gate import DryRunResult, DryRunStepResult
from ..models.remediation import RemediationPlan, RemediationStep
from .mcp_readwrite_client import ReadWriteMCPClient

logger = get_logger(Component.PIPELINE)


async def run_dry_run_preflight(
    plan: RemediationPlan,
    artifact: ImmutableDiagnosisArtifact,
    mcp_client: ReadWriteMCPClient | None = None,
) -> DryRunResult:
    """Execute dry-run pre-flight validation against the live cluster.

    Uses the read-write MCP Server to validate each remediation step
    via --dry-run=server without persisting changes.
    """
    client = mcp_client or ReadWriteMCPClient()
    step_results: list[DryRunStepResult] = []

    for step in plan.steps:
        if step.command is None:
            step_results.append(DryRunStepResult(
                step_order=step.order,
                command="(no command)",
                success=True,
                message="Informational step — no command to validate",
            ))
            continue

        result = await _validate_step(client, step)
        step_results.append(result)

    overall = all(r.success for r in step_results)

    return DryRunResult(
        incident_id=plan.incident_id,
        plan_id=plan.id,
        step_results=step_results,
        rbac_check_passed=overall,
        quota_check_passed=overall,
        admission_check_passed=overall,
        overall_passed=overall,
    )


async def _validate_step(
    client: ReadWriteMCPClient,
    step: RemediationStep,
) -> DryRunStepResult:
    """Validate a single step via MCP apply_resource with dry-run=server."""
    try:
        result = await client.query(
            "apply_resource",
            {
                "command": step.command,
                "resource": step.resource,
                "dry_run": "server",
            },
        )
        return DryRunStepResult(
            step_order=step.order,
            command=step.command or "",
            success=True,
            message=f"Dry-run passed: {result[:200]}",
        )
    except Exception as exc:
        logger.warning(
            "Dry-run step validation failed",
            extra={"step_order": step.order, "error": str(exc)},
        )
        return DryRunStepResult(
            step_order=step.order,
            command=step.command or "",
            success=False,
            message="Dry-run validation failed",
            error_detail=str(exc),
        )

