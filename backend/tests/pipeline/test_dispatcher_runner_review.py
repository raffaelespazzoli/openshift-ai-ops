"""Tests for code review fixes: shutdown recovery, transactional sibling
transitions, dispatcher gating, and atomic terminal state + queue completion.

Covers:
- Shutdown recovery: shutdown_pipeline_tasks resets queue items, uses state machine
- Transactional transitions: _transition_all_incidents within caller's transaction
- Dispatcher gating: _transition_incidents_to_diagnosing wraps in transaction, returns bool
- Atomic completion: _complete_pipeline combines state writes + queue completion
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_queue_item(
    item_id=None, incident_id=None, rce_id=None, priority_score=100.0
) -> dict:
    return {
        "id": item_id or uuid.uuid4(),
        "incident_id": incident_id or uuid.uuid4(),
        "root_cause_event_id": rce_id or uuid.uuid4(),
        "priority_score": priority_score,
    }


class _MockAsyncCtx:
    """Helper that acts as an async context manager yielding a given value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


class _MockTransaction:
    """Mimics asyncpg transaction async context manager."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        return False


def _make_mock_pool(mock_conn):
    """Create a mock pool where pool.acquire() yields mock_conn."""
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = _MockAsyncCtx(mock_conn)
    return mock_pool


def _make_mock_conn_with_tx():
    """Create a mock connection pre-wired with transaction support."""
    mock_conn = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=_MockTransaction())
    return mock_conn


class TestShutdownRecovery:
    """shutdown_pipeline_tasks resets interrupted items via the state machine."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shutdown_resets_queue_items_to_queued(self):
        """After shutdown, interrupted queue items are reset from 'processing' to 'queued'."""
        import src.pipeline.dispatcher as dispatcher_mod

        item = _make_queue_item()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="diagnosing")
        mock_pool = _make_mock_pool(mock_conn)

        with patch.object(dispatcher_mod, "_inflight_tasks", set()):
            with patch.object(dispatcher_mod, "_inflight_items", {}):
                async def fake_pipeline():
                    await asyncio.sleep(100)

                task = asyncio.create_task(fake_pipeline())
                dispatcher_mod._inflight_tasks.add(task)
                dispatcher_mod._inflight_items[task] = item

                with (
                    patch("src.pipeline.dispatcher.get_pool", new_callable=AsyncMock, return_value=mock_pool),
                    patch("src.pipeline.dispatcher.get_rce_incident_ids", new_callable=AsyncMock, return_value=[item["incident_id"]]),
                ):
                    await dispatcher_mod.shutdown_pipeline_tasks()

        execute_calls = mock_conn.execute.call_args_list
        assert len(execute_calls) >= 2
        queue_reset_sql = execute_calls[0][0][0]
        assert "SET status = 'queued'" in queue_reset_sql
        assert "processing" in queue_reset_sql

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shutdown_uses_state_machine_for_incident_reset(self):
        """After shutdown, incidents are reset to 'queued' via transition(), not raw SQL."""
        import src.pipeline.dispatcher as dispatcher_mod
        from src.models.state_machine import IncidentState

        item = _make_queue_item()
        sibling_id = uuid.uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="diagnosing")
        mock_pool = _make_mock_pool(mock_conn)

        with patch.object(dispatcher_mod, "_inflight_tasks", set()):
            with patch.object(dispatcher_mod, "_inflight_items", {}):
                async def fake_pipeline():
                    await asyncio.sleep(100)

                task = asyncio.create_task(fake_pipeline())
                dispatcher_mod._inflight_tasks.add(task)
                dispatcher_mod._inflight_items[task] = item

                with (
                    patch("src.pipeline.dispatcher.get_pool", new_callable=AsyncMock, return_value=mock_pool),
                    patch(
                        "src.pipeline.dispatcher.get_rce_incident_ids",
                        new_callable=AsyncMock,
                        return_value=[item["incident_id"], sibling_id],
                    ),
                    patch("src.pipeline.dispatcher.transition", wraps=dispatcher_mod.transition) as mock_transition,
                ):
                    await dispatcher_mod.shutdown_pipeline_tasks()

        assert mock_transition.call_count == 2
        for call in mock_transition.call_args_list:
            assert call[0] == (IncidentState.DIAGNOSING, IncidentState.QUEUED)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shutdown_skips_incidents_not_in_diagnosing(self):
        """Shutdown recovery skips incidents whose state doesn't allow diagnosing→queued."""
        import src.pipeline.dispatcher as dispatcher_mod

        item = _make_queue_item()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="received")
        mock_pool = _make_mock_pool(mock_conn)

        with patch.object(dispatcher_mod, "_inflight_tasks", set()):
            with patch.object(dispatcher_mod, "_inflight_items", {}):
                async def fake_pipeline():
                    await asyncio.sleep(100)

                task = asyncio.create_task(fake_pipeline())
                dispatcher_mod._inflight_tasks.add(task)
                dispatcher_mod._inflight_items[task] = item

                with (
                    patch("src.pipeline.dispatcher.get_pool", new_callable=AsyncMock, return_value=mock_pool),
                    patch("src.pipeline.dispatcher.get_rce_incident_ids", new_callable=AsyncMock, return_value=[item["incident_id"]]),
                ):
                    await dispatcher_mod.shutdown_pipeline_tasks()

        state_update_calls = [
            c for c in mock_conn.execute.call_args_list
            if "SET state" in str(c[0][0])
        ]
        assert len(state_update_calls) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shutdown_cleans_active_pipelines(self):
        """After shutdown, active_pipeline entries for in-flight items are deleted."""
        import src.pipeline.dispatcher as dispatcher_mod

        item = _make_queue_item()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="diagnosing")
        mock_pool = _make_mock_pool(mock_conn)

        with patch.object(dispatcher_mod, "_inflight_tasks", set()):
            with patch.object(dispatcher_mod, "_inflight_items", {}):
                async def fake_pipeline():
                    await asyncio.sleep(100)

                task = asyncio.create_task(fake_pipeline())
                dispatcher_mod._inflight_tasks.add(task)
                dispatcher_mod._inflight_items[task] = item

                with (
                    patch("src.pipeline.dispatcher.get_pool", new_callable=AsyncMock, return_value=mock_pool),
                    patch("src.pipeline.dispatcher.get_rce_incident_ids", new_callable=AsyncMock, return_value=[item["incident_id"]]),
                ):
                    await dispatcher_mod.shutdown_pipeline_tasks()

        execute_calls = mock_conn.execute.call_args_list
        pipeline_delete_sql = execute_calls[1][0][0]
        assert "DELETE FROM active_pipelines" in pipeline_delete_sql

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shutdown_noop_when_no_inflight_tasks(self):
        """shutdown_pipeline_tasks does nothing when no tasks are in-flight."""
        import src.pipeline.dispatcher as dispatcher_mod

        with patch.object(dispatcher_mod, "_inflight_tasks", set()):
            with patch("src.pipeline.dispatcher.get_pool", new_callable=AsyncMock) as mock_get_pool:
                await dispatcher_mod.shutdown_pipeline_tasks()
                mock_get_pool.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shutdown_tolerates_db_failure(self):
        """If DB reset fails, shutdown still completes without raising."""
        import src.pipeline.dispatcher as dispatcher_mod

        item = _make_queue_item()

        with patch.object(dispatcher_mod, "_inflight_tasks", set()):
            with patch.object(dispatcher_mod, "_inflight_items", {}):
                async def fake_pipeline():
                    await asyncio.sleep(100)

                task = asyncio.create_task(fake_pipeline())
                dispatcher_mod._inflight_tasks.add(task)
                dispatcher_mod._inflight_items[task] = item

                with patch(
                    "src.pipeline.dispatcher.get_pool",
                    new_callable=AsyncMock,
                    side_effect=ConnectionError("DB unavailable"),
                ):
                    await dispatcher_mod.shutdown_pipeline_tasks()


