"""Manifest generation pipeline stage (AD-1, Story 4.0).

Queries the cluster for current resource state via the read-write MCP Server,
applies the planned change to produce complete YAML manifests, and writes them
to a temp directory scoped to the incident.  Eligible actions are ``apply``
and ``create``.  Imperative actions (restart, scale, patch, etc.) are skipped
with an honest report.  Failures are recorded per-step; the pipeline is never
aborted by a single step failure.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import yaml

from ..config.logging import Component, get_logger
from ..models.remediation import RemediationPlan, RemediationStep
from .mcp_readwrite_client import ReadWriteMCPClient

logger = get_logger(Component.PIPELINE)

MANIFEST_ELIGIBLE_ACTIONS: frozenset[str] = frozenset({"apply", "create"})


async def generate_manifests(
    plan: RemediationPlan,
    mcp_client: ReadWriteMCPClient,
    base_temp_dir: str | None = None,
) -> RemediationPlan:
    """Generate YAML manifests for eligible remediation steps.

    For each ``apply`` or ``create`` step the generator queries the current
    cluster state, applies the planned change, and writes the resulting YAML
    to ``{temp_dir}/{incident_id}/step-{order}.yaml``.

    Args:
        plan: The validated remediation plan (post-skeptic).
        mcp_client: The read-write MCP client for querying cluster state.
        base_temp_dir: Override the temp directory root (for testing).

    Returns:
        A new ``RemediationPlan`` with ``manifest_path`` and
        ``manifest_generation_failed`` set on applicable steps.
    """
    incident_id = str(plan.incident_id)

    if base_temp_dir is None:
        base_temp_dir = tempfile.mkdtemp(prefix="aiops-manifests-")

    incident_dir = Path(base_temp_dir) / incident_id
    incident_dir.mkdir(parents=True, exist_ok=True)

    counts = {"eligible": 0, "generated": 0, "skipped": 0, "failed": 0}
    updated_steps: list[RemediationStep] = []

    for step in plan.steps:
        new_step = await _process_step(step, mcp_client, incident_dir, counts)
        updated_steps.append(new_step)

    logger.info(
        "Manifest generation complete",
        extra={
            "incident_id": incident_id,
            "eligible": counts["eligible"],
            "generated": counts["generated"],
            "skipped": counts["skipped"],
            "failed": counts["failed"],
        },
    )

    return plan.model_copy(update={"steps": updated_steps})


async def _process_step(
    step: RemediationStep,
    mcp_client: ReadWriteMCPClient,
    incident_dir: Path,
    counts: dict[str, int],
) -> RemediationStep:
    """Process a single step: generate manifest or skip/fail as appropriate."""
    if step.command is None:
        counts["skipped"] += 1
        logger.debug(
            "Skipping informational step (no command)",
            extra={"step_order": step.order},
        )
        return step

    if step.action.lower() not in MANIFEST_ELIGIBLE_ACTIONS:
        counts["skipped"] += 1
        logger.info(
            "Imperative action '%s' has no manifest equivalent — skipped",
            step.action,
            extra={"step_order": step.order},
        )
        return step

    counts["eligible"] += 1

    try:
        current_yaml = await mcp_client.query(
            "resources_get",
            {"resource": step.resource},
        )

        resource_data = yaml.safe_load(current_yaml)
        if resource_data is None:
            raise ValueError(f"Empty YAML returned for resource {step.resource}")

        manifest_content = _apply_planned_change(resource_data, step)
        manifest_yaml = yaml.dump(manifest_content, default_flow_style=False)

        manifest_path = incident_dir / f"step-{step.order}.yaml"
        manifest_path.write_text(manifest_yaml)

        counts["generated"] += 1
        logger.info(
            "Manifest generated",
            extra={
                "step_order": step.order,
                "manifest_path": str(manifest_path),
            },
        )
        return step.model_copy(update={"manifest_path": str(manifest_path)})

    except Exception as exc:
        counts["failed"] += 1
        logger.warning(
            "Manifest generation failed for step",
            extra={
                "step_order": step.order,
                "error": str(exc),
            },
        )
        return step.model_copy(update={"manifest_generation_failed": True})


def _apply_planned_change(
    current_resource: dict,
    step: RemediationStep,
) -> dict:
    """Apply the planned change to the current resource state.

    Strips server-managed metadata that should not appear in an apply
    manifest, then returns the resource ready for ``kubectl apply``.
    """
    resource = copy.deepcopy(current_resource)

    metadata = resource.get("metadata", {})
    for key in ("resourceVersion", "uid", "creationTimestamp",
                "generation", "managedFields"):
        metadata.pop(key, None)

    status = resource.pop("status", None)
    if status is not None:
        logger.debug(
            "Stripped 'status' from manifest for step %d", step.order,
        )

    return resource
