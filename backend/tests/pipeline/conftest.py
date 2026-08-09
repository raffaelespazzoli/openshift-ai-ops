"""Mock MCP server fixture and mock LLM fixtures for pipeline tests.

The mock MCP server provides canned responses for pipeline tests.
Integration tests in test_mcp_integration.py use the MCP SDK's
MCPServer + in-memory transport for full protocol-level testing
(ClientSession.initialize(), call_tool, response parsing).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.models.diagnosis import (
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
)


CANNED_RESPONSES: dict[str, Any] = {
    "get_resources": {
        "items": [
            {"kind": "Pod", "metadata": {"name": "test-pod-1", "namespace": "default"}},
            {"kind": "Pod", "metadata": {"name": "test-pod-2", "namespace": "default"}},
        ]
    },
    "get_resource": {
        "kind": "Pod",
        "metadata": {"name": "test-pod-1", "namespace": "default"},
        "status": {"phase": "Running"},
    },
    "describe_resource": {
        "kind": "Pod",
        "metadata": {"name": "test-pod-1"},
        "events": [
            {"type": "Warning", "reason": "OOMKilled", "message": "Container killed due to OOM"},
        ],
    },
    "get_logs": "2026-08-09T00:00:00Z ERROR: OOMKilled\n2026-08-09T00:00:01Z Container restart",
    "get_events": {
        "items": [
            {"type": "Warning", "reason": "MemoryPressure", "message": "Node under memory pressure"},
        ]
    },
}


@pytest.fixture
def mock_mcp_client():
    """Fixture that patches _call_tool for unit tests that don't need full transport."""
    async def mock_call_tool(self, tool_name: str, arguments: dict) -> str:
        if tool_name in CANNED_RESPONSES:
            result = CANNED_RESPONSES[tool_name]
            if isinstance(result, str):
                return result
            return json.dumps(result)
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    with patch(
        "src.pipeline.mcp_client.ReadOnlyMCPClient._call_tool",
        mock_call_tool,
    ):
        yield


@pytest.fixture
def mock_mcp_client_timeout():
    """Fixture that patches _call_tool to simulate timeouts."""
    async def mock_call_tool_slow(self, tool_name: str, arguments: dict) -> str:
        await asyncio.sleep(100)
        return "{}"

    with patch(
        "src.pipeline.mcp_client.ReadOnlyMCPClient._call_tool",
        mock_call_tool_slow,
    ):
        yield


@pytest.fixture
def mock_mcp_client_delayed():
    """Fixture returning a factory for delayed MCP responses (configurable delay)."""
    def _factory(delay_seconds: float):
        async def mock_call_tool_delay(self, tool_name: str, arguments: dict) -> str:
            await asyncio.sleep(delay_seconds)
            if tool_name in CANNED_RESPONSES:
                result = CANNED_RESPONSES[tool_name]
                return json.dumps(result) if not isinstance(result, str) else result
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        return patch(
            "src.pipeline.mcp_client.ReadOnlyMCPClient._call_tool",
            mock_call_tool_delay,
        )

    return _factory


@pytest.fixture
def mock_mcp_client_error():
    """Fixture that patches _call_tool to raise connection errors."""
    async def mock_call_tool_error(self, tool_name: str, arguments: dict) -> str:
        raise ConnectionError("MCP server is unreachable")

    with patch(
        "src.pipeline.mcp_client.ReadOnlyMCPClient._call_tool",
        mock_call_tool_error,
    ):
        yield


@pytest.fixture
def mock_orchestrator_agent():
    """Mock the orchestrator agent to return a valid diagnosis without real LLM calls."""

    async def mock_run_orchestrator(state, config=None):
        incident_id = state.get("incident_id", str(uuid.uuid4()))
        alerts = state.get("alerts", [])
        alert_names = [
            a.get("labels", a).get("alertname", "KubePodCrashLooping")
            for a in alerts
        ] if alerts else ["KubePodCrashLooping"]
        alert_summary = ", ".join(alert_names)
        diagnosis = DiagnosisObject(
            incident_id=uuid.UUID(incident_id),
            root_cause_component="workload",
            failure_mode="crash-loop-backoff",
            root_cause_code="workload/crash-loop-backoff",
            causal_chain=["Pod CrashLoopBackOff due to OOM"],
            affected_resources=["pod/test-app-xyz-123"],
            evidence=[
                EvidenceArtifact(
                    source=EvidenceSource.MCP_CLUSTER,
                    query="get_resources({'kind': 'Pod'})",
                    result='{"status": {"phase": "CrashLoopBackOff"}}',
                    timestamp=datetime.now(timezone.utc),
                ),
            ],
            confidence=0.85,
            agent_summary=f"Pod crash-loop due to OOM kills — alerts: {alert_summary}",
        )
        completeness_attempts = state.get("completeness_attempts", 0)
        return {
            "diagnosis": diagnosis.model_dump(mode="json"),
            "runbook_context": [],
            "completeness_attempts": completeness_attempts + 1,
            "coverage_gaps": [f"no specialist covers: {n} (MVP generalist mode)" for n in alert_names],
            "rejected_hypotheses": [],
            "evidence_ledger": [],
            "stage": "diagnosed",
        }

    with patch("src.agents.orchestrator.run_orchestrator", side_effect=mock_run_orchestrator):
        yield
