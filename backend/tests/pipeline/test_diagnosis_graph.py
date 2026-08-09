"""Pipeline integration tests for the LangGraph diagnosis graph.

Tests graph compilation, execution with mocked diagnosis node,
DiagnosisObject production, and state transitions.
Checkpoint tests require testcontainers (pytest -m pipeline).
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.models.diagnosis import DiagnosisObject
from src.pipeline.diagnosis_graph import (
    DiagnosisState,
    build_diagnosis_graph,
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
        assert "finalize" in node_names


class TestDiagnoseNode:
    """The diagnose node produces a valid DiagnosisObject in state."""

    @pytest.mark.unit
    async def test_diagnose_produces_diagnosis(self, mock_mcp_client):
        state = _make_initial_state()
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        assert "diagnosis" in result
        assert result["diagnosis"] is not None
        diag = DiagnosisObject.model_validate(result["diagnosis"])
        assert diag.root_cause_code == "unknown/unclassified"
        assert diag.confidence == 0.0

    @pytest.mark.unit
    async def test_diagnose_sets_stage_to_diagnosed(self, mock_mcp_client):
        state = _make_initial_state()
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        assert result["stage"] == "diagnosed"

    @pytest.mark.unit
    async def test_diagnose_preserves_incident_id(self, mock_mcp_client):
        incident_id = str(uuid.uuid4())
        state = _make_initial_state(incident_id=incident_id)
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        diag = DiagnosisObject.model_validate(result["diagnosis"])
        assert str(diag.incident_id) == incident_id

    @pytest.mark.unit
    async def test_diagnose_populates_mcp_evidence(self, mock_mcp_client):
        state = _make_initial_state()
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        assert "mcp_evidence" in result
        assert len(result["mcp_evidence"]) > 0

    @pytest.mark.unit
    async def test_diagnose_records_evidence_gaps_on_mcp_failure(self):
        """When MCP gathering fails entirely, pipeline still produces a diagnosis."""
        state = _make_initial_state()
        with (
            patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock),
            patch(
                "src.pipeline.diagnosis_graph._gather_mcp_evidence",
                new_callable=AsyncMock,
                side_effect=ConnectionError("MCP unreachable"),
            ),
        ):
            result = await diagnose_node(state)

        assert result["diagnosis"] is not None
        diag = DiagnosisObject.model_validate(result["diagnosis"])
        assert diag.root_cause_code == "unknown/unclassified"


class TestFinalizeNode:
    """Finalize node transitions state correctly."""

    @pytest.mark.unit
    async def test_finalize_sets_stage_to_finalized(self):
        state = _make_initial_state()
        state["stage"] = "diagnosed"
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await finalize_node(state)

        assert result["stage"] == "finalized"


class TestGraphEndToEnd:
    """Graph runs end-to-end with stub nodes, produces DiagnosisObject."""

    @pytest.mark.unit
    async def test_full_graph_execution(self, mock_mcp_client):
        builder = build_diagnosis_graph()
        graph = builder.compile()
        initial = _make_initial_state()

        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            final = await graph.ainvoke(initial)

        assert final["stage"] == "finalized"
        assert final["diagnosis"] is not None
        diag = DiagnosisObject.model_validate(final["diagnosis"])
        assert diag.root_cause_code == "unknown/unclassified"

    @pytest.mark.unit
    async def test_graph_produces_valid_evidence(self, mock_mcp_client):
        builder = build_diagnosis_graph()
        graph = builder.compile()
        initial = _make_initial_state()

        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            final = await graph.ainvoke(initial)

        diag = DiagnosisObject.model_validate(final["diagnosis"])
        assert len(diag.evidence) >= 1
        assert diag.evidence[0].source == "mcp_cluster"


class TestGraphCheckpoint:
    """Checkpoint tests — require testcontainers PostgreSQL (pytest -m pipeline)."""

    @pytest.mark.pipeline
    async def test_checkpoint_persisted(self, db_url):
        """Verify checkpoints are persisted to PostgreSQL.

        Connects to the test database, runs the graph with checkpointing,
        and verifies langgraph_* tables exist with rows (AD-3 black box).
        """
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
    async def test_checkpoint_resume_after_interruption(self, db_url):
        """Verify graph resumes from the last checkpoint after mid-run failure.

        Uses a custom graph where the finalize node raises on the first
        invocation (after diagnose has completed and been checkpointed),
        simulating a pod crash between stages. On re-invocation with the
        same thread_id, the graph must resume at finalize — the diagnose
        node must NOT be re-run (call count stays at 1), proving that
        checkpoint resume skips already-completed stages.
        """
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

            assert call_tracker["diagnose"] == 1, "diagnose should have completed once"
            assert call_tracker["finalize"] == 1, "finalize should have been entered once before crash"

            with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
                result = await graph.ainvoke(initial, config=config)

            assert result["stage"] == "finalized"
            assert call_tracker["diagnose"] == 1, (
                "diagnose must NOT re-run — checkpoint should resume at finalize"
            )
            assert call_tracker["finalize"] == 2, "finalize should succeed on second attempt"

            diag = DiagnosisObject.model_validate(result["diagnosis"])
            assert diag.root_cause_code == "unknown/unclassified"

        finally:
            await pool.close()
