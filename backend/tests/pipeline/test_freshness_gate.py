"""Unit tests for the freshness gate (Story 3.5).

Tests: alert still firing → pass; alert resolved → stale.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.diagnosis import (
    EvidenceArtifact,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)
from src.pipeline.freshness_gate import FreshnessResult, check_freshness

pytestmark = pytest.mark.unit


def _make_artifact(incident_id=None) -> ImmutableDiagnosisArtifact:
    from datetime import datetime, timezone

    return ImmutableDiagnosisArtifact(
        id=uuid.uuid4(),
        incident_id=incident_id or uuid.uuid4(),
        root_cause_component="workload",
        failure_mode="crash-loop-backoff",
        root_cause_code="workload/crash-loop-backoff",
        causal_chain=("Pod CrashLoopBackOff",),
        affected_resources=("pod/test-pod",),
        evidence=(
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources",
                result="{}",
                timestamp=datetime.now(timezone.utc),
            ),
        ),
        confidence=0.9,
        agent_summary="OOM crash loop",
        skeptic_verdict={
            "passed": True,
            "rounds_completed": 1,
            "original_hash": "a" * 64,
            "final_hash": "a" * 64,
            "challenge_history": [],
            "verdict_reasoning": "ok",
        },
        sealed_at=datetime.now(timezone.utc),
    )


class TestFreshnessGateAlertFiring:
    """Alert still firing → freshness gate passes."""

    async def test_alert_still_firing_is_fresh(self):
        incident_id = uuid.uuid4()
        artifact = _make_artifact(incident_id)

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)

        result = await check_freshness(incident_id, artifact, conn)

        assert result.is_fresh is True
        assert result.alert_still_firing is True
        assert result.reason is None

    async def test_alert_resolved_is_stale(self):
        incident_id = uuid.uuid4()
        artifact = _make_artifact(incident_id)

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=1)

        result = await check_freshness(incident_id, artifact, conn)

        assert result.is_fresh is False
        assert result.alert_still_firing is False
        assert result.reason is not None
        assert "resolved" in result.reason.lower()

    async def test_multiple_resolved_alerts_is_stale(self):
        incident_id = uuid.uuid4()
        artifact = _make_artifact(incident_id)

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=3)

        result = await check_freshness(incident_id, artifact, conn)

        assert result.is_fresh is False
        assert result.alert_still_firing is False


class TestFreshnessGateDiagnosis:
    """Diagnosis relevance checks (conservative — defaults to relevant)."""

    async def test_diagnosis_assumed_relevant(self):
        incident_id = uuid.uuid4()
        artifact = _make_artifact(incident_id)

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)

        result = await check_freshness(incident_id, artifact, conn)

        assert result.diagnosis_still_relevant is True


class TestFreshnessResult:
    """FreshnessResult dataclass behavior."""

    def test_result_defaults(self):
        result = FreshnessResult(
            is_fresh=True,
            alert_still_firing=True,
            diagnosis_still_relevant=True,
        )
        assert result.reason is None
