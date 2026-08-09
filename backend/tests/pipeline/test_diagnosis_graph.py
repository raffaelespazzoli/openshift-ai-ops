"""Pipeline integration tests for the LangGraph diagnosis graph.

Tests graph compilation, execution with orchestrator agent (mocked LLM),
DiagnosisObject production, completeness gate, and state transitions.
Checkpoint tests require testcontainers (pytest -m pipeline).
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.models.diagnosis import DiagnosisObject
from src.pipeline.diagnosis_graph import (
    DiagnosisState,
    _completeness_routing,
    build_diagnosis_graph,
    completeness_gate_node,
    diagnose_node,
    finalize_node,
)


def _make_initial_state(incident_id: str | None = None) -> DiagnosisState:
    return {
        "incident_id": incident_id or str(uuid.uuid4()),
        "root_cause_event": {"id": str(uuid.uuid4()), "priority_score": 100.0},
        "alerts": [],
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


class TestGraphCompilation:
    """LangGraph graph compiles and runs with mocked diagnosis node."""

    @pytest.mark.unit
    def test_graph_builder_compiles(self):
        builder = build_diagnosis_graph()
        graph = builder.compile()
        assert graph is not None

    @pytest.mark.unit
    def test_graph_has_correct_nodes(self):
        builder = build_diagnosis_graph()
        graph = builder.compile()
        node_names = set(graph.nodes.keys())
        assert "diagnose" in node_names
        assert "completeness_gate" in node_names
        assert "finalize" in node_names


class TestDiagnoseNode:
    """The diagnose node invokes the orchestrator and produces a DiagnosisObject."""

    @pytest.mark.unit
    async def test_diagnose_produces_diagnosis(self, mock_orchestrator_agent):
        state = _make_initial_state()
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        assert "diagnosis" in result
        assert result["diagnosis"] is not None
        diag = DiagnosisObject.model_validate(result["diagnosis"])
        assert diag.confidence > 0.0

    @pytest.mark.unit
    async def test_diagnose_sets_stage_to_diagnosed(self, mock_orchestrator_agent):
        state = _make_initial_state()
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        assert result["stage"] == "diagnosed"

    @pytest.mark.unit
    async def test_diagnose_preserves_incident_id(self, mock_orchestrator_agent):
        incident_id = str(uuid.uuid4())
        state = _make_initial_state(incident_id=incident_id)
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        diag = DiagnosisObject.model_validate(result["diagnosis"])
        assert str(diag.incident_id) == incident_id

    @pytest.mark.unit
    async def test_diagnose_returns_coverage_gaps(self, mock_orchestrator_agent):
        state = _make_initial_state()
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        assert "coverage_gaps" in result

    @pytest.mark.unit
    async def test_diagnose_handles_orchestrator_failure(self):
        """When the orchestrator fails, a fallback diagnosis is produced."""
        state = _make_initial_state()
        with (
            patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock),
            patch(
                "src.agents.orchestrator.run_orchestrator",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Agent crashed"),
            ),
        ):
            result = await diagnose_node(state)

        assert result["diagnosis"] is not None
        diag = DiagnosisObject.model_validate(result["diagnosis"])
        assert diag.root_cause_code == "unknown/unclassified"
        assert diag.confidence == 0.0


class TestFinalizeNode:
    """Finalize node transitions state correctly."""

    @pytest.mark.unit
    async def test_finalize_sets_stage_to_finalized(self):
        state = _make_initial_state()
        state["stage"] = "diagnosed"
        with (
            patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock),
            patch("src.api.event_bus.get_event_bus", side_effect=ImportError("no bus")),
        ):
            result = await finalize_node(state)

        assert result["stage"] == "finalized"


class TestCompletenessRouting:
    """Tests for the graph-level completeness routing logic."""

    @pytest.mark.unit
    def test_routes_to_finalize_when_no_unaddressed(self):
        state = _make_initial_state()
        state["unaddressed_alerts"] = []
        state["completeness_attempts"] = 1
        assert _completeness_routing(state) == "finalize"

    @pytest.mark.unit
    def test_routes_to_orchestrate_when_unaddressed_and_retries_remain(self):
        state = _make_initial_state()
        state["unaddressed_alerts"] = ["alert-fp-123"]
        state["completeness_attempts"] = 1
        assert _completeness_routing(state) == "orchestrate"

    @pytest.mark.unit
    def test_routes_to_orchestrate_on_second_retry(self):
        state = _make_initial_state()
        state["unaddressed_alerts"] = ["alert-fp-123"]
        state["completeness_attempts"] = 2
        assert _completeness_routing(state) == "orchestrate"

    @pytest.mark.unit
    def test_routes_to_finalize_when_max_retries_exhausted(self):
        state = _make_initial_state()
        state["unaddressed_alerts"] = ["alert-fp-123"]
        state["completeness_attempts"] = 3
        assert _completeness_routing(state) == "finalize"


class TestCompletenessGateNode:
    """Tests for the completeness_gate_node function."""

    @pytest.mark.unit
    async def test_gate_passes_with_no_alerts(self, mock_orchestrator_agent):
        state = _make_initial_state()
        state["diagnosis"] = {
            "incident_id": state["incident_id"],
            "root_cause_component": "workload",
            "failure_mode": "crash-loop-backoff",
            "root_cause_code": "workload/crash-loop-backoff",
            "causal_chain": ["Test"],
            "affected_resources": [],
            "evidence": [],
            "evidence_gaps": [],
            "confidence": 0.8,
            "agent_summary": "Test diagnosis",
        }
        result = await completeness_gate_node(state)
        assert result["unaddressed_alerts"] == []

    @pytest.mark.unit
    async def test_gate_returns_unaddressed_when_incomplete(self):
        state = _make_initial_state()
        state["alerts"] = [
            {"fingerprint": "fp-missing", "labels": {"alertname": "MissingAlert"}},
        ]
        state["completeness_attempts"] = 1
        state["diagnosis"] = {
            "incident_id": state["incident_id"],
            "root_cause_component": "workload",
            "failure_mode": "crash-loop-backoff",
            "root_cause_code": "workload/crash-loop-backoff",
            "causal_chain": ["Different issue"],
            "affected_resources": [],
            "evidence": [],
            "evidence_gaps": [],
            "confidence": 0.5,
            "agent_summary": "Diagnosis about something else",
        }
        result = await completeness_gate_node(state)
        assert len(result["unaddressed_alerts"]) > 0


class TestGraphEndToEnd:
    """Graph runs end-to-end with mocked orchestrator, produces DiagnosisObject."""

    @pytest.mark.unit
    async def test_full_graph_execution(self, mock_orchestrator_agent):
        builder = build_diagnosis_graph()
        graph = builder.compile()
        initial = _make_initial_state()

        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            final = await graph.ainvoke(initial)

        assert final["stage"] == "finalized"
        assert final["diagnosis"] is not None
        diag = DiagnosisObject.model_validate(final["diagnosis"])
        assert diag.confidence > 0.0

    @pytest.mark.unit
    async def test_graph_state_transitions(self, mock_orchestrator_agent):
        """Verify state transitions: entered → diagnosed → finalized."""
        builder = build_diagnosis_graph()
        graph = builder.compile()
        initial = _make_initial_state()
        initial["stage"] = "entered"

        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            final = await graph.ainvoke(initial)

        assert final["stage"] == "finalized"

    @pytest.mark.unit
    async def test_graph_completeness_attempts_tracked(self, mock_orchestrator_agent):
        """Graph execution tracks completeness attempts."""
        builder = build_diagnosis_graph()
        graph = builder.compile()
        initial = _make_initial_state()

        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            final = await graph.ainvoke(initial)

        assert "completeness_attempts" in final
        assert final["completeness_attempts"] >= 1


class TestGraphCheckpoint:
    """Checkpoint tests — require testcontainers PostgreSQL (pytest -m pipeline)."""

    @pytest.mark.pipeline
    async def test_checkpoint_persisted(self, db_url, mock_orchestrator_agent):
        """Verify checkpoints are persisted to PostgreSQL."""
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        from src.pipeline.diagnosis_graph import build_diagnosis_graph

        pool = AsyncConnectionPool(
            conninfo=db_url,
            kwargs={"autocommit": True, "row_factory": dict_row},
            min_size=1,
            max_size=2,
        )
        await pool.open()

        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()

            builder = build_diagnosis_graph()
            graph = builder.compile(checkpointer=checkpointer)

            incident_id = str(uuid.uuid4())
            initial = _make_initial_state(incident_id=incident_id)
            config = {"configurable": {"thread_id": incident_id}}

            with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
                await graph.ainvoke(initial, config=config)

            async with pool.connection() as conn:
                tables = await conn.execute(
                    "SELECT tablename FROM pg_tables WHERE tablename LIKE 'checkpoint%'"
                )
                table_rows = await tables.fetchall()
                assert len(table_rows) > 0, "No langgraph checkpoint tables found"

        finally:
            await pool.close()

    @pytest.mark.pipeline
    async def test_checkpoint_resume_after_interruption(self, db_url, mock_orchestrator_agent):
        """Verify graph resumes from the last checkpoint after mid-run failure."""
        from langgraph.graph import END, StateGraph
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=db_url,
            kwargs={"autocommit": True, "row_factory": dict_row},
            min_size=1,
            max_size=2,
        )
        await pool.open()

        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()

            call_tracker: dict[str, int] = {"diagnose": 0, "finalize": 0}

            async def tracking_diagnose(state: DiagnosisState) -> dict:
                call_tracker["diagnose"] += 1
                return await diagnose_node(state)

            async def tracking_finalize(state: DiagnosisState) -> dict:
                call_tracker["finalize"] += 1
                if call_tracker["finalize"] == 1:
                    raise RuntimeError("Simulated pod crash after diagnose checkpoint")
                return await finalize_node(state)

            builder = StateGraph(DiagnosisState)
            builder.add_node("diagnose", tracking_diagnose)
            builder.add_node("finalize", tracking_finalize)
            builder.add_edge("diagnose", "finalize")
            builder.add_edge("finalize", END)
            builder.set_entry_point("diagnose")
            graph = builder.compile(checkpointer=checkpointer)

            incident_id = str(uuid.uuid4())
            initial = _make_initial_state(incident_id=incident_id)
            config = {"configurable": {"thread_id": incident_id}}

            with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
                with pytest.raises(RuntimeError, match="Simulated pod crash"):
                    await graph.ainvoke(initial, config=config)

            assert call_tracker["diagnose"] == 1
            assert call_tracker["finalize"] == 1

            with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
                result = await graph.ainvoke(initial, config=config)

            assert result["stage"] == "finalized"
            assert call_tracker["diagnose"] == 1
            assert call_tracker["finalize"] == 2

        finally:
            await pool.close()
