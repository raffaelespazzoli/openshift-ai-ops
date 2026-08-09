"""Unit tests for DiagnosisObject, EvidenceGap, ImmutableDiagnosisArtifact, and taxonomy."""

import uuid
from datetime import datetime, timezone
from types import MappingProxyType

import pytest

from src.models.diagnosis import (
    ROOT_CAUSE_TAXONOMY,
    VALID_SUBSYSTEMS,
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)


def _make_evidence() -> EvidenceArtifact:
    return EvidenceArtifact(
        source=EvidenceSource.MCP_CLUSTER,
        query="get_resources({'kind': 'Pod'})",
        result='{"items": []}',
        timestamp=datetime.now(timezone.utc),
    )


def _make_verdict_dict() -> dict:
    """Create a minimal SkepticVerdict dict for sealing tests."""
    return {
        "passed": True,
        "rounds_completed": 1,
        "original_hash": "a" * 64,
        "final_hash": "a" * 64,
        "challenge_history": [{"round": 1}],
        "verdict_reasoning": "validated",
    }


def _make_diagnosis(**overrides) -> DiagnosisObject:
    defaults = {
        "incident_id": uuid.uuid4(),
        "root_cause_component": "node",
        "failure_mode": "memory-pressure",
        "root_cause_code": "node/memory-pressure",
        "causal_chain": ["pod eviction", "node memory threshold exceeded"],
        "affected_resources": ["node/worker-1"],
        "evidence": [_make_evidence()],
        "confidence": 0.85,
    }
    defaults.update(overrides)
    return DiagnosisObject(**defaults)


class TestDiagnosisObjectValidation:
    """DiagnosisObject validates schema: required fields, confidence range, root_cause_code format."""

    @pytest.mark.unit
    def test_valid_diagnosis_object(self):
        diag = _make_diagnosis()
        assert diag.root_cause_component == "node"
        assert diag.failure_mode == "memory-pressure"
        assert diag.root_cause_code == "node/memory-pressure"
        assert 0.0 <= diag.confidence <= 1.0

    @pytest.mark.unit
    def test_confidence_below_zero_rejected(self):
        with pytest.raises(Exception):
            _make_diagnosis(confidence=-0.1)

    @pytest.mark.unit
    def test_confidence_above_one_rejected(self):
        with pytest.raises(Exception):
            _make_diagnosis(confidence=1.1)

    @pytest.mark.unit
    def test_confidence_zero_accepted(self):
        diag = _make_diagnosis(confidence=0.0)
        assert diag.confidence == 0.0

    @pytest.mark.unit
    def test_confidence_one_accepted(self):
        diag = _make_diagnosis(confidence=1.0)
        assert diag.confidence == 1.0

    @pytest.mark.unit
    def test_root_cause_code_must_be_slash_delimited(self):
        with pytest.raises(ValueError, match="slash-delimited"):
            _make_diagnosis(
                root_cause_component="node",
                failure_mode="memory-pressure",
                root_cause_code="node-memory-pressure",
            )

    @pytest.mark.unit
    def test_root_cause_code_must_match_component_and_mode(self):
        with pytest.raises(ValueError, match="must equal"):
            _make_diagnosis(
                root_cause_component="node",
                failure_mode="memory-pressure",
                root_cause_code="storage/pvc-stuck-pending",
            )

    @pytest.mark.unit
    def test_unknown_subsystem_rejected(self):
        with pytest.raises(ValueError, match="not in the controlled taxonomy"):
            _make_diagnosis(
                root_cause_component="cosmic",
                failure_mode="ray-impact",
                root_cause_code="cosmic/ray-impact",
            )

    @pytest.mark.unit
    def test_arbitrary_failure_mode_rejected(self):
        """Valid subsystem but arbitrary failure mode is not in the taxonomy."""
        with pytest.raises(ValueError, match="not in the controlled taxonomy"):
            _make_diagnosis(
                root_cause_component="node",
                failure_mode="custom-mode",
                root_cause_code="node/custom-mode",
            )

    @pytest.mark.unit
    def test_id_auto_generated(self):
        d1 = _make_diagnosis()
        d2 = _make_diagnosis()
        assert d1.id != d2.id

    @pytest.mark.unit
    def test_created_at_auto_set(self):
        diag = _make_diagnosis()
        assert diag.created_at is not None
        assert diag.created_at.tzinfo is not None

    @pytest.mark.unit
    def test_evidence_gaps_default_empty(self):
        diag = _make_diagnosis()
        assert diag.evidence_gaps == []


