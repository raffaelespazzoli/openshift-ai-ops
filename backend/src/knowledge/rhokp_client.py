"""RHOKP MCP client — queries the Red Hat knowledge base via okp-mcp (AD-13 path 2, AD-15).

Connects to the okp-mcp server via Streamable HTTP transport.
Uses `search_portal` for multi-query search with reciprocal rank fusion
and `get_document` for full content retrieval with BM25-scored passages.
Timeouts produce EvidenceGap objects instead of raising exceptions.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from ..config.logging import Component, get_logger
from ..config.rhokp_settings import RHOKPSettings, get_rhokp_settings
from ..models.diagnosis import EvidenceGap

logger = get_logger(Component.KNOWLEDGE)


def _parse_mcp_response(raw: str) -> dict | list:
    """Parse a raw MCP text response into structured data.

    MCP tool responses come back as text blocks. The okp-mcp server returns
    JSON-formatted strings for both search_portal (list of hits) and
    get_document (single document dict). This function attempts JSON parsing
    and falls back to a structured wrapper if the response is not valid JSON.
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"raw_content": raw}


def _normalize_search_results(parsed: dict | list) -> list[dict]:
    """Normalize parsed MCP search response to a stable ``list[dict]`` contract.

    The okp-mcp server may return:
    - A plain ``list`` of hit dicts (direct JSON array).
    - A ``dict`` with a ``"results"`` key containing the list.
    - A ``dict`` with a ``"raw_content"`` fallback from non-JSON text.

    This function always returns ``list[dict]`` so callers have a single,
    predictable shape.
    """
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        if "results" in parsed and isinstance(parsed["results"], list):
            return parsed["results"]
        return [parsed]
    return []


class RHOKPClient:
    """Client for querying the RHOKP knowledge base via okp-mcp MCP server."""

    def __init__(self, settings: RHOKPSettings | None = None) -> None:
        self._settings = settings or get_rhokp_settings()

    async def search_portal(
        self, queries: list[str], top_k: int | None = None
    ) -> dict[str, Any]:
        """Multi-query search with reciprocal rank fusion.

        Args:
            queries: List of search queries to combine via rank fusion.
            top_k: Maximum results to return. Uses settings default if None.

        Returns:
            Dict with 'success' bool. On success includes 'data' as
            ``list[dict]`` — a stable typed contract regardless of how the
            okp-mcp server formats its JSON response.
            On timeout/failure includes 'evidence_gap' EvidenceGap object.
        """
        effective_top_k = top_k if top_k is not None else self._settings.top_k
        try:
            result = await asyncio.wait_for(
                self._call_tool("search_portal", {
                    "queries": queries,
                    "rows": effective_top_k,
                }),
                timeout=self._settings.timeout_seconds,
            )
            parsed = _parse_mcp_response(result)
            return {"success": True, "data": _normalize_search_results(parsed)}
        except asyncio.TimeoutError:
            logger.warning(
                "RHOKP search_portal timed out",
                extra={"queries": queries, "timeout": self._settings.timeout_seconds},
            )
            return {
                "success": False,
                "evidence_gap": EvidenceGap(
                    query=f"search_portal({queries})",
                    reason="RHOKP query timed out",
                    timeout_seconds=self._settings.timeout_seconds,
                ),
            }
        except Exception as exc:
            logger.warning(
                "RHOKP search_portal failed",
                extra={"queries": queries, "error": str(exc)},
            )
            return {
                "success": False,
                "evidence_gap": EvidenceGap(
                    query=f"search_portal({queries})",
                    reason=f"RHOKP query failed: {exc}",
                ),
            }

    async def get_document(self, doc_id: str) -> dict[str, Any]:
        """Full document retrieval with BM25-scored passage extraction.

        Args:
            doc_id: The document ID to retrieve.

        Returns:
            Dict with 'success' bool. On success includes 'data' as a
            structured dict (parsed from MCP JSON response).
            On timeout/failure includes 'evidence_gap' EvidenceGap object.
        """
        try:
            result = await asyncio.wait_for(
                self._call_tool("get_document", {"id": doc_id}),
                timeout=self._settings.timeout_seconds,
            )
            return {"success": True, "data": _parse_mcp_response(result)}
        except asyncio.TimeoutError:
            logger.warning(
                "RHOKP get_document timed out",
                extra={"doc_id": doc_id, "timeout": self._settings.timeout_seconds},
            )
            return {
                "success": False,
                "evidence_gap": EvidenceGap(
                    query=f"get_document({doc_id})",
                    reason="RHOKP document retrieval timed out",
                    timeout_seconds=self._settings.timeout_seconds,
                ),
            }
        except Exception as exc:
            logger.warning(
                "RHOKP get_document failed",
                extra={"doc_id": doc_id, "error": str(exc)},
            )
            return {
                "success": False,
                "evidence_gap": EvidenceGap(
                    query=f"get_document({doc_id})",
                    reason=f"RHOKP document retrieval failed: {exc}",
                ),
            }

    async def _call_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute the actual MCP tool call via Streamable HTTP transport."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(self._settings.url) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                contents = []
                for block in result.content:
                    if hasattr(block, "text"):
                        contents.append(block.text)
                    else:
                        contents.append(str(block))
                return "\n".join(contents)
