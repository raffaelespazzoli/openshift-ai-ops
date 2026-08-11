"""Remediation planner agent — AI-powered fix planning (AD-1, Story 3.1).

The planner is a LangGraph create_react_agent subgraph invoked by the
plan node in the remediation graph. It receives the ImmutableDiagnosisArtifact
as read-only context and uses the read-write MCP client to query current
cluster state when designing fix steps.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from ..config.llm_settings import AgentRole
from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.remediation import RemediationPlan
from ..models.remediation_skeptic import RemediationSkepticChallenge
from ..pipeline.mcp_readwrite_client import ReadWriteMCPClient
from .llm_client import get_chat_model
from .prompts import (
    PLANNER_REBUTTAL_PROMPT_TEMPLATE,
    PLANNER_STRUCTURED_PROMPT,
    PLANNER_SYSTEM_PROMPT,
)

logger = get_logger(Component.AGENT)

_rw_mcp_client: ReadWriteMCPClient | None = None


def _get_rw_mcp_client() -> ReadWriteMCPClient:
    global _rw_mcp_client
    if _rw_mcp_client is None:
        _rw_mcp_client = ReadWriteMCPClient()
    return _rw_mcp_client


def set_rw_mcp_client(client: ReadWriteMCPClient | None) -> None:
    """Override the read-write MCP client (for testing)."""
    global _rw_mcp_client
    _rw_mcp_client = client


@tool
async def query_cluster_state(
    resource_type: str,
    namespace: str = "default",
    name: str = "",
) -> dict[str, Any]:
    """Query current cluster resource state via the read-write MCP Server.

    Used by the planner to inspect live resources before designing fix steps.

    Args:
        resource_type: Kind of resource to query (e.g. Pod, Node, Deployment).
        namespace: Kubernetes namespace to search in.
        name: Optional specific resource name.
    """
    client = _get_rw_mcp_client()
    arguments: dict[str, Any] = {"kind": resource_type, "namespace": namespace}
    if name:
        arguments["name"] = name

    tool_name = "get_resource" if name else "get_resources"
    try:
        result = await client.query(tool_name, arguments)
        return {
            "type": "cluster_state",
            "query": f"{tool_name}({arguments})",
            "result": result,
        }
    except Exception as exc:
        return {
            "type": "error",
            "query": f"{tool_name}({arguments})",
            "error": str(exc),
        }


@tool
async def check_rbac_permissions(
    namespace: str,
    verb: str,
    resource: str,
) -> dict[str, Any]:
    """Check if the remediation ServiceAccount has a specific RBAC permission.

    Args:
        namespace: Kubernetes namespace to check in.
        verb: The API verb (get, list, create, update, patch, delete).
        resource: The resource type (pods, deployments, nodes, etc.).
    """
    client = _get_rw_mcp_client()
    try:
        result = await client.query(
            "get_resources",
            {
                "kind": "SelfSubjectAccessReview",
                "namespace": namespace,
                "verb": verb,
                "resource": resource,
            },
        )
        return {
            "type": "rbac_check",
            "namespace": namespace,
            "verb": verb,
            "resource": resource,
            "result": result,
        }
    except Exception as exc:
        return {
            "type": "rbac_check",
            "namespace": namespace,
            "verb": verb,
            "resource": resource,
            "error": str(exc),
            "allowed": False,
            "probe_failed": True,
        }


@tool
async def check_resource_quota(
    namespace: str,
) -> dict[str, Any]:
    """Check resource quota availability in a namespace.

    Args:
        namespace: Kubernetes namespace to check quotas for.
    """
    client = _get_rw_mcp_client()
    try:
        result = await client.query(
            "get_resources",
            {"kind": "ResourceQuota", "namespace": namespace},
        )
        return {
            "type": "quota_check",
            "namespace": namespace,
            "result": result,
        }
    except Exception as exc:
        return {
            "type": "quota_check",
            "namespace": namespace,
            "error": str(exc),
        }


def get_planner_tools() -> list:
    """Return the list of tools available to the planner agent."""
    return [query_cluster_state, check_rbac_permissions, check_resource_quota]


def build_planner_agent(llm=None, tools: list | None = None):
    """Build the planner as a LangGraph create_react_agent subgraph.

    Args:
        llm: Override LLM instance (for testing). Uses default if None.
        tools: Override tool list (for testing). Uses default tools if None.

    Returns:
        A compiled LangGraph agent ready for invocation.
    """
    if llm is None:
        llm = get_chat_model(AgentRole.PLANNER)
    if tools is None:
        tools = get_planner_tools()

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=PLANNER_SYSTEM_PROMPT,
        response_format=(PLANNER_STRUCTURED_PROMPT, RemediationPlan),
    )


def build_planning_prompt(artifact: ImmutableDiagnosisArtifact) -> str:
    """Build the planner prompt from the immutable diagnosis artifact.

    Args:
        artifact: The sealed diagnosis artifact (read-only).

    Returns:
        A formatted prompt string containing diagnosis context.
    """
    evidence_summary = []
    for ev in artifact.evidence:
        evidence_summary.append(f"- [{ev.source.value}] {ev.query}: {ev.result[:200]}")

    gap_summary = []
    for gap in artifact.evidence_gaps:
        gap_summary.append(f"- {gap.query}: {gap.reason}")

    return f"""Incident ID: {artifact.incident_id}