class TestRootCauseHash:
    """root_cause_hash() is deterministic: same inputs → same hash, different → different."""

    @pytest.mark.unit
    def test_same_inputs_same_hash(self):
        d1 = _make_diagnosis(
            causal_chain=["a", "b", "c"],
        )
        d2 = _make_diagnosis(
            causal_chain=["a", "b", "c"],
        )
        assert d1.root_cause_hash() == d2.root_cause_hash()

    @pytest.mark.unit
    def test_order_independent_causal_chain(self):
        d1 = _make_diagnosis(causal_chain=["b", "a", "c"])
        d2 = _make_diagnosis(causal_chain=["a", "c", "b"])
        assert d1.root_cause_hash() == d2.root_cause_hash()

    @pytest.mark.unit
    def test_different_root_cause_different_hash(self):
        d1 = _make_diagnosis(
            root_cause_component="node",
            failure_mode="memory-pressure",
            root_cause_code="node/memory-pressure",
        )
        d2 = _make_diagnosis(
            root_cause_component="node",
            failure_mode="disk-pressure",
            root_cause_code="node/disk-pressure",
        )
        assert d1.root_cause_hash() != d2.root_cause_hash()

    @pytest.mark.unit
    def test_different_causal_chain_different_hash(self):
        d1 = _make_diagnosis(causal_chain=["a"])
        d2 = _make_diagnosis(causal_chain=["b"])
        assert d1.root_cause_hash() != d2.root_cause_hash()

    @pytest.mark.unit
    def test_hash_is_sha256_hex_string(self):
        h = _make_diagnosis().root_cause_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestEvidenceGapSerialization:
    """EvidenceGap serializes correctly with query, reason, timeout_seconds."""

    @pytest.mark.unit
    def test_evidence_gap_with_timeout(self):
        gap = EvidenceGap(
            query="get_resources({'kind': 'Node'})",
            reason="MCP query timed out",
            timeout_seconds=30.0,
        )
        data = gap.model_dump()
        assert data["query"] == "get_resources({'kind': 'Node'})"
        assert data["reason"] == "MCP query timed out"
        assert data["timeout_seconds"] == 30.0

    @pytest.mark.unit
    def test_evidence_gap_without_timeout(self):
        gap = EvidenceGap(
            query="describe_resource({})",
            reason="MCP server unavailable",
        )
        data = gap.model_dump()
        assert data["timeout_seconds"] is None

    @pytest.mark.unit
    def test_evidence_gap_roundtrip_json(self):
        gap = EvidenceGap(
            query="get_logs({'pod': 'test'})",
            reason="Connection refused",
            timeout_seconds=10.0,
        )
        json_str = gap.model_dump_json()
        restored = EvidenceGap.model_validate_json(json_str)
        assert restored == gap


class TestRootCauseTaxonomy:
    """Root-cause taxonomy codes follow slash-delimited format."""

    @pytest.mark.unit
    def test_all_taxonomy_codes_are_slash_delimited(self):
        for code in ROOT_CAUSE_TAXONOMY:
            parts = code.split("/")
            assert len(parts) == 2, f"Code {code!r} is not slash-delimited"
            assert parts[0], f"Code {code!r} has empty subsystem"
            assert parts[1], f"Code {code!r} has empty failure-mode"

    @pytest.mark.unit
    def test_valid_subsystems_derived_from_taxonomy(self):
        subsystems = {code.split("/")[0] for code in ROOT_CAUSE_TAXONOMY}
        assert subsystems == VALID_SUBSYSTEMS

    @pytest.mark.unit
    def test_taxonomy_contains_expected_codes(self):
        assert "node/memory-pressure" in ROOT_CAUSE_TAXONOMY
        assert "storage/pvc-stuck-pending" in ROOT_CAUSE_TAXONOMY
        assert "workload/crash-loop-backoff" in ROOT_CAUSE_TAXONOMY
        assert "unknown/unclassified" in ROOT_CAUSE_TAXONOMY

    @pytest.mark.unit
    def test_all_taxonomy_codes_produce_valid_diagnosis(self):
        for code in ROOT_CAUSE_TAXONOMY:
            component, mode = code.split("/")
            diag = _make_diagnosis(
                root_cause_component=component,
                failure_mode=mode,
                root_cause_code=code,
            )
            assert diag.root_cause_code == code


