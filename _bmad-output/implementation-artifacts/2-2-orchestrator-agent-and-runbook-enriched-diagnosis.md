# Story 2.2: Orchestrator Agent & Runbook-Enriched Diagnosis

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want an AI orchestrator to diagnose root causes using cluster data and OpenShift runbooks,
so that I receive structured, evidence-backed diagnoses without manually correlating symptoms across tools.

## Acceptance Criteria

1. **Given** a Root-Cause Event enters the diagnosis stage **When** the Orchestrator agent processes it **Then** it forms an initial subsystem hypothesis from the alert metadata (labels, annotations, alert name) and contextual knowledge

2. **Given** the Orchestrator has formed a hypothesis **When** it investigates the root cause **Then** it queries the cluster via the read-only MCP Server to gather evidence (resource states, logs, metrics) **And** each piece of evidence is recorded as a concrete Evidence Artifact in the diagnosis (specific log line, metric value, or resource state — not free-text rationale)

3. **Given** OpenShift runbooks are bundled at container build time **When** the diagnosis pipeline starts **Then** runbooks have been chunked, embedded, and stored in pgvector for similarity search

4. **Given** the Orchestrator is diagnosing a Root-Cause Event **When** it retrieves knowledge **Then** it performs pgvector similarity search against runbook embeddings using the alert context and injects the top-k matching chunks into its reasoning context

5. **Given** the Orchestrator has completed its investigation **When** it produces a Structured Diagnosis Object **Then** the object includes a confidence score (0–1) reflecting the strength and completeness of supporting evidence

6. **Given** the Orchestrator is preparing to hand off to the Skeptic **When** the completeness gate is evaluated **Then** it verifies that the diagnosis addresses all correlated alerts in the Root-Cause Event and that no gathered evidence was left unexamined **And** the diagnosis does not pass the completeness gate until all alerts are accounted for

7. **Given** an alert type that no Specialist claims (MVP has no specialists) **When** the Orchestrator handles it as generalist of last resort **Then** it flags a coverage gap in the diagnosis metadata ("no specialist covers this alert type") for visibility in the UI

8. **Given** conflicting evidence or multiple possible root causes **When** the Orchestrator synthesizes a diagnosis **Then** it produces a single diagnosis with a rationale for the selected root cause **And** rejected alternative hypotheses are preserved in the audit trail

## Tasks / Subtasks