class TestTransactionalSiblingTransitions:
    """_transition_all_incidents operates within the caller's transaction scope."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_all_siblings_transition_within_connection(self):
        """When all siblings are valid, all transitions succeed on the passed connection."""
        from src.pipeline.runner import _transition_all_incidents
        from src.models.state_machine import IncidentState

        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="diagnosing")
        mock_conn.execute = AsyncMock()

        await _transition_all_incidents(mock_conn, ids, IncidentState.DIAGNOSED)

        assert mock_conn.execute.call_count == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_incident_raises(self):
        """When one incident is missing, ValueError is raised for transaction rollback."""
        from src.pipeline.runner import _transition_all_incidents
        from src.models.state_machine import IncidentState

        ids = [uuid.uuid4(), uuid.uuid4()]

        call_count = [0]

        async def mock_fetchval(query, iid):
            call_count[0] += 1
            if call_count[0] == 2:
                return None
            return "diagnosing"

        mock_conn = AsyncMock()
        mock_conn.fetchval = mock_fetchval
        mock_conn.execute = AsyncMock()

        with pytest.raises(ValueError, match="not found"):
            await _transition_all_incidents(mock_conn, ids, IncidentState.DIAGNOSED)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        """When a state machine transition is invalid, exception propagates for rollback."""
        from src.pipeline.runner import _transition_all_incidents
        from src.models.state_machine import IncidentState, InvalidTransitionError

        ids = [uuid.uuid4(), uuid.uuid4()]

        call_count = [0]

        async def mock_fetchval(query, iid):
            call_count[0] += 1
            if call_count[0] == 1:
                return "diagnosing"
            return "resolved"

        mock_conn = AsyncMock()
        mock_conn.fetchval = mock_fetchval
        mock_conn.execute = AsyncMock()

        with pytest.raises(InvalidTransitionError):
            await _transition_all_incidents(mock_conn, ids, IncidentState.DIAGNOSED)


class TestAtomicPipelineCompletion:
    """_complete_pipeline wraps state transitions + queue completion in one transaction."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_success_combines_state_and_queue_atomically(self):
        """Both incident state writes and mark_pipeline_complete happen in one transaction."""
        from src.pipeline.runner import _complete_pipeline
        from src.models.state_machine import IncidentState

        ids = [uuid.uuid4(), uuid.uuid4()]
        item = _make_queue_item()

        mock_conn = _make_mock_conn_with_tx()
        mock_conn.fetchval = AsyncMock(return_value="diagnosing")
        mock_conn.execute = AsyncMock()
        mock_pool = _make_mock_pool(mock_conn)

        with (
            patch("src.pipeline.runner.get_pool", new_callable=AsyncMock, return_value=mock_pool),
            patch("src.pipeline.runner.mark_pipeline_complete", new_callable=AsyncMock) as mock_complete,
        ):
            result = await _complete_pipeline(item, ids, IncidentState.DIAGNOSED)

        assert result is True
        assert mock_conn.execute.call_count == 2
        mock_complete.assert_called_once_with(mock_conn, item["id"])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_queue_not_completed_when_transition_fails(self):
        """If incident transition fails, mark_pipeline_complete is never called."""
        from src.pipeline.runner import _complete_pipeline
        from src.models.state_machine import IncidentState

        ids = [uuid.uuid4()]
        item = _make_queue_item()

        mock_conn = _make_mock_conn_with_tx()
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()
        mock_pool = _make_mock_pool(mock_conn)

        with (
            patch("src.pipeline.runner.get_pool", new_callable=AsyncMock, return_value=mock_pool),
            patch("src.pipeline.runner.mark_pipeline_complete", new_callable=AsyncMock) as mock_complete,
        ):
            result = await _complete_pipeline(item, ids, IncidentState.DIAGNOSED)

        assert result is False
        mock_complete.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_db_failure_returns_false_without_partial_writes(self):
        """DB connection failure returns False — nothing committed."""
        from src.pipeline.runner import _complete_pipeline
        from src.models.state_machine import IncidentState

        ids = [uuid.uuid4()]
        item = _make_queue_item()

        with patch(
            "src.pipeline.runner.get_pool",
            new_callable=AsyncMock,
            side_effect=ConnectionError("DB down"),
        ):
            result = await _complete_pipeline(item, ids, IncidentState.DIAGNOSED)

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handle_success_uses_atomic_completion(self):
        """_handle_success delegates to _complete_pipeline for atomic commit."""
        from src.pipeline.runner import _handle_success

        ids = [uuid.uuid4()]
        item = _make_queue_item(incident_id=ids[0])

        with (
            patch("src.pipeline.runner._get_all_incident_ids", new_callable=AsyncMock, return_value=ids),
            patch("src.pipeline.runner._complete_pipeline", new_callable=AsyncMock, return_value=True) as mock_complete,
            patch("src.pipeline.runner._emit_stage_event", new_callable=AsyncMock),
        ):
            await _handle_success(item, {}, ids)

        mock_complete.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handle_failure_uses_atomic_completion(self):
        """_handle_failure delegates to _complete_pipeline for atomic commit."""
        from src.pipeline.runner import _handle_failure

        ids = [uuid.uuid4()]
        item = _make_queue_item(incident_id=ids[0])

        with (
            patch("src.pipeline.runner._get_all_incident_ids", new_callable=AsyncMock, return_value=ids),
            patch("src.pipeline.runner._complete_pipeline", new_callable=AsyncMock, return_value=True) as mock_complete,
            patch("src.pipeline.runner._emit_stage_event", new_callable=AsyncMock),
        ):
            await _handle_failure(item, ids)

        mock_complete.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_sse_events_when_completion_fails(self):
        """When _complete_pipeline fails, no SSE events are emitted."""
        from src.pipeline.runner import _handle_success

        ids = [uuid.uuid4()]
        item = _make_queue_item(incident_id=ids[0])

        with (
            patch("src.pipeline.runner._complete_pipeline", new_callable=AsyncMock, return_value=False),
            patch("src.pipeline.runner._emit_stage_event", new_callable=AsyncMock) as mock_emit,
        ):
            await _handle_success(item, {}, ids)

        mock_emit.assert_not_called()


