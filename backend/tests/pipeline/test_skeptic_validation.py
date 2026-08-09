"""Unit tests for the skeptic validation loop and seal_diagnosis."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models.diagnosis import (
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)
from src.models.skeptic import (
    SkepticChallenge,
    SkepticRebuttal,
    SkepticResponse,
    SkepticVerdict,
)
from src.pipeline.skeptic_validation import (
    MAX_SKEPTIC_ROUNDS,
    run_skeptic_validation,
    seal_diagnosis,
)


def _make_diagnosis(
    root_cause_code: str = "workload/crash-loop-backoff",
    causal_chain: list[str] | None = None,
    evidence_gaps: list[EvidenceGap] | None = None,
) -> DiagnosisObject:
    component, mode = root_cause_code.split("/")
    return DiagnosisObject(
        incident_id=uuid.uuid4(),
        root_cause_component=component,
        failure_mode=mode,
        root_cause_code=root_cause_code,
        causal_chain=causal_chain or ["Pod CrashLoopBackOff", "OOM killed"],
        affected_resources=["pod/test-app-xyz"],
        evidence=[
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="test",
                result="test",
                timestamp=datetime.now(timezone.utc),
            )
        ],
        evidence_gaps=evidence_gaps or [],
        confidence=0.85,
        agent_summary="test diagnosis",
    )


def _make_challenge(**overrides) -> SkepticChallenge:
    defaults = {
        "alternative_hypotheses": ["alternative root cause"],
        "evidence_gap_challenges": [],
        "logical_weaknesses": ["logical gap"],
        "overall_assessment": "needs review",
    }
    defaults.update(overrides)
    return SkepticChallenge(**defaults)


def _make_response(
    revised_diagnosis: DiagnosisObject | None = None,
) -> SkepticResponse:
    return SkepticResponse(
        rebuttals=[
            SkepticRebuttal(
                challenge_point="alt hypothesis",
                rebuttal="ruled out",
            )
        ],
        revised_diagnosis=revised_diagnosis,
        summary="defended",
    )


class TestRunSkepticValidation:
    """Tests for the skeptic validation loop with hash-based termination."""

    @pytest.mark.unit
    async def test_hash_unchanged_passes_in_one_round(self):
        """Hash unchanged after round 1 → verdict has rounds_completed=1, passed=True."""
        diagnosis = _make_diagnosis()
        state = {"incident_id": str(uuid.uuid4())}

        with (
            patch(
                "src.agents.skeptic.run_skeptic",
                new_callable=AsyncMock,
                return_value=_make_challenge(),
            ),
            patch(
                "src.agents.orchestrator.run_orchestrator_rebuttal",
                new_callable=AsyncMock,
                return_value=_make_response(revised_diagnosis=None),
            ),
        ):
            final_diag, verdict = await run_skeptic_validation(diagnosis, state)

        assert verdict.passed is True
        assert verdict.rounds_completed == 1
        assert verdict.original_hash == verdict.final_hash

    @pytest.mark.unit
    async def test_hash_changed_runs_two_rounds(self):
        """Hash changed after round 1 → runs exactly 2 rounds, passes."""
        original_diagnosis = _make_diagnosis(root_cause_code="workload/crash-loop-backoff")
        revised_diagnosis = _make_diagnosis(root_cause_code="node/memory-pressure")
        state = {"incident_id": str(uuid.uuid4())}

        call_count = {"skeptic": 0, "rebuttal": 0}

        async def mock_skeptic(diag, st):
            call_count["skeptic"] += 1
            return _make_challenge()

        async def mock_rebuttal(diag, challenge, st, round_number=1):
            call_count["rebuttal"] += 1
            if call_count["rebuttal"] == 1:
                return _make_response(revised_diagnosis=revised_diagnosis)
            return _make_response(revised_diagnosis=None)

        with (
            patch("src.agents.skeptic.run_skeptic", side_effect=mock_skeptic),
            patch("src.agents.orchestrator.run_orchestrator_rebuttal", side_effect=mock_rebuttal),
        ):
            final_diag, verdict = await run_skeptic_validation(original_diagnosis, state)

        assert verdict.passed is True
        assert verdict.rounds_completed == 2
        assert call_count["skeptic"] == 2
        assert call_count["rebuttal"] == 2

    @pytest.mark.unit
    async def test_hash_changed_both_rounds_still_passes(self):
        """Hash changed after both rounds → still passed=True (no infinite loops)."""
        original_diagnosis = _make_diagnosis(root_cause_code="workload/crash-loop-backoff")
        revised_1 = _make_diagnosis(root_cause_code="node/memory-pressure")
        revised_2 = _make_diagnosis(root_cause_code="node/disk-pressure")
        state = {"incident_id": str(uuid.uuid4())}

        call_count = {"rebuttal": 0}

        async def mock_rebuttal(diag, challenge, st, round_number=1):
            call_count["rebuttal"] += 1
            if call_count["rebuttal"] == 1:
                return _make_response(revised_diagnosis=revised_1)
            return _make_response(revised_diagnosis=revised_2)

        with (
            patch(
                "src.agents.skeptic.run_skeptic",
                new_callable=AsyncMock,
                return_value=_make_challenge(),
            ),
            patch("src.agents.orchestrator.run_orchestrator_rebuttal", side_effect=mock_rebuttal),
        ):
            final_diag, verdict = await run_skeptic_validation(original_diagnosis, state)

        assert verdict.passed is True
        assert verdict.rounds_completed == 2
        assert verdict.original_hash != verdict.final_hash

    @pytest.mark.unit
    async def test_evidence_gaps_present_in_challenge(self):
        """Evidence gaps present → skeptic challenge includes gap-specific challenges."""
        gaps = [
            EvidenceGap(query="get_logs", reason="MCP timeout", timeout_seconds=30.0),
        ]
        diagnosis = _make_diagnosis(evidence_gaps=gaps)
        state = {"incident_id": str(uuid.uuid4())}

        challenge_with_gaps = _make_challenge(
            evidence_gap_challenges=["Evidence gap: get_logs not available"]
        )

        with (
            patch(
                "src.agents.skeptic.run_skeptic",
                new_callable=AsyncMock,
                return_value=challenge_with_gaps,
            ),
            patch(
                "src.agents.orchestrator.run_orchestrator_rebuttal",
                new_callable=AsyncMock,
                return_value=_make_response(),
            ),
        ):
            _, verdict = await run_skeptic_validation(diagnosis, state)

        round_1 = verdict.challenge_history[0]
        challenge_data = round_1["challenge"]
        assert len(challenge_data["evidence_gap_challenges"]) >= 1

    @pytest.mark.unit
    async def test_challenge_history_contains_pairs(self):
        """Challenge history contains full challenge/response pairs."""
        diagnosis = _make_diagnosis()
        state = {"incident_id": str(uuid.uuid4())}

        with (
            patch(
                "src.agents.skeptic.run_skeptic",
                new_callable=AsyncMock,
                return_value=_make_challenge(),
            ),
            patch(
                "src.agents.orchestrator.run_orchestrator_rebuttal",
                new_callable=AsyncMock,
                return_value=_make_response(),
            ),
        ):
            _, verdict = await run_skeptic_validation(diagnosis, state)

        assert len(verdict.challenge_history) >= 1
        entry = verdict.challenge_history[0]
        assert "round" in entry
        assert "challenge" in entry
        assert "response" in entry

    @pytest.mark.unit
    async def test_max_rounds_constant_is_two(self):
        assert MAX_SKEPTIC_ROUNDS == 2


class TestSealDiagnosis:
    """seal_diagnosis creates a valid ImmutableDiagnosisArtifact."""

    @pytest.mark.unit
    def test_seal_copies_all_fields(self):
        diagnosis = _make_diagnosis()
        verdict = SkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_hash=diagnosis.root_cause_hash(),
            final_hash=diagnosis.root_cause_hash(),
            challenge_history=[{"round": 1}],
            verdict_reasoning="validated",
        )

        sealed = seal_diagnosis(diagnosis, verdict)

        assert isinstance(sealed, ImmutableDiagnosisArtifact)
        assert sealed.id == diagnosis.id
        assert sealed.incident_id == diagnosis.incident_id
        assert sealed.root_cause_component == diagnosis.root_cause_component
        assert sealed.failure_mode == diagnosis.failure_mode
        assert sealed.root_cause_code == diagnosis.root_cause_code
        assert sealed.confidence == diagnosis.confidence
        assert sealed.agent_summary == diagnosis.agent_summary
        assert tuple(diagnosis.causal_chain) == sealed.causal_chain
        assert tuple(diagnosis.affected_resources) == sealed.affected_resources

    @pytest.mark.unit
    def test_seal_includes_skeptic_verdict(self):
        """Sealed artifact contains the skeptic_verdict dict."""
        diagnosis = _make_diagnosis()
        verdict = SkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_hash=diagnosis.root_cause_hash(),
            final_hash=diagnosis.root_cause_hash(),
            challenge_history=[{"round": 1}],
            verdict_reasoning="validated",
        )

        sealed = seal_diagnosis(diagnosis, verdict)

        assert sealed.skeptic_verdict is not None
        assert sealed.skeptic_verdict["passed"] is True
        assert sealed.skeptic_verdict["rounds_completed"] == 1

    @pytest.mark.unit
    def test_seal_includes_sealed_at(self):
        """Sealed artifact has a non-None sealed_at timestamp."""
        diagnosis = _make_diagnosis()
        verdict = SkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_hash=diagnosis.root_cause_hash(),
            final_hash=diagnosis.root_cause_hash(),
            challenge_history=[],
            verdict_reasoning="validated",
        )

        sealed = seal_diagnosis(diagnosis, verdict)

        assert sealed.sealed_at is not None

    @pytest.mark.unit
    def test_sealed_artifact_is_frozen(self):
        diagnosis = _make_diagnosis()
        verdict = SkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_hash=diagnosis.root_cause_hash(),
            final_hash=diagnosis.root_cause_hash(),
            challenge_history=[],
            verdict_reasoning="validated",
        )

        sealed = seal_diagnosis(diagnosis, verdict)

        with pytest.raises(Exception):
            sealed.confidence = 0.99  # type: ignore[misc]

    @pytest.mark.unit
    def test_sealed_hash_matches_diagnosis(self):
        diagnosis = _make_diagnosis()
        verdict = SkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_hash=diagnosis.root_cause_hash(),
            final_hash=diagnosis.root_cause_hash(),
            challenge_history=[],
            verdict_reasoning="validated",
        )

        sealed = seal_diagnosis(diagnosis, verdict)
        assert sealed.root_cause_hash() == diagnosis.root_cause_hash()

    @pytest.mark.unit
    def test_sealed_uses_tuples(self):
        diagnosis = _make_diagnosis()
        verdict = SkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_hash=diagnosis.root_cause_hash(),
            final_hash=diagnosis.root_cause_hash(),
            challenge_history=[],
            verdict_reasoning="validated",
        )

        sealed = seal_diagnosis(diagnosis, verdict)
        assert isinstance(sealed.causal_chain, tuple)
        assert isinstance(sealed.affected_resources, tuple)
        assert isinstance(sealed.evidence, tuple)

    @pytest.mark.unit
    def test_sealed_verdict_is_immutable(self):
        """Sealed skeptic_verdict cannot be mutated in place."""
        from types import MappingProxyType

        diagnosis = _make_diagnosis()
        verdict = SkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_hash=diagnosis.root_cause_hash(),
            final_hash=diagnosis.root_cause_hash(),
            challenge_history=[],
            verdict_reasoning="validated",
        )

        sealed = seal_diagnosis(diagnosis, verdict)
        assert isinstance(sealed.skeptic_verdict, MappingProxyType)
        with pytest.raises(TypeError):
            sealed.skeptic_verdict["passed"] = False  # type: ignore[index]

    @pytest.mark.unit
    def test_sealed_model_dump_roundtrip(self):
        """Sealed artifact model_dump produces valid JSON-serializable dict."""
        diagnosis = _make_diagnosis()
        verdict = SkepticVerdict(
            passed=True,
            rounds_completed=1,
            original_hash=diagnosis.root_cause_hash(),
            final_hash=diagnosis.root_cause_hash(),
            challenge_history=[{"round": 1}],
            verdict_reasoning="validated",
        )

        sealed = seal_diagnosis(diagnosis, verdict)
        data = sealed.model_dump(mode="json")
        assert isinstance(data["skeptic_verdict"], dict)
        assert data["skeptic_verdict"]["passed"] is True
        assert data["sealed_at"] is not None

        roundtrip = ImmutableDiagnosisArtifact.model_validate(data)
        assert roundtrip.root_cause_hash() == sealed.root_cause_hash()
