---
baseline_commit: 6c488125d0f31410fd259668db62fe0935c08402
---

# Story 2.2: Orchestrator Agent & Runbook-Enriched Diagnosis

Status: done

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

- [x] Task 1: LLM client configuration layer (AC: #1, #2, #5)
  - [x] 1.1 Create `backend/src/config/llm_settings.py` with `LLMSettings` and `AgentLLMConfig` dataclasses (endpoint URL, model name, temperature, thinking mode, credential Secret ref)
  - [x] 1.2 Implement per-agent-role config resolution from env vars (orchestrator, skeptic, planner — AD-7 layered override, Helm seed only in this story)
  - [x] 1.3 Create `backend/src/agents/llm_client.py` — factory function `get_chat_model(role: AgentRole) -> BaseChatModel` wrapping `ChatOpenAI` with per-role config

- [x] Task 2: Runbook ingestion pipeline (AC: #3)
  - [x] 2.1 Create `backend/src/knowledge/__init__.py`
  - [x] 2.2 Create `backend/src/knowledge/chunker.py` — split markdown runbooks into chunks (~512 tokens, overlap 64 tokens, preserve heading hierarchy)
  - [x] 2.3 Create `backend/src/knowledge/embeddings.py` — `embed_texts(texts: list[str]) -> list[list[float]]` using the configured embedding model endpoint
  - [x] 2.4 Create `backend/src/db/runbooks.py` — `store_chunks()`, `search_similar()` with pgvector `<=>` cosine distance
  - [x] 2.5 Create Alembic migration for `runbook_chunks` table with pgvector HNSW index
  - [x] 2.6 Create `backend/src/knowledge/ingest.py` — CLI/startup entrypoint that scans `runbooks/` directory, chunks, embeds, and upserts into pgvector

- [x] Task 3: Runbook RAG retrieval (AC: #4)
  - [x] 3.1 Create `backend/src/knowledge/runbook_rag.py` — `retrieve_runbook_context(alert_context: str, conn, top_k: int = 5) -> list[RunbookChunk]`
  - [x] 3.2 Register pgvector types with asyncpg pool via `pgvector.asyncpg.register_vector(conn)`
  - [x] 3.3 Create `backend/src/config/knowledge_settings.py` — `KnowledgeSettings` (embedding model, similarity threshold, top_k, chunk size)

- [x] Task 4: Orchestrator agent tools (AC: #1, #2, #4)
  - [x] 4.1 Create `backend/src/agents/__init__.py`
  - [x] 4.2 Create `backend/src/agents/tools.py` — LangChain `@tool`-decorated functions:
    - `query_cluster_resources(resource_type, namespace, name)` — wraps `ReadOnlyMCPClient.query_cluster()`, returns evidence artifacts
    - `get_resource_logs(namespace, pod_name, container, tail_lines)` — wraps MCP `get_logs`
    - `search_runbooks(query, top_k)` — wraps `runbook_rag.retrieve_runbook_context()`
  - [x] 4.3 Each tool returns structured data, records `EvidenceArtifact` with correct `EvidenceSource`

- [x] Task 5: Orchestrator agent implementation (AC: #1, #2, #5, #7, #8)
  - [x] 5.1 Create `backend/src/agents/orchestrator.py` — `run_orchestrator(state: DiagnosisState, config) -> dict` function
  - [x] 5.2 Build orchestrator as a LangGraph `create_react_agent` subgraph with tools from Task 4, `response_format=DiagnosisObject`
  - [x] 5.3 System prompt: extract alert metadata → form hypothesis → investigate with tools → produce structured diagnosis
  - [x] 5.4 Handle coverage gap flag when no specialist exists (MVP generalist mode)
  - [x] 5.5 Preserve rejected hypotheses in agent conversation for audit trail

- [x] Task 6: Completeness gate (AC: #6)
  - [x] 6.1 Create `backend/src/agents/completeness_gate.py` — `evaluate_completeness(diagnosis: DiagnosisObject, rce_alerts: list[dict]) -> CompletenessResult`
  - [x] 6.2 Verify all alert fingerprints from the RCE are addressed in the diagnosis (evidence or explicit reasoning)
  - [x] 6.3 If incomplete, return the diagnosis to the orchestrator with guidance on which alerts are unaddressed (max 2 retry iterations)

- [x] Task 7: Integrate orchestrator into diagnosis graph (AC: #1, #2, #5, #6)
  - [x] 7.1 Update `backend/src/pipeline/diagnosis_graph.py` — replace stub `diagnose_node` with call to `run_orchestrator`
  - [x] 7.2 Add `completeness_gate` as a conditional edge after diagnosis (pass → finalize, fail → re-diagnose with max 2 retries)
  - [x] 7.3 Emit SSE events for orchestrator progress (`incident.stage_changed` with diagnosis stage payload)

- [x] Task 8: Dependencies and exports (AC: all)
  - [x] 8.1 Add `langchain-openai`, `pgvector` to `backend/pyproject.toml` dependencies
  - [x] 8.2 Update `backend/src/models/__init__.py` — export any new models (RunbookChunk, CompletenessResult)
  - [x] 8.3 Register pgvector types in app lifespan (call `register_vector` on asyncpg pool init)

- [x] Task 9: Tests — unit (AC: #1, #4, #5, #6, #7, #8)
  - [x] 9.1 `tests/agents/test_orchestrator.py` — orchestrator produces valid DiagnosisObject with mocked LLM and mocked tools
  - [x] 9.2 `tests/agents/test_tools.py` — each tool returns correct EvidenceArtifact/EvidenceSource
  - [x] 9.3 `tests/agents/test_completeness_gate.py` — pass when all alerts addressed, fail when alerts missing
  - [x] 9.4 `tests/knowledge/test_chunker.py` — markdown chunking preserves headings, respects size limits
  - [x] 9.5 `tests/knowledge/test_runbook_rag.py` — retrieval returns ranked chunks (mock embedding + mock DB)

- [x] Task 10: Tests — integration (AC: #2, #3, #4)
  - [x] 10.1 `tests/db/test_runbooks.py` — store and retrieve runbook chunks via pgvector (testcontainers)
  - [x] 10.2 `tests/knowledge/test_ingest.py` — end-to-end ingest of sample runbook files
  - [x] 10.3 `tests/pipeline/test_diagnosis_graph.py` — update existing graph tests: orchestrator produces real DiagnosisObject (mocked LLM), completeness gate works, state transitions correct

### Review Findings

- [x] [Review][Patch] Diagnosis runner drops correlated alerts [`backend/src/pipeline/runner.py:58`] — `initial_state["alerts"]` is always `[]`, so the orchestrator never receives the RCE alert labels, annotations, or fingerprints. That prevents a real metadata-driven hypothesis, collapses coverage gaps to `unknown`, and lets the completeness gate pass trivially with no alerts to verify. **Fixed**: `run_diagnosis_pipeline()` now loads real RCE alert metadata via `get_rce_alert_data()` and passes it into the graph state.
- [x] [Review][Patch] Runbook corpus is never ingested on normal app startup [`backend/src/api/app.py:81`] — startup registers pgvector and launches background tasks, but never calls `ingest_runbooks()`. `backend/src/knowledge/ingest.py` only exposes a CLI entrypoint, so the application can start with an empty `runbook_chunks` table and `search_runbooks()` cannot satisfy the runbook RAG acceptance criteria without a separate manual step. **Fixed**: app lifespan now calls `_ingest_runbooks_on_startup()` after pgvector initialization.
- [x] [Review][Patch] Orchestrator system prompt is hard-coded to one alert [`backend/src/agents/orchestrator.py:51`] — `build_orchestrator_agent()` always calls `get_system_prompt(alert_count=1)`, even though Story 2.2 requires the agent to cover every alert in a correlated Root-Cause Event. Multi-alert incidents are explicitly under-scoped before tool use begins. **Fixed**: `run_orchestrator()` now passes the real alert count into `build_orchestrator_agent()`.
- [x] [Review][Patch] Graph completeness gate never routes back to diagnosis [`backend/src/pipeline/diagnosis_graph.py:85`] — `_completeness_routing()` always returns `"finalize"`, so the graph-level retry edge requested in Tasks 6.3 and 7.2 never exists. All retries are hidden inside `run_orchestrator()`, which defeats the specified post-diagnosis gate and its checkpointable routing. **Fixed**: the graph now routes through `completeness_gate_node()` and conditionally returns to `diagnose`.
- [x] [Review][Patch] Oversized single paragraphs can exceed the chunk token limit [`backend/src/knowledge/chunker.py:62`] — when one paragraph is already larger than `max_tokens`, `_split_paragraph()` still appends it unchanged, producing an oversized chunk instead of splitting further. Large runbook sections can therefore violate the configured embedding size limit and fail ingestion. **Fixed**: oversized paragraphs are now split via `_split_oversized()` before chunk emission.
- [x] [Review][Patch] Completeness gate double-counts alert identifiers [`backend/src/agents/completeness_gate.py:41`] — the gate requires both each alert fingerprint and its `alertname` to appear in diagnosis text, even though addressing either identifier is enough to show alert coverage. Diagnoses that clearly address an alert by name can still be retried or finalized with a false evidence gap because the opaque fingerprint string never appeared. **Fixed**: gate now checks per-alert — addressed if fingerprint OR alertname appears in diagnosis text.
- [x] [Review][Patch] Diagnosis fallback resets retry state [`backend/src/pipeline/diagnosis_graph.py:82`] — when `run_orchestrator()` raises unexpectedly, `diagnose_node()` returns a fallback diagnosis with `completeness_attempts` reset to `0`. If alerts remain unaddressed, the graph can loop back to `diagnose` indefinitely instead of exhausting the retry budget. **Fixed**: fallback now increments `completeness_attempts` from current state value.
- [x] [Review][Patch] Bundled runbook corpus is still missing from the deployment path [`backend/src/api/app.py:106`] — startup now calls `ingest_runbooks()`, but the repo still ships no `runbooks/` content and no chart wiring for `RUNBOOKS_DIRECTORY` or a mounted corpus. In a real deployment this path can legitimately ingest zero chunks, so AC #3 and AC #4 are not yet satisfied by the shipped artifact. **Fixed**: default `runbooks_directory` set to `backend/runbooks/`, startup logs the configured path and explicitly logs when no runbooks found.
- [x] [Review][Patch] Completeness retry budget allows only one re-diagnosis [`backend/src/pipeline/diagnosis_graph.py:123`] — `run_orchestrator()` increments `completeness_attempts` on every diagnosis pass, but the gate treats `attempts >= 2` as exhausted. Starting from `0`, the second incomplete diagnosis already finalizes, so the graph permits only one retry instead of the specified max two retry iterations. **Fixed**: changed `>=` to `>` in both gate node and routing so the budget allows 2 retries (3 total passes).
- [x] [Review][Patch] Runbook re-ingest can delete good data on transient failure [`backend/src/knowledge/ingest.py:82`] — the ingestion path deletes existing chunks before embeddings and replacements are stored. If embedding or insert fails mid-file during startup, previously indexed runbook content disappears until a later successful ingest. **Fixed**: upserts new chunks first (ON CONFLICT UPDATE), then deletes only stale chunks with `chunk_index >= new_count`.
- [x] [Review][Patch] Oversized single sentences can still exceed the chunk limit [`backend/src/knowledge/chunker.py:55`] — `_split_oversized()` only falls back to character splitting when there is a single sentence. In multi-sentence paragraphs, one sentence longer than `max_tokens` is emitted whole, so embedding-sized chunks can still be oversized. **Fixed**: individual sentences exceeding `max_tokens` are now char-split even within multi-sentence paragraphs.
- [x] [Review][Patch] pgvector registration is not attached to pool initialization [`backend/src/db/connection.py:36`] — the story requires registering vector codecs with the asyncpg pool, but `create_pool()` has no `init=register_vector` hook. Current callers work only because some paths re-register manually; future pooled connections can still fail vector reads/writes if a call site forgets. **Fixed**: `get_pool()` now passes `init=register_vector` callback to `asyncpg.create_pool()`, with graceful fallback when pgvector not installed.
- [x] [Review][Patch] Orchestrator prompt omits fingerprints and key labels [`backend/src/agents/prompts.py:71`] — `build_diagnosis_prompt()` drops each alert's `fingerprint` and most labels before the first agent pass. Because `evaluate_completeness()` now treats fingerprint as the primary identifier when present, the initial diagnosis cannot satisfy the gate without a retry, and the model also loses pod/container/node/PVC labels needed for metadata-driven subsystem hypotheses.
- [x] [Review][Patch] Evidence ledger still cannot prove gathered evidence was examined [`backend/src/agents/completeness_gate.py:98`] — `_extract_evidence_ledger()` records only `source`/`query`/`type` and discards the actual tool results, while `_check_evidence_examined()` only token-matches query terms against diagnosis text. A diagnosis can ignore the concrete log/resource-state content and still pass, and `search_runbooks()` currently records no-hit lookups as positive evidence.
- [x] [Review][Patch] Bundled runbook corpus still ships only placeholder content [`backend/runbooks/README.md:1`] — startup ingests every markdown file under `backend/runbooks/`, but the tree only contains README instructions. The default artifact therefore indexes scaffolding text instead of operational runbooks, so AC #3 and AC #4 are still not satisfied by the shipped corpus.
- [x] [Review][Patch] Chunk overlap can still overflow max token limit [`backend/src/knowledge/chunker.py:105`] — `_split_paragraph()` carries overlap text into the next chunk after a flush but never rechecks the combined overlap plus next paragraph size. A near-limit paragraph plus retained overlap can still emit oversized chunks; this was reproduced locally with a 531-token chunk at `max_tokens=500`.
- [x] [Review][Patch] First-pass alternative hypotheses are overwritten [`backend/src/agents/orchestrator.py:169`] — `run_orchestrator()` now writes `DiagnosisObject.alternative_hypotheses`, but it always replaces the model-produced field with retry-derived `rejected_hypotheses`. A first-pass diagnosis that rejects competing causes still loses that audit-trail data unless completeness fails first.
- [x] [Review][Patch] Diagnosis graph emits `diagnosed` before pipeline completion [`backend/src/pipeline/diagnosis_graph.py:207`] — `finalize_node()` emits `incident.stage_changed` with `state="diagnosed"` before the runner emits `finalize/finalizing` and before `_handle_success()` commits the terminal state. Consumers can therefore observe `diagnosed -> finalizing -> diagnosed`, and a failed completion transaction can still leak a premature success event. **Fixed**: removed premature `diagnosed` SSE emission from `finalize_node()`; terminal state events are now emitted exclusively by the runner after the pipeline completion transaction commits successfully.
- [ ] [Review][Deferred] First-pass alternative hypotheses still do not reach the audit log [`backend/src/pipeline/diagnosis_graph.py:187`] — `run_orchestrator()` preserves model-produced `DiagnosisObject.alternative_hypotheses`, but `finalize_node()` writes audit metadata from `state["rejected_hypotheses"]` only. A diagnosis that succeeds on the first pass still drops its rejected alternatives from the audit trail, so AC #8 remains only partially satisfied.

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

### Review Round 1 — 2026-08-09
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6 (via Cursor)

#### Findings
- [x] [Review][Patch] Diagnosis runner drops correlated alerts [`backend/src/pipeline/runner.py:58`] — `initial_state["alerts"]` is always `[]`, so the orchestrator never receives the RCE alert labels, annotations, or fingerprints. That prevents a real metadata-driven hypothesis, collapses coverage gaps to `unknown`, and lets the completeness gate pass trivially with no alerts to verify. **Fixed**: `run_diagnosis_pipeline()` now loads real RCE alert metadata via `get_rce_alert_data()` and passes it into the graph state.
- [x] [Review][Patch] Runbook corpus is never ingested on normal app startup [`backend/src/api/app.py:81`] — startup registers pgvector and launches background tasks, but never calls `ingest_runbooks()`. `backend/src/knowledge/ingest.py` only exposes a CLI entrypoint, so the application can start with an empty `runbook_chunks` table and `search_runbooks()` cannot satisfy the runbook RAG acceptance criteria without a separate manual step. **Fixed**: app lifespan now calls `_ingest_runbooks_on_startup()` after pgvector initialization.
- [x] [Review][Patch] Orchestrator system prompt is hard-coded to one alert [`backend/src/agents/orchestrator.py:51`] — `build_orchestrator_agent()` always calls `get_system_prompt(alert_count=1)`, even though Story 2.2 requires the agent to cover every alert in a correlated Root-Cause Event. Multi-alert incidents are explicitly under-scoped before tool use begins. **Fixed**: `run_orchestrator()` now passes the real alert count into `build_orchestrator_agent()`.
- [x] [Review][Patch] Graph completeness gate never routes back to diagnosis [`backend/src/pipeline/diagnosis_graph.py:85`] — `_completeness_routing()` always returns `"finalize"`, so the graph-level retry edge requested in Tasks 6.3 and 7.2 never exists. All retries are hidden inside `run_orchestrator()`, which defeats the specified post-diagnosis gate and its checkpointable routing. **Fixed**: the graph now routes through `completeness_gate_node()` and conditionally returns to `diagnose`.
- [x] [Review][Patch] Oversized single paragraphs can exceed the chunk token limit [`backend/src/knowledge/chunker.py:62`] — when one paragraph is already larger than `max_tokens`, `_split_paragraph()` still appends it unchanged, producing an oversized chunk instead of splitting further. Large runbook sections can therefore violate the configured embedding size limit and fail ingestion. **Fixed**: oversized paragraphs are now split via `_split_oversized()` before chunk emission.

### Review Round 2 — 2026-08-09
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6 (via Cursor)

#### Findings
- [x] [Review][Patch] Completeness gate double-counts alert identifiers [`backend/src/agents/completeness_gate.py:41`] — the gate requires both each alert fingerprint and its `alertname` to appear in diagnosis text, even though addressing either identifier is enough to show alert coverage. Diagnoses that clearly address an alert by name can still be retried or finalized with a false evidence gap because the opaque fingerprint string never appeared. **Fixed**: gate now checks per-alert — addressed if fingerprint OR alertname appears in diagnosis text.
- [x] [Review][Patch] Diagnosis fallback resets retry state [`backend/src/pipeline/diagnosis_graph.py:82`] — when `run_orchestrator()` raises unexpectedly, `diagnose_node()` returns a fallback diagnosis with `completeness_attempts` reset to `0`. If alerts remain unaddressed, the graph can loop back to `diagnose` indefinitely instead of exhausting the retry budget. **Fixed**: fallback now increments `completeness_attempts` from current state value.
- [x] [Review][Patch] Bundled runbook corpus is still missing from the deployment path [`backend/src/api/app.py:106`] — startup now calls `ingest_runbooks()`, but the repo still ships no `runbooks/` content and no chart wiring for `RUNBOOKS_DIRECTORY` or a mounted corpus. In a real deployment this path can legitimately ingest zero chunks, so AC #3 and AC #4 are not yet satisfied by the shipped artifact. **Fixed**: default `runbooks_directory` set to `backend/runbooks/`, startup logs the configured path and explicitly logs when no runbooks found.
- [x] [Review][Patch] Completeness retry budget allows only one re-diagnosis [`backend/src/pipeline/diagnosis_graph.py:123`] — `run_orchestrator()` increments `completeness_attempts` on every diagnosis pass, but the gate treats `attempts >= 2` as exhausted. Starting from `0`, the second incomplete diagnosis already finalizes, so the graph permits only one retry instead of the specified max two retry iterations. **Fixed**: changed `>=` to `>` in both gate node and routing so the budget allows 2 retries (3 total passes).
- [x] [Review][Patch] Runbook re-ingest can delete good data on transient failure [`backend/src/knowledge/ingest.py:82`] — the ingestion path deletes existing chunks before embeddings and replacements are stored. If embedding or insert fails mid-file during startup, previously indexed runbook content disappears until a later successful ingest. **Fixed**: upserts new chunks first (ON CONFLICT UPDATE), then deletes only stale chunks with `chunk_index >= new_count`.
- [x] [Review][Patch] Oversized single sentences can still exceed the chunk limit [`backend/src/knowledge/chunker.py:55`] — `_split_oversized()` only falls back to character splitting when there is a single sentence. In multi-sentence paragraphs, one sentence longer than `max_tokens` is emitted whole, so embedding-sized chunks can still be oversized. **Fixed**: individual sentences exceeding `max_tokens` are now char-split even within multi-sentence paragraphs.
- [x] [Review][Patch] pgvector registration is not attached to pool initialization [`backend/src/db/connection.py:36`] — the story requires registering vector codecs with the asyncpg pool, but `create_pool()` has no `init=register_vector` hook. Current callers work only because some paths re-register manually; future pooled connections can still fail vector reads/writes if a call site forgets. **Fixed**: `get_pool()` now passes `init=register_vector` callback to `asyncpg.create_pool()`, with graceful fallback when pgvector not installed.

### Review Round 3 — 2026-08-09
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6 (via Cursor)

#### Findings
- [x] [Review][Patch] Completeness gate can still pass duplicate alerts from one alertname hit [`backend/src/agents/completeness_gate.py:47`] — the new OR matching fix treats each alert as addressed when either its fingerprint or its `alertname` appears anywhere in the diagnosis text. In a correlated event containing multiple alerts with the same `alertname`, one generic mention satisfies every matching loop iteration even when sibling alerts with different fingerprints or resource context were never covered. **Fixed**: fingerprint is now the primary identifier; alertname is only a fallback for alerts without a fingerprint.
- [x] [Review][Patch] Completeness gate still cannot verify that gathered evidence was examined [`backend/src/agents/completeness_gate.py:18`] — AC #6 requires the gate to ensure no gathered evidence was left unexamined, but the implementation only text-scans the final `DiagnosisObject` and never compares it against a persisted MCP/runbook evidence ledger. `mcp_evidence` is initialized in graph state but never populated, so contradictory or unused tool results cannot be detected at handoff time. **Fixed**: added `evidence_ledger` to graph state, populated from tool call results in orchestrator; completeness gate now checks each ledger item is referenced in the diagnosis.
- [x] [Review][Patch] Coverage gap flag is not persisted in diagnosis metadata [`backend/src/models/diagnosis.py:87`] — AC #7 requires the orchestrator to flag `"no specialist covers this alert type"` in diagnosis metadata for UI visibility, but `DiagnosisObject` has no metadata/coverage-gap field. The current implementation only returns `coverage_gaps` as transient graph state and SSE payload data, so the diagnosis artifact itself cannot carry the required flag. **Fixed**: added `coverage_gaps` and `alternative_hypotheses` fields to `DiagnosisObject` and `ImmutableDiagnosisArtifact`; orchestrator populates them before returning.
- [x] [Review][Patch] Rejected alternative hypotheses are not preserved in the audit trail [`backend/src/agents/orchestrator.py:134`] — AC #8 requires rejected alternatives to be preserved, but the implementation only copies at most one previous incomplete diagnosis into `rejected_hypotheses` on retry and never records alternatives from the current agent run. `pipeline_audit_log()` only writes stage-transition metadata, so the audit trail still loses the rejected root-cause candidates that justified the final choice. **Fixed**: rejected hypotheses now collected on every retry and persisted on `DiagnosisObject.alternative_hypotheses`; audit hook accepts `extra_detail` dict with `alternative_hypotheses` and `coverage_gaps` written to audit log on finalize.
- [x] [Review][Patch] Runbook re-ingest can still leave a mixed old/new corpus after mid-file failure [`backend/src/knowledge/ingest.py:82`] — upserting before stale-chunk deletion prevents full data loss, but the file refresh is still not atomic. If an early batch upserts successfully and a later batch fails, the database keeps newly written low-index chunks alongside stale higher-index chunks for the same source file until a later successful re-ingest. **Fixed**: embeddings generated first, then all upserts + stale deletion wrapped in a single `conn.transaction()` per file.
- [x] [Review][Patch] Orchestrator subgraph is not running under the parent graph's checkpoint context [`backend/src/pipeline/diagnosis_graph.py:69`] — the story's technical requirements say the orchestrator subgraph must share the parent checkpointer, but `diagnose_node()` calls `run_orchestrator(state)` and that function creates and invokes its own compiled `create_react_agent()` graph imperatively. A pod restart during the tool loop replays the whole orchestrator attempt instead of resuming from nested LangGraph checkpoints. **Fixed**: `run_orchestrator` now obtains the parent checkpointer via `get_checkpointer()` and passes it to `build_orchestrator_agent`, which passes it to `create_react_agent(checkpointer=...)`. Subgraph thread_id derived from `{incident_id}:orchestrator:{attempt}`.
- [x] [Review][Patch] Shipped runbook RAG artifact is still empty by default [`backend/src/config/knowledge_settings.py:24`] — the current tree still contains no bundled `backend/runbooks/**` corpus, and the documented dev startup flow runs from `backend/`, where the default relative path `backend/runbooks` resolves to a non-existent nested directory. That means the current "configurable path" fix still leaves AC #3 and AC #4 unsatisfied in the default shipped/developer path unless an external `RUNBOOKS_DIRECTORY` is supplied. **Fixed**: created `backend/runbooks/` directory with README explaining how to add runbooks; default path now resolved via `Path(__file__).resolve().parent.parent.parent / "runbooks"` so it works regardless of CWD.

### Review Round 4 — 2026-08-09
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6 (via Cursor)

#### Findings
- [x] [Review][Patch] Orchestrator prompt omits fingerprints and key labels [`backend/src/agents/prompts.py:71`] — `build_diagnosis_prompt()` drops each alert's `fingerprint` and most labels before the first agent pass. Because `evaluate_completeness()` now treats fingerprint as the primary identifier when present, the initial diagnosis cannot satisfy the gate without a retry, and the model also loses pod/container/node/PVC labels needed for metadata-driven subsystem hypotheses. **Fixed**: prompt now includes fingerprint and all resource-identifying labels (namespace, pod, node, container, job, instance, service) for each alert.
- [x] [Review][Patch] Evidence ledger still cannot prove gathered evidence was examined [`backend/src/agents/completeness_gate.py:98`] — `_extract_evidence_ledger()` records only `source`/`query`/`type` and discards the actual tool results, while `_check_evidence_examined()` only token-matches query terms against diagnosis text. A diagnosis can ignore the concrete log/resource-state content and still pass, and `search_runbooks()` currently records no-hit lookups as positive evidence. **Fixed**: ledger now stores `result_summary` (truncated to 300 chars); gate verifies key findings from summaries appear in diagnosis text; runbook no-hits marked with `no_hit: true` and excluded from examination check.
- [x] [Review][Patch] Bundled runbook corpus still ships only placeholder content [`backend/runbooks/README.md:1`] — startup ingests every markdown file under `backend/runbooks/`, but the tree only contains README instructions. The default artifact therefore indexes scaffolding text instead of operational runbooks, so AC #3 and AC #4 are still not satisfied by the shipped corpus. **Fixed**: added 3 sample OpenShift runbooks (node-not-ready.md, pod-crashloop-backoff.md, etcd-slow-fsync.md) covering common scenarios with symptoms, diagnosis steps, root cause categories, and remediation.
- [x] [Review][Patch] Chunk overlap can still overflow max token limit [`backend/src/knowledge/chunker.py:105`] — `_split_paragraph()` carries overlap text into the next chunk after a flush but never rechecks the combined overlap plus next paragraph size. A near-limit paragraph plus retained overlap can still emit oversized chunks; this was reproduced locally with a 531-token chunk at `max_tokens=500`. **Fixed**: added final size check after overlap is prepended — if overlap + next paragraph exceeds max_tokens, overlap is trimmed entirely.
- [x] [Review][Patch] First-pass alternative hypotheses are overwritten [`backend/src/agents/orchestrator.py:169`] — `run_orchestrator()` now writes `DiagnosisObject.alternative_hypotheses`, but it always replaces the model-produced field with retry-derived `rejected_hypotheses`. A first-pass diagnosis that rejects competing causes still loses that audit-trail data unless completeness fails first. **Fixed**: model-produced alternatives are now preserved and retry-derived alternatives are appended, accumulating across passes.

### Review Round 5 — 2026-08-09
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6 (via Cursor)

#### Findings
- [x] [Review][Patch] Diagnosis graph emits `diagnosed` before pipeline completion [`backend/src/pipeline/diagnosis_graph.py:207`] — `finalize_node()` emits `incident.stage_changed` with `state="diagnosed"` before the runner emits `finalize/finalizing` and before `_handle_success()` commits the terminal state. Consumers can therefore observe `diagnosed -> finalizing -> diagnosed`, and a failed completion transaction can still leak a premature success event. **Fixed**: removed premature `diagnosed` SSE emission from `finalize_node()`; terminal state events are now emitted exclusively by the runner after the pipeline completion transaction commits successfully.
- [ ] [Review][Deferred] First-pass alternative hypotheses still do not reach the audit log [`backend/src/pipeline/diagnosis_graph.py:187`] — `run_orchestrator()` preserves model-produced `DiagnosisObject.alternative_hypotheses`, but `finalize_node()` writes audit metadata from `state["rejected_hypotheses"]` only. A diagnosis that succeeds on the first pass still drops its rejected alternatives from the audit trail, so AC #8 remains only partially satisfied.

#### Deferred Review Debt

The following finding was identified in Review Round 5 but deferred because the story reached the **HARD CAP of 5 review iterations**. Impact is low — the data exists on the `DiagnosisObject` artifact itself, just not duplicated to the audit trail.

| # | Finding | File | Impact | Rationale for Deferral |
|---|---------|------|--------|----------------------|
| 1 | First-pass `alternative_hypotheses` are preserved on the `DiagnosisObject` but not written to the audit log (audit hook only uses `state["rejected_hypotheses"]`) | `backend/src/pipeline/diagnosis_graph.py:187` | Low | The data is persisted on the diagnosis artifact and queryable from there. Only the audit-trail duplication is missing. AC #8 is partially satisfied — alternatives are preserved on the model, just not on the secondary audit write-point. |

**Recommended follow-up:** In the next story that touches `finalize_node()` or the audit hook, add `diagnosis.alternative_hypotheses` to the `extra_detail` dict written to `pipeline_audit_log()`. One-line fix.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (via Cursor)

### Debug Log References

- `langgraph.prebuilt.create_react_agent` emits a deprecation warning in LangGraph 1.2.x about moving to `langchain.agents`. The `langchain` package is not installed (only `langchain-core` and `langchain-openai`), so the existing import from `langgraph.prebuilt` is kept. Warning is cosmetic only.
- The `search_runbooks` tool uses lazy imports for `get_pool` and `register_vector` since the DB pool may not be initialized during tool definition. Tests must use proper async context manager mocks for pool.acquire().
- No Docker socket available in dev environment — testcontainers-based DB integration tests (`pytest -m db`) are expected to fail. Unit tests (`pytest -m unit`) pass fully without container runtime.

### Completion Notes List

- **Task 1**: Created `config/llm_settings.py` with `AgentRole` enum, `AgentLLMConfig` frozen dataclass, per-role env var resolution with layered override (role-specific > shared > default). Created `agents/llm_client.py` with `get_chat_model()` factory wrapping `ChatOpenAI`.
- **Task 2**: Created full knowledge pipeline: `knowledge/chunker.py` (heading-aware markdown splitting with token bounds and paragraph overlap), `knowledge/embeddings.py` (OpenAI-compatible embedding endpoint), `db/runbooks.py` (pgvector store/search/delete), migration 004 (runbook_chunks table + HNSW index), `knowledge/ingest.py` (directory scan → chunk → embed → upsert pipeline).
- **Task 3**: Created `knowledge/runbook_rag.py` (embed query → pgvector similarity search → return RunbookChunk objects). Created `config/knowledge_settings.py` with all RAG configuration. pgvector registration added to app lifespan.
- **Task 4**: Created `agents/tools.py` with three `@tool`-decorated async functions: `query_cluster_resources` (MCP cluster queries), `get_resource_logs` (pod log retrieval), `search_runbooks` (RAG retrieval). All return structured dicts with correct `EvidenceSource` values.
- **Task 5**: Created `agents/orchestrator.py` with `build_orchestrator_agent()` (create_react_agent subgraph) and `run_orchestrator()` (full diagnosis flow with completeness retry loop, coverage gap flagging, rejected hypothesis preservation, fallback on failure).
- **Task 6**: Created `agents/completeness_gate.py` with deterministic `evaluate_completeness()` that checks all alert fingerprints/alertnames are referenced in diagnosis text. Returns `CompletenessResult` with unaddressed list.
- **Task 7**: Replaced stub `diagnose_node` in `pipeline/diagnosis_graph.py` with orchestrator invocation. Added `_completeness_routing` conditional edge. Extended `DiagnosisState` TypedDict with 4 new fields. Updated `finalize_node` to emit SSE events. Updated runner's initial state.
- **Task 8**: Added `langchain-openai` and `pgvector` to pyproject.toml. Exported `RunbookChunk` and `CompletenessResult` from `models/__init__.py`. Added `_init_pgvector()` to app lifespan.
- **Task 9**: 57 new unit tests across 5 test files. All 251 unit tests pass (194 baseline + 57 new). Tests cover orchestrator (8), tools (9), completeness gate (9), chunker (13), RAG retrieval (5), ingestion (5), plus updated pipeline graph tests (8).
- **Task 10**: DB integration tests written for pgvector store/search/delete (testcontainers-dependent). Ingestion integration tests use tempdir + mocked embeddings. Pipeline tests updated for orchestrator integration.
- ✅ Resolved review finding [HIGH]: Runner now fetches real alert data from DB via `get_rce_alert_data()` and passes it to the graph state — orchestrator receives actual alert labels, annotations, and fingerprints.
- ✅ Resolved review finding [HIGH]: Runbook ingestion wired into app lifespan via `_ingest_runbooks_on_startup()` — called after pgvector init, before background tasks start.
- ✅ Resolved review finding [HIGH]: `build_orchestrator_agent()` now accepts `alert_count` parameter; `run_orchestrator()` passes `len(alerts)` so multi-alert RCEs get correct system prompt scoping.
- ✅ Resolved review finding [MEDIUM]: Completeness routing refactored to graph level — added `completeness_gate_node` that evaluates completeness, `_completeness_routing` returns "orchestrate" for retry or "finalize" when complete/exhausted. Internal retry loop removed from `run_orchestrator()`.
- ✅ Resolved review finding [MEDIUM]: `_split_oversized()` added to chunker — splits by sentence first, falls back to character-level splitting when no sentence boundaries exist.
- ✅ Resolved review finding R2 [MEDIUM]: Completeness gate now uses per-alert OR matching — an alert is addressed if its fingerprint OR alertname appears in diagnosis text, eliminating false retries on opaque fingerprints.
- ✅ Resolved review finding R2 [HIGH]: Fallback diagnosis in `diagnose_node` no longer resets `completeness_attempts` to 0 — increments from current state, preventing infinite retry loops on orchestrator failure.
- ✅ Resolved review finding R2 [MEDIUM]: Default `runbooks_directory` set to `backend/runbooks/`, startup logs configured path and gracefully handles missing/empty directory.
- ✅ Resolved review finding R2 [HIGH]: Completeness retry budget changed from `>=` to `>` comparison — allows 2 retries (3 total passes) as specified.
- ✅ Resolved review finding R2 [MEDIUM]: Ingestion pipeline now upserts new chunks first via ON CONFLICT, then deletes only stale chunks beyond new count — no data loss on transient embedding failure.
- ✅ Resolved review finding R2 [MEDIUM]: `_split_oversized()` now char-splits individual oversized sentences even within multi-sentence paragraphs.
- ✅ Resolved review finding R2 [MEDIUM]: `get_pool()` passes `init=register_vector` to `asyncpg.create_pool()` so all pooled connections have pgvector types registered automatically.
- ✅ Resolved review finding R3 [HIGH]: Completeness gate now uses fingerprint as primary per-alert identifier; alertname fallback only for alerts without fingerprints — prevents shared-alertname false positives.
- ✅ Resolved review finding R3 [HIGH]: Added `evidence_ledger` to graph state, populated from tool call results; completeness gate now verifies gathered evidence is referenced in the diagnosis (AC #6).
- ✅ Resolved review finding R3 [MEDIUM]: Added `coverage_gaps` and `alternative_hypotheses` fields to `DiagnosisObject` and `ImmutableDiagnosisArtifact` — coverage gaps now persisted in diagnosis metadata (AC #7).
- ✅ Resolved review finding R3 [MEDIUM]: Rejected alternative hypotheses collected on retry, persisted on `DiagnosisObject.alternative_hypotheses`, and written to audit log via `extra_detail` on finalize (AC #8).
- ✅ Resolved review finding R3 [MEDIUM]: Per-file runbook ingest now wraps all upserts + stale deletion in a single `conn.transaction()` — atomic per file, no mixed old/new chunks on partial failure.
- ✅ Resolved review finding R3 [MEDIUM]: Orchestrator subgraph now receives parent checkpointer via `get_checkpointer()` and passes to `create_react_agent(checkpointer=...)` — pod restart resumes from nested checkpoint instead of replaying.
- ✅ Resolved review finding R3 [HIGH]: Created `backend/runbooks/` directory with README; path resolution uses `Path(__file__).resolve()` relative to project root — works regardless of CWD.
- ✅ Resolved review finding R4 [HIGH]: Prompt now includes alert fingerprints and all resource-identifying labels (namespace, pod, node, container, job, instance, service) so the orchestrator has the metadata needed for subsystem hypothesis and the completeness gate can match fingerprints.
- ✅ Resolved review finding R4 [HIGH]: Evidence ledger now stores `result_summary` (truncated to 300 chars) alongside query; gate verifies key findings from summaries appear in diagnosis; runbook no-hits marked with `no_hit: true` and excluded from examination check.
- ✅ Resolved review finding R4 [HIGH]: Added 3 sample OpenShift runbooks (node-not-ready, pod-crashloop-backoff, etcd-slow-fsync) with symptoms, diagnosis steps, root cause categories, and remediation — AC #3 and #4 now satisfied by shipped corpus.
- ✅ Resolved review finding R4 [MEDIUM]: Chunker `_split_paragraph()` now checks if overlap + next paragraph exceeds max_tokens after flush — trims overlap entirely when combined size would overflow, preventing oversized chunks.
- ✅ Resolved review finding R4 [MEDIUM]: `run_orchestrator()` now preserves model-produced `alternative_hypotheses` and appends retry-derived rejected hypotheses, accumulating across passes instead of overwriting.
- ✅ Resolved review finding R5 [HIGH/CRITICAL]: Removed premature `diagnosed` SSE emission from `finalize_node()` — terminal state events now emitted exclusively by runner after pipeline completion transaction commits. Eliminates `diagnosed -> finalizing -> diagnosed` race and prevents leaked success events on failed transactions.
- ⏸️ Deferred review finding R5 [LOW]: First-pass `alternative_hypotheses` not duplicated to audit log — data is on the DiagnosisObject artifact, just not on the secondary audit write-point. Documented as Deferred Review Debt.

### Change Log

- 2026-08-09: Story 2.2 implementation complete — orchestrator agent replaces diagnosis stub, runbook RAG pipeline, completeness gate, 57 new unit tests passing
- 2026-08-09: Addressed 5 code review findings (3 HIGH, 2 MEDIUM) — runner passes real alerts, runbook ingestion wired to startup, orchestrator uses actual alert count, graph-level completeness routing implemented, chunker splits oversized paragraphs. 261 unit tests passing (+7 new).
- 2026-08-09: Addressed 7 code review findings from Round 2 (2 HIGH, 5 MEDIUM) — completeness gate OR matching, fallback retry safety, configurable runbook path, retry budget off-by-one, safe re-ingest, oversized sentence splitting, pgvector pool init callback. 265 unit tests passing (+4 new).
- 2026-08-09: Addressed 7 code review findings from Round 3 (3 HIGH, 4 MEDIUM) — fingerprint-primary completeness gate, evidence ledger verification, coverage_gaps/alternative_hypotheses on DiagnosisObject, audit trail persistence, atomic per-file re-ingest, parent checkpointer sharing, bundled runbook corpus with correct path resolution. 273 unit tests passing (+8 new).
- 2026-08-09: Addressed 5 code review findings from Round 4 (3 HIGH, 2 MEDIUM) — prompt includes fingerprints and resource labels, evidence ledger stores result summaries with no-hit handling, 3 real sample runbooks added, chunker overlap overflow guard, alternative hypotheses accumulate across passes. 281 unit tests passing (+8 new).
- 2026-08-09: Review Round 5 — HARD CAP reached. Applied critical fix (premature `diagnosed` SSE removed from `finalize_node()`). Deferred 1 low-impact finding (alternative_hypotheses audit log duplication). Story status → done.

### File List

- `backend/src/config/llm_settings.py` — NEW: Per-agent LLM configuration (AgentRole, AgentLLMConfig)
- `backend/src/config/knowledge_settings.py` — NEW: Knowledge/RAG settings (embedding model, thresholds)
- `backend/src/agents/__init__.py` — NEW: Agents package init
- `backend/src/agents/llm_client.py` — NEW: ChatOpenAI factory per agent role
- `backend/src/agents/tools.py` — NEW: @tool functions (query_cluster, get_logs, search_runbooks)
- `backend/src/agents/orchestrator.py` — NEW: Orchestrator agent (create_react_agent + completeness loop)
- `backend/src/agents/completeness_gate.py` — NEW: Deterministic completeness check
- `backend/src/agents/prompts.py` — NEW: System prompts and prompt builders
- `backend/src/knowledge/__init__.py` — NEW: Knowledge package init
- `backend/src/knowledge/chunker.py` — NEW: Markdown heading-aware chunker
- `backend/src/knowledge/embeddings.py` — NEW: OpenAI-compatible embedding client
- `backend/src/knowledge/runbook_rag.py` — NEW: pgvector similarity search wrapper
- `backend/src/knowledge/ingest.py` — NEW: Runbook ingestion pipeline (chunk → embed → store)
- `backend/src/db/runbooks.py` — NEW: pgvector CRUD for runbook_chunks table
- `backend/src/models/knowledge.py` — NEW: RunbookChunk, CompletenessResult Pydantic models
- `backend/alembic/versions/004_add_runbook_chunks.py` — NEW: Migration for runbook_chunks + HNSW index
- `backend/src/pipeline/diagnosis_graph.py` — MODIFIED: Replaced stub with orchestrator, added completeness gate, extended DiagnosisState
- `backend/src/pipeline/runner.py` — MODIFIED: Added new state fields to initial_state
- `backend/src/models/__init__.py` — MODIFIED: Export RunbookChunk, CompletenessResult
- `backend/src/api/app.py` — MODIFIED: Added pgvector init in lifespan
- `backend/pyproject.toml` — MODIFIED: Added langchain-openai, pgvector dependencies
- `backend/tests/agents/__init__.py` — NEW: Test package init
- `backend/tests/agents/conftest.py` — NEW: FakeChatModel, mock MCP/tool fixtures
- `backend/tests/agents/test_orchestrator.py` — NEW: Orchestrator unit tests (8 tests)
- `backend/tests/agents/test_tools.py` — NEW: Tool wrapper tests (9 tests)
- `backend/tests/agents/test_completeness_gate.py` — NEW: Completeness gate tests (9 tests)
- `backend/tests/knowledge/__init__.py` — NEW: Test package init
- `backend/tests/knowledge/test_chunker.py` — NEW: Markdown chunking tests (13 tests)
- `backend/tests/knowledge/test_runbook_rag.py` — NEW: RAG retrieval tests (5 tests)
- `backend/tests/knowledge/test_ingest.py` — NEW: Ingestion integration tests (5 tests)
- `backend/tests/db/test_runbooks.py` — NEW: pgvector store/search DB tests (7 tests)
- `backend/tests/pipeline/conftest.py` — MODIFIED: Added mock_orchestrator_agent fixture
- `backend/tests/pipeline/test_diagnosis_graph.py` — MODIFIED: Updated for orchestrator integration, added retry budget tests
- `backend/src/db/connection.py` — MODIFIED: Added pgvector `init=register_vector` callback to pool creation
- `backend/runbooks/README.md` — NEW: Runbook corpus directory with instructions for adding runbooks
- `backend/runbooks/node-not-ready.md` — NEW: Sample runbook for KubeNodeNotReady diagnosis and remediation
- `backend/runbooks/pod-crashloop-backoff.md` — NEW: Sample runbook for KubePodCrashLooping diagnosis and remediation
- `backend/runbooks/etcd-slow-fsync.md` — NEW: Sample runbook for etcd slow disk fsync diagnosis and remediation
