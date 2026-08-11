"""Dry-run pre-flight executor (AD-2, Story 3.3).

Validates each remediation step against the live API server via
the read-write MCP Server's ``apply_resource`` tool with
``--dry-run=server``. Checks RBAC permissions and admission
webhooks without persisting changes. Quota is validated implicitly
by the server-side dry-run.
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

    rbac_passed = await _check_rbac(client, plan)
    admission_passed = all(
        r.success for r in step_results if r.command != "(no command)"
    )

    overall = (
        rbac_passed
        and admission_passed
        and all(r.success for r in step_results)
    )

    return DryRunResult(
        incident_id=plan.incident_id,
        plan_id=plan.id,
        step_results=step_results,
        rbac_check_passed=rbac_passed,
        quota_check_passed=True,
        admission_check_passed=admission_passed,
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


async def _check_rbac(
    client: ReadWriteMCPClient,
    plan: RemediationPlan,
) -> bool:
    """Verify ServiceAccount permissions via SelfSubjectAccessReview.

    Matches the established MCP contract used by the planner-side RBAC helper.
    """
    try:
        for step in plan.steps:
            if step.command is None:
                continue
            namespace = _extract_namespace(step.resource)
            result = await client.query(
                "get_resources",
                {
                    "kind": "SelfSubjectAccessReview",
                    "namespace": namespace,
                    "verb": step.action,
                    "resource": step.resource,
                },
            )
            if "denied" in result.lower() or "allowed: false" in result.lower():
                logger.warning(
                    "RBAC check failed for step",
                    extra={"step_order": step.order, "resource": step.resource},
                )
                return False
        return True
    except Exception as exc:
        logger.warning("RBAC check failed", extra={"error": str(exc)})
        return False


def _extract_namespace(resource: str) -> str:
    """Extract namespace from a resource string, defaulting to 'default'."""
    parts = resource.split("/")
    if len(parts) >= 3:
        return parts[1]
    return "default"


