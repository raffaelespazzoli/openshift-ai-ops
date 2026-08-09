"""Unit tests for SkepticChallenge, SkepticResponse, SkepticVerdict models."""

import uuid
from datetime import datetime, timezone

import pytest

from src.models.diagnosis import (
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceSource,
)
from src.models.skeptic import (
    SkepticChallenge,
    SkepticRebuttal,
    SkepticResponse,
    SkepticVerdict,
)


def _make_challenge(**overrides) -> SkepticChallenge:
    defaults = {
        "alternative_hypotheses": ["The issue could be network/dns-failure"],
        "evidence_gap_challenges": ["MCP timeout gap not addressed"],
        "logical_weaknesses": ["Causal chain has unexplained jump from alert to root cause"],
        "overall_assessment": "Diagnosis has moderate evidence but gaps remain",
    }
    defaults.update(overrides)
    return SkepticChallenge(**defaults)


def _make_verdict(**overrides) -> SkepticVerdict:
    defaults = {
        "passed": True,
        "rounds_completed": 1,
        "original_hash": "a" * 64,
        "final_hash": "a" * 64,
        "challenge_history": [{"round": 1, "challenge": {}, "response": {}}],
        "verdict_reasoning": "Diagnosis stable after 1 round",
    }
    defaults.update(overrides)
    return SkepticVerdict(**defaults)


class TestSkepticChallengeValidation:
    """SkepticChallenge validates required fields and serialization."""

    @pytest.mark.unit
    def test_valid_challenge(self):
        c = _make_challenge()
        assert len(c.alternative_hypotheses) >= 1
        assert len(c.logical_weaknesses) >= 1
        assert c.overall_assessment

    @pytest.mark.unit
    def test_empty_alternative_hypotheses_rejected(self):
        with pytest.raises(Exception):
            _make_challenge(alternative_hypotheses=[])

    @pytest.mark.unit
    def test_empty_logical_weaknesses_rejected(self):
        with pytest.raises(Exception):
            _make_challenge(logical_weaknesses=[])

    @pytest.mark.unit
    def test_evidence_gap_challenges_optional(self):
        c = SkepticChallenge(
            alternative_hypotheses=["alt"],
            logical_weaknesses=["weakness"],
            overall_assessment="test",
        )
        assert c.evidence_gap_challenges == []

    @pytest.mark.unit
    def test_created_at_auto_set(self):
        c = _make_challenge()
        assert c.created_at is not None
        assert c.created_at.tzinfo is not None

    @pytest.mark.unit
    def test_roundtrip_json(self):
        c = _make_challenge()
        json_str = c.model_dump_json()
        restored = SkepticChallenge.model_validate_json(json_str)
        assert restored.alternative_hypotheses == c.alternative_hypotheses
        assert restored.logical_weaknesses == c.logical_weaknesses


class TestSkepticResponseValidation:
    """SkepticResponse validates rebuttals and optional revised_diagnosis."""

    @pytest.mark.unit
    def test_valid_response_without_revised_diagnosis(self):
        r = SkepticResponse(
            rebuttals=[
                SkepticRebuttal(
                    challenge_point="alt hypothesis",
                    rebuttal="Evidence rules it out",
                )
            ],
            revised_diagnosis=None,
            summary="Original diagnosis defended",
        )
        assert r.revised_diagnosis is None
        assert len(r.rebuttals) == 1

    @pytest.mark.unit
    def test_valid_response_with_revised_diagnosis(self):
        diag = DiagnosisObject(
            incident_id=uuid.uuid4(),
            root_cause_component="node",
            failure_mode="disk-pressure",
            root_cause_code="node/disk-pressure",
            causal_chain=["disk full"],
            affected_resources=["node/worker-1"],
            evidence=[
                EvidenceArtifact(
                    source=EvidenceSource.MCP_CLUSTER,
                    query="test",
                    result="test",
                    timestamp=datetime.now(timezone.utc),
                )
            ],
            confidence=0.7,
        )
        r = SkepticResponse(
            rebuttals=[],
            revised_diagnosis=diag,
            summary="Revised to disk-pressure",
        )
        assert r.revised_diagnosis is not None
        assert r.revised_diagnosis.root_cause_code == "node/disk-pressure"

    @pytest.mark.unit
    def test_response_roundtrip_json(self):
        r = SkepticResponse(
            rebuttals=[
                SkepticRebuttal(
                    challenge_point="gap challenge",
                    rebuttal="addressed",
                    additional_evidence="new log data",
                )
            ],
            summary="All points addressed",
        )
        json_str = r.model_dump_json()
        restored = SkepticResponse.model_validate_json(json_str)
        assert restored.summary == r.summary
        assert len(restored.rebuttals) == 1


class TestSkepticVerdictValidation:
    """SkepticVerdict validates rounds_completed, hashes, and history."""

    @pytest.mark.unit
    def test_valid_verdict_one_round(self):
        v = _make_verdict(rounds_completed=1)
        assert v.passed is True
        assert v.rounds_completed == 1

    @pytest.mark.unit
    def test_valid_verdict_two_rounds(self):
        v = _make_verdict(rounds_completed=2)
        assert v.rounds_completed == 2

    @pytest.mark.unit
    def test_rounds_completed_zero_rejected(self):
        with pytest.raises(Exception):
            _make_verdict(rounds_completed=0)

    @pytest.mark.unit
    def test_rounds_completed_three_rejected(self):
        with pytest.raises(Exception):
            _make_verdict(rounds_completed=3)

    @pytest.mark.unit
    def test_hashes_are_non_empty(self):
        v = _make_verdict()
        assert v.original_hash
        assert v.final_hash

    @pytest.mark.unit
    def test_challenge_history_contains_entries(self):
        v = _make_verdict()
        assert len(v.challenge_history) >= 1

    @pytest.mark.unit
    def test_verdict_roundtrip_json(self):
        v = _make_verdict()
        json_str = v.model_dump_json()
        restored = SkepticVerdict.model_validate_json(json_str)
        assert restored.passed == v.passed
        assert restored.rounds_completed == v.rounds_completed
        assert restored.original_hash == v.original_hash


class TestSkepticRebuttal:
    """SkepticRebuttal model tests."""

    @pytest.mark.unit
    def test_rebuttal_with_additional_evidence(self):
        r = SkepticRebuttal(
            challenge_point="Alternative root cause",
            rebuttal="Ruled out by log evidence",
            additional_evidence="Container logs show OOM at timestamp T",
        )
        assert r.additional_evidence

    @pytest.mark.unit
    def test_rebuttal_without_additional_evidence(self):
        r = SkepticRebuttal(
            challenge_point="Logical gap",
            rebuttal="Causal chain is complete",
        )
        assert r.additional_evidence == ""
