"""LangChain @tool functions for the orchestrator agent (AD-1, AD-2).

All tools operate via the read-only MCP client (AD-2 RBAC Airlock),
the runbook RAG retrieval (AD-13), RHOKP knowledge base (AD-13 path 2),
Learning Store (AD-20), or agentic skills (read-only only).
Zero write access to the cluster.
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
_rhokp_client: Any = None
_db_pool: Any = None


def _get_mcp_client() -> ReadOnlyMCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = ReadOnlyMCPClient()
    return _mcp_client


def set_mcp_client(client: ReadOnlyMCPClient | None) -> None:
    """Override the MCP client (for testing)."""
    global _mcp_client
    _mcp_client = client


def set_rhokp_client(client: Any) -> None:
    """Override the RHOKP client (for testing)."""
    global _rhokp_client
    _rhokp_client = client


def _get_rhokp_client():
    global _rhokp_client
    if _rhokp_client is None:
        from ..knowledge.rhokp_client import RHOKPClient
        _rhokp_client = RHOKPClient()
    return _rhokp_client


def set_db_pool(pool: Any) -> None:
    """Override the DB pool (for testing)."""
    global _db_pool
    _db_pool = pool


async def _get_db_pool():
    global _db_pool
    if _db_pool is None:
        from ..db import get_pool
        _db_pool = await get_pool()
    return _db_pool


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


@tool
async def search_rhokp(
    queries: list[str],
    top_k: int = 5,
) -> dict[str, Any]:
    """Search the Red Hat knowledge base (RHOKP) for platform-level guidance.

    Queries 600k+ Red Hat documentation, solutions, CVEs, errata, and articles
    via the okp-mcp MCP server.  Accepts multiple queries for reciprocal rank
    fusion — supply different phrasings or perspectives on the same issue for
    better recall.

    Args:
        queries: One or more search queries to combine via reciprocal rank fusion.
        top_k: Maximum number of results to return.
    """
    client = _get_rhokp_client()
    result = await client.search_portal(queries, top_k=top_k)

    display_query = "; ".join(queries)
    if not result["success"]:
        gap = result["evidence_gap"]
        return {
            "type": "evidence_gap",
            "source": EvidenceSource.RHOKP.value,
            "query": display_query,
            "reason": gap.reason,
        }

    return {
        "type": "evidence",
        "source": EvidenceSource.RHOKP.value,
        "query": display_query,
        "result": result["data"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@tool
async def get_rhokp_document(
    doc_id: str,
) -> dict[str, Any]:
    """Retrieve a full document from the Red Hat knowledge base (RHOKP).

    Gets complete document content with BM25-scored passage extraction.
    Use after search_rhokp identifies a relevant document.

    Args:
        doc_id: The document ID to retrieve.
    """
    client = _get_rhokp_client()
    result = await client.get_document(doc_id)

    if not result["success"]:
        gap = result["evidence_gap"]
        return {
            "type": "evidence_gap",
            "source": EvidenceSource.RHOKP.value,
            "query": f"get_document({doc_id})",
            "reason": gap.reason,
        }

    return {
        "type": "evidence",
        "source": EvidenceSource.RHOKP.value,
        "query": f"get_document({doc_id})",
        "result": result["data"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _get_cluster_ocp_version() -> str:
    """Query the live cluster OCP version via the read-only MCP path.

    Returns the major.minor version string (e.g. "4.15") or just the major
    version (e.g. "4") if the query fails, to be used for version relevance
    scoring in the Learning Store.
    """
    client = _get_mcp_client()
    result = await client.query(
        "get_resource",
        {"kind": "ClusterVersion", "name": "version", "namespace": ""},
    )

    if isinstance(result, EvidenceGap):
        logger.info(
            "Could not retrieve cluster OCP version, using fallback",
            extra={"reason": result.reason},
        )
        return "4"

    try:
        import json as _json
        payload = _json.loads(result.result)
        histories = payload.get("status", {}).get("history", [])
        if histories:
            return histories[0].get("version", "4")
        desired = payload.get("status", {}).get("desired", {}).get("version")
        if desired:
            return desired
    except (ValueError, TypeError, KeyError, AttributeError):
        pass

    return "4"


@tool
async def query_past_incidents(
    alert_context: str,
    top_k: int = 3,
) -> dict[str, Any]:
    """Query the Learning Store for past incidents similar to current symptoms.

    Searches case records by embedding similarity with temporal decay applied.
    Returns past root-cause codes, outcomes, and effective confidence scores.

    Args:
        alert_context: Description of the current alert/symptoms to match.
        top_k: Maximum number of past cases to return.
    """
    try:
        from ..config.knowledge_settings import get_knowledge_settings
        from ..knowledge.learning_store import query_learning_store

        current_ocp_version = await _get_cluster_ocp_version()
        similarity_threshold = get_knowledge_settings().learning_store_similarity_threshold

        pool = await _get_db_pool()
        async with pool.acquire() as conn:
            from pgvector.asyncpg import register_vector
            await register_vector(conn)
            cases = await query_learning_store(
                alert_context, conn, top_k=top_k,
                similarity_threshold=similarity_threshold,
                current_ocp_version=current_ocp_version,
            )

        if not cases:
            return {
                "type": "evidence",
                "source": EvidenceSource.LEARNING_STORE.value,
                "query": alert_context,
                "result": "No matching past incidents found in the Learning Store.",
                "cases": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        case_data = []
        for c in cases:
            age_days = (datetime.now(timezone.utc) - c.created_at).days
            case_data.append({
                "root_cause_code": c.root_cause_code,
                "outcome": c.outcome,
                "effective_confidence": round(c.effective_confidence, 3),
                "similarity": round(c.similarity, 3),
                "ocp_version": c.ocp_version,
                "days_ago": age_days,
            })

        combined = "\n".join(
            f"- {cd['root_cause_code']} (outcome={cd['outcome']}, "
            f"confidence={cd['effective_confidence']}, "
            f"similarity={cd['similarity']}, "
            f"{cd['days_ago']}d ago, OCP {cd['ocp_version']})"
            for cd in case_data
        )

        return {
            "type": "evidence",
            "source": EvidenceSource.LEARNING_STORE.value,
            "query": alert_context,
            "result": combined,
            "cases": case_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning(
            "Learning Store query failed",
            extra={"query": alert_context, "error": str(exc)},
        )
        return {
            "type": "evidence_gap",
            "source": EvidenceSource.LEARNING_STORE.value,
            "query": alert_context,
            "reason": f"Learning Store query failed: {exc}",
        }


def get_orchestrator_tools() -> list:
    """Return the list of tools available to the orchestrator agent."""
    return [
        query_cluster_resources,
        get_resource_logs,
        search_runbooks,
        search_rhokp,
        get_rhokp_document,
        query_past_incidents,
    ]
