"""Mock LLM and tool fixtures for agent tests.

Provides FakeChatModel that returns deterministic responses for orchestrator
testing without real LLM calls. Reusable in Stories 2.3, 2.4.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.models.diagnosis import (
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
)


class FakeChatModel(BaseChatModel):
    """Deterministic mock LLM for agent testing.

    Supports configurable response sequences for multi-turn tool-calling.
    """

    responses: list[BaseMessage]
    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _generate(self, messages, stop=None, **kwargs):
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return ChatResult(generations=[ChatGeneration(message=response)])

    async def _agenerate(self, messages, stop=None, **kwargs):
        return self._generate(messages, stop=stop, **kwargs)


def make_valid_diagnosis(
    incident_id: str | None = None,
    root_cause_code: str = "workload/crash-loop-backoff",
    confidence: float = 0.85,
) -> DiagnosisObject:
    """Create a valid DiagnosisObject for testing."""
    iid = incident_id or str(uuid.uuid4())
    component, mode = root_cause_code.split("/")
    return DiagnosisObject(
        incident_id=uuid.UUID(iid),
        root_cause_component=component,
        failure_mode=mode,
        root_cause_code=root_cause_code,
        causal_chain=[
            "Pod entered CrashLoopBackOff state",
            "Container OOM killed repeatedly",
            "Memory limit too low for workload",
        ],
        affected_resources=["pod/test-app-xyz-123"],
        evidence=[
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources({'kind': 'Pod', 'namespace': 'default'})",
                result='{"status": {"phase": "CrashLoopBackOff"}}',
                timestamp=datetime.now(timezone.utc),
            ),
        ],
        evidence_gaps=[],
        confidence=confidence,
        agent_summary="Pod crash-loop due to OOM kills — memory limit insufficient",
    )


@pytest.fixture
def fake_diagnosis():
    """Provide a valid DiagnosisObject for tests."""
    return make_valid_diagnosis()


@pytest.fixture
def mock_orchestrator_agent():
    """Mock the orchestrator agent to return a valid diagnosis without LLM calls."""

    async def mock_run_orchestrator(state, config=None):
        incident_id = state.get("incident_id", str(uuid.uuid4()))
        diagnosis = make_valid_diagnosis(incident_id=incident_id)
        return {
            "diagnosis": diagnosis.model_dump(mode="json"),
            "runbook_context": [],
            "completeness_attempts": 1,
            "coverage_gaps": ["no specialist covers: KubePodCrashLooping (MVP generalist mode)"],
            "rejected_hypotheses": [],
            "evidence_ledger": [],
            "stage": "diagnosed",
        }

    with patch("src.agents.orchestrator.run_orchestrator", side_effect=mock_run_orchestrator):
        yield


CANNED_RESPONSES: dict[str, Any] = {
    "get_resources": {
        "items": [
            {"kind": "Pod", "metadata": {"name": "test-pod-1", "namespace": "default"}},
        ]
    },
    "get_resource": {
        "kind": "Pod",
        "metadata": {"name": "test-pod-1", "namespace": "default"},
        "status": {"phase": "Running"},
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
def mock_llm_client():
    """Patch get_chat_model to return a FakeChatModel."""
    fake = FakeChatModel(responses=[
        AIMessage(content="I'll diagnose this incident."),
    ])
    with patch("src.agents.llm_client.get_chat_model", return_value=fake):
        yield fake


@pytest.fixture
def mock_tools():
    """Provide mock tool functions that return canned responses."""
    async def mock_query_cluster(resource_type, namespace="default", name=""):
        return {
            "type": "evidence",
            "source": "mcp_cluster",
            "query": f"get_resources({{'kind': '{resource_type}', 'namespace': '{namespace}'}})",
            "result": '{"items": [{"kind": "Pod", "status": {"phase": "CrashLoopBackOff"}}]}',
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def mock_get_logs(namespace, pod_name, container="", tail_lines=100):
        return {
            "type": "evidence",
            "source": "mcp_cluster",
            "query": f"get_logs({{'namespace': '{namespace}', 'pod': '{pod_name}'}})",
            "result": "2026-08-09T00:00:00Z ERROR: OOMKilled\n2026-08-09T00:00:01Z Container restart",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def mock_search_runbooks(query, top_k=5):
        return {
            "type": "evidence",
            "source": "runbook",
            "query": query,
            "result": "## Troubleshooting CrashLoopBackOff\nCheck memory limits and OOM events.",
            "chunks": [{"source_file": "crashloop.md", "content": "Check memory limits"}],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "query_cluster_resources": mock_query_cluster,
        "get_resource_logs": mock_get_logs,
        "search_runbooks": mock_search_runbooks,
    }