class TestImmutableDiagnosisArtifact:
    """ImmutableDiagnosisArtifact is frozen after creation."""

    @pytest.mark.unit
    def test_immutable_from_diagnosis(self):
        diag = _make_diagnosis()
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        assert frozen.id == diag.id
        assert frozen.root_cause_code == diag.root_cause_code
        assert frozen.confidence == diag.confidence

    @pytest.mark.unit
    def test_immutable_cannot_mutate(self):
        diag = _make_diagnosis()
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        with pytest.raises(Exception):
            frozen.confidence = 0.99  # type: ignore[misc]

    @pytest.mark.unit
    def test_immutable_hash_matches_mutable(self):
        diag = _make_diagnosis()
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        assert frozen.root_cause_hash() == diag.root_cause_hash()

    @pytest.mark.unit
    def test_immutable_tuples_not_lists(self):
        diag = _make_diagnosis()
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        assert isinstance(frozen.causal_chain, tuple)
        assert isinstance(frozen.affected_resources, tuple)
        assert isinstance(frozen.evidence, tuple)
        assert isinstance(frozen.evidence_gaps, tuple)

    @pytest.mark.unit
    def test_nested_evidence_is_deeply_immutable(self):
        """EvidenceArtifact inside ImmutableDiagnosisArtifact cannot be mutated."""
        diag = _make_diagnosis()
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        with pytest.raises(Exception):
            frozen.evidence[0].result = "tampered"  # type: ignore[misc]

    @pytest.mark.unit
    def test_nested_evidence_gap_is_deeply_immutable(self):
        """EvidenceGap inside ImmutableDiagnosisArtifact cannot be mutated."""
        gap = EvidenceGap(query="test", reason="timeout", timeout_seconds=5.0)
        diag = _make_diagnosis(evidence_gaps=[gap])
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        with pytest.raises(Exception):
            frozen.evidence_gaps[0].reason = "tampered"  # type: ignore[misc]

    @pytest.mark.unit
    def test_immutable_requires_skeptic_verdict(self):
        """ImmutableDiagnosisArtifact requires non-None skeptic_verdict."""
        diag = _make_diagnosis()
        with pytest.raises(Exception):
            ImmutableDiagnosisArtifact.from_diagnosis(
                diag, skeptic_verdict=None, sealed_at=datetime.now(timezone.utc),
            )

    @pytest.mark.unit
    def test_immutable_requires_sealed_at(self):
        """ImmutableDiagnosisArtifact requires non-None sealed_at."""
        diag = _make_diagnosis()
        with pytest.raises(Exception):
            ImmutableDiagnosisArtifact.from_diagnosis(
                diag, skeptic_verdict=_make_verdict_dict(), sealed_at=None,
            )

    @pytest.mark.unit
    def test_skeptic_verdict_is_frozen(self):
        """skeptic_verdict dict is frozen via MappingProxyType after sealing."""
        diag = _make_diagnosis()
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        assert isinstance(frozen.skeptic_verdict, MappingProxyType)
        with pytest.raises(TypeError):
            frozen.skeptic_verdict["passed"] = False  # type: ignore[index]

    @pytest.mark.unit
    def test_alternative_hypotheses_dicts_are_frozen(self):
        """alternative_hypotheses dict entries are frozen via MappingProxyType."""
        diag = _make_diagnosis()
        diag = diag.model_copy(update={
            "alternative_hypotheses": [{"code": "network/dns-failure", "confidence": 0.3}],
        })
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        assert isinstance(frozen.alternative_hypotheses[0], MappingProxyType)
        with pytest.raises(TypeError):
            frozen.alternative_hypotheses[0]["code"] = "tampered"  # type: ignore[index]


class TestImmutableDiagnosisSealIntegration:
    """ImmutableDiagnosisArtifact.from_diagnosis copies all fields correctly (Task 9.4)."""

    @pytest.mark.unit
    def test_seal_preserves_all_fields(self):
        gap = EvidenceGap(query="get_logs", reason="MCP timeout", timeout_seconds=10.0)
        diag = _make_diagnosis(evidence_gaps=[gap])
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        assert frozen.id == diag.id
        assert frozen.incident_id == diag.incident_id
        assert frozen.root_cause_component == diag.root_cause_component
        assert frozen.failure_mode == diag.failure_mode
        assert frozen.root_cause_code == diag.root_cause_code
        assert frozen.confidence == diag.confidence
        assert frozen.agent_summary == diag.agent_summary
        assert frozen.created_at == diag.created_at
        assert len(frozen.causal_chain) == len(diag.causal_chain)
        assert len(frozen.evidence) == len(diag.evidence)
        assert len(frozen.evidence_gaps) == len(diag.evidence_gaps)

    @pytest.mark.unit
    def test_frozen_raises_on_any_field_mutation(self):
        diag = _make_diagnosis()
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        with pytest.raises(Exception):
            frozen.root_cause_component = "tampered"  # type: ignore[misc]
        with pytest.raises(Exception):
            frozen.agent_summary = "tampered"  # type: ignore[misc]
        with pytest.raises(Exception):
            frozen.id = uuid.uuid4()  # type: ignore[misc]

    @pytest.mark.unit
    def test_model_dump_works_on_frozen(self):
        """model_dump() still works on frozen artifacts."""
        diag = _make_diagnosis()
        now = datetime.now(timezone.utc)
        frozen = ImmutableDiagnosisArtifact.from_diagnosis(
            diag, skeptic_verdict=_make_verdict_dict(), sealed_at=now,
        )
        data = frozen.model_dump(mode="json")
        assert data["root_cause_code"] == diag.root_cause_code
        assert data["confidence"] == diag.confidence
        assert data["skeptic_verdict"]["passed"] is True
        assert data["sealed_at"] is not None


class TestEvidenceArtifact:
    """EvidenceArtifact model tests."""

    @pytest.mark.unit
    def test_evidence_artifact_creation(self):
        ea = _make_evidence()
        assert ea.source == EvidenceSource.MCP_CLUSTER
        assert ea.query
        assert ea.result

    @pytest.mark.unit
    def test_evidence_source_values(self):
        assert EvidenceSource.MCP_CLUSTER == "mcp_cluster"
        assert EvidenceSource.RUNBOOK == "runbook"
        assert EvidenceSource.RHOKP == "rhokp"