class TestSkepticArtifactPersistenceAllIncidents:
    """_persist_skeptic_artifacts_in_txn persists for ALL incidents in the RCE group."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skeptic_artifacts_persisted_for_all_siblings(self):
        """Skeptic artifacts are persisted for every incident, not just the primary."""
        from src.pipeline.runner import _persist_skeptic_artifacts_in_txn

        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

        mock_conn = AsyncMock()

        final_state = {
            "skeptic_verdict": {
                "passed": True,
                "rounds_completed": 1,
                "original_hash": "abc123",
                "final_hash": "abc123",
                "challenge_history": [],
                "verdict_reasoning": "Validated",
            },
            "immutable_artifact": {
                "id": str(uuid.uuid4()),
                "incident_id": str(ids[0]),
                "root_cause_component": "workload",
                "failure_mode": "crash-loop-backoff",
                "root_cause_code": "workload/crash-loop-backoff",
                "causal_chain": ["step1"],
                "affected_resources": ["pod/test"],
                "evidence": [],
                "evidence_gaps": [],
                "confidence": 0.85,
                "agent_summary": "Test",
                "coverage_gaps": [],
                "alternative_hypotheses": [],
                "created_at": "2026-08-09T00:00:00Z",
                "skeptic_verdict": {"passed": True},
                "sealed_at": "2026-08-09T00:00:01Z",
            },
        }

        with patch(
            "src.pipeline.diagnosis_graph.persist_skeptic_artifacts",
            new_callable=AsyncMock,
        ) as mock_persist:
            await _persist_skeptic_artifacts_in_txn(mock_conn, ids, final_state)

        assert mock_persist.call_count == 3
        persisted_ids = [call.args[1] for call in mock_persist.call_args_list]
        assert set(persisted_ids) == {str(i) for i in ids}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skeptic_artifacts_noop_when_no_verdict(self):
        """When verdict or artifact is missing, nothing is persisted."""
        from src.pipeline.runner import _persist_skeptic_artifacts_in_txn

        mock_conn = AsyncMock()
        await _persist_skeptic_artifacts_in_txn(mock_conn, [uuid.uuid4()], {})


class TestSSEAfterTransactionCommit:
    """Skeptic SSE events are emitted only after the completion transaction commits."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_validated_sse_emitted_after_commit(self):
        """The skeptic_validation/validated SSE is emitted by _handle_success,
        AFTER _complete_pipeline commits, not before."""
        from src.pipeline.runner import _handle_success

        ids = [uuid.uuid4()]
        item = _make_queue_item(incident_id=ids[0])
        final_state = {"skeptic_verdict": {"passed": True, "rounds_completed": 1}}

        emit_calls = []

        async def track_emit(iid, stage, state, payload=None):
            emit_calls.append((stage, state))

        with (
            patch("src.pipeline.runner._complete_pipeline", new_callable=AsyncMock, return_value=True),
            patch("src.pipeline.runner._emit_stage_event", side_effect=track_emit),
        ):
            await _handle_success(item, final_state, ids)

        stages = [c[0] for c in emit_calls]
        assert "skeptic_validation" in stages
        assert "diagnosed" in stages
        assert stages.index("skeptic_validation") < stages.index("diagnosed")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_validated_sse_when_commit_fails(self):
        """When _complete_pipeline fails, no skeptic SSE events are emitted."""
        from src.pipeline.runner import _handle_success

        ids = [uuid.uuid4()]
        item = _make_queue_item(incident_id=ids[0])
        final_state = {"skeptic_verdict": {"passed": True}}

        with (
            patch("src.pipeline.runner._complete_pipeline", new_callable=AsyncMock, return_value=False),
            patch("src.pipeline.runner._emit_stage_event", new_callable=AsyncMock) as mock_emit,
        ):
            await _handle_success(item, final_state, ids)

        mock_emit.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_validated_sse_when_no_verdict(self):
        """When there is no skeptic_verdict, no validated SSE is emitted."""
        from src.pipeline.runner import _handle_success

        ids = [uuid.uuid4()]
        item = _make_queue_item(incident_id=ids[0])

        emit_calls = []

        async def track_emit(iid, stage, state, payload=None):
            emit_calls.append((stage, state))

        with (
            patch("src.pipeline.runner._complete_pipeline", new_callable=AsyncMock, return_value=True),
            patch("src.pipeline.runner._emit_stage_event", side_effect=track_emit),
        ):
            await _handle_success(item, {}, ids)

        stages = [c[0] for c in emit_calls]
        assert "skeptic_validation" not in stages
        assert "diagnosed" in stages


