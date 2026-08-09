"""LangChain @tool functions for the orchestrator agent (AD-1, AD-2).

All tools operate via the read-only MCP client (AD-2 RBAC Airlock)
or the runbook RAG retrieval (AD-13). Zero write access to the cluster.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from ..config.logging import Component, get_logger
from ..models.diagnosis import EvidenceArtifact, EvidenceGap, EvidenceSource
from ..pipeline.mcp_client import ReadOnlyMCPClient

logger = get_logger(Component.AGENT)

_mcp_client: ReadOnlyMCPClient | None = None


def _get_mcp_client() -> ReadOnlyMCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = ReadOnlyMCPClient()
    return _mcp_client


def set_mcp_client(client: ReadOnlyMCPClient | None) -> None:
    """Override the MCP client (for testing)."""
    global _mcp_client
    _mcp_client = client


@tool
async def query_cluster_resources(
    resource_type: str,
    namespace: str = "default",
    name: str = "",
) -> dict[str, Any]:
    """Query cluster resources via the read-only MCP Server.

    Retrieves Kubernetes resource state (pods, nodes, deployments, etc.)
    for diagnostic evidence gathering.

    Args:
        resource_type: Kind of resource to query (e.g. Pod, Node, Deployment).
        namespace: Kubernetes namespace to search in.
        name: Optional specific resource name.
    """
    client = _get_mcp_client()
    arguments = {"kind": resource_type, "namespace": namespace}
    if name:
        arguments["name"] = name

    tool_name = "get_resource" if name else "get_resources"
    result = await client.query(tool_name, arguments)

    if isinstance(result, EvidenceGap):
        return {
            "type": "evidence_gap",
            "query": result.query,
            "reason": result.reason,
            "source": EvidenceSource.MCP_CLUSTER.value,
        }

    return {
        "type": "evidence",
        "source": EvidenceSource.MCP_CLUSTER.value,
        "query": result.query,
        "result": result.result,
        "timestamp": result.timestamp.isoformat(),
    }


@tool
async def get_resource_logs(
    namespace: str,
    pod_name: str,
    container: str = "",
    tail_lines: int = 100,
) -> dict[str, Any]:
    """Get logs from a specific pod container.

    Retrieves recent log lines from a pod for diagnostic evidence.

    Args:
        namespace: Pod namespace.
        pod_name: Name of the pod.
        container: Container name (empty for default container).
        tail_lines: Number of recent log lines to retrieve.
    """
    client = _get_mcp_client()
    arguments = {
        "namespace": namespace,
        "pod": pod_name,
        "tail": tail_lines,
    }
    if container:
        arguments["container"] = container

    result = await client.query("get_logs", arguments)

    if isinstance(result, EvidenceGap):
        return {
            "type": "evidence_gap",
            "query": result.query,
            "reason": result.reason,
            "source": EvidenceSource.MCP_CLUSTER.value,
        }

    return {
        "type": "evidence",
        "source": EvidenceSource.MCP_CLUSTER.value,
        "query": result.query,
        "result": result.result,
        "timestamp": result.timestamp.isoformat(),
    }


@tool
async def search_runbooks(
    query: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """Search OpenShift runbooks for relevant operational guidance.

    Performs semantic similarity search against embedded runbook chunks
    to find relevant troubleshooting procedures and known issues.

    Args:
        query: Search query describing the symptoms or alert context.
        top_k: Maximum number of runbook chunks to return.
    """
    try:
        from ..db import get_pool
        from ..knowledge.runbook_rag import retrieve_runbook_context

        pool = await get_pool()
        async with pool.acquire() as conn:
            from pgvector.asyncpg import register_vector
            await register_vector(conn)
            chunks = await retrieve_runbook_context(query, conn, top_k=top_k)

        if not chunks:
            return {
                "type": "evidence",
                "source": EvidenceSource.RUNBOOK.value,
                "query": query,
                "result": "No relevant runbook content found.",
                "chunks": [],
            }

        chunk_data = []
        for c in chunks:
            chunk_data.append({
                "source_file": c.source_file,
                "heading_hierarchy": c.heading_hierarchy,
                "content": c.content,
            })

        combined_content = "\n\n---\n\n".join(
            f"[{c.source_file}] {' > '.join(c.heading_hierarchy)}\n{c.content}"
            for c in chunks
        )

        return {
            "type": "evidence",
            "source": EvidenceSource.RUNBOOK.value,
            "query": query,
            "result": combined_content,
            "chunks": chunk_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning(
            "Runbook search failed",
            extra={"query": query, "error": str(exc)},
        )
        return {
            "type": "evidence_gap",
            "source": EvidenceSource.RUNBOOK.value,
            "query": query,
            "reason": f"Runbook search failed: {exc}",
        }


def get_orchestrator_tools() -> list:
    """Return the list of tools available to the orchestrator agent."""
    return [query_cluster_resources, get_resource_logs, search_runbooks]
