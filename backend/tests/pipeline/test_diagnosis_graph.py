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


class TestMultiSourceEvidence:
    """Tests for multi-source evidence with RHOKP, Learning Store, and skills."""

    @pytest.mark.unit
    async def test_orchestrator_tools_include_new_sources(self):
        """Orchestrator tool list includes RHOKP, Learning Store, and skill tools."""
        from src.agents.tools import get_orchestrator_tools

        tools = get_orchestrator_tools()
        names = {t.name for t in tools}
        assert "search_rhokp" in names
        assert "get_rhokp_document" in names
        assert "query_past_incidents" in names

    @pytest.mark.unit
    async def test_diagnosis_with_rhokp_evidence(self, mock_orchestrator_agent):
        """Orchestrator produces diagnosis when RHOKP tools are available."""
        state = _make_initial_state()
        with patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock):
            result = await diagnose_node(state)

        assert result["diagnosis"] is not None
        diag = DiagnosisObject.model_validate(result["diagnosis"])
        assert diag.confidence > 0.0

    @pytest.mark.unit
    async def test_missing_rhokp_produces_evidence_gap(self):
        """When RHOKP is unavailable, diagnosis proceeds with other sources."""
        from src.agents.tools import search_rhokp, set_rhokp_client
        from src.knowledge.rhokp_client import RHOKPClient
        from src.models.diagnosis import EvidenceGap

        mock_client = AsyncMock(spec=RHOKPClient)
        mock_client.search_portal = AsyncMock(return_value={
            "success": False,
            "evidence_gap": EvidenceGap(
                query="search_portal(['test'])",
                reason="RHOKP connection refused",
            ),
        })
        set_rhokp_client(mock_client)

        try:
            result = await search_rhokp.ainvoke({"queries": ["test"]})
            assert result["type"] == "evidence_gap"
            assert result["source"] == "rhokp"
        finally:
            set_rhokp_client(None)

    @pytest.mark.unit
    async def test_empty_learning_store_no_evidence_gap(self):
        """Empty Learning Store returns evidence (not gap) — expected on fresh deploy."""
        from contextlib import asynccontextmanager

        from src.agents.tools import query_past_incidents

        mock_conn = AsyncMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool = AsyncMock()
        mock_pool.acquire = mock_acquire

        with (
            patch("src.agents.tools._get_db_pool", new_callable=AsyncMock, return_value=mock_pool),
            patch("pgvector.asyncpg.register_vector", new_callable=AsyncMock),
            patch(
                "src.knowledge.learning_store.query_learning_store",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await query_past_incidents.ainvoke({"alert_context": "test"})

        assert result["type"] == "evidence"
        assert result["source"] == "learning_store"
        assert result["cases"] == []

    @pytest.mark.unit
    async def test_no_skills_directory_proceeds_without_skills(self):
        """When skills directory is missing, orchestrator proceeds with other tools."""
        from src.agents.orchestrator import _get_skill_tools, set_skill_registry
        from src.config.skills_settings import SkillsSettings
        from src.knowledge.skills import SkillRegistry

        settings = SkillsSettings(skills_directory="/nonexistent/path")
        registry = SkillRegistry(settings=settings)
        set_skill_registry(registry)

        try:
            skill_tools = _get_skill_tools()
            assert skill_tools == []
        finally:
            set_skill_registry(None)

    @pytest.mark.unit
    async def test_multi_source_evidence_attribution(self):
        """DiagnosisObject.evidence contains entries from all knowledge sources (AC #6, Task 10.2).

        Constructs a DiagnosisObject with evidence from MCP, runbook, RHOKP,
        Learning Store, and agentic skill sources and verifies all
        EvidenceSource values appear in the evidence array.
        """
        from datetime import datetime, timezone

        from src.models.diagnosis import EvidenceArtifact, EvidenceSource

        now = datetime.now(timezone.utc)

        multi_source_evidence = [
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources({'kind': 'Pod'})",
                result='{"items": [{"status": {"phase": "CrashLoopBackOff"}}]}',
                timestamp=now,
            ),
            EvidenceArtifact(
                source=EvidenceSource.RUNBOOK,
                query="search_runbooks('OOMKilled pod')",
                result="Runbook: Check memory limits and requests configuration",
                timestamp=now,
            ),
            EvidenceArtifact(
                source=EvidenceSource.RHOKP,
                query="search_portal(['OOMKilled', 'memory pressure'])",
                result='{"results": [{"id": "doc-1", "title": "Memory management"}]}',
                timestamp=now,
            ),
            EvidenceArtifact(
                source=EvidenceSource.LEARNING_STORE,
                query="query_past_incidents('KubePodCrashLooping')",
                result='{"cases": [{"root_cause_code": "workload/oom-killed", "confidence": 0.82}]}',
                timestamp=now,
            ),
            EvidenceArtifact(
                source=EvidenceSource.AGENTIC_SKILL,
                query="skill_cluster-troubleshoot(check memory usage)",
                result='{"memory_usage": "92%", "eviction_threshold": "100Mi"}',
                timestamp=now,
            ),
        ]

        incident_id = uuid.uuid4()
        diag = DiagnosisObject(
            incident_id=incident_id,
            root_cause_component="workload",
            failure_mode="oom-killed",
            root_cause_code="workload/oom-killed",
            causal_chain=["Container OOMKilled due to memory limit exceeded"],
            affected_resources=["pod/test-app-xyz-123"],
            evidence=multi_source_evidence,
            confidence=0.92,
            agent_summary="Pod OOM killed — all knowledge sources contributed evidence",
        )

        evidence_sources = {e.source for e in diag.evidence}
        assert EvidenceSource.MCP_CLUSTER in evidence_sources
        assert EvidenceSource.RUNBOOK in evidence_sources
        assert EvidenceSource.RHOKP in evidence_sources
        assert EvidenceSource.LEARNING_STORE in evidence_sources
        assert EvidenceSource.AGENTIC_SKILL in evidence_sources
        assert len(evidence_sources) == 5
        assert len(diag.evidence) == 5

    @pytest.mark.unit
    async def test_multi_source_evidence_via_mock_orchestrator(self):
        """Orchestrator mock producing multi-source evidence validates through the graph.

        Verifies the end-to-end flow: a mock orchestrator returning evidence
        from all five sources produces a valid DiagnosisObject with all
        EvidenceSource values present.
        """
        from datetime import datetime, timezone

        from src.models.diagnosis import EvidenceArtifact, EvidenceSource

        now = datetime.now(timezone.utc)

        all_source_evidence = [
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources({'kind': 'Pod'})",
                result='{"status": {"phase": "CrashLoopBackOff"}}',
                timestamp=now,
            ),
            EvidenceArtifact(
                source=EvidenceSource.RUNBOOK,
                query="search_runbooks('crash loop')",
                result="Runbook: Restart policy checks",
                timestamp=now,
            ),
            EvidenceArtifact(
                source=EvidenceSource.RHOKP,
                query="search_portal(['crash loop'])",
                result='{"results": [{"id": "rhokp-1"}]}',
                timestamp=now,
            ),
            EvidenceArtifact(
                source=EvidenceSource.LEARNING_STORE,
                query="query_past_incidents('CrashLoopBackOff')",
                result='{"cases": []}',
                timestamp=now,
            ),
            EvidenceArtifact(
                source=EvidenceSource.AGENTIC_SKILL,
                query="skill_node-diag(check node health)",
                result='{"node_status": "Ready"}',
                timestamp=now,
            ),
        ]

        async def mock_run_with_all_sources(state, config=None):
            incident_id = state.get("incident_id", str(uuid.uuid4()))
            diagnosis = DiagnosisObject(
                incident_id=uuid.UUID(incident_id),
                root_cause_component="workload",
                failure_mode="crash-loop-backoff",
                root_cause_code="workload/crash-loop-backoff",
                causal_chain=["Pod CrashLoopBackOff due to config error"],
                affected_resources=["pod/app-xyz-123"],
                evidence=all_source_evidence,
                confidence=0.90,
                agent_summary="Crash loop diagnosed with evidence from all sources",
            )
            return {
                "diagnosis": diagnosis.model_dump(mode="json"),
                "runbook_context": [],
                "completeness_attempts": state.get("completeness_attempts", 0) + 1,
                "coverage_gaps": [],
                "rejected_hypotheses": [],
                "evidence_ledger": [],
                "stage": "diagnosed",
            }

        state = _make_initial_state()
        with (
            patch("src.pipeline.diagnosis_graph.pipeline_audit_log", new_callable=AsyncMock),
            patch("src.agents.orchestrator.run_orchestrator", side_effect=mock_run_with_all_sources),
        ):
            result = await diagnose_node(state)

        assert result["diagnosis"] is not None
        diag = DiagnosisObject.model_validate(result["diagnosis"])
        evidence_sources = {e.source for e in diag.evidence}
        assert evidence_sources == {
            EvidenceSource.MCP_CLUSTER,
            EvidenceSource.RUNBOOK,
            EvidenceSource.RHOKP,
            EvidenceSource.LEARNING_STORE,
            EvidenceSource.AGENTIC_SKILL,
        }
        assert len(diag.evidence) == 5
        assert diag.confidence == 0.90