- [ ] Task 1: LLM client configuration layer (AC: #1, #2, #5)
  - [ ] 1.1 Create `backend/src/config/llm_settings.py` with `LLMSettings` and `AgentLLMConfig` dataclasses (endpoint URL, model name, temperature, thinking mode, credential Secret ref)
  - [ ] 1.2 Implement per-agent-role config resolution from env vars (orchestrator, skeptic, planner — AD-7 layered override, Helm seed only in this story)
  - [ ] 1.3 Create `backend/src/agents/llm_client.py` — factory function `get_chat_model(role: AgentRole) -> BaseChatModel` wrapping `ChatOpenAI` with per-role config

- [ ] Task 2: Runbook ingestion pipeline (AC: #3)
  - [ ] 2.1 Create `backend/src/knowledge/__init__.py`
  - [ ] 2.2 Create `backend/src/knowledge/chunker.py` — split markdown runbooks into chunks (~512 tokens, overlap 64 tokens, preserve heading hierarchy)
  - [ ] 2.3 Create `backend/src/knowledge/embeddings.py` — `embed_texts(texts: list[str]) -> list[list[float]]` using the configured embedding model endpoint
  - [ ] 2.4 Create `backend/src/db/runbooks.py` — `store_chunks()`, `search_similar()` with pgvector `<=>` cosine distance
  - [ ] 2.5 Create Alembic migration for `runbook_chunks` table with pgvector HNSW index
  - [ ] 2.6 Create `backend/src/knowledge/ingest.py` — CLI/startup entrypoint that scans `runbooks/` directory, chunks, embeds, and upserts into pgvector

- [ ] Task 3: Runbook RAG retrieval (AC: #4)
  - [ ] 3.1 Create `backend/src/knowledge/runbook_rag.py` — `retrieve_runbook_context(alert_context: str, conn, top_k: int = 5) -> list[RunbookChunk]`
  - [ ] 3.2 Register pgvector types with asyncpg pool via `pgvector.asyncpg.register_vector(conn)`
  - [ ] 3.3 Create `backend/src/config/knowledge_settings.py` — `KnowledgeSettings` (embedding model, similarity threshold, top_k, chunk size)

- [ ] Task 4: Orchestrator agent tools (AC: #1, #2, #4)
  - [ ] 4.1 Create `backend/src/agents/__init__.py`
  - [ ] 4.2 Create `backend/src/agents/tools.py` — LangChain `@tool`-decorated functions:
    - `query_cluster_resources(resource_type, namespace, name)` — wraps `ReadOnlyMCPClient.query_cluster()`, returns evidence artifacts
    - `get_resource_logs(namespace, pod_name, container, tail_lines)` — wraps MCP `get_logs`
    - `search_runbooks(query, top_k)` — wraps `runbook_rag.retrieve_runbook_context()`
  - [ ] 4.3 Each tool returns structured data, records `EvidenceArtifact` with correct `EvidenceSource`

- [ ] Task 5: Orchestrator agent implementation (AC: #1, #2, #5, #7, #8)
  - [ ] 5.1 Create `backend/src/agents/orchestrator.py` — `run_orchestrator(state: DiagnosisState, config) -> dict` function
  - [ ] 5.2 Build orchestrator as a LangGraph `create_react_agent` subgraph with tools from Task 4, `response_format=DiagnosisObject`
  - [ ] 5.3 System prompt: extract alert metadata → form hypothesis → investigate with tools → produce structured diagnosis
  - [ ] 5.4 Handle coverage gap flag when no specialist exists (MVP generalist mode)
  - [ ] 5.5 Preserve rejected hypotheses in agent conversation for audit trail

- [ ] Task 6: Completeness gate (AC: #6)
  - [ ] 6.1 Create `backend/src/agents/completeness_gate.py` — `evaluate_completeness(diagnosis: DiagnosisObject, rce_alerts: list[dict]) -> CompletenessResult`
  - [ ] 6.2 Verify all alert fingerprints from the RCE are addressed in the diagnosis (evidence or explicit reasoning)
  - [ ] 6.3 If incomplete, return the diagnosis to the orchestrator with guidance on which alerts are unaddressed (max 2 retry iterations)

- [ ] Task 7: Integrate orchestrator into diagnosis graph (AC: #1, #2, #5, #6)
  - [ ] 7.1 Update `backend/src/pipeline/diagnosis_graph.py` — replace stub `diagnose_node` with call to `run_orchestrator`
  - [ ] 7.2 Add `completeness_gate` as a conditional edge after diagnosis (pass → finalize, fail → re-diagnose with max 2 retries)
  - [ ] 7.3 Emit SSE events for orchestrator progress (`incident.stage_changed` with diagnosis stage payload)

- [ ] Task 8: Dependencies and exports (AC: all)
  - [ ] 8.1 Add `langchain-openai`, `pgvector` to `backend/pyproject.toml` dependencies
  - [ ] 8.2 Update `backend/src/models/__init__.py` — export any new models (RunbookChunk, CompletenessResult)
  - [ ] 8.3 Register pgvector types in app lifespan (call `register_vector` on asyncpg pool init)

- [ ] Task 9: Tests — unit (AC: #1, #4, #5, #6, #7, #8)
  - [ ] 9.1 `tests/agents/test_orchestrator.py` — orchestrator produces valid DiagnosisObject with mocked LLM and mocked tools
  - [ ] 9.2 `tests/agents/test_tools.py` — each tool returns correct EvidenceArtifact/EvidenceSource
  - [ ] 9.3 `tests/agents/test_completeness_gate.py` — pass when all alerts addressed, fail when alerts missing
  - [ ] 9.4 `tests/knowledge/test_chunker.py` — markdown chunking preserves headings, respects size limits
  - [ ] 9.5 `tests/knowledge/test_runbook_rag.py` — retrieval returns ranked chunks (mock embedding + mock DB)

- [ ] Task 10: Tests — integration (AC: #2, #3, #4)
  - [ ] 10.1 `tests/db/test_runbooks.py` — store and retrieve runbook chunks via pgvector (testcontainers)
  - [ ] 10.2 `tests/knowledge/test_ingest.py` — end-to-end ingest of sample runbook files
  - [ ] 10.3 `tests/pipeline/test_diagnosis_graph.py` — update existing graph tests: orchestrator produces real DiagnosisObject (mocked LLM), completeness gate works, state transitions correct

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 2.1 (LangGraph Diagnosis Pipeline & MCP Integration) — DIRECT PREDECESSOR:**

Story 2.1 created the LangGraph diagnosis pipeline infrastructure that this story builds on. Key deliverables:

- **`pipeline/diagnosis_graph.py`** — LangGraph `StateGraph` with `DiagnosisState` TypedDict. Two nodes: `diagnose` (STUB producing placeholder DiagnosisObject) and `finalize`. The `diagnose` node is the STUB this story replaces with the full Orchestrator agent.
- **`pipeline/mcp_client.py`** — `ReadOnlyMCPClient` wrapping the MCP Python SDK with Streamable HTTP transport. `query_cluster(tool_name, arguments, timeout)` returns evidence or `EvidenceGap` on timeout. Connection to `http://mcp-readonly:8080/mcp`.
- **`pipeline/runner.py`** — `run_diagnosis_pipeline(item, conn)` invokes the LangGraph graph. Maps queue item to thread_id (incident UUID). Handles completion/failure, emits SSE events.
- **`pipeline/audit_hook.py`** — LangGraph callback writing pipeline state transitions to `audit_log` (AD-25 write point #2).
- **`db/checkpointer.py`** — `get_checkpointer()` returning `AsyncPostgresSaver` with psycopg pool. `setup()` called in app lifespan.
- **`config/mcp_settings.py`** — `MCPSettings` (URL, timeout, retries).
- **`models/diagnosis.py`** — `DiagnosisObject`, `EvidenceArtifact`, `EvidenceGap`, `ImmutableDiagnosisArtifact`, `EvidenceSource` enum, root-cause taxonomy constants. `root_cause_hash()` for deterministic comparison.
- **`pipeline/dispatcher.py`** — Updated from stub to async `_run_pipeline_task()` using `asyncio.create_task`.
- **`mcp` package** added to pyproject.toml dependencies.

**Critical patterns from 2.1 this story MUST follow:**
- `DiagnosisState` TypedDict is the graph state — extend it if needed but don't break existing fields
- The `diagnose` node receives the full `DiagnosisState` and must return a dict with updated state fields
- `EvidenceArtifact.source` must use `EvidenceSource` enum values (`MCP_CLUSTER`, `RUNBOOK`, etc.)
- MCP timeout → `EvidenceGap`, never an exception (AD-15)
- State transitions via `transition()` from `models/state_machine.py`
- Structured logging via `get_logger(Component.AGENT)`
- Two separate DB pools: asyncpg (application) and psycopg (LangGraph checkpoints)

**From Epic 1 (all stories complete):**
- State machine in `models/state_machine.py` — `transition(current, target)` raises `InvalidTransitionError`
- Event bus: `event_bus.emit(EventNames.INCIDENT_STAGE_CHANGED, SSEEventData(...))`
- DB operations always in `db/` module — never inline SQL
- Config pattern: frozen dataclass with `from_env()` classmethod and module-level singleton getter
- Logger pattern: `logger = get_logger(Component.X)`
- Test markers: `unit`, `db`, `api`, `pipeline`

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-1 | Agents internal to stages | Orchestrator lives in `agents/orchestrator.py`, called BY the `diagnose` node in `pipeline/diagnosis_graph.py`. It is NOT a pipeline-level node |
| AD-2 | RBAC Airlock | Orchestrator tools use `ReadOnlyMCPClient` ONLY. `cluster-reader` SA, `--read-only` MCP. Zero write access |
| AD-4 | Shared types module | `DiagnosisObject` already in `models/`. New models (RunbookChunk, CompletenessResult) go in `models/` |
| AD-7 | Per-agent LLM config | Orchestrator LLM config loaded from env vars. Helm values seed. Runtime API override is Story 6.1 scope |
| AD-13 | Dual-path knowledge retrieval | This story implements path 1: runbooks via pgvector RAG. Path 2 (RHOKP via okp-mcp) is Story 2.3 |
| AD-14 | Monorepo source tree | New agent code in `agents/`, knowledge code in `knowledge/`, DB operations in `db/` |
| AD-15 | MCP timeout → partial evidence | Already handled by `ReadOnlyMCPClient` from 2.1. Tools must propagate `EvidenceGap` correctly |
| AD-22 | Semantic cache in `knowledge/` | NOT this story — Story 6.4 implements the semantic cache middleware |
| AD-24 | In-process event bus | Orchestrator progress events emitted via the bus for SSE delivery |
| AD-25 | Audit log | Pipeline audit hook from 2.1 captures orchestrator state transitions. Rejected hypotheses logged to audit trail |

### Technical Requirements

#### Orchestrator Agent Architecture

The orchestrator is a LangGraph `create_react_agent` subgraph invoked by the diagnosis stage node. It runs INSIDE the diagnosis node — not as a separate graph node:

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

def build_orchestrator_agent(
    llm: BaseChatModel,
    tools: list,
    checkpointer=None,
) -> CompiledStateGraph:
    system_prompt = ORCHESTRATOR_SYSTEM_PROMPT
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
        response_format=(STRUCTURED_OUTPUT_PROMPT, DiagnosisObject),
    )
```

The diagnosis node calls the subgraph:

```python
async def diagnose_node(state: DiagnosisState) -> dict:
    orchestrator = build_orchestrator_agent(llm, tools)
    result = await orchestrator.ainvoke({
        "messages": [HumanMessage(content=build_diagnosis_prompt(state))],
    })
    diagnosis = result["structured_response"]
    return {"diagnosis": diagnosis.model_dump()}
```

Key constraints:
- The orchestrator subgraph uses the SAME checkpointer as the parent graph — LangGraph handles nested subgraph checkpointing automatically when the subgraph is compiled without its own checkpointer
- Tool calls are executed within the agent loop — the agent decides when to call `query_cluster`, `search_runbooks`, etc.
- `response_format=DiagnosisObject` triggers a final LLM call to produce structured output after the tool loop
- The `DiagnosisObject` is validated by Pydantic — invalid outputs raise, triggering a retry

#### LLM Client Configuration

```python
@dataclass(frozen=True)
class AgentLLMConfig:
    endpoint_url: str
    model_name: str
    temperature: float = 0.0
    api_key_env: str = "LLM_API_KEY"
    thinking_mode: bool = False
    max_tokens: int = 4096

class AgentRole(StrEnum):
    ORCHESTRATOR = "orchestrator"
    SKEPTIC = "skeptic"
    PLANNER = "planner"

def get_chat_model(role: AgentRole) -> ChatOpenAI:
    config = get_agent_llm_config(role)
    return ChatOpenAI(
        base_url=config.endpoint_url,
        model=config.model_name,
        temperature=config.temperature,
        api_key=os.environ.get(config.api_key_env, ""),
        max_tokens=config.max_tokens,
    )
```

Environment variables (Helm values → env):
- `LLM_ORCHESTRATOR_ENDPOINT` — default: `http://localhost:11434/v1` (ollama-compatible)
- `LLM_ORCHESTRATOR_MODEL` — default: `gpt-4o` (overridden per deployment)
- `LLM_ORCHESTRATOR_TEMPERATURE` — default: `0.0`
- `LLM_API_KEY` — from Kubernetes Secret (shared unless per-role override exists)

`ChatOpenAI` is used because most LLM providers (vLLM, ollama, Azure OpenAI, Anthropic via proxy, etc.) expose an OpenAI-compatible API. The `base_url` parameter allows pointing to any compatible endpoint without changing code. Per AD-7, runtime API override (DB layer) is Story 6.1 scope — this story implements Helm-seed-only config.

#### Runbook Ingestion and RAG

**Runbook storage schema:**
```sql
CREATE TABLE runbook_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    heading_hierarchy TEXT[] DEFAULT '{}',
    content TEXT NOT NULL,
    embedding vector(1536),
    token_count INTEGER NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_file, chunk_index)
);

CREATE INDEX runbook_chunks_embedding_idx
    ON runbook_chunks USING hnsw (embedding vector_cosine_ops);
```

**Chunking strategy:**
```python
def chunk_markdown(
    content: str,
    source_file: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[RunbookChunk]:
```
- Split on heading boundaries (`##`, `###`) first
- If a section exceeds `max_tokens`, split on paragraph boundaries
- Preserve heading hierarchy in `heading_hierarchy` field for context
- Overlap ensures cross-boundary continuity

**Similarity search:**
```python
async def search_similar(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    top_k: int = 5,
    similarity_threshold: float = 0.7,
) -> list[dict]:
    return await conn.fetch(
        """
        SELECT id, source_file, heading_hierarchy, content, token_count,
               1 - (embedding <=> $1::vector) AS similarity
        FROM runbook_chunks
        WHERE 1 - (embedding <=> $1::vector) > $3
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        query_embedding, top_k, similarity_threshold,
    )
```

**pgvector asyncpg registration:**
```python
from pgvector.asyncpg import register_vector

async def init_pgvector(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await register_vector(conn)
```

Call `init_pgvector` during app lifespan startup, after pool creation. Must be called once per connection that uses vector types. For pool usage, register on each acquired connection via pool's `init` callback:
```python
pool = await asyncpg.create_pool(..., init=register_vector)
```

**Embedding generation:**
```python
async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings via the configured embedding endpoint."""
    client = AsyncOpenAI(
        base_url=settings.embedding_endpoint,
        api_key=os.environ.get(settings.embedding_api_key_env, ""),
    )
    response = await client.embeddings.create(
        input=texts,
        model=settings.embedding_model,
    )
    return [item.embedding for item in response.data]
```

Uses the OpenAI embeddings API format — compatible with vLLM, ollama, etc. The embedding model and endpoint are configurable via `KnowledgeSettings`.

#### Completeness Gate

```python
@dataclass
class CompletenessResult:
    complete: bool
    unaddressed_alerts: list[str]
    reasoning: str

def evaluate_completeness(
    diagnosis: DiagnosisObject,
    rce_alerts: list[dict],
) -> CompletenessResult:
    addressed_fingerprints = set()
    for evidence in diagnosis.evidence:
        if "fingerprint" in evidence.query or "alert" in evidence.query.lower():
            addressed_fingerprints.add(...)

    all_fingerprints = {a["fingerprint"] for a in rce_alerts}
    unaddressed = all_fingerprints - addressed_fingerprints

    return CompletenessResult(
        complete=len(unaddressed) == 0,
        unaddressed_alerts=list(unaddressed),
        reasoning=f"Addressed {len(addressed_fingerprints)}/{len(all_fingerprints)} alerts",
    )
```

The completeness gate is a deterministic check (no LLM). If incomplete, the diagnosis is sent back to the orchestrator with the list of unaddressed alerts. Max 2 retries — after that, the diagnosis passes with an explicit `evidence_gaps` entry noting unaddressed alerts.

#### Orchestrator System Prompt

The system prompt must:
1. Identify the subsystem from alert labels (namespace, alertname, severity)
2. Instruct the agent to form hypotheses BEFORE tool use
3. Require concrete evidence for every claim (specific log lines, metric values, resource states)
4. Enforce root-cause code selection from the taxonomy
5. Instruct handling of conflicting evidence (pick most supported, preserve alternatives)
6. Require coverage of ALL alerts in the RCE

```python
ORCHESTRATOR_SYSTEM_PROMPT = """You are an OpenShift cluster diagnosis agent.
You receive a Root-Cause Event containing correlated alerts and must determine the root cause.

PROCESS:
1. Analyze the alert metadata (labels, annotations, alert name) to form an initial hypothesis
2. Query the cluster for evidence using the available tools
3. Search runbooks for operational guidance relevant to the symptoms
4. Synthesize findings into a structured diagnosis

RULES:
- Every claim MUST be backed by concrete evidence (specific log line, metric value, or resource state)
- Use root-cause codes from the taxonomy: {taxonomy_codes}
- If multiple root causes are possible, select the one with strongest evidence
- Preserve rejected hypotheses in your reasoning
- Address ALL {alert_count} alerts in the Root-Cause Event
- Flag coverage gaps when no specialist domain applies
- Record each piece of evidence with its source type
"""
```

#### DiagnosisState Extension

The `DiagnosisState` TypedDict from Story 2.1 may need extension:

```python
class DiagnosisState(TypedDict):
    incident_id: str
    root_cause_event: dict
    alerts: list[dict]
    mcp_evidence: list[dict]
    evidence_gaps: list[dict]
    diagnosis: dict | None
    stage: str
    # New fields for 2.2:
    runbook_context: list[dict]       # Retrieved runbook chunks
    completeness_attempts: int         # Track retry count (max 2)
    coverage_gaps: list[str]           # Alert types with no specialist
    rejected_hypotheses: list[dict]    # Alternative diagnoses considered
```

Add new fields with defaults so existing graph invocations don't break.

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ~=1.2 | Already in pyproject.toml. Agent subgraph via `create_react_agent` |
| langchain-openai | latest | **NEW — add to pyproject.toml**. `ChatOpenAI` for LLM calls with tool-calling + structured output |
| langchain-core | (transitive) | Already a transitive dep of langgraph. Base abstractions (`BaseChatModel`, `@tool`, `HumanMessage`) |
| pgvector | latest | **NEW — add to pyproject.toml**. pgvector-python for asyncpg vector type registration |
| openai | (transitive) | Already a transitive dep of langchain-openai. `AsyncOpenAI` for embedding API calls |
| asyncpg | latest | Already in pyproject.toml. Application DB + pgvector queries |
| mcp | latest | Already in pyproject.toml (added in 2.1). MCP Python SDK for cluster queries |

**ADD to `pyproject.toml` dependencies:**
```toml
"langchain-openai",
"pgvector",
```

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/agents/__init__.py` | Agents package init | NEW |
| `backend/src/agents/orchestrator.py` | Orchestrator agent — `build_orchestrator_agent()`, `run_orchestrator()` | NEW |
| `backend/src/agents/tools.py` | LangChain `@tool` functions (query_cluster, get_logs, search_runbooks) | NEW |
| `backend/src/agents/completeness_gate.py` | Completeness check before Skeptic handoff | NEW |
| `backend/src/agents/llm_client.py` | `get_chat_model(role)` factory wrapping `ChatOpenAI` | NEW |
| `backend/src/agents/prompts.py` | System prompts and prompt templates for orchestrator | NEW |
| `backend/src/knowledge/__init__.py` | Knowledge package init | NEW |
| `backend/src/knowledge/chunker.py` | Markdown runbook chunker (heading-aware, token-bounded) | NEW |
| `backend/src/knowledge/embeddings.py` | `embed_texts()` via OpenAI-compatible embedding endpoint | NEW |
| `backend/src/knowledge/runbook_rag.py` | `retrieve_runbook_context()` — top-k similarity search wrapper | NEW |
| `backend/src/knowledge/ingest.py` | Runbook ingestion pipeline (chunk → embed → upsert) | NEW |
| `backend/src/db/runbooks.py` | `store_chunks()`, `search_similar()`, pgvector queries | NEW |
| `backend/src/config/llm_settings.py` | `AgentLLMConfig`, `AgentRole`, per-role config resolution | NEW |
| `backend/src/config/knowledge_settings.py` | `KnowledgeSettings` (embedding model, thresholds, chunk sizes) | NEW |
| `backend/src/models/knowledge.py` | `RunbookChunk`, `CompletenessResult` Pydantic models | NEW |
| `backend/alembic/versions/xxx_add_runbook_chunks.py` | Migration: `runbook_chunks` table + HNSW index | NEW |
| `backend/tests/agents/__init__.py` | Test package init | NEW |
| `backend/tests/agents/conftest.py` | Mock LLM fixtures, mock tool fixtures | NEW |
| `backend/tests/agents/test_orchestrator.py` | Orchestrator unit tests (mocked LLM + tools) | NEW |
| `backend/tests/agents/test_tools.py` | Tool wrapper tests | NEW |
| `backend/tests/agents/test_completeness_gate.py` | Completeness gate tests | NEW |
| `backend/tests/knowledge/__init__.py` | Test package init | NEW |
| `backend/tests/knowledge/test_chunker.py` | Markdown chunking tests | NEW |
| `backend/tests/knowledge/test_runbook_rag.py` | RAG retrieval tests (mocked) | NEW |
| `backend/tests/knowledge/test_ingest.py` | Ingestion integration tests | NEW |
| `backend/tests/db/test_runbooks.py` | pgvector store/search DB tests (testcontainers) | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/pipeline/diagnosis_graph.py` | Replace stub `diagnose_node` with orchestrator invocation, add completeness gate conditional edge | UPDATE |
| `backend/src/models/__init__.py` | Export `RunbookChunk`, `CompletenessResult` | UPDATE |
| `backend/src/api/app.py` | Add pgvector `register_vector` to lifespan pool init | UPDATE |
| `backend/pyproject.toml` | Add `langchain-openai`, `pgvector` dependencies | UPDATE |
| `backend/tests/pipeline/test_diagnosis_graph.py` | Update graph tests for real orchestrator (mocked LLM) | UPDATE |

### Dependency Direction (ENFORCED)

```
models/knowledge.py → nothing (leaf, Pydantic only)
agents/tools.py → pipeline/mcp_client.py (MCP queries), knowledge/runbook_rag.py (RAG), models/ (EvidenceArtifact)
agents/orchestrator.py → agents/tools.py, agents/llm_client.py, agents/completeness_gate.py, models/ (DiagnosisObject)
agents/llm_client.py → config/llm_settings.py
agents/completeness_gate.py → models/ (DiagnosisObject)
knowledge/runbook_rag.py → knowledge/embeddings.py, db/runbooks.py
knowledge/embeddings.py → config/knowledge_settings.py
knowledge/chunker.py → models/knowledge.py (RunbookChunk)
knowledge/ingest.py → knowledge/chunker.py, knowledge/embeddings.py, db/runbooks.py
db/runbooks.py → models/knowledge.py (for types)
pipeline/diagnosis_graph.py → agents/orchestrator.py (replaces stub)
config/llm_settings.py → nothing (leaf, reads env vars)
config/knowledge_settings.py → nothing (leaf, reads env vars)
```

- **NEVER**: `models/` imports from `agents/`, `knowledge/`, `pipeline/`, `api/`, or `db/`
- **NEVER**: `agents/` imports from `api/` or `pipeline/` (except `pipeline/mcp_client.py` for tool wrapping)
- **NEVER**: `knowledge/` imports from `agents/` or `api/`
- **ALLOWED**: `agents/` imports from `knowledge/` (for RAG retrieval in tools)
- **ALLOWED**: `agents/` imports from `pipeline/mcp_client.py` (for cluster query tools)

### Testing Requirements

**Unit tests** (`pytest -m unit`):
- Orchestrator with mocked LLM returns valid `DiagnosisObject` — correct root_cause_code format, confidence 0–1, non-empty evidence
- Orchestrator with mocked LLM and mocked tools — tool calls are made (query_cluster, search_runbooks), evidence artifacts have correct `EvidenceSource`
- Coverage gap flagged when no specialist covers alert type (always in MVP)
- Conflicting evidence produces single diagnosis with rationale + preserved alternatives
- `query_cluster_resources` tool wraps MCP client, returns `EvidenceArtifact` with `source=EvidenceSource.MCP_CLUSTER`
- `search_runbooks` tool wraps RAG retrieval, returns `EvidenceArtifact` with `source=EvidenceSource.RUNBOOK`
- Completeness gate passes when all alert fingerprints are addressed in evidence
- Completeness gate fails when alert fingerprints are missing, returns unaddressed list
- Markdown chunker splits on heading boundaries, respects max token limit
- Markdown chunker preserves heading hierarchy in chunk metadata
- RAG retrieval returns ranked chunks by similarity score (mocked embedding + mocked DB)

**DB integration tests** (`pytest -m db`):
- `runbook_chunks` table created by migration (testcontainers)
- `store_chunks()` inserts chunks with embeddings
- `search_similar()` returns results ranked by cosine similarity
- `search_similar()` filters by `similarity_threshold`
- Duplicate chunk upsert (same `source_file` + `chunk_index`) updates content

**Pipeline integration tests** (`pytest -m pipeline`):
- Updated graph tests: orchestrator node produces `DiagnosisObject` with mocked LLM
- Completeness gate conditional edge: pass → finalize, fail → retry diagnosis
- Max 2 completeness retries enforced — diagnosis passes after 2 failures
- State transitions: `queued→diagnosing→diagnosed` for success path
- Event bus receives `incident.stage_changed` events during orchestrator execution

**Mock LLM Fixture:**
The orchestrator tests must mock the LLM at the `ChatOpenAI` boundary. Create a `FakeChatModel` fixture that:
- Returns deterministic tool-call responses when given specific prompts
- Produces a valid `DiagnosisObject` as structured output on the final call
- Supports configurable response sequences (for multi-turn tool-calling loops)
- Lives in `tests/agents/conftest.py` for reuse in Stories 2.3 and 2.4

```python
class FakeChatModel(BaseChatModel):
    responses: list[BaseMessage]
    call_count: int = 0

    def _generate(self, messages, stop=None, **kwargs):
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return ChatResult(generations=[ChatGeneration(message=response)])
```

### Anti-Patterns / DO NOT

- **DO NOT** implement the Skeptic agent. Story 2.4 adds the Diagnosis Skeptic. The completeness gate hands off to `finalize_node` — which will become the Skeptic handoff in 2.4.
- **DO NOT** implement RHOKP integration. Story 2.3 adds RHOKP via okp-mcp + Learning Store. This story only implements runbook pgvector RAG.
- **DO NOT** implement agentic skills. Story 2.3 adds callable skills. This story uses MCP tools + runbook RAG only.
- **DO NOT** implement runtime API override for LLM config. Story 6.1 adds the DB-persisted override layer. This story implements Helm-seed-only config (env vars).
- **DO NOT** implement the semantic cache. Story 6.4 adds the semantic cache middleware in `knowledge/`. This story's embedding/RAG code is separate from cache.
- **DO NOT** create a write-capable MCP client or connect to `mcp-readwrite`. This story is diagnosis-only — `cluster-reader` SA with `--read-only` flag. The read-write MCP is Story 3.x scope.
- **DO NOT** modify existing models from 2.1 (`diagnosis.py`, `state_machine.py`). Extend `DiagnosisState` with new fields only — don't change existing field types or names.
- **DO NOT** modify the graph structure beyond replacing the `diagnose` stub and adding the completeness gate edge. The Skeptic node is Story 2.4.
- **DO NOT** implement production-grade runbook ingestion with scheduled refresh. This story bundles runbooks at build time — refresh = image rebuild per AD-13.
- **DO NOT** use `litellm` directly — use `ChatOpenAI` with `base_url` for multi-provider support. This keeps the dependency chain clean (LangGraph → langchain-openai → openai).
- **DO NOT** add any frontend code. Frontend is Epic 5 scope.
- **DO NOT** create new Helm chart templates. MCP Server deployment was added in 2.1.
- **DO NOT** implement any E2E tests against real LLM or MCP endpoints — mock everything. Real integration is deferred to post-Epic 3.

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  agents/                    # NEW directory (first agent code in the project)
    __init__.py              # NEW
    orchestrator.py          # NEW: Orchestrator agent (create_react_agent subgraph)
    tools.py                 # NEW: @tool functions (MCP, RAG)
    completeness_gate.py     # NEW: Pre-Skeptic completeness check
    llm_client.py            # NEW: ChatOpenAI factory per agent role
    prompts.py               # NEW: System prompts
  knowledge/                 # NEW directory (first knowledge code)
    __init__.py              # NEW
    chunker.py               # NEW: Markdown → chunks
    embeddings.py            # NEW: Text → embeddings
    runbook_rag.py           # NEW: pgvector similarity search
    ingest.py                # NEW: Runbook ingestion pipeline
  models/
    knowledge.py             # NEW: RunbookChunk, CompletenessResult
    __init__.py              # UPDATE: export new models
  pipeline/
    diagnosis_graph.py       # UPDATE: replace stub, add completeness gate
  db/
    runbooks.py              # NEW: pgvector CRUD for runbook_chunks
  config/
    llm_settings.py          # NEW: Per-agent LLM config
    knowledge_settings.py    # NEW: Embedding + RAG settings
  api/
    app.py                   # UPDATE: pgvector init in lifespan
backend/tests/
  agents/                    # NEW test directory
    __init__.py              # NEW
    conftest.py              # NEW: FakeChatModel, mock tool fixtures
    test_orchestrator.py     # NEW
    test_tools.py            # NEW
    test_completeness_gate.py # NEW
  knowledge/                 # NEW test directory
    __init__.py              # NEW
    test_chunker.py          # NEW
    test_runbook_rag.py      # NEW
    test_ingest.py           # NEW
  db/
    test_runbooks.py         # NEW: pgvector tests (testcontainers)
  pipeline/
    test_diagnosis_graph.py  # UPDATE: orchestrator integration
```

### Latest Technology Notes

**LangGraph 1.2.x — `create_react_agent`:**
- `create_react_agent(model, tools, prompt=..., response_format=PydanticModel)` creates a complete ReAct agent subgraph
- `response_format` triggers an additional LLM call after the tool loop to produce structured output stored in `state["structured_response"]`
- For dedicated structured output prompt, pass `response_format=(prompt_str, PydanticModel)` as a tuple
- `version="v2"` is the default and recommended version
- Tools must be `@tool`-decorated functions or LangChain `BaseTool` instances
- `ToolNode` handles parallel tool execution automatically
- The agent loop: model → check tool_calls → yes → execute tools → back to model → no → (optional structured response) → END
- Subgraph checkpointing: when used inside a parent `StateGraph`, the subgraph's state is checkpointed with the parent's checkpointer

**pgvector 0.8.x with asyncpg:**
- `pgvector.asyncpg.register_vector(conn)` must be called per connection before vector operations
- For connection pools: pass `init=register_vector` to `asyncpg.create_pool()` to auto-register on each connection
- HNSW index: `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)` — better query performance than IVFFlat, can be created on empty tables
- Cosine distance operator: `<=>` — lower = more similar. Convert to similarity: `1 - (embedding <=> query::vector)`
- Vector dimension must match embedding model output (1536 for text-embedding-3-small, 768 for smaller models)
- Python types: input as list/numpy array, output as numpy.ndarray (dtype=float32)

**langchain-openai:**
- `ChatOpenAI(base_url=..., model=..., api_key=..., temperature=...)` — works with any OpenAI-compatible API endpoint
- Supports `.with_structured_output(PydanticModel)` for direct structured output binding
- Tool calling via `.bind_tools(tools)` — model must support function calling
- `ChatOpenAI` is the recommended model class for LangGraph's `create_react_agent`

### References

- [Source: ARCHITECTURE-SPINE.md#AD-1] — Agents internal to stages (orchestrator in `agents/`, called by diagnosis node)
- [Source: ARCHITECTURE-SPINE.md#AD-2] — RBAC Airlock (cluster-reader for diagnosis, read-only MCP only)
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types module (DiagnosisObject, new models in `models/`)
- [Source: ARCHITECTURE-SPINE.md#AD-7] — Per-agent LLM config (Helm seed layer, env vars)
- [Source: ARCHITECTURE-SPINE.md#AD-13] — Runbooks via pgvector RAG (path 1 of dual-path retrieval)
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout (`agents/`, `knowledge/`, `db/`, `config/`)
- [Source: ARCHITECTURE-SPINE.md#AD-15] — MCP timeout → partial evidence with `evidence_gaps`
- [Source: ARCHITECTURE-SPINE.md#AD-22] — Semantic cache in `knowledge/` (NOT this story — Story 6.4)
- [Source: ARCHITECTURE-SPINE.md#AD-24] — In-process event bus for SSE
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit log write points (pipeline audit hook from 2.1)
- [Source: project-context.md#LangGraph] — Agents internal to stages, checkpoints, state machine
- [Source: project-context.md#Testing Rules] — Mock MCP, mock LLM, test layers
- [Source: project-context.md#Critical Don't-Miss Rules] — RBAC Airlock, never query langgraph_* tables
- [Source: epics.md#Story 2.2] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 2] — FR-4, FR-5, FR-6 coverage
- [Source: Story 2.1 spec] — DiagnosisState, DiagnosisObject, ReadOnlyMCPClient, diagnosis_graph.py stub
- [Source: Story 1.4] — Event bus pattern, SSE plumbing, audit middleware
- [Source: LangGraph docs — create_react_agent] — Prebuilt ReAct agent with response_format
- [Source: pgvector-python docs] — asyncpg integration, register_vector, HNSW indexing

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
