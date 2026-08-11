"""Unit tests for outcome observer (Story 3.5).

Tests: webhook resolves → resolved with high confidence; timeout → failed;
verification pass/fail affects confidence score.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.config.execution_settings import ExecutionSettings
from src.models.diagnosis import (
    EvidenceArtifact,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)
from src.models.execution import ExecutionLog, ExecutionStepLog, OutcomeConfidence
from src.pipeline.outcome_observer import observe_outcome

pytestmark = pytest.mark.unit


def _make_artifact(incident_id=None) -> ImmutableDiagnosisArtifact:
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


def _make_execution_log(incident_id) -> ExecutionLog:
    return ExecutionLog(
        incident_id=incident_id,
        plan_id=uuid.uuid4(),
        steps=[
            ExecutionStepLog(
                step_order=1,
                command="kubectl apply",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                success=True,
                output="applied",
            )
        ],
        status="completed",
    )


def _fast_settings() -> ExecutionSettings:
    return ExecutionSettings(
        observation_timeout_seconds=1,
        cooldown_seconds=0,
        refire_window_seconds=1,
        lock_poll_interval_seconds=1,
    )


class TestOutcomeWebhookResolved:
    """Webhook resolves → resolved with high confidence."""

    async def test_webhook_and_verification_confidence_1_0(self):
        incident_id = uuid.uuid4()
        artifact = _make_artifact(incident_id)
        execution_log = _make_execution_log(incident_id)

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        mock_pool = AsyncMock()
        mock_pool.acquire = lambda: _AsyncCtx(mock_conn)

        async def instant_sleep(_):
            pass

        with (
            patch(
                "src.pipeline.outcome_observer.get_pool",
                new_callable=AsyncMock,
                return_value=mock_pool,
            ),
            patch(
                "src.pipeline.outcome_observer._verify_affected_resources",
                new_callable=AsyncMock,
                return_value={"all_healthy": True, "resources": []},
            ),
        ):
            result = await observe_outcome(
                incident_id, artifact, execution_log,
                settings=_fast_settings(),
                _sleep=instant_sleep,
            )

        assert result.alert_resolved is True
        assert result.outcome_confidence == OutcomeConfidence.BOTH
        assert result.resolution_method == "webhook"

    async def test_webhook_only_confidence_0_7(self):
        incident_id = uuid.uuid4()
        artifact = _make_artifact(incident_id)
        execution_log = _make_execution_log(incident_id)

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        mock_pool = AsyncMock()
        mock_pool.acquire = lambda: _AsyncCtx(mock_conn)

        async def instant_sleep(_):
            pass

        with (
            patch(
                "src.pipeline.outcome_observer.get_pool",
                new_callable=AsyncMock,
                return_value=mock_pool,
            ),
            patch(
                "src.pipeline.outcome_observer._verify_affected_resources",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await observe_outcome(
                incident_id, artifact, execution_log,
                settings=_fast_settings(),
                _sleep=instant_sleep,
            )

        assert result.alert_resolved is True
        assert result.outcome_confidence == OutcomeConfidence.WEBHOOK_ONLY

    async def test_verification_only_confidence_0_5(self):
        incident_id = uuid.uuid4()
        artifact = _make_artifact(incident_id)
        execution_log = _make_execution_log(incident_id)

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=0)

        mock_pool = AsyncMock()
        mock_pool.acquire = lambda: _AsyncCtx(mock_conn)

        fake_now = datetime(2025, 1, 1, tzinfo=timezone.utc)

        async def time_advancing_sleep(_duration):
            nonlocal fake_now
            fake_now += timedelta(seconds=10)

        settings = ExecutionSettings(
            observation_timeout_seconds=1,
            cooldown_seconds=0,
            refire_window_seconds=0,
            lock_poll_interval_seconds=1,
        )

        with (
            patch(
                "src.pipeline.outcome_observer.get_pool",
                new_callable=AsyncMock,
                return_value=mock_pool,
            ),
            patch(
                "src.pipeline.outcome_observer._verify_affected_resources",
                new_callable=AsyncMock,
                return_value={"all_healthy": True, "resources": []},
            ),
            patch(
                "src.pipeline.outcome_observer.datetime",
                wraps=datetime,
            ) as mock_dt,
        ):
            mock_dt.now = lambda tz=None: fake_now
            result = await observe_outcome(
                incident_id, artifact, execution_log,
                settings=settings,
                _sleep=time_advancing_sleep,
            )

        assert result.alert_resolved is False
        assert result.outcome_confidence == OutcomeConfidence.VERIFICATION_ONLY
        assert result.resolution_method == "verification"


class TestOutcomeTimeout:
    """Timeout → confidence 0.2."""

    async def test_timeout_confidence_0_2(self):
        incident_id = uuid.uuid4()
        artifact = _make_artifact(incident_id)
        execution_log = _make_execution_log(incident_id)

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=0)

        mock_pool = AsyncMock()
        mock_pool.acquire = lambda: _AsyncCtx(mock_conn)

        settings = ExecutionSettings(
            observation_timeout_seconds=1,
            cooldown_seconds=0,
            refire_window_seconds=0,
            lock_poll_interval_seconds=1,
        )

        async def instant_sleep(_):
            pass

        with (
            patch(
                "src.pipeline.outcome_observer.get_pool",
                new_callable=AsyncMock,
                return_value=mock_pool,
            ),
            patch(
                "src.pipeline.outcome_observer._verify_affected_resources",
                new_callable=AsyncMock,
                return_value={"all_healthy": False, "resources": []},
            ),
        ):
            result = await observe_outcome(
                incident_id, artifact, execution_log,
                settings=settings,
                _sleep=instant_sleep,
            )

        assert result.alert_resolved is False
        assert result.outcome_confidence == OutcomeConfidence.TIMEOUT
        assert result.resolution_method == "timeout"


class _AsyncCtx:
    """Helper async context manager for mocking pool.acquire()."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        pass
