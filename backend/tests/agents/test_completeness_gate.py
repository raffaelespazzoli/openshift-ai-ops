"""Unit tests for the completeness gate (AC: #6).

Tests that the gate passes when all alert fingerprints are addressed
and fails when alerts are missing from the diagnosis.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.agents.completeness_gate import evaluate_completeness
from src.models.diagnosis import (
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceSource,
)


def _make_diagnosis(
    evidence_queries: list[str] | None = None,
    summary: str = "Test diagnosis",
    causal_chain: list[str] | None = None,
) -> DiagnosisObject:
    """Create a diagnosis with configurable evidence queries."""
    evidence = []
    for q in (evidence_queries or ["default_query"]):
        evidence.append(EvidenceArtifact(
            source=EvidenceSource.MCP_CLUSTER,
            query=q,
            result="some result",
            timestamp=datetime.now(timezone.utc),
        ))

    return DiagnosisObject(
        incident_id=uuid.uuid4(),
        root_cause_component="workload",
        failure_mode="crash-loop-backoff",
        root_cause_code="workload/crash-loop-backoff",
        causal_chain=causal_chain or ["cause"],
        affected_resources=[],
        evidence=evidence,
        confidence=0.8,
        agent_summary=summary,
    )


class TestCompletenessGatePass:
    """Tests where the completeness gate should PASS."""

    @pytest.mark.unit
    def test_passes_when_no_alerts(self):
        diagnosis = _make_diagnosis()
        result = evaluate_completeness(diagnosis, [])
        assert result.complete is True
        assert result.unaddressed_alerts == []

    @pytest.mark.unit
    def test_passes_when_all_fingerprints_in_evidence(self):
        alerts = [
            {"fingerprint": "abc123", "labels": {"alertname": "KubePodCrashLooping"}},
            {"fingerprint": "def456", "labels": {"alertname": "NodeMemoryPressure"}},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=[
                "Investigating alert abc123 KubePodCrashLooping",
                "Checking node def456 NodeMemoryPressure",
            ],
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is True

    @pytest.mark.unit
    def test_passes_when_alertnames_in_summary(self):
        alerts = [
            {"labels": {"alertname": "KubePodCrashLooping"}},
        ]
        diagnosis = _make_diagnosis(
            summary="Root cause: KubePodCrashLooping due to OOM",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is True

    @pytest.mark.unit
    def test_passes_when_alertnames_in_causal_chain(self):
        alerts = [
            {"labels": {"alertname": "NodeMemoryPressure"}},
        ]
        diagnosis = _make_diagnosis(
            causal_chain=["NodeMemoryPressure triggered by large workload"],
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is True

    @pytest.mark.unit
    def test_fails_when_alertname_found_but_fingerprint_not_in_text(self):
        """Alert with a fingerprint requires that fingerprint in text — alertname alone
        is insufficient to prevent shared-alertname false positives."""
        alerts = [
            {"fingerprint": "opaque-fp-123", "labels": {"alertname": "KubePodCrashLooping"}},
        ]
        diagnosis = _make_diagnosis(
            summary="Root cause is KubePodCrashLooping due to OOM",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is False
        assert "opaque-fp-123" in result.unaddressed_alerts

    @pytest.mark.unit
    def test_passes_when_fingerprint_found_but_alertname_absent(self):
        """An alert is addressed if its fingerprint appears, even without alertname."""
        alerts = [
            {"fingerprint": "fp-match-me", "labels": {"alertname": "SomeObscureAlert"}},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["Checked alert fp-match-me cluster state"],
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is True

    @pytest.mark.unit
    def test_passes_case_insensitive_matching(self):
        alerts = [
            {"labels": {"alertname": "KubePodCrashLooping"}},
        ]
        diagnosis = _make_diagnosis(
            summary="kubepodcrashlooping detected in default namespace",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is True


class TestCompletenessGateFail:
    """Tests where the completeness gate should FAIL."""

    @pytest.mark.unit
    def test_fails_when_fingerprint_missing(self):
        alerts = [
            {"fingerprint": "abc123", "labels": {"alertname": "Alert1"}},
            {"fingerprint": "def456", "labels": {"alertname": "Alert2"}},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["Investigated abc123 Alert1"],
            summary="Only Alert1 addressed",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is False
        assert "def456" in result.unaddressed_alerts or "Alert2" in result.unaddressed_alerts

    @pytest.mark.unit
    def test_fails_when_no_alerts_mentioned_anywhere(self):
        alerts = [
            {"fingerprint": "xyz999", "labels": {"alertname": "UnknownAlert"}},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["generic_query"],
            summary="Generic diagnosis with no alert references",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is False
        assert len(result.unaddressed_alerts) > 0

    @pytest.mark.unit
    def test_returns_correct_unaddressed_list(self):
        alerts = [
            {"fingerprint": "aaa111", "labels": {"alertname": "KubePodOOMKilled"}},
            {"fingerprint": "bbb222", "labels": {"alertname": "NodeDiskPressure"}},
            {"fingerprint": "ccc333", "labels": {"alertname": "EtcdHighLatency"}},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["Alert aaa111 KubePodOOMKilled investigated"],
            summary="Only KubePodOOMKilled addressed",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is False
        unaddressed_set = set(result.unaddressed_alerts)
        assert "bbb222" in unaddressed_set
        assert "ccc333" in unaddressed_set

    @pytest.mark.unit
    def test_reasoning_includes_counts(self):
        alerts = [
            {"fingerprint": "fp-alert1", "labels": {"alertname": "KubeContainerWaiting"}},
            {"fingerprint": "fp-alert2", "labels": {"alertname": "NodeFilesystemFull"}},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["KubeContainerWaiting fp-alert1 checked"],
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert "Addressed" in result.reasoning or "addressed" in result.reasoning.lower()


class TestCompletenessGateSharedAlertnames:
    """Tests for Finding R3-1: shared alertname deduplication."""

    @pytest.mark.unit
    def test_shared_alertname_requires_fingerprints(self):
        """Multiple alerts with same alertname must each have fingerprint matched."""
        alerts = [
            {"fingerprint": "fp-pod-A", "labels": {"alertname": "KubePodCrashLooping"}},
            {"fingerprint": "fp-pod-B", "labels": {"alertname": "KubePodCrashLooping"}},
            {"fingerprint": "fp-pod-C", "labels": {"alertname": "KubePodCrashLooping"}},
        ]
        diagnosis = _make_diagnosis(
            summary="KubePodCrashLooping detected across multiple pods",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is False
        assert len(result.unaddressed_alerts) == 3

    @pytest.mark.unit
    def test_shared_alertname_passes_when_all_fingerprints_present(self):
        """All fingerprints addressed => complete, even with shared alertname."""
        alerts = [
            {"fingerprint": "fp-pod-A", "labels": {"alertname": "KubePodCrashLooping"}},
            {"fingerprint": "fp-pod-B", "labels": {"alertname": "KubePodCrashLooping"}},
        ]
        diagnosis = _make_diagnosis(
            summary="fp-pod-A and fp-pod-B both crash-looping due to OOM",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is True

    @pytest.mark.unit
    def test_alertname_fallback_only_when_no_fingerprint(self):
        """Alertname match is only a fallback for alerts without fingerprint."""
        alerts = [
            {"labels": {"alertname": "NodeMemoryPressure"}},
        ]
        diagnosis = _make_diagnosis(
            summary="NodeMemoryPressure detected on worker-1",
        )
        result = evaluate_completeness(diagnosis, alerts)
        assert result.complete is True


class TestCompletenessGateEvidenceLedger:
    """Tests for Finding R3-2: evidence examination verification."""

    @pytest.mark.unit
    def test_passes_when_all_evidence_examined(self):
        """Diagnosis passes when all evidence ledger items are referenced."""
        alerts = [
            {"fingerprint": "fp1", "labels": {"alertname": "TestAlert"}},
        ]
        ledger = [
            {"source": "mcp_cluster", "query": "get_resources Pod default", "type": "evidence"},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["fp1 get_resources Pod default check"],
            summary="TestAlert fp1 diagnosed — Pod default namespace",
        )
        result = evaluate_completeness(diagnosis, alerts, evidence_ledger=ledger)
        assert result.complete is True

    @pytest.mark.unit
    def test_fails_when_evidence_unexamined(self):
        """Diagnosis fails when gathered evidence is not referenced."""
        alerts = [
            {"fingerprint": "fp1", "labels": {"alertname": "TestAlert"}},
        ]
        ledger = [
            {"source": "mcp_cluster", "query": "describe_resource StorageClass ceph-rbd", "type": "evidence"},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["fp1 investigated TestAlert"],
            summary="TestAlert fp1 diagnosed",
        )
        result = evaluate_completeness(diagnosis, alerts, evidence_ledger=ledger)
        assert result.complete is False
        assert any("unexamined" in u for u in result.unaddressed_alerts)

    @pytest.mark.unit
    def test_passes_with_empty_ledger(self):
        """Empty evidence ledger does not block completion."""
        alerts = [
            {"fingerprint": "fp1", "labels": {"alertname": "TestAlert"}},
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["fp1 TestAlert investigated"],
        )
        result = evaluate_completeness(diagnosis, alerts, evidence_ledger=[])
        assert result.complete is True

    @pytest.mark.unit
    def test_result_summary_used_for_matching(self):
        """Gate checks result_summary content, not just query strings."""
        alerts = [
            {"fingerprint": "fp1", "labels": {"alertname": "TestAlert"}},
        ]
        ledger = [
            {
                "source": "mcp_cluster",
                "query": "get_resources Pod",
                "type": "evidence",
                "result_summary": "CrashLoopBackOff container=grafana restartCount=42",
                "no_hit": False,
            },
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["fp1 TestAlert CrashLoopBackOff grafana restartCount"],
            summary="TestAlert fp1 diagnosed — CrashLoopBackOff grafana",
        )
        result = evaluate_completeness(diagnosis, alerts, evidence_ledger=ledger)
        assert result.complete is True

    @pytest.mark.unit
    def test_runbook_no_hit_excluded_from_examination(self):
        """Runbook searches with no results should not count as positive evidence."""
        alerts = [
            {"fingerprint": "fp1", "labels": {"alertname": "TestAlert"}},
        ]
        ledger = [
            {
                "source": "runbook",
                "query": "CrashLoopBackOff troubleshooting",
                "type": "evidence",
                "result_summary": "",
                "no_hit": True,
            },
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["fp1 TestAlert investigated"],
            summary="TestAlert fp1 diagnosed",
        )
        result = evaluate_completeness(diagnosis, alerts, evidence_ledger=ledger)
        assert result.complete is True

    @pytest.mark.unit
    def test_fails_when_result_summary_not_in_diagnosis(self):
        """Gate fails when tool result content is not referenced in diagnosis."""
        alerts = [
            {"fingerprint": "fp1", "labels": {"alertname": "TestAlert"}},
        ]
        ledger = [
            {
                "source": "mcp_cluster",
                "query": "describe StorageClass ceph-rbd",
                "type": "evidence",
                "result_summary": "provisioner=rbd.csi.ceph.com reclaimPolicy=Delete",
                "no_hit": False,
            },
        ]
        diagnosis = _make_diagnosis(
            evidence_queries=["fp1 investigated TestAlert"],
            summary="TestAlert fp1 diagnosed — completely unrelated content",
        )
        result = evaluate_completeness(diagnosis, alerts, evidence_ledger=ledger)
        assert result.complete is False
        assert any("unexamined" in u for u in result.unaddressed_alerts)
