# Story 2.3: RHOKP, Learning Store & Agentic Skills Integration

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want diagnosis enriched with Red Hat platform knowledge, past incident experience, and executable operational skills,
so that the system leverages all available knowledge sources for deeper, more accurate root-cause analysis.

## Acceptance Criteria

1. **Given** the RHOKP Solr instance is deployed with 600k+ Red Hat knowledge base documents **When** the Orchestrator needs platform-level guidance during diagnosis **Then** it queries RHOKP via the okp-mcp MCP server using Streamable HTTP transport **And** uses the `search_portal` tool for multi-query search with reciprocal rank fusion and `get_document` for full content retrieval with BM25-scored passage extraction

2. **Given** past Case Records exist in the Learning Store (populated by Epic 4) **When** the Orchestrator diagnoses a new Root-Cause Event **Then** it queries pgvector for Case Records matching the current alert signature via embedding similarity **And** relevant past diagnoses and outcomes inform the current investigation

3. **Given** no past Case Records exist yet (fresh deployment) **When** the Learning Store is queried **Then** the query returns empty results gracefully and diagnosis proceeds with other knowledge sources

4. **Given** agentic skills are available (e.g., cluster-update checks, token discovery, node diagnostics) **When** the Orchestrator determines a skill is relevant during diagnosis **Then** it invokes the skill as a callable tool **And** the skill executes under the `cluster-reader` ServiceAccount (read-only enforcement)

5. **Given** a skill that requires write access exists **When** the Orchestrator attempts to use it during diagnosis **Then** the skill is classified as remediation-only and is unavailable — the invocation is blocked

6. **Given** the Orchestrator uses multiple knowledge sources during diagnosis **When** the Structured Diagnosis Object is produced **Then** the evidence array distinguishes the source of each artifact (MCP cluster query, runbook, RHOKP, Learning Store, agentic skill)

## Tasks / Subtasks

