"""Dry-run pre-flight executor (AD-2, Story 3.3).

Validates each remediation step against the live API server via
the read-write MCP Server's ``apply_resource`` tool with
``--dry-run=server``. The server-side dry-run validates RBAC,
quota, and admission webhooks in a single pass without persisting
changes.

Not all remediation steps are dry-runnable. Imperative operations
(restart, scale, patch, etc.) are skipped with an honest report
of what could and could not be validated.
"""

from __future__ import annotations

from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.policy_gate import DryRunResult, DryRunStepResult
from ..models.remediation import RemediationPlan, RemediationStep
from .mcp_readwrite_client import ReadWriteMCPClient

logger = get_logger(Component.PIPELINE)

DRY_RUNNABLE_ACTIONS: frozenset[str] = frozenset({"apply", "create"})


async def run_dry_run_preflight(
    plan: RemediationPlan,
    artifact: ImmutableDiagnosisArtifact,
    mcp_client: ReadWriteMCPClient | None = None,
) -> DryRunResult:
    """Execute dry-run pre-flight validation against the live cluster.

    Uses the read-write MCP Server to validate each remediation step
    via --dry-run=server without persisting changes.  Imperative steps
    (restart, scale, patch, etc.) are marked as skipped because they
    cannot be validated through server-side dry-run.
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
                skipped=True,
            ))
            continue

        if not _is_dry_runnable(step):
            step_results.append(DryRunStepResult(
                step_order=step.order,
                command=step.command,
                success=True,
                message=(
                    f"Imperative action '{step.action}' is not dry-runnable — skipped"
                ),
                skipped=True,
            ))
            continue

        result = await _validate_step(client, step)
        step_results.append(result)

    overall = all(r.success for r in step_results)
    errors = [
        r.error_detail or r.message
        for r in step_results
        if not r.success
    ]

    return DryRunResult(
        incident_id=plan.incident_id,
        plan_id=plan.id,
        step_results=step_results,
        dry_run_passed=overall,
        dry_run_errors=errors,
    )


def _is_dry_runnable(step: RemediationStep) -> bool:
    """Determine whether a step can be validated via server-side dry-run."""
    return step.action.lower() in DRY_RUNNABLE_ACTIONS


_ERROR_MARKERS: frozenset[str] = frozenset({
    "error", "denied", "forbidden", "failed",
    "refused", "rejected", "unable to",
    "admission webhook", "exceeded quota",
})


def _response_indicates_error(response: str) -> bool:
    """Detect error payloads returned as normal MCP text instead of exceptions."""
    lower = response.lower()
    return any(marker in lower for marker in _ERROR_MARKERS)


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

        if _response_indicates_error(result):
            logger.warning(
                "Dry-run step returned error payload without exception",
                extra={"step_order": step.order, "response_preview": result[:200]},
            )
            return DryRunStepResult(
                step_order=step.order,
                command=step.command or "",
                success=False,
                message="Server-side dry-run returned error response",
                error_detail=result[:500],
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

