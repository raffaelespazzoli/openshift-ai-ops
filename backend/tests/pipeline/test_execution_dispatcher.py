"""Unit tests for the execution dispatcher (Story 3.5, review round 1).

Tests: dispatch finds executing incidents; lock contention prevents concurrent
execution; state re-check prevents duplicates; stale freshness gates produce
terminal state.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.execution_settings import ExecutionSettings
from src.pipeline.execution_dispatcher import _dispatch_one, _execute_with_lock

pytestmark = pytest.mark.unit

FAST_SETTINGS = ExecutionSettings(
    observation_timeout_seconds=1,
    cooldown_seconds=0,
    refire_window_seconds=1,
    lock_poll_interval_seconds=1,
)


def _incident_row(incident_id: uuid.UUID | None = None) -> dict:
    iid = incident_id or uuid.uuid4()
    plan = {
        "incident_id": str(iid),
        "diagnosis_id": str(uuid.uuid4()),
        "steps": [
            {
                "order": 1,
                "description": "Apply fix",
                "command": "kubectl apply -f fix.yaml",
                "resource": "deployment/app",
                "action": "apply",
                "expected_outcome": "Deployment updated",
            }
        ],
        "blast_radius": "workload",
        "rollback_plan": [],
        "estimated_risk": "low",
        "plan_summary": "test plan",
    }
    return {
        "id": iid,
        "plan": json.dumps(plan),
        "plan_id": uuid.uuid4(),
    }


def _make_mock_pool(fetchrow_return=None):
    """Create a mock pool with async context manager support."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_conn.execute = AsyncMock()

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = _AsyncCtx(mock_conn)

    return mock_pool, mock_conn


class _AsyncCtx:
    """Minimal async context manager wrapping a value."""

    def __init__(self, val):
        self._val = val

    async def __aenter__(self):
        return self._val

    async def __aexit__(self, *args):
        pass


class _FakeTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class TestDispatchFindsExecutingIncident:
    """Dispatcher picks up an incident in 'executing' state."""

    async def test_dispatches_when_incident_found(self):
        incident_id = uuid.uuid4()
        row = _incident_row(incident_id)

        mock_pool, mock_conn = _make_mock_pool(fetchrow_return=row)

        with patch(
            "src.pipeline.execution_dispatcher.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            with patch(
                "src.pipeline.execution_dispatcher._execute_with_lock",
                new_callable=AsyncMock,
            ) as mock_exec:
                await _dispatch_one(FAST_SETTINGS)
                mock_exec.assert_called_once_with(incident_id, row, FAST_SETTINGS)

    async def test_no_op_when_no_incident(self):
        mock_pool, mock_conn = _make_mock_pool(fetchrow_return=None)

        with patch(
            "src.pipeline.execution_dispatcher.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            with patch(
                "src.pipeline.execution_dispatcher._execute_with_lock",
                new_callable=AsyncMock,
            ) as mock_exec:
                await _dispatch_one(FAST_SETTINGS)
                mock_exec.assert_not_called()


class TestLockContentionPreventsExecution:
    """When lock not available, execution is skipped."""

    async def test_lock_not_acquired_skips(self):
        incident_id = uuid.uuid4()
        row = _incident_row(incident_id)

        lock_conn = AsyncMock()
        lock_conn.transaction = MagicMock(return_value=_FakeTxn())

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = _AsyncCtx(lock_conn)

        with patch(
            "src.pipeline.execution_dispatcher.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            with patch(
                "src.pipeline.execution_dispatcher.acquire_remediation_lock",
                new_callable=AsyncMock,
                return_value=False,
            ):
                with patch(
                    "src.pipeline.execution_dispatcher._run_execution_cycle",
                    new_callable=AsyncMock,
                ) as mock_cycle:
                    await _execute_with_lock(incident_id, row, FAST_SETTINGS)
                    mock_cycle.assert_not_called()


