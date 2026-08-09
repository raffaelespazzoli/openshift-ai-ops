"""Unit tests for the orchestrator agent (AC: #1, #5, #7, #8).

Tests orchestrator produces valid DiagnosisObject with mocked LLM,
handles coverage gaps, and preserves rejected hypotheses.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.completeness_gate import evaluate_completeness
from src.agents.orchestrator import (
    MAX_COMPLETENESS_RETRIES,
    _build_fallback_diagnosis,
    build_orchestrator_agent,
    run_orchestrator,
)
from src.models.diagnosis import DiagnosisObject, EvidenceSource

from .conftest import make_valid_diagnosis


class TestBuildOrchestratorAgent:
    """Tests for building the orchestrator agent subgraph."""

    @pytest.mark.unit
    def test_build_orchestrator_agent_returns_compiled_graph(self):
        with patch("src.agents.orchestrator.get_chat_model") as mock_llm:
            mock_llm.return_value = MagicMock()
            agent = build_orchestrator_agent(tools=[])
        assert agent is not None

    @pytest.mark.unit
    def test_build_orchestrator_agent_uses_orchestrator_role(self):
        with patch("src.agents.orchestrator.get_chat_model") as mock_llm:
            mock_llm.return_value = MagicMock()
            build_orchestrator_agent(tools=[])
            mock_llm.assert_called_once()
            from src.config.llm_settings import AgentRole
            assert mock_llm.call_args[0][0] == AgentRole.ORCHESTRATOR


class TestRunOrchestrator:
    """Tests for the run_orchestrator function."""

    @pytest.mark.unit
    async def test_orchestrator_produces_valid_diagnosis(self):
        """Orchestrator returns a valid DiagnosisObject with mocked agent."""
        diagnosis = make_valid_diagnosis()

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": diagnosis,
            "messages": [],
        }

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            state = _make_state()
            result = await run_orchestrator(state)

        assert result["diagnosis"] is not None
        validated = DiagnosisObject.model_validate(result["diagnosis"])
        assert validated.root_cause_code == "workload/crash-loop-backoff"
        assert 0.0 <= validated.confidence <= 1.0

    @pytest.mark.unit
    async def test_orchestrator_sets_stage_to_diagnosed(self):
        """Result state includes stage=diagnosed."""
        diagnosis = make_valid_diagnosis()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": diagnosis,
            "messages": [],
        }

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            result = await run_orchestrator(_make_state())

        assert result["stage"] == "diagnosed"

    @pytest.mark.unit
    async def test_orchestrator_flags_coverage_gaps_mvp(self):
        """MVP always flags coverage gaps since no specialists exist."""
        diagnosis = make_valid_diagnosis()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": diagnosis,
            "messages": [],
        }

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            state = _make_state(alerts=[
                {"labels": {"alertname": "KubePodCrashLooping", "severity": "critical"}},
            ])
            result = await run_orchestrator(state)

        assert len(result["coverage_gaps"]) > 0
        assert any("no specialist" in gap for gap in result["coverage_gaps"])

    @pytest.mark.unit
    async def test_orchestrator_preserves_rejected_hypotheses_on_retry(self):
        """When completeness fails, rejected hypotheses are preserved."""
        incomplete_diag = make_valid_diagnosis(confidence=0.3)
        complete_diag = make_valid_diagnosis(confidence=0.9)

        call_count = {"n": 0}

        async def mock_invoke(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"structured_response": incomplete_diag, "messages": []}
            return {"structured_response": complete_diag, "messages": []}

        mock_agent = AsyncMock()
        mock_agent.ainvoke = mock_invoke

        alerts = [
            {"labels": {"alertname": "KubePodCrashLooping"}, "fingerprint": "abc123"},
            {"labels": {"alertname": "NodeMemoryPressure"}, "fingerprint": "def456"},
        ]

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            state = _make_state(alerts=alerts)
            result = await run_orchestrator(state)

        assert result["completeness_attempts"] >= 1

    @pytest.mark.unit
    async def test_orchestrator_fallback_on_agent_failure(self):
        """Agent failure produces a valid fallback diagnosis."""
        mock_agent = AsyncMock()
        mock_agent.ainvoke.side_effect = RuntimeError("LLM endpoint unreachable")

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            result = await run_orchestrator(_make_state())

        assert result["diagnosis"] is not None
        validated = DiagnosisObject.model_validate(result["diagnosis"])
        assert validated.root_cause_code == "unknown/unclassified"
        assert validated.confidence == 0.0

    @pytest.mark.unit
    async def test_orchestrator_single_attempt_increments_counter(self):
        """Orchestrator runs once and increments completeness_attempts by 1.

        Max retries are enforced at the graph level (completeness_gate_node
        + _completeness_routing), not inside run_orchestrator.
        """
        incomplete_diag = make_valid_diagnosis(confidence=0.2)

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": incomplete_diag,
            "messages": [],
        }

        alerts = [
            {"labels": {"alertname": "UnknownAlert999"}, "fingerprint": "xyz999"},
        ]

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            state = _make_state(alerts=alerts)
            result = await run_orchestrator(state)

        assert result["completeness_attempts"] == 1
        assert result["diagnosis"] is not None

    @pytest.mark.unit
    async def test_orchestrator_includes_unaddressed_on_retry(self):
        """On retry (completeness_attempts > 0), unaddressed alerts are in prompt."""
        diagnosis = make_valid_diagnosis()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": diagnosis,
            "messages": [],
        }

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            state = _make_state(alerts=[
                {"labels": {"alertname": "TestAlert"}, "fingerprint": "fp1"},
            ])
            state["completeness_attempts"] = 1
            state["unaddressed_alerts"] = ["fp1"]
            result = await run_orchestrator(state)

        call_args = mock_agent.ainvoke.call_args
        prompt_text = call_args[0][0]["messages"][0].content
        assert "COMPLETENESS CHECK FAILED" in prompt_text
        assert "fp1" in prompt_text


class TestCoverageGapsOnDiagnosis:
    """Tests for Finding R3-3: coverage_gaps persisted on DiagnosisObject."""

    @pytest.mark.unit
    async def test_coverage_gaps_in_diagnosis_object(self):
        """Coverage gaps are set on the DiagnosisObject itself."""
        diagnosis = make_valid_diagnosis()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": diagnosis,
            "messages": [],
        }

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent):
            state = _make_state(alerts=[
                {"labels": {"alertname": "KubePodCrashLooping"}, "fingerprint": "fp1"},
            ])
            with patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
                result = await run_orchestrator(state)

        validated = DiagnosisObject.model_validate(result["diagnosis"])
        assert len(validated.coverage_gaps) > 0
        assert any("no specialist" in gap for gap in validated.coverage_gaps)

    @pytest.mark.unit
    async def test_alternative_hypotheses_on_diagnosis(self):
        """Alternative hypotheses are persisted on DiagnosisObject on retry."""
        first_diag = make_valid_diagnosis(confidence=0.3)
        second_diag = make_valid_diagnosis(confidence=0.9)

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": second_diag,
            "messages": [],
        }

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent):
            state = _make_state(alerts=[
                {"labels": {"alertname": "TestAlert"}, "fingerprint": "fp1"},
            ])
            state["completeness_attempts"] = 1
            state["diagnosis"] = first_diag.model_dump(mode="json")
            state["unaddressed_alerts"] = ["fp1"]
            with patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
                result = await run_orchestrator(state)

        validated = DiagnosisObject.model_validate(result["diagnosis"])
        assert len(validated.alternative_hypotheses) > 0


class TestPromptIncludesFingerprints:
    """Tests for Finding R4-1: prompts include fingerprints and resource labels."""

    @pytest.mark.unit
    async def test_prompt_includes_alert_fingerprint(self):
        """Prompt text must contain the alert fingerprint for completeness gate."""
        diagnosis = make_valid_diagnosis()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": diagnosis,
            "messages": [],
        }

        alerts = [
            {
                "fingerprint": "fp-abc-123",
                "labels": {"alertname": "KubePodCrashLooping", "namespace": "prod"},
            },
        ]

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            await run_orchestrator(_make_state(alerts=alerts))

        call_args = mock_agent.ainvoke.call_args
        prompt_text = call_args[0][0]["messages"][0].content
        assert "fp-abc-123" in prompt_text

    @pytest.mark.unit
    async def test_prompt_includes_resource_labels(self):
        """Prompt text must include pod, node, container, and other resource labels."""
        diagnosis = make_valid_diagnosis()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": diagnosis,
            "messages": [],
        }

        alerts = [
            {
                "fingerprint": "fp-x",
                "labels": {
                    "alertname": "KubePodCrashLooping",
                    "namespace": "monitoring",
                    "pod": "grafana-abc-xyz",
                    "node": "worker-3.example.com",
                    "container": "grafana",
                    "job": "kubelet",
                    "instance": "10.0.1.5:10250",
                    "service": "grafana-svc",
                },
            },
        ]

        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            await run_orchestrator(_make_state(alerts=alerts))

        call_args = mock_agent.ainvoke.call_args
        prompt_text = call_args[0][0]["messages"][0].content
        assert "grafana-abc-xyz" in prompt_text
        assert "worker-3.example.com" in prompt_text
        assert "container=grafana" in prompt_text
        assert "monitoring" in prompt_text

    @pytest.mark.unit
    async def test_alternatives_accumulate_across_passes(self):
        """Model-produced alternatives are preserved when retry adds more."""
        model_diag = make_valid_diagnosis(confidence=0.9)
        model_diag = model_diag.model_copy(update={
            "alternative_hypotheses": [
                {"root_cause_code": "network/dns-failure", "confidence": 0.3, "reason": "Model-produced"},
            ],
        })

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "structured_response": model_diag,
            "messages": [],
        }

        first_diag = make_valid_diagnosis(confidence=0.3)
        with patch("src.agents.orchestrator.build_orchestrator_agent", return_value=mock_agent), \
             patch("src.db.checkpointer.get_checkpointer", new_callable=AsyncMock, return_value=None):
            state = _make_state(alerts=[
                {"labels": {"alertname": "TestAlert"}, "fingerprint": "fp1"},
            ])
            state["completeness_attempts"] = 1
            state["diagnosis"] = first_diag.model_dump(mode="json")
            state["unaddressed_alerts"] = ["fp1"]
            result = await run_orchestrator(state)

        validated = DiagnosisObject.model_validate(result["diagnosis"])
        reasons = [h.get("reason", "") for h in validated.alternative_hypotheses]
        assert any("Model-produced" in r for r in reasons), "Model-produced alternative must survive"
        assert any("Incomplete" in r for r in reasons), "Retry-derived alternative must be added"


class TestFallbackDiagnosis:
    """Tests for the fallback diagnosis builder."""

    @pytest.mark.unit
    def test_fallback_produces_valid_diagnosis(self):
        incident_id = str(uuid.uuid4())
        diag = _build_fallback_diagnosis(incident_id, ["gap1"])
        assert diag.root_cause_code == "unknown/unclassified"
        assert diag.confidence == 0.0
        assert len(diag.evidence) >= 1
        assert len(diag.evidence_gaps) >= 1

    @pytest.mark.unit
    def test_fallback_includes_coverage_gaps_in_summary(self):
        incident_id = str(uuid.uuid4())
        diag = _build_fallback_diagnosis(incident_id, ["no specialist covers: X"])
        assert "no specialist covers: X" in diag.agent_summary


def _make_state(
    incident_id: str | None = None,
    alerts: list | None = None,
) -> dict:
    """Create a minimal DiagnosisState dict for testing."""
    return {
        "incident_id": incident_id or str(uuid.uuid4()),
        "root_cause_event": {"id": str(uuid.uuid4()), "priority_score": 100.0},
        "alerts": alerts or [],
        "mcp_evidence": [],
        "evidence_gaps": [],
        "diagnosis": None,
        "stage": "entered",
        "runbook_context": [],
        "completeness_attempts": 0,
        "coverage_gaps": [],
        "rejected_hypotheses": [],
        "unaddressed_alerts": [],
        "evidence_ledger": [],
    }