- [ ] Task 1: RHOKP MCP client (AC: #1, #6)
  - [ ] 1.1 Create `backend/src/knowledge/rhokp_client.py` — `RHOKPClient` wrapping the MCP Python SDK Streamable HTTP transport to `http://okp-mcp:8000/mcp`
  - [ ] 1.2 Implement `search_portal(queries: list[str], top_k: int) -> list[dict]` — multi-query search with reciprocal rank fusion results
  - [ ] 1.3 Implement `get_document(doc_id: str) -> dict` — full content retrieval with BM25-scored passage extraction
  - [ ] 1.4 Implement timeout handling producing `EvidenceGap` objects (consistent with `ReadOnlyMCPClient` pattern from 2.1)
  - [ ] 1.5 Create `backend/src/config/rhokp_settings.py` — `RHOKPSettings` (URL, timeout, top_k defaults)

- [ ] Task 2: RHOKP orchestrator tools (AC: #1, #6)
  - [ ] 2.1 Add `search_rhokp(query: str, top_k: int = 5) -> str` to `backend/src/agents/tools.py` — `@tool`-decorated, wraps `RHOKPClient.search_portal()`, returns formatted search results, records `EvidenceArtifact` with `source=EvidenceSource.RHOKP`
  - [ ] 2.2 Add `get_rhokp_document(doc_id: str) -> str` to `backend/src/agents/tools.py` — `@tool`-decorated, wraps `RHOKPClient.get_document()`, returns document content, records `EvidenceArtifact` with `source=EvidenceSource.RHOKP`

- [ ] Task 3: Learning Store query interface (AC: #2, #3, #6)
  - [ ] 3.1 Create `backend/src/models/case_record.py` — `CaseRecordSummary` Pydantic model (minimal read-only projection: id, alert_signature, root_cause_code, outcome, outcome_confidence, ocp_version, created_at, embedding). Full schema is Epic 4's responsibility.
  - [ ] 3.2 Create Alembic migration for `case_records` table with pgvector HNSW index (minimal schema: id, alert_signature_embedding, root_cause_code, outcome, outcome_confidence, ocp_version, created_at). Table is empty until Epic 4 populates it. Schema ownership per AD-20: owned by Learning Store module in `db/`.
  - [ ] 3.3 Create `backend/src/db/case_records.py` — `search_similar_cases(conn, query_embedding, top_k, similarity_threshold) -> list[dict]` using pgvector `<=>` cosine distance. Read-only: no inserts/updates (Epic 4 writes).
  - [ ] 3.4 Create `backend/src/knowledge/learning_store.py` — `query_learning_store(alert_context: str, conn, top_k: int = 3) -> list[CaseRecordSummary]`. Embeds the alert context, queries pgvector, applies temporal decay formula `effective_confidence = base_confidence × decay_factor(age) × version_relevance(ocp_version)`, returns ranked results. Returns empty list gracefully when no records exist.

- [ ] Task 4: Learning Store orchestrator tool (AC: #2, #3, #6)
  - [ ] 4.1 Add `query_past_incidents(alert_context: str, top_k: int = 3) -> str` to `backend/src/agents/tools.py` — `@tool`-decorated, wraps `learning_store.query_learning_store()`, records `EvidenceArtifact` with `source=EvidenceSource.LEARNING_STORE`
  - [ ] 4.2 Format results to include: past root-cause code, outcome (success/failure), effective confidence, time since occurrence

- [ ] Task 5: Agentic skills loader and registry (AC: #4, #5)
  - [ ] 5.1 Create `backend/src/knowledge/skills.py` — `SkillRegistry` class that loads skill definitions from a configurable directory (mounted as image volume from openshift/agentic-skills container)
  - [ ] 5.2 Implement skill classification: each skill declares `access_level: "read-only" | "read-write"`. Only `read-only` skills are available during diagnosis.
  - [ ] 5.3 Implement `get_diagnosis_skills() -> list[BaseTool]` returning LangChain `@tool`-decorated functions for all read-only skills
  - [ ] 5.4 Implement write-access blocking: if a skill is classified `read-write`, `get_diagnosis_skills()` excludes it and logs the exclusion
  - [ ] 5.5 Create `backend/src/config/skills_settings.py` — `SkillsSettings` (skills directory path, enabled skill list)

- [ ] Task 6: Agentic skills execution wrapper (AC: #4, #5, #6)
  - [ ] 6.1 Create skill execution wrapper that runs skills under the `cluster-reader` ServiceAccount context via the read-only MCP Server
  - [ ] 6.2 Each skill invocation records `EvidenceArtifact` with `source=EvidenceSource.AGENTIC_SKILL` and the skill name in the query field
  - [ ] 6.3 Skill timeout handling produces `EvidenceGap` (consistent with MCP timeout pattern)

- [ ] Task 7: Integrate new tools into orchestrator (AC: #1, #2, #4, #6)
  - [ ] 7.1 Update `backend/src/agents/orchestrator.py` — add RHOKP, Learning Store, and agentic skill tools to the orchestrator's tool list
  - [ ] 7.2 Update `backend/src/agents/prompts.py` — extend system prompt with guidance on when to use RHOKP (platform-level guidance, Red Hat knowledge base), Learning Store (past incident patterns), and agentic skills (executable diagnostic checks)
  - [ ] 7.3 Ensure orchestrator tool calling order: MCP cluster evidence first, then RHOKP/runbooks for context, then Learning Store for past patterns, then skills for targeted checks

- [ ] Task 8: Helm chart updates (AC: #1)
  - [ ] 8.1 Add `solr` StatefulSet to Helm templates: RHOKP Solr image (`registry.redhat.io/offline-knowledge-portal/rhokp-rhel9`), PVC-backed, port 8983
  - [ ] 8.2 Add `okp-mcp` Deployment to Helm templates: okp-mcp image (`quay.io/redhat-user-workloads/rhel-lightspeed-tenant/rhel-knowledge-bridge`), Streamable HTTP transport, port 8000, env `MCP_SOLR_URL=http://{{ .Release.Name }}-solr:8983`
  - [ ] 8.3 Add Kubernetes Services for both Solr and okp-mcp
  - [ ] 8.4 Add Solr and okp-mcp configuration to `values.yaml` (images, ports, resource limits, PVC size, access key Secret reference)
  - [ ] 8.5 Add agentic-skills image volume mount to backend Deployment (mount path: `/skills`, read-only)

- [ ] Task 9: Tests — unit (AC: #1, #2, #3, #4, #5, #6)
  - [ ] 9.1 `tests/knowledge/test_rhokp_client.py` — RHOKP client connects to mock MCP, `search_portal` returns ranked results, `get_document` returns content, timeout produces `EvidenceGap`
  - [ ] 9.2 `tests/knowledge/test_learning_store.py` — query returns ranked results with temporal decay applied, empty Learning Store returns empty list gracefully, version relevance reduces confidence for different OCP versions
  - [ ] 9.3 `tests/knowledge/test_skills.py` — skill registry loads skills from directory, read-only skills included, read-write skills excluded, missing directory handled gracefully
  - [ ] 9.4 `tests/agents/test_tools.py` — update: `search_rhokp` returns `EvidenceArtifact` with `source=RHOKP`, `query_past_incidents` returns `EvidenceArtifact` with `source=LEARNING_STORE`, skill tools return `EvidenceArtifact` with `source=AGENTIC_SKILL`

- [ ] Task 10: Tests — integration (AC: #1, #2, #3)
  - [ ] 10.1 `tests/db/test_case_records.py` — `case_records` table created by migration, `search_similar_cases` returns results ranked by cosine similarity, empty table returns empty list (testcontainers)
  - [ ] 10.2 `tests/pipeline/test_diagnosis_graph.py` — update: orchestrator with RHOKP + Learning Store + skills tools produces DiagnosisObject with multi-source evidence (mocked LLM + mocked RHOKP MCP + mocked Learning Store)
  - [ ] 10.3 `tests/knowledge/test_rhokp_integration.py` — RHOKP client Streamable HTTP integration with mock okp-mcp server fixture

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 2.2 (Orchestrator Agent & Runbook-Enriched Diagnosis) — DIRECT PREDECESSOR:**

Story 2.2 created the Orchestrator agent that this story extends with additional knowledge sources and tools. Key deliverables:

- **`agents/orchestrator.py`** — `build_orchestrator_agent()` creates a `create_react_agent` subgraph with tools and `response_format=DiagnosisObject`. `run_orchestrator(state, config)` invokes the agent and returns updated state. The orchestrator receives existing tools (MCP cluster queries, runbook RAG) — this story ADDS tools for RHOKP, Learning Store, and agentic skills.
- **`agents/tools.py`** — LangChain `@tool`-decorated functions: `query_cluster_resources`, `get_resource_logs`, `search_runbooks`. Each returns structured data and records `EvidenceArtifact` with the correct `EvidenceSource`. This story ADDS new tool functions alongside the existing ones.
- **`agents/llm_client.py`** — `get_chat_model(role: AgentRole) -> ChatOpenAI` factory with per-role config via env vars. Reuse as-is.
- **`agents/prompts.py`** — `ORCHESTRATOR_SYSTEM_PROMPT` with hypothesis-first investigation process. This story EXTENDS the prompt with RHOKP/Learning Store/skills guidance.
- **`agents/completeness_gate.py`** — `evaluate_completeness()` checks all alert fingerprints are addressed. Reuse as-is — the new knowledge sources should improve completeness, not change the gate logic.
- **`knowledge/chunker.py`**, **`knowledge/embeddings.py`**, **`knowledge/runbook_rag.py`**, **`knowledge/ingest.py`** — Runbook ingestion and RAG retrieval pipeline. `embed_texts()` using OpenAI-compatible endpoint via `AsyncOpenAI` — reuse for Learning Store embedding queries.
- **`db/runbooks.py`** — pgvector CRUD for `runbook_chunks` table. Pattern to follow for `case_records` pgvector queries.
- **`config/knowledge_settings.py`** — `KnowledgeSettings` with embedding model, similarity threshold, top_k. Extend or add parallel settings for RHOKP and Learning Store.
- **`models/knowledge.py`** — `RunbookChunk`, `CompletenessResult` Pydantic models. Add `CaseRecordSummary` alongside.
- **Alembic migration** — `runbook_chunks` table with HNSW index. Follow same pattern for `case_records` table.
- **`tests/agents/conftest.py`** — `FakeChatModel` mock LLM fixture. Reuse and extend for new tool testing.

**Critical patterns from 2.2 this story MUST follow:**
- Tools are `@tool`-decorated functions in `agents/tools.py` — add new tools in the same file, don't create separate tool files
- Each tool returns `EvidenceArtifact` with the correct `EvidenceSource` enum value
- The orchestrator's tool list is assembled in `build_orchestrator_agent()` — add new tools to that list
- `embed_texts()` from `knowledge/embeddings.py` is the single embedding function — reuse it for Learning Store queries
- pgvector similarity search uses `<=>` cosine distance with threshold — follow `db/runbooks.py` pattern
- Config follows frozen dataclass with `from_env()` classmethod pattern

**From Story 2.1 (LangGraph Diagnosis Pipeline & MCP Integration):**
- **`pipeline/mcp_client.py`** — `ReadOnlyMCPClient` wrapping MCP Python SDK Streamable HTTP. Pattern for RHOKP client. Key: `Client("http://...")` auto-selects transport; timeout → `EvidenceGap`, never exception.
- **`models/diagnosis.py`** — `EvidenceSource` enum already includes `RHOKP`, `LEARNING_STORE`, `AGENTIC_SKILL` values (forward-declared in 2.1). `EvidenceArtifact`, `EvidenceGap`, `DiagnosisObject` models ready.
- **`config/mcp_settings.py`** — `MCPSettings` pattern for MCP connection config. Follow same pattern for RHOKP settings.

**From Epic 1 (all stories complete):**
- State machine in `models/state_machine.py` — transitions via `transition()`, never direct SQL
- Event bus: `event_bus.emit(EventNames.INCIDENT_STAGE_CHANGED, SSEEventData(...))`
- DB operations always in `db/` module
- Config pattern: frozen dataclass with `from_env()` classmethod
- Logger: `get_logger(Component.KNOWLEDGE)` or `get_logger(Component.AGENT)`
- Test markers: `unit`, `db`, `api`, `pipeline`
- Testcontainers PostgreSQL fixture in `conftest.py`

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-1 | Agents internal to stages | RHOKP, Learning Store, and skills are tools WITHIN the orchestrator subgraph — not new pipeline nodes |
| AD-2 | RBAC Airlock | All new tools execute under `cluster-reader` SA. RHOKP is a knowledge query (no cluster access). Learning Store is a DB query. Agentic skills MUST use read-only MCP only. Write-access skills are BLOCKED |
| AD-4 | Shared types module | `CaseRecordSummary` model in `models/`. `EvidenceSource` enum values already defined |
| AD-9 | Seven-deployment topology | Add `solr` StatefulSet (#6) and `okp-mcp` Deployment (#7) — completes the seven-deployment topology |
| AD-13 | Dual-path knowledge retrieval | This story implements path 2: RHOKP via Solr + okp-mcp. Path 1 (runbooks via pgvector RAG) was Story 2.2. Both paths now active |
| AD-14 | Monorepo source tree | Knowledge code in `knowledge/`, DB in `db/`, config in `config/`, tools in `agents/tools.py` |
| AD-15 | MCP timeout → partial evidence | RHOKP client timeout → `EvidenceGap`. Skill timeout → `EvidenceGap`. Same pattern as `ReadOnlyMCPClient` |
| AD-20 | Case Record schema owned by Learning Store | This story creates the table schema and migration — read-only queries only. Epic 4 will write to it. Correlation (Epic 1 layer 5) will read via these same query functions |
| AD-25 | Audit log | Existing pipeline audit hook from 2.1 captures orchestrator tool calls. No additional audit hooks needed |

### Technical Requirements

#### RHOKP Client via okp-mcp

```python
from mcp import Client

RHOKP_MCP_URL = "http://okp-mcp:8000/mcp"

class RHOKPClient:
    def __init__(self, url: str = RHOKP_MCP_URL, timeout: float = 30.0):
        self.url = url
        self.timeout = timeout

    async def search_portal(
        self, queries: list[str], top_k: int = 5
    ) -> dict:
        """Multi-query search with reciprocal rank fusion."""
        async with Client(self.url) as client:
            try:
                result = await asyncio.wait_for(
                    client.call_tool("search_portal", {
                        "queries": queries,
                        "rows": top_k,
                    }),
                    timeout=self.timeout,
                )
                return {"success": True, "data": result}
            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "evidence_gap": EvidenceGap(
                        query=f"search_portal({queries})",
                        reason="RHOKP query timed out",
                        timeout_seconds=self.timeout,
                    ),
                }

    async def get_document(self, doc_id: str) -> dict:
        """Full document retrieval with BM25 passage extraction."""
        async with Client(self.url) as client:
            try:
                result = await asyncio.wait_for(
                    client.call_tool("get_document", {"id": doc_id}),
                    timeout=self.timeout,
                )
                return {"success": True, "data": result}
            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "evidence_gap": EvidenceGap(
                        query=f"get_document({doc_id})",
                        reason="RHOKP document retrieval timed out",
                        timeout_seconds=self.timeout,
                    ),
                }
```

Key details:
- okp-mcp exposes MCP tools: `search_portal` (multi-query search, reciprocal rank fusion across Solr) and `get_document` (full content retrieval with BM25 passage scoring)
- The okp-mcp server name is `"RHEL OKP Knowledge Base"` — it searches 600k+ Red Hat documentation, solutions, CVEs, errata, and articles
- Connection to `http://okp-mcp:8000/mcp` — the Kubernetes Service name within the namespace
- Timeout handling produces `EvidenceGap`, consistent with the `ReadOnlyMCPClient` pattern from Story 2.1 (AD-15)
- The okp-mcp container image is `quay.io/redhat-user-workloads/rhel-lightspeed-tenant/rhel-knowledge-bridge`
- Solr image: `registry.redhat.io/offline-knowledge-portal/rhokp-rhel9:latest` — ~10 GB, PVC-backed for persistence

#### Learning Store Query Interface

The Learning Store query interface provides read-only access to past Case Records. The table is created by this story but only populated by Epic 4 (Case Record Persistence). This story's query must handle empty results gracefully.

```python
async def search_similar_cases(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    top_k: int = 3,
    similarity_threshold: float = 0.75,
) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, alert_signature, root_cause_code, outcome,
               outcome_confidence, ocp_version, created_at,
               1 - (alert_signature_embedding <=> $1::vector) AS similarity
        FROM case_records
        WHERE 1 - (alert_signature_embedding <=> $1::vector) > $4
        ORDER BY alert_signature_embedding <=> $1::vector
        LIMIT $2
        """,
        query_embedding, top_k, similarity_threshold,
    )
    return [dict(r) for r in rows]
```

**Temporal decay at query time:**

```python
import math
from datetime import datetime, timezone

def apply_temporal_decay(
    case: dict,
    current_ocp_version: str,
    decay_half_life_days: float = 90.0,
) -> float:
    age_days = (datetime.now(timezone.utc) - case["created_at"]).days
    decay_factor = math.exp(-0.693 * age_days / decay_half_life_days)

    case_major = case["ocp_version"].split(".")[0]
    current_major = current_ocp_version.split(".")[0]
    version_relevance = 1.0 if case_major == current_major else 0.5

    return case["outcome_confidence"] * decay_factor * version_relevance
```

The `effective_confidence` replaces raw `outcome_confidence` for ranking, per FR-19.

**Case Records table schema (minimal — Epic 4 extends):**

```sql
CREATE TABLE case_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_signature TEXT NOT NULL,
    alert_signature_embedding vector(1536),
    root_cause_code TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure')),
    outcome_confidence FLOAT NOT NULL CHECK (outcome_confidence >= 0 AND outcome_confidence <= 1),
    ocp_version TEXT NOT NULL,
    cluster_context JSONB DEFAULT '{}',
    diagnosis_summary TEXT DEFAULT '',
    remediation_summary TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX case_records_embedding_idx
    ON case_records USING hnsw (alert_signature_embedding vector_cosine_ops);
```

The schema is intentionally minimal. AD-20 states the Case Record table is owned by the Learning Store module in `db/`. Epic 4 (Story 4.1) will extend this with the full Case Record schema including the complete `DiagnosisObject`, `RemediationPlan`, and cluster topology snapshot. This story creates the table and index for query readiness — writing is deferred.

#### Agentic Skills Integration

Skills from `openshift/agentic-skills` are loaded from a container image mounted as a volume. The skills follow an open standard format with a `SKILL.md` file describing capabilities and access requirements.

```python
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class SkillDefinition:
    name: str
    description: str
    access_level: str  # "read-only" or "read-write"
    skill_path: Path
    enabled: bool = True

class SkillRegistry:
    def __init__(self, skills_dir: str = "/skills"):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillDefinition] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        if not self.skills_dir.exists():
            logger.warning("Skills directory not found", path=str(self.skills_dir))
            return
        for skill_path in self.skills_dir.iterdir():
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                skill = self._parse_skill(skill_path)
                if skill:
                    self._skills[skill.name] = skill

    def get_diagnosis_skills(self) -> list[SkillDefinition]:
        """Return only read-only skills for diagnosis stage."""
        read_only = []
        for skill in self._skills.values():
            if skill.access_level == "read-only" and skill.enabled:
                read_only.append(skill)
            elif skill.access_level == "read-write":
                logger.info(
                    "Skill excluded from diagnosis (write access required)",
                    skill=skill.name,
                )
        return read_only
```

Skill execution wraps the read-only MCP Server or executes the skill's defined tools under the `cluster-reader` SA. Each skill becomes a LangChain `@tool` function:

```python
def skill_to_tool(skill: SkillDefinition, mcp_client: ReadOnlyMCPClient) -> BaseTool:
    @tool(name=f"skill_{skill.name}", description=skill.description)
    async def execute_skill(**kwargs) -> str:
        result = await mcp_client.query_cluster(
            tool_name=kwargs.get("tool", "describe_resource"),
            arguments=kwargs,
        )
        return json.dumps(result)
    return execute_skill
```

Key constraints:
- Skills directory is mounted at `/skills` from the `openshift/agentic-skills` container image via Kubernetes image volumes
- Skills that declare `access_level: "read-write"` (e.g., `cluster-ops` — patch, scale, delete) are NEVER available during diagnosis
- Skills that use MCP tools MUST route through the existing `ReadOnlyMCPClient` — they CANNOT create their own MCP connections
- If the skills directory doesn't exist or is empty, diagnosis proceeds without skills (graceful degradation)

#### Orchestrator Tool List Extension

The orchestrator's tool list in `build_orchestrator_agent()` grows from 3 tools (2.2) to 5+ tools:

```python
def build_orchestrator_tools(
    mcp_client: ReadOnlyMCPClient,
    rhokp_client: RHOKPClient,
    db_pool: asyncpg.Pool,
    skill_registry: SkillRegistry,
) -> list[BaseTool]:
    tools = [
        # From Story 2.2 — MCP cluster queries
        query_cluster_resources,
        get_resource_logs,
        # From Story 2.2 — Runbook RAG
        search_runbooks,
        # NEW in Story 2.3 — RHOKP
        search_rhokp,
        get_rhokp_document,
        # NEW in Story 2.3 — Learning Store
        query_past_incidents,
    ]
    # NEW in Story 2.3 — Agentic skills (dynamic, read-only only)
    diagnosis_skills = skill_registry.get_diagnosis_skills()
    for skill in diagnosis_skills:
        tools.append(skill_to_tool(skill, mcp_client))
    return tools
```

#### System Prompt Extension

Add to `ORCHESTRATOR_SYSTEM_PROMPT` in `agents/prompts.py`:

```
KNOWLEDGE SOURCES (use in this order of preference):
1. CLUSTER STATE (query_cluster_resources, get_resource_logs) — always start here for current evidence
2. RUNBOOKS (search_runbooks) — operational guidance and known procedures
3. RHOKP (search_rhokp, get_rhokp_document) — Red Hat platform knowledge base for deeper context
4. LEARNING STORE (query_past_incidents) — past incident patterns and outcomes
5. AGENTIC SKILLS (skill_*) — specialized diagnostic checks when targeted investigation is needed

EVIDENCE ATTRIBUTION:
- Tag every evidence artifact with its source type
- When using RHOKP results, cite the document ID and relevant passage
- When using Learning Store results, note the similarity score and effective confidence
- When using agentic skills, record the skill name and specific check performed
```

#### Helm Chart: Solr StatefulSet and okp-mcp Deployment

**Solr StatefulSet:**
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ .Release.Name }}-solr
spec:
  replicas: 1
  serviceName: {{ .Release.Name }}-solr
  template:
    spec:
      containers:
      - name: solr
        image: "{{ .Values.solr.image.repository }}:{{ .Values.solr.image.tag }}"
        env:
        - name: ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: {{ .Values.solr.accessKeySecret }}
              key: access-key
        - name: SOLR_JETTY_HOST
          value: "0.0.0.0"
        ports:
        - containerPort: 8983
        volumeMounts:
        - name: solr-data
          mountPath: /opt/solr/server/solr/portal/data
  volumeClaimTemplates:
  - metadata:
      name: solr-data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: {{ .Values.solr.storage.size | default "15Gi" }}
```

**okp-mcp Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-okp-mcp
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: okp-mcp
        image: "{{ .Values.okpMcp.image.repository }}:{{ .Values.okpMcp.image.tag }}"
        env:
        - name: MCP_TRANSPORT
          value: "streamable-http"
        - name: MCP_SOLR_URL
          value: "http://{{ .Release.Name }}-solr:8983"
        - name: MCP_PORT
          value: "8000"
        ports:
        - containerPort: 8000
```

**Backend Deployment update — agentic-skills image volume:**
```yaml
spec:
  template:
    spec:
      containers:
      - name: backend
        volumeMounts:
        - name: agentic-skills
          mountPath: /skills
          readOnly: true
      volumes:
      - name: agentic-skills
        image:
          reference: "{{ .Values.agenticSkills.image.repository }}:{{ .Values.agenticSkills.image.tag }}"
          pullPolicy: IfNotPresent
```

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ~=1.2 | Already in pyproject.toml. Agent subgraph, orchestrator |
| langchain-openai | latest | Already in pyproject.toml (added in 2.2). ChatOpenAI, embedding client |
| pgvector | latest | Already in pyproject.toml (added in 2.2). pgvector-python for asyncpg |
| mcp | latest | Already in pyproject.toml (added in 2.1). MCP Python SDK for RHOKP client |
| asyncpg | latest | Already in pyproject.toml. Application DB + pgvector queries |

**No new dependencies needed.** All required packages were already added in Stories 2.1 and 2.2. The `mcp` package handles the RHOKP MCP connection (same SDK as the cluster MCP client).

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/knowledge/rhokp_client.py` | RHOKP MCP client — `search_portal()`, `get_document()` with timeout→EvidenceGap | NEW |
| `backend/src/knowledge/learning_store.py` | Learning Store query interface — pgvector similarity + temporal decay | NEW |
| `backend/src/knowledge/skills.py` | Agentic skill registry — load, classify read-only/read-write, convert to tools | NEW |
| `backend/src/config/rhokp_settings.py` | RHOKP connection settings (URL, timeout, top_k) | NEW |
| `backend/src/config/skills_settings.py` | Skills configuration (directory path, enabled list) | NEW |
| `backend/src/models/case_record.py` | `CaseRecordSummary` Pydantic model (minimal read-only projection) | NEW |
| `backend/src/db/case_records.py` | pgvector similarity search for case records (read-only) | NEW |
| `backend/alembic/versions/xxx_add_case_records.py` | Migration: `case_records` table + HNSW index | NEW |
| `charts/openshift-ai-ops/templates/statefulset-solr.yaml` | RHOKP Solr StatefulSet | NEW |
| `charts/openshift-ai-ops/templates/service-solr.yaml` | Solr Service | NEW |
| `charts/openshift-ai-ops/templates/deployment-okp-mcp.yaml` | okp-mcp Deployment | NEW |
| `charts/openshift-ai-ops/templates/service-okp-mcp.yaml` | okp-mcp Service | NEW |
| `backend/tests/knowledge/test_rhokp_client.py` | RHOKP client unit tests | NEW |
| `backend/tests/knowledge/test_learning_store.py` | Learning Store query tests | NEW |
| `backend/tests/knowledge/test_skills.py` | Skill registry tests | NEW |
| `backend/tests/knowledge/test_rhokp_integration.py` | RHOKP Streamable HTTP integration tests | NEW |
| `backend/tests/db/test_case_records.py` | Case records pgvector tests (testcontainers) | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/agents/tools.py` | Add `search_rhokp`, `get_rhokp_document`, `query_past_incidents`, and skill execution tools | UPDATE |
| `backend/src/agents/orchestrator.py` | Add RHOKP, Learning Store, and skill tools to orchestrator tool list | UPDATE |
| `backend/src/agents/prompts.py` | Extend system prompt with RHOKP/Learning Store/skills guidance and evidence attribution rules | UPDATE |
| `backend/src/models/__init__.py` | Export `CaseRecordSummary` | UPDATE |
| `backend/src/api/app.py` | Add skill registry initialization to lifespan (load skills on startup) | UPDATE |
| `charts/openshift-ai-ops/values.yaml` | Add `solr`, `okpMcp`, and `agenticSkills` sections | UPDATE |
| `charts/openshift-ai-ops/templates/deployment-backend.yaml` | Add agentic-skills image volume mount | UPDATE |
| `backend/tests/agents/test_tools.py` | Add tests for new RHOKP, Learning Store, and skill tools | UPDATE |
| `backend/tests/pipeline/test_diagnosis_graph.py` | Update: orchestrator with full tool set produces multi-source evidence DiagnosisObject | UPDATE |

### Dependency Direction (ENFORCED)

```
models/case_record.py → nothing (leaf, Pydantic only)
knowledge/rhokp_client.py → models/diagnosis.py (EvidenceGap), config/rhokp_settings.py
knowledge/learning_store.py → knowledge/embeddings.py (embed_texts), db/case_records.py, models/case_record.py
knowledge/skills.py → models/diagnosis.py (EvidenceGap), config/skills_settings.py
db/case_records.py → models/case_record.py (for types)
agents/tools.py → knowledge/rhokp_client.py, knowledge/learning_store.py, knowledge/skills.py, pipeline/mcp_client.py, knowledge/runbook_rag.py, models/ (EvidenceArtifact)
agents/orchestrator.py → agents/tools.py, agents/llm_client.py, knowledge/skills.py (SkillRegistry)
config/rhokp_settings.py → nothing (leaf, reads env vars)
config/skills_settings.py → nothing (leaf, reads env vars)
```

- **NEVER**: `models/` imports from `agents/`, `knowledge/`, `pipeline/`, `api/`, or `db/`
- **NEVER**: `agents/` imports from `api/` or `pipeline/` (except `pipeline/mcp_client.py` for tool wrapping)
- **NEVER**: `knowledge/` imports from `agents/` or `api/`
- **ALLOWED**: `agents/` imports from `knowledge/` (for RHOKP, Learning Store, skills)
- **ALLOWED**: `knowledge/` imports from `db/` (for pgvector queries)

### Testing Requirements

**Unit tests** (`pytest -m unit`):
- `RHOKPClient` with mock MCP server: `search_portal` returns ranked results, `get_document` returns document content
- `RHOKPClient` timeout produces `EvidenceGap` (not exception)
- `query_learning_store` with empty DB returns empty list (no exception)
- `query_learning_store` with populated DB returns results ranked by effective confidence (temporal decay applied)
- Temporal decay reduces confidence for older records
- Version relevance reduces confidence when OCP major version differs
- `SkillRegistry` loads skills from a directory with `SKILL.md` files
- `SkillRegistry.get_diagnosis_skills()` returns only `read-only` skills
- `SkillRegistry.get_diagnosis_skills()` excludes `read-write` skills with logged exclusion
- `SkillRegistry` handles missing/empty skills directory gracefully
- `search_rhokp` tool returns `EvidenceArtifact` with `source=EvidenceSource.RHOKP`
- `query_past_incidents` tool returns `EvidenceArtifact` with `source=EvidenceSource.LEARNING_STORE`
- Skill tools return `EvidenceArtifact` with `source=EvidenceSource.AGENTIC_SKILL`

**DB integration tests** (`pytest -m db`):
- `case_records` table created by migration (testcontainers)
- `search_similar_cases()` returns results ranked by cosine similarity
- `search_similar_cases()` filters by `similarity_threshold`
- Empty `case_records` table returns empty list (graceful handling)
- HNSW index exists on `alert_signature_embedding` column

**Pipeline integration tests** (`pytest -m pipeline`):
- Updated graph tests: orchestrator with RHOKP + Learning Store + skills tools produces `DiagnosisObject` (mocked LLM + mocked MCP)
- Evidence array contains artifacts from multiple sources (MCP, runbook, RHOKP, Learning Store, skill) with correct `EvidenceSource` values
- Missing RHOKP (connection refused) → diagnosis proceeds with other sources, `EvidenceGap` recorded
- Empty Learning Store → diagnosis proceeds, no `EvidenceGap` (expected state on fresh deployment)
- No skills directory → diagnosis proceeds with MCP + runbook + RHOKP + Learning Store tools only

**Mock okp-mcp Server Fixture:**
Extend the mock MCP server from Story 2.1's `tests/pipeline/conftest.py` or create a parallel fixture that:
- Accepts MCP `initialize` handshake with `serverInfo.name: "RHEL OKP Knowledge Base"`
- Returns canned results for `search_portal` (ranked documents with scores)
- Returns canned results for `get_document` (full document content with passages)
- Supports configurable response delays for timeout testing
- Lives in `tests/knowledge/conftest.py`

**Mock Skills Directory Fixture:**
Create a temporary directory with sample skill definitions:
- A read-only skill (e.g., `cluster-troubleshoot`) with `access_level: "read-only"` in `SKILL.md`
- A read-write skill (e.g., `cluster-ops`) with `access_level: "read-write"` in `SKILL.md`
- Lives in `tests/knowledge/conftest.py`

### Anti-Patterns / DO NOT

- **DO NOT** write to the `case_records` table. This story creates the table and reads from it. Story 4.1 (Case Record Persistence) implements the write path. The table will be empty until Epic 4 runs.
- **DO NOT** modify the `case_records` schema beyond what's defined here. AD-20 states the schema is owned by the Learning Store module — Epic 4 will extend it with full Case Record fields.
- **DO NOT** implement the fast-path bypass. Story 4.3 implements the fast-path logic that queries the Learning Store for proven remediations. This story only provides the query interface.
- **DO NOT** implement temporal decay configuration via runtime API. Story 6.1 adds runtime API config. This story uses Helm-configurable decay parameters via env vars.
- **DO NOT** create a write-capable MCP client or connect to `mcp-readwrite`. Agentic skills MUST route through `ReadOnlyMCPClient`. Write-access skills are BLOCKED.
- **DO NOT** implement custom RHOKP Solr queries. Use the okp-mcp MCP tools (`search_portal`, `get_document`) exclusively. Direct Solr queries bypass the MCP abstraction.
- **DO NOT** create a new `agents/rhokp_tools.py` or `agents/learning_store_tools.py`. All tools go in `agents/tools.py` following the pattern from Story 2.2.
- **DO NOT** modify the Orchestrator's `create_react_agent` structure. Only extend the tool list and system prompt. The agent loop, checkpointing, and structured output are unchanged from 2.2.
- **DO NOT** modify the completeness gate logic. The new knowledge sources improve evidence coverage but don't change how completeness is evaluated.
- **DO NOT** implement the Skeptic. Story 2.4 adds the Diagnosis Skeptic. The orchestrator still hands off to `finalize_node`.
- **DO NOT** modify existing models (`diagnosis.py`, `state_machine.py`, `knowledge.py`). Add `case_record.py` alongside them. Extend `DiagnosisState` with new fields only if needed — don't change existing field types.
- **DO NOT** add the `mcp-readwrite` Deployment — that's Story 3.x scope. This story adds `solr` and `okp-mcp` only.
- **DO NOT** implement skill auto-discovery or dynamic skill updates. Skills are loaded once at startup from the mounted volume. Refresh = pod restart.
- **DO NOT** modify `pyproject.toml` dependencies — all required packages (`mcp`, `pgvector`, `langchain-openai`) were already added in Stories 2.1 and 2.2.

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  knowledge/
    rhokp_client.py          # NEW: okp-mcp MCP client (search_portal, get_document)
    learning_store.py         # NEW: Learning Store pgvector query + temporal decay
    skills.py                 # NEW: Agentic skill registry (load, classify, convert)
  models/
    case_record.py            # NEW: CaseRecordSummary model
    __init__.py               # UPDATE: export CaseRecordSummary
  agents/
    tools.py                  # UPDATE: add RHOKP, Learning Store, skill tools
    orchestrator.py           # UPDATE: extend tool list
    prompts.py                # UPDATE: extend system prompt
  db/
    case_records.py           # NEW: pgvector similarity search (read-only)
  config/
    rhokp_settings.py         # NEW: RHOKP connection settings
    skills_settings.py        # NEW: Skills configuration
  api/
    app.py                    # UPDATE: skill registry init in lifespan
backend/alembic/versions/
  xxx_add_case_records.py     # NEW: case_records table + HNSW index
backend/tests/
  knowledge/
    test_rhokp_client.py      # NEW
    test_learning_store.py    # NEW
    test_skills.py            # NEW
    test_rhokp_integration.py # NEW
    conftest.py               # UPDATE: add mock okp-mcp fixture, mock skills dir
  db/
    test_case_records.py      # NEW
  agents/
    test_tools.py             # UPDATE: new tool tests
  pipeline/
    test_diagnosis_graph.py   # UPDATE: multi-source evidence tests
charts/openshift-ai-ops/
  templates/
    statefulset-solr.yaml     # NEW
    service-solr.yaml         # NEW
    deployment-okp-mcp.yaml   # NEW
    service-okp-mcp.yaml      # NEW
    deployment-backend.yaml   # UPDATE: skills volume mount
  values.yaml                 # UPDATE: solr, okpMcp, agenticSkills sections
```

### Latest Technology Notes

**okp-mcp (latest):**
- Python-based MCP server for Red Hat Offline Knowledge Portal (OKP)
- Default transport: `streamable-http` (compatible with MCP Python SDK `Client()`)
- Tools: `search_portal` (multi-query search with reciprocal rank fusion), `get_document` (full content with BM25 passages)
- Connects to Solr via `MCP_SOLR_URL` env var
- Container image: `quay.io/redhat-user-workloads/rhel-lightspeed-tenant/rhel-knowledge-bridge`
- No authentication required — Solr access is in-cluster only

**RHOKP Solr (registry.redhat.io/offline-knowledge-portal/rhokp-rhel9:latest):**
- ~10 GB image, first start indexes content (several minutes)
- 600k+ documents: RHEL documentation, CVEs, errata, solutions, articles
- Port 8983, Solr core name: `portal`
- PVC-backed for persistence (`/opt/solr/server/solr/portal/data`)
- Requires `ACCESS_KEY` from Red Hat OKP portal — stored in Kubernetes Secret
- Subsequent starts faster when data persisted via PVC

**openshift/agentic-skills:**
- Open-format skills for AI agents working with OpenShift clusters
- Container image with skills mounted as image volume (`subPath` support)
- Skills include: `cluster-troubleshoot` (read-only diagnostics), `cluster-ops` (read-write operations), `rbac-security` (minimum-privilege analysis)
- Each skill has `SKILL.md` with description and access requirements
- Skills execute via MCP tools or direct `oc` commands under the pod's ServiceAccount
- Pre-1.0 — skill format and available skills evolving

**pgvector 0.8.x HNSW index:**
- HNSW index can be created on empty tables (unlike IVFFlat which needs data first)
- Better query performance than IVFFlat for similarity search
- `vector_cosine_ops` for cosine distance
- Creating index: `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`

**MCP Python SDK (latest):**
- Same SDK used for both `ReadOnlyMCPClient` (kubernetes-mcp-server) and `RHOKPClient` (okp-mcp)
- `Client("http://host:port/mcp")` auto-selects Streamable HTTP transport
- Tool names and arguments are server-specific — discover via `client.list_tools()`

### References

- [Source: ARCHITECTURE-SPINE.md#AD-1] — Agents internal to stages (tools within orchestrator)
- [Source: ARCHITECTURE-SPINE.md#AD-2] — RBAC Airlock (read-only for diagnosis, write skills blocked)
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types module (CaseRecordSummary in models/)
- [Source: ARCHITECTURE-SPINE.md#AD-9] — Seven-deployment topology (add Solr #6, okp-mcp #7)
- [Source: ARCHITECTURE-SPINE.md#AD-13] — Dual-path knowledge retrieval (path 2: RHOKP via okp-mcp)
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout (knowledge/, db/, config/, agents/)
- [Source: ARCHITECTURE-SPINE.md#AD-15] — MCP timeout → partial evidence with evidence_gaps
- [Source: ARCHITECTURE-SPINE.md#AD-20] — Case Record schema owned by Learning Store module
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit log (existing pipeline audit hook covers tool calls)
- [Source: project-context.md#LangGraph] — Agents internal to stages, tools within orchestrator
- [Source: project-context.md#Testing Rules] — Mock MCP, mock LLM, test layers
- [Source: project-context.md#Critical Don't-Miss Rules] — RBAC Airlock, read-only enforcement
- [Source: epics.md#Story 2.3] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 2] — FR-4, FR-5, FR-6 coverage
- [Source: epics.md#Epic 4] — Learning Store responsibilities (Case Record writes are Epic 4)
- [Source: Story 2.1 spec] — ReadOnlyMCPClient, EvidenceSource enum, MCP timeout pattern
- [Source: Story 2.2 spec] — Orchestrator agent, tools.py, build_orchestrator_agent(), prompts.py, knowledge/ module
- [Source: okp-mcp GitHub] — search_portal, get_document tools, Streamable HTTP, Solr connection
- [Source: openshift/agentic-skills GitHub] — Skill format, container image volumes, access levels

## Code Review Record

### Review Model Used

(to be filled during review — must differ from dev model)

### Review Findings

(to be filled during review)

### Decisions Needed / Decisions Taken

(to be filled during review)

### Fixes Applied

(to be filled during review)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### Change Log

### File List