class TestStateRecheckPreventsDuplicate:
    """After lock acquired, if incident moved out of executing state, skip."""

    async def test_incident_already_observing(self):
        incident_id = uuid.uuid4()
        row = _incident_row(incident_id)

        call_count = {"n": 0}

        lock_conn = AsyncMock()
        lock_conn.transaction = MagicMock(return_value=_FakeTxn())

        check_conn = AsyncMock()
        check_conn.fetchrow = AsyncMock(return_value={"state": "observing"})

        def _acquire_side_effect():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _AsyncCtx(lock_conn)
            return _AsyncCtx(check_conn)

        mock_pool = MagicMock()
        mock_pool.acquire.side_effect = _acquire_side_effect

        with patch(
            "src.pipeline.execution_dispatcher.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            with patch(
                "src.pipeline.execution_dispatcher.acquire_remediation_lock",
                new_callable=AsyncMock,
                return_value=True,
            ):
                with patch(
                    "src.pipeline.execution_dispatcher._run_execution_cycle",
                    new_callable=AsyncMock,
                ) as mock_cycle:
                    await _execute_with_lock(incident_id, row, FAST_SETTINGS)
                    mock_cycle.assert_not_called()

    async def test_incident_still_executing_proceeds(self):
        incident_id = uuid.uuid4()
        row = _incident_row(incident_id)

        call_count = {"n": 0}

        lock_conn = AsyncMock()
        lock_conn.transaction = MagicMock(return_value=_FakeTxn())

        check_conn = AsyncMock()
        check_conn.fetchrow = AsyncMock(return_value={"state": "executing"})

        def _acquire_side_effect():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _AsyncCtx(lock_conn)
            return _AsyncCtx(check_conn)

        mock_pool = MagicMock()
        mock_pool.acquire.side_effect = _acquire_side_effect

        with patch(
            "src.pipeline.execution_dispatcher.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            with patch(
                "src.pipeline.execution_dispatcher.acquire_remediation_lock",
                new_callable=AsyncMock,
                return_value=True,
            ):
                with patch(
                    "src.pipeline.execution_dispatcher.release_remediation_lock",
                    new_callable=AsyncMock,
                ):
                    with patch(
                        "src.pipeline.execution_dispatcher._run_execution_cycle",
                        new_callable=AsyncMock,
                    ) as mock_cycle:
                        await _execute_with_lock(incident_id, row, FAST_SETTINGS)
                        mock_cycle.assert_called_once()


class TestStaleFreshnessGateTerminal:
    """When freshness gate fails, incident reaches terminal state."""

    async def test_stale_incident_transitions_to_failed(self):
        incident_id = uuid.uuid4()
        row = _incident_row(incident_id)

        diagnosis_data = json.dumps({
            "id": str(uuid.uuid4()),
            "incident_id": str(incident_id),
            "root_cause_component": "workload",
            "failure_mode": "crash-loop",
            "root_cause_code": "workload/crash-loop",
            "causal_chain": ["OOM"],
            "affected_resources": ["pod/test"],
            "evidence": [],
            "confidence": 0.8,
            "agent_summary": "test diagnosis",
            "skeptic_verdict": {"approved": True, "reason": "test"},
            "sealed_at": "2026-08-10T00:00:00Z",
        })

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"diagnosis": diagnosis_data})
        mock_conn.execute = AsyncMock()
        mock_conn.transaction.return_value = _FakeTxn()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = _AsyncCtx(mock_conn)

        mock_freshness = MagicMock()
        mock_freshness.is_fresh = False
        mock_freshness.reason = "data too old"

        with patch(
            "src.pipeline.execution_dispatcher.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            with patch(
                "src.pipeline.freshness_gate.check_freshness",
                new_callable=AsyncMock,
                return_value=mock_freshness,
            ):
                with patch(
                    "src.pipeline.execution_dispatcher.transition_incident_state",
                    new_callable=AsyncMock,
                ) as mock_transition:
                    from src.pipeline.execution_dispatcher import _run_execution_cycle

                    await _run_execution_cycle(incident_id, row, FAST_SETTINGS)

                    calls = mock_transition.call_args_list
                    assert len(calls) >= 1
                    final_call = calls[-1]
                    assert final_call[0][3] == "failed"