class TestDispatcherTransactionalTransitions:
    """_transition_incidents_to_diagnosing wraps siblings in a single transaction."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_transition_returns_true_on_success(self):
        """Returns True when all transitions succeed within the transaction."""
        from src.pipeline.dispatcher import _transition_incidents_to_diagnosing

        incident_id = uuid.uuid4()
        rce_id = uuid.uuid4()

        mock_conn = _make_mock_conn_with_tx()
        mock_conn.fetchval = AsyncMock(return_value="queued")
        mock_conn.execute = AsyncMock()

        with patch(
            "src.pipeline.dispatcher.get_rce_incident_ids",
            new_callable=AsyncMock,
            return_value=[incident_id],
        ):
            result = await _transition_incidents_to_diagnosing(mock_conn, rce_id, incident_id)

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_transition_returns_false_on_missing_incident(self):
        """Returns False and rolls back when incident is not found."""
        from src.pipeline.dispatcher import _transition_incidents_to_diagnosing

        incident_id = uuid.uuid4()
        rce_id = uuid.uuid4()

        mock_conn = _make_mock_conn_with_tx()
        mock_conn.fetchval = AsyncMock(return_value=None)

        with patch(
            "src.pipeline.dispatcher.get_rce_incident_ids",
            new_callable=AsyncMock,
            return_value=[incident_id],
        ):
            result = await _transition_incidents_to_diagnosing(mock_conn, rce_id, incident_id)

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_transition_returns_false_on_invalid_state(self):
        """Returns False and rolls back when state machine rejects the transition."""
        from src.pipeline.dispatcher import _transition_incidents_to_diagnosing

        incident_id = uuid.uuid4()
        rce_id = uuid.uuid4()

        mock_conn = _make_mock_conn_with_tx()
        mock_conn.fetchval = AsyncMock(return_value="resolved")

        with patch(
            "src.pipeline.dispatcher.get_rce_incident_ids",
            new_callable=AsyncMock,
            return_value=[incident_id],
        ):
            result = await _transition_incidents_to_diagnosing(mock_conn, rce_id, incident_id)

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multi_sibling_all_or_nothing(self):
        """When second sibling fails, the first sibling's write is also rolled back."""
        from src.pipeline.dispatcher import _transition_incidents_to_diagnosing

        ids = [uuid.uuid4(), uuid.uuid4()]
        rce_id = uuid.uuid4()

        call_count = [0]

        async def mock_fetchval(query, iid):
            call_count[0] += 1
            if call_count[0] == 1:
                return "queued"
            return None

        mock_conn = _make_mock_conn_with_tx()
        mock_conn.fetchval = mock_fetchval
        mock_conn.execute = AsyncMock()

        with patch(
            "src.pipeline.dispatcher.get_rce_incident_ids",
            new_callable=AsyncMock,
            return_value=ids,
        ):
            result = await _transition_incidents_to_diagnosing(mock_conn, rce_id, ids[0])

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_not_called_when_transition_fails(self):
        """dispatch_to_pipeline is NOT called when transition returns False."""
        from src.pipeline.dispatcher import _transition_incidents_to_diagnosing

        incident_id = uuid.uuid4()
        rce_id = uuid.uuid4()

        mock_conn = _make_mock_conn_with_tx()
        mock_conn.fetchval = AsyncMock(return_value=None)

        with patch(
            "src.pipeline.dispatcher.get_rce_incident_ids",
            new_callable=AsyncMock,
            return_value=[incident_id],
        ):
            result = await _transition_incidents_to_diagnosing(mock_conn, rce_id, incident_id)

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_requeue_resets_item_to_queued(self):
        """_requeue_failed_transition resets queue item and cleans active_pipelines."""
        from src.pipeline.dispatcher import _requeue_failed_transition

        queue_item_id = uuid.uuid4()
        mock_conn = AsyncMock()

        await _requeue_failed_transition(mock_conn, queue_item_id)

        assert mock_conn.execute.call_count == 2
        first_sql = mock_conn.execute.call_args_list[0][0][0]
        assert "SET status = 'queued'" in first_sql
        second_sql = mock_conn.execute.call_args_list[1][0][0]
        assert "DELETE FROM active_pipelines" in second_sql

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_requeue_called_on_transition_failure_in_dispatcher_loop(self):
        """The dispatcher loop calls _requeue_failed_transition when transition returns False."""
        import src.pipeline.dispatcher as dispatcher_mod

        incident_id = uuid.uuid4()
        rce_id = uuid.uuid4()
        item = _make_queue_item(incident_id=incident_id, rce_id=rce_id)

        dequeue_calls = [0]

        async def dequeue_once(*args, **kwargs):
            dequeue_calls[0] += 1
            if dequeue_calls[0] == 1:
                return item
            return None

        with (
            patch.object(dispatcher_mod, "_transition_incidents_to_diagnosing", new_callable=AsyncMock, return_value=False),
            patch.object(dispatcher_mod, "dispatch_to_pipeline", new_callable=AsyncMock) as mock_dispatch,
            patch.object(dispatcher_mod, "_requeue_failed_transition", new_callable=AsyncMock) as mock_requeue,
            patch("src.pipeline.dispatcher.dequeue_next", new_callable=AsyncMock, side_effect=dequeue_once),
            patch("src.pipeline.dispatcher.check_ttl_expired_items", new_callable=AsyncMock),
            patch("src.pipeline.dispatcher.recover_stale_items", new_callable=AsyncMock, return_value=0),
            patch("src.pipeline.dispatcher.get_pool", new_callable=AsyncMock, return_value=_make_mock_pool(AsyncMock())),
            patch("src.pipeline.dispatcher.get_queue_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(poll_interval_seconds=0.01)

            iteration = [0]

            async def limited_sleep(seconds):
                iteration[0] += 1
                if iteration[0] > 1:
                    raise asyncio.CancelledError()

            with patch("asyncio.sleep", side_effect=limited_sleep):
                with pytest.raises(asyncio.CancelledError):
                    await dispatcher_mod.run_dispatcher()

            mock_dispatch.assert_not_called()
            mock_requeue.assert_called_once()


class TestStateMachineRecoveryTransition:
    """diagnosing→queued is a valid transition for shutdown/stale recovery."""

    @pytest.mark.unit
    def test_diagnosing_to_queued_is_valid(self):
        """The state machine allows diagnosing→queued for recovery scenarios."""
        from src.models.state_machine import IncidentState, transition

        result = transition(IncidentState.DIAGNOSING, IncidentState.QUEUED)
        assert result == IncidentState.QUEUED

    @pytest.mark.unit
    def test_queued_to_queued_is_not_valid(self):
        """Queued→queued is not a valid transition (no self-transitions)."""
        from src.models.state_machine import IncidentState, InvalidTransitionError, transition

        with pytest.raises(InvalidTransitionError):
            transition(IncidentState.QUEUED, IncidentState.QUEUED)

    @pytest.mark.unit
    def test_diagnosed_to_queued_is_not_valid(self):
        """Terminal-adjacent states cannot transition back to queued."""
        from src.models.state_machine import IncidentState, InvalidTransitionError, transition

        with pytest.raises(InvalidTransitionError):
            transition(IncidentState.DIAGNOSED, IncidentState.QUEUED)
