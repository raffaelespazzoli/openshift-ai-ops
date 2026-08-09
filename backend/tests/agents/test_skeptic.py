"""Unit tests for the Skeptic agent — mocked LLM produces valid challenges."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.skeptic import (
    _build_fallback_challenge,
    _ensure_evidence_gaps_challenged,
    build_skeptic_agent,
    run_skeptic,
)
from src.models.diagnosis import (
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
)
from src.models.skeptic import SkepticChallenge


def _make_diagnosis(
    evidence_gaps: list[EvidenceGap] | None = None,
    root_cause_code: str = "workload/crash-loop-backoff",
) -> DiagnosisObject:
    component, mode = root_cause_code.split("/")
    return DiagnosisObject(
        incident_id=uuid.uuid4(),
        root_cause_component=component,
        failure_mode=mode,
        root_cause_code=root_cause_code,
        causal_chain=["Pod CrashLoopBackOff", "OOM killed repeatedly"],
        affected_resources=["pod/test-app-xyz"],
        evidence=[
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources({'kind': 'Pod'})",
                result='{"status": {"phase": "CrashLoopBackOff"}}',
                timestamp=datetime.now(timezone.utc),
            )
        ],
        evidence_gaps=evidence_gaps or [],
        confidence=0.85,
        agent_summary="Pod crash-loop due to OOM kills",
    )


def _make_challenge_dict(**overrides) -> dict:
    defaults = {
        "alternative_hypotheses": ["Could be network/dns-failure instead"],
        "evidence_gap_challenges": [],
        "logical_weaknesses": ["Causal chain has unexplained jump"],
        "overall_assessment": "Diagnosis needs stronger evidence",
    }
    defaults.update(overrides)
    return defaults


class TestBuildSkepticAgent:
    """build_skeptic_agent creates a compiled agent with no tools."""

    @pytest.mark.unit
    def test_build_skeptic_agent_returns_compiled_graph(self):
        with patch("src.agents.skeptic.get_chat_model") as mock_gcm:
            from tests.agents.conftest import FakeChatModel
            mock_gcm.return_value = FakeChatModel(
                responses=[AIMessage(content="challenge")]
            )
            agent = build_skeptic_agent()
            assert agent is not None

    @pytest.mark.unit
    def test_build_skeptic_agent_uses_skeptic_role(self):
        from src.config.llm_settings import AgentRole

        with patch("src.agents.skeptic.get_chat_model") as mock_gcm:
            from tests.agents.conftest import FakeChatModel
            mock_gcm.return_value = FakeChatModel(
                responses=[AIMessage(content="challenge")]
            )
            build_skeptic_agent()
            mock_gcm.assert_called_once_with(AgentRole.SKEPTIC)


class TestRunSkeptic:
    """run_skeptic produces a valid SkepticChallenge with mocked LLM."""

    @pytest.mark.unit
    async def test_run_skeptic_produces_challenge(self):
        diagnosis = _make_diagnosis()
        state = {"incident_id": str(uuid.uuid4())}

        mock_challenge = SkepticChallenge(**_make_challenge_dict())
        mock_result = {
            "structured_response": mock_challenge,
            "messages": [AIMessage(content="challenged")],
        }

        with patch("src.agents.skeptic.build_skeptic_agent") as mock_build:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_result
            mock_build.return_value = mock_agent

            challenge = await run_skeptic(diagnosis, state)

        assert isinstance(challenge, SkepticChallenge)
        assert len(challenge.alternative_hypotheses) >= 1
        assert len(challenge.logical_weaknesses) >= 1

    @pytest.mark.unit
    async def test_run_skeptic_challenges_evidence_gaps(self):
        """When evidence_gaps is non-empty, fallback produces gap-specific challenges."""
        gaps = [
            EvidenceGap(query="get_logs(pod-x)", reason="MCP timeout", timeout_seconds=30.0),
            EvidenceGap(query="get_events(ns-y)", reason="Connection refused"),
        ]
        diagnosis = _make_diagnosis(evidence_gaps=gaps)
        state = {"incident_id": str(uuid.uuid4())}

        mock_result = {
            "structured_response": None,
            "messages": [AIMessage(content="fallback")],
        }

        with patch("src.agents.skeptic.build_skeptic_agent") as mock_build:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_result
            mock_build.return_value = mock_agent

            challenge = await run_skeptic(diagnosis, state)

        assert len(challenge.evidence_gap_challenges) == 2
        assert "get_logs" in challenge.evidence_gap_challenges[0]
        assert "get_events" in challenge.evidence_gap_challenges[1]

    @pytest.mark.unit
    async def test_run_skeptic_handles_empty_response(self):
        """When structured_response is None, a fallback challenge is produced."""
        diagnosis = _make_diagnosis()
        state = {"incident_id": str(uuid.uuid4())}

        with patch("src.agents.skeptic.build_skeptic_agent") as mock_build:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = {
                "structured_response": None,
                "messages": [],
            }
            mock_build.return_value = mock_agent

            challenge = await run_skeptic(diagnosis, state)

        assert isinstance(challenge, SkepticChallenge)
        assert "fallback" in challenge.logical_weaknesses[0].lower()

    @pytest.mark.unit
    async def test_run_skeptic_handles_ainvoke_exception(self):
        """When ainvoke() raises, the fallback path is used instead of propagating."""
        diagnosis = _make_diagnosis()
        state = {"incident_id": str(uuid.uuid4())}

        with patch("src.agents.skeptic.build_skeptic_agent") as mock_build:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.side_effect = RuntimeError("LLM service unavailable")
            mock_build.return_value = mock_agent

            challenge = await run_skeptic(diagnosis, state)

        assert isinstance(challenge, SkepticChallenge)
        assert "fallback" in challenge.logical_weaknesses[0].lower()

    @pytest.mark.unit
    async def test_run_skeptic_enforces_evidence_gap_challenges(self):
        """Successful LLM response missing evidence gap challenges gets augmented (AC #8)."""
        gaps = [
            EvidenceGap(query="get_logs(pod-x)", reason="MCP timeout", timeout_seconds=30.0),
        ]
        diagnosis = _make_diagnosis(evidence_gaps=gaps)
        state = {"incident_id": str(uuid.uuid4())}

        challenge_without_gaps = SkepticChallenge(
            alternative_hypotheses=["Could be network issue"],
            evidence_gap_challenges=[],
            logical_weaknesses=["Gap in causal chain"],
            overall_assessment="Missing evidence",
        )
        mock_result = {
            "structured_response": challenge_without_gaps,
            "messages": [AIMessage(content="challenged")],
        }

        with patch("src.agents.skeptic.build_skeptic_agent") as mock_build:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_result
            mock_build.return_value = mock_agent

            challenge = await run_skeptic(diagnosis, state)

        assert len(challenge.evidence_gap_challenges) >= 1
        assert any("get_logs" in c for c in challenge.evidence_gap_challenges)


class TestEnsureEvidenceGapsChallenged:
    """_ensure_evidence_gaps_challenged augments challenges with missing gaps."""

    @pytest.mark.unit
    def test_no_gaps_returns_unchanged(self):
        diagnosis = _make_diagnosis(evidence_gaps=[])
        challenge = SkepticChallenge(
            alternative_hypotheses=["alt"],
            evidence_gap_challenges=[],
            logical_weaknesses=["weakness"],
            overall_assessment="ok",
        )
        result = _ensure_evidence_gaps_challenged(diagnosis, challenge)
        assert result.evidence_gap_challenges == []

    @pytest.mark.unit
    def test_missing_gap_is_added(self):
        gaps = [EvidenceGap(query="get_logs", reason="timeout")]
        diagnosis = _make_diagnosis(evidence_gaps=gaps)
        challenge = SkepticChallenge(
            alternative_hypotheses=["alt"],
            evidence_gap_challenges=[],
            logical_weaknesses=["weakness"],
            overall_assessment="ok",
        )
        result = _ensure_evidence_gaps_challenged(diagnosis, challenge)
        assert len(result.evidence_gap_challenges) == 1
        assert "get_logs" in result.evidence_gap_challenges[0]

    @pytest.mark.unit
    def test_already_covered_gap_not_duplicated(self):
        gaps = [EvidenceGap(query="get_logs", reason="timeout")]
        diagnosis = _make_diagnosis(evidence_gaps=gaps)
        challenge = SkepticChallenge(
            alternative_hypotheses=["alt"],
            evidence_gap_challenges=["The get_logs query had a timeout — could change conclusion"],
            logical_weaknesses=["weakness"],
            overall_assessment="ok",
        )
        result = _ensure_evidence_gaps_challenged(diagnosis, challenge)
        assert len(result.evidence_gap_challenges) == 1

    @pytest.mark.unit
    def test_same_query_different_reason_not_conflated(self):
        """Gaps sharing query text but with different reasons must each be challenged (AC #8)."""
        gaps = [
            EvidenceGap(query="get_logs", reason="MCP timeout"),
            EvidenceGap(query="get_logs", reason="Connection refused"),
        ]
        diagnosis = _make_diagnosis(evidence_gaps=gaps)
        challenge = SkepticChallenge(
            alternative_hypotheses=["alt"],
            evidence_gap_challenges=[
                "Evidence gap not addressed: get_logs — MCP timeout",
            ],
            logical_weaknesses=["weakness"],
            overall_assessment="ok",
        )
        result = _ensure_evidence_gaps_challenged(diagnosis, challenge)
        assert len(result.evidence_gap_challenges) == 2
        reasons_covered = " ".join(result.evidence_gap_challenges)
        assert "Connection refused" in reasons_covered

    @pytest.mark.unit
    def test_same_reason_different_query_not_conflated(self):
        """Gaps sharing reason text but with different queries must each be challenged."""
        gaps = [
            EvidenceGap(query="get_logs(pod-a)", reason="timeout"),
            EvidenceGap(query="get_events(ns-b)", reason="timeout"),
        ]
        diagnosis = _make_diagnosis(evidence_gaps=gaps)
        challenge = SkepticChallenge(
            alternative_hypotheses=["alt"],
            evidence_gap_challenges=[
                "Evidence gap not addressed: get_logs(pod-a) — timeout",
            ],
            logical_weaknesses=["weakness"],
            overall_assessment="ok",
        )
        result = _ensure_evidence_gaps_challenged(diagnosis, challenge)
        assert len(result.evidence_gap_challenges) == 2
        queries_covered = " ".join(result.evidence_gap_challenges)
        assert "get_events(ns-b)" in queries_covered


class TestFallbackChallenge:
    """_build_fallback_challenge always produces a valid challenge."""

    @pytest.mark.unit
    def test_fallback_with_no_evidence_gaps(self):
        diagnosis = _make_diagnosis()
        challenge = _build_fallback_challenge(diagnosis)
        assert len(challenge.alternative_hypotheses) >= 1
        assert len(challenge.logical_weaknesses) >= 1
        assert challenge.evidence_gap_challenges == []

    @pytest.mark.unit
    def test_fallback_with_evidence_gaps(self):
        gaps = [
            EvidenceGap(query="get_logs", reason="timeout", timeout_seconds=10.0),
        ]
        diagnosis = _make_diagnosis(evidence_gaps=gaps)
        challenge = _build_fallback_challenge(diagnosis)
        assert len(challenge.evidence_gap_challenges) == 1
        assert "get_logs" in challenge.evidence_gap_challenges[0]