class TestCaseRecordCreatedAfterOutcome:
    """Verify case record is created after outcome observation (Story 4.1)."""

    async def test_case_record_called_after_successful_outcome(self):
        incident_id = uuid.uuid4()
        row = _incident_row(incident_id)

        diagnosis_data = json.dumps({
            "id": str(uuid.uuid4()),
            "incident_id": str(incident_id),
            "root_cause_component": "workload",
            "failure_mode": "crash-loop",
            "root_cause_code": "workload/crash-loop",
            "causal_chain": ["OOM"],
            "affected_resources": [],
            "evidence": [],
            "confidence": 0.8,
            "agent_summary": "test",
            "skeptic_verdict": {"approved": True, "reason": "ok"},
            "sealed_at": "2026-08-10T00:00:00Z",
        })

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"diagnosis": diagnosis_data})
        mock_conn.execute = AsyncMock()
        mock_conn.transaction = MagicMock(return_value=_FakeTxn())

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = _AsyncCtx(mock_conn)

        mock_freshness = MagicMock()
        mock_freshness.is_fresh = True

        from src.models.execution import ExecutionLog, OutcomeResult

        mock_outcome = OutcomeResult(
            incident_id=incident_id,
            alert_resolved=True,
            resolution_method="webhook",
            outcome_confidence=0.7,
        )

        mock_exec_log = ExecutionLog(
            incident_id=incident_id,
            plan_id=uuid.uuid4(),
            status="completed",
        )

        with (
            patch(
                "src.pipeline.execution_dispatcher.get_pool",
                new_callable=AsyncMock, return_value=mock_pool,
            ),
            patch(
                "src.pipeline.freshness_gate.check_freshness",
                new_callable=AsyncMock, return_value=mock_freshness,
            ),
            patch(
                "src.pipeline.execution_dispatcher.execute_remediation",
                new_callable=AsyncMock, return_value=mock_exec_log,
            ),
            patch(
                "src.pipeline.execution_dispatcher.observe_outcome",
                new_callable=AsyncMock, return_value=mock_outcome,
            ),
            patch(
                "src.pipeline.execution_dispatcher.persist_execution_log",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.execution_dispatcher.persist_outcome_result",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.execution_dispatcher.transition_incident_state",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.execution_dispatcher.pipeline_audit_log",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.case_record_writer.create_case_record",
                new_callable=AsyncMock, return_value=MagicMock(),
            ) as mock_create_cr,
            patch(
                "src.pipeline.execution_dispatcher._emit_execution_event",
                new_callable=AsyncMock,
            ),
            patch(
                "src.pipeline.execution_dispatcher.monitor_for_refire",
                new_callable=AsyncMock,
            ),
        ):
            from src.pipeline.execution_dispatcher import _run_execution_cycle

            await _run_execution_cycle(incident_id, row, FAST_SETTINGS)
            mock_create_cr.assert_called_once_with(incident_id)


class TestRefireTriggersDowngrade:
    """Verify re-fire detection triggers case record downgrade (Story 4.1)."""

    async def test_refire_calls_downgrade(self):
        incident_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = _AsyncCtx(mock_conn)

        async def _fake_check(conn, iid):
            return True

        with (
            patch(
                "src.pipeline.outcome_observer.get_pool",
                new_callable=AsyncMock, return_value=mock_pool,
            ),
            patch(
                "src.pipeline.outcome_observer._check_alert_refired",
                side_effect=_fake_check,
            ),
            patch(
                "src.db.case_records.downgrade_case_record",
                new_callable=AsyncMock,
            ) as mock_downgrade,
        ):
            from src.pipeline.outcome_observer import monitor_for_refire

            result = await monitor_for_refire(
                incident_id, settings=FAST_SETTINGS, _sleep=AsyncMock(),
            )
            assert result is True
            mock_downgrade.assert_called_once()
            call_args = mock_downgrade.call_args
            assert call_args[0][1] == incident_id
            assert call_args[1]["new_confidence"] == 0.2