Diagnosis ID: {artifact.id}

ROOT CAUSE:
- Component: {artifact.root_cause_component}
- Failure Mode: {artifact.failure_mode}
- Root Cause Code: {artifact.root_cause_code}
- Confidence: {artifact.confidence}

CAUSAL CHAIN:
{chr(10).join(f"  {i+1}. {step}" for i, step in enumerate(artifact.causal_chain))}

AFFECTED RESOURCES:
{chr(10).join(f"  - {r}" for r in artifact.affected_resources)}

EVIDENCE GATHERED:
{chr(10).join(evidence_summary) if evidence_summary else "  (none)"}

EVIDENCE GAPS (acknowledge but do NOT attempt to fill):
{chr(10).join(gap_summary) if gap_summary else "  (none)"}

AGENT SUMMARY:
{artifact.agent_summary}

Design a concrete remediation plan to address the root cause. Query the cluster
for current state before finalizing steps. Include rollback procedures and
enumerate all preconditions."""


async def run_planner(artifact: ImmutableDiagnosisArtifact) -> RemediationPlan:
    """Run the planner agent on the given diagnosis artifact.

    Args:
        artifact: The sealed, immutable diagnosis artifact from Epic 2.

    Returns:
        A structured RemediationPlan.
    """
    logger.info(
        "Planner starting remediation planning",
        extra={
            "incident_id": str(artifact.incident_id),
            "root_cause_code": artifact.root_cause_code,
        },
    )

    agent = build_planner_agent()
    prompt = build_planning_prompt(artifact)

    result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})

    plan: RemediationPlan = result["structured_response"]
    plan = plan.model_copy(update={
        "incident_id": artifact.incident_id,
        "diagnosis_id": artifact.id,
    })

    logger.info(
        "Planner completed remediation plan",
        extra={
            "incident_id": str(artifact.incident_id),
            "step_count": len(plan.steps),
            "blast_radius": plan.blast_radius.value,
            "risk_level": plan.estimated_risk.value,
        },
    )

    return plan


async def run_planner_rebuttal(
    plan: RemediationPlan,
    challenge: RemediationSkepticChallenge,
    artifact: ImmutableDiagnosisArtifact,
) -> RemediationPlan:
    """Run the planner in rebuttal mode to address skeptic challenges.

    The planner can query the cluster again to verify/refine the plan.
    Returns a potentially revised RemediationPlan.

    Args:
        plan: The current RemediationPlan being challenged.
        challenge: The RemediationSkepticChallenge to address.
        artifact: The sealed diagnosis artifact (read-only context).

    Returns:
        A potentially revised RemediationPlan.
    """
    incident_id = str(plan.incident_id)
    logger.info(
        "Planner starting rebuttal",
        extra={"incident_id": incident_id},
    )

    agent = build_planner_agent()

    prompt = PLANNER_REBUTTAL_PROMPT_TEMPLATE.format(
        plan_json=plan.model_dump_json(indent=2),
        step_correctness_issues=json.dumps(challenge.step_correctness_issues),
        blast_radius_assessment=challenge.blast_radius_assessment,
        rollback_feasibility_issues=json.dumps(
            challenge.rollback_feasibility_issues
        ),
        precondition_gaps=json.dumps(challenge.precondition_gaps),
        risk_assessment_critique=challenge.risk_assessment_critique,
        overall_verdict=challenge.overall_verdict,
        artifact_json=json.dumps(
            artifact.model_dump(mode="json"), indent=2, default=str
        ),
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
    revised_plan: RemediationPlan = result["structured_response"]
    revised_plan = revised_plan.model_copy(
        update={
            "incident_id": plan.incident_id,
            "diagnosis_id": plan.diagnosis_id,
        }
    )

    logger.info(
        "Planner rebuttal completed",
        extra={
            "incident_id": incident_id,
            "step_count": len(revised_plan.steps),
            "blast_radius": revised_plan.blast_radius.value,
            "risk_level": revised_plan.estimated_risk.value,
        },
    )

    return revised_plan
