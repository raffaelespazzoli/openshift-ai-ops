# Story 2.1: LangGraph Diagnosis Pipeline & MCP Integration

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want a persistent agent pipeline that securely queries the cluster in read-only mode,
so that diagnosis work survives pod restarts and never risks modifying the cluster being diagnosed.

## Acceptance Criteria

1. **Given** a Root-Cause Event is dequeued from the priority queue **When** it enters the diagnosis pipeline **Then** LangGraph processes it as a directed graph with the diagnosis stage as a node **And** the incident state transitions from `queued` to `diagnosing` via the state machine function

2. **Given** the LangGraph runtime is configured **When** a pipeline checkpoint is written **Then** it is persisted to PostgreSQL in the `langgraph_*` schema domain (black box — no application queries against these tables)

3. **Given** the backend pod crashes mid-diagnosis **When** the pod restarts **Then** the LangGraph pipeline resumes from the last persisted checkpoint without re-processing completed stages

4. **Given** the diagnosis pipeline needs cluster state **When** it queries the cluster **Then** it connects to the read-only MCP Server instance via Streamable HTTP transport **And** the MCP Server is bound to the `cluster-reader` ServiceAccount with the `--read-only` flag

5. **Given** the Structured Diagnosis Object model is defined **When** a diagnosis is produced **Then** it conforms to the schema: `{root_cause_component, failure_mode, causal_chain: [...], affected_resources: [...], evidence: [...], evidence_gaps: [...], confidence: float}` **And** root-cause codes come from the controlled taxonomy using slash-delimited format (e.g., `node/memory-pressure`, `storage/pvc-stuck-pending`)

6. **Given** two Structured Diagnosis Objects **When** they are compared **Then** deterministic comparison is available via root-cause hash (field diff of root_cause_component + failure_mode + sorted causal_chain)

7. **Given** an MCP Server query times out **When** the diagnosis pipeline handles the timeout **Then** it produces a partial-evidence continuation with the timed-out query listed in the `evidence_gaps` field **And** diagnosis continues with available data rather than failing the pipeline

## Tasks / Subtasks

- [ ] Task 1: Structured Diagnosis Object model (AC: #5, #6)
  - [ ] 1.1 Create `backend/src/models/diagnosis.py` with `EvidenceArtifact`, `EvidenceGap`, `DiagnosisObject`, `ImmutableDiagnosisArtifact` Pydantic models
  - [ ] 1.2 Implement `root_cause_hash()` for deterministic comparison
  - [ ] 1.3 Define initial root-cause taxonomy constants (slash-delimited codes)
  - [ ] 1.4 Export from `backend/src/models/__init__.py`

- [ ] Task 2: MCP client wrapper for read-only cluster access (AC: #4, #7)
  - [ ] 2.1 Create `backend/src/pipeline/mcp_client.py` with `ReadOnlyMCPClient` wrapping the MCP Python SDK Streamable HTTP transport
  - [ ] 2.2 Implement configurable connection URL, timeouts, and retry logic
  - [ ] 2.3 Implement timeout handling that produces `EvidenceGap` objects instead of raising exceptions
  - [ ] 2.4 Create `backend/src/config/mcp_settings.py` with `MCPSettings` (URL, timeout, retries)

- [ ] Task 3: LangGraph diagnosis graph definition (AC: #1, #2, #3)
  - [ ] 3.1 Create `backend/src/pipeline/diagnosis_graph.py` defining the LangGraph `StateGraph` with typed state schema
  - [ ] 3.2 Define graph nodes: `diagnose` (stub for Story 2.2 Orchestrator), `finalize_diagnosis`
  - [ ] 3.3 Define conditional edges for future stages (skeptic, remediation) as passthrough stubs
  - [ ] 3.4 Configure `AsyncPostgresSaver` checkpointer using existing psycopg pool from `db/connection.py`
  - [ ] 3.5 Compile graph with checkpointer

- [ ] Task 4: Pipeline runner integrating dispatcher (AC: #1, #2, #3)
  - [ ] 4.1 Create `backend/src/pipeline/runner.py` with `run_diagnosis_pipeline(item, conn)` that invokes the LangGraph graph
  - [ ] 4.2 Map queue item fields to LangGraph thread_id (use incident UUID) and initial state
  - [ ] 4.3 Handle graph completion: call `mark_pipeline_complete()` and transition incident state
  - [ ] 4.4 Handle graph failure: transition to `failed` state, log error, free pipeline slot
  - [ ] 4.5 Emit SSE events via event bus for stage transitions (`incident.stage_changed`)

- [ ] Task 5: Replace dispatcher stub (AC: #1)
  - [ ] 5.1 Update `backend/src/pipeline/dispatcher.py` — replace `dispatch_to_pipeline()` stub with async call to `runner.run_diagnosis_pipeline()`
  - [ ] 5.2 Ensure the async invocation does not block the dispatcher loop (fire as asyncio task, respect parallelism cap)

- [ ] Task 6: Checkpointer lifecycle management (AC: #2, #3)
  - [ ] 6.1 Create `backend/src/db/checkpointer.py` with `get_checkpointer()` returning a configured `AsyncPostgresSaver`
  - [ ] 6.2 Call `checkpointer.setup()` once during application startup (lifespan) to create `langgraph_*` tables
  - [ ] 6.3 Register checkpointer in FastAPI lifespan alongside existing pool/bus initialization

- [ ] Task 7: Pipeline audit hook (AC: #1)
  - [ ] 7.1 Create `backend/src/pipeline/audit_hook.py` — register a LangGraph callback that writes internal state transitions to `audit_log` (AD-25 write point #2)
  - [ ] 7.2 Log: incident_id, stage name, state before/after, timestamp

- [ ] Task 8: Helm chart updates (AC: #4)
  - [ ] 8.1 Add `mcp-readonly` Deployment to Helm templates: kubernetes-mcp-server image with `--port 8080 --read-only`, `cluster-reader` ServiceAccount
  - [ ] 8.2 Add `cluster-reader` ServiceAccount + ClusterRoleBinding (`cluster-reader` ClusterRole) to Helm templates
  - [ ] 8.3 Add MCP-related configuration to `values.yaml` (image tag, port, resource limits, readiness probe)

- [ ] Task 9: Tests — unit (AC: #5, #6, #7)
  - [ ] 9.1 `tests/models/test_diagnosis.py` — DiagnosisObject validation, root_cause_hash determinism, EvidenceGap serialization, taxonomy code validation
  - [ ] 9.2 `tests/pipeline/test_mcp_client.py` — timeout produces EvidenceGap (mock MCP), partial evidence continuation

- [ ] Task 10: Tests — pipeline integration (AC: #1, #2, #3)
  - [ ] 10.1 `tests/pipeline/test_diagnosis_graph.py` — graph runs end-to-end with mocked LLM and mock MCP, produces DiagnosisObject, state transitions correct
  - [ ] 10.2 `tests/pipeline/test_diagnosis_graph.py` — checkpoint persisted to PostgreSQL (testcontainers), graph resumes from checkpoint after simulated interruption
  - [ ] 10.3 Create mock MCP server fixture for canned Streamable HTTP responses

- [ ] Task 11: Tests — MCP integration (AC: #4)
  - [ ] 11.1 `tests/pipeline/test_mcp_integration.py` — MCP client connects via Streamable HTTP to mock server, receives canned responses
  - [ ] 11.2 `tests/pipeline/test_mcp_integration.py` — MCP timeout scenario returns partial evidence with evidence_gaps populated

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Epic 1 (all stories complete):**
- **Story 1.0** established the monorepo layout, shared types in `backend/src/models/`, the canonical state machine in `state_machine.py`, DB infrastructure with asyncpg and Alembic migrations, testcontainers fixtures, structured JSON logging, and the Helm chart skeleton.
- **Story 1.1** created the webhook receiver at `POST /api/v1/webhooks/alertmanager`, incident/alert persistence in `db/incidents.py`, and the `BackgroundTasks` pattern for non-blocking operations.
- **Story 1.2** built the five-layer correlator in `pipeline/correlator.py`, RCE model in `models/root_cause_event.py`, and settling windows with severity-based timers.
- **Story 1.3** built the priority queue in `db/queue.py` using `SELECT FOR UPDATE SKIP LOCKED`, the dispatcher loop in `pipeline/dispatcher.py` with the parallelism cap, and the `active_pipelines` table for tracking. **Critically, `dispatch_to_pipeline()` is a STUB** that immediately marks items complete — this story replaces it.
- **Story 1.4** built the REST API foundation: envelope format (`ApiResponse`), auth (`api/auth.py`), audit middleware (`api/audit.py`, AD-25 write point #1), SSE via `EventSourceResponse` (`api/events.py`), and the in-process asyncio event bus (`api/event_bus.py`). Review fixes included: structured auth errors, SSE reconnect with replay buffer, audit only on 2xx responses.

**Key patterns established:**
- State transitions always via `transition()` from `models/state_machine.py` — never direct SQL updates
- Structured logging with `get_logger(Component.X)` from `config/logging.py`
- Database operations in `db/` module, never inline SQL in pipeline or API code
- Test markers: `unit`, `db`, `api`, `pipeline`
- Testcontainers PostgreSQL fixture in `conftest.py`
- Event bus for SSE: `event_bus.emit(EventNames.INCIDENT_STAGE_CHANGED, SSEEventData(...))`

**Epic 1 Retrospective Action Items (OPEN — address in this story):**
- "LangGraph spike — understand checkpoint persistence, graph patterns, langgraph_* schema interaction" → This story IS the spike: implement the graph, configure checkpointing, verify it works.
- "MCP Server container image — identify or build read-only instance, validate Streamable HTTP transport" → This story adds the Helm template for `mcp-readonly` and the Python MCP client.
- "Define LLM test strategy — mocking patterns for unit tests, contract tests for MCP interactions" → This story establishes the mock MCP server fixture and mock LLM patterns that all subsequent stories will reuse.

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-1 | Staged pipeline paradigm | LangGraph graph IS the pipeline. Stages are graph nodes. Diagnosis is a node (stub for 2.2). Fast-path and re-challenge are conditional edges (stubs for later stories) |
| AD-2 | RBAC Airlock | Diagnosis uses `cluster-reader` SA + `--read-only` MCP Server ONLY. No write-capable MCP in this story |
| AD-3 | Two schema domains | LangGraph owns `langgraph_*` tables (black box). Application schema is separate. NEVER query `langgraph_*` tables |
| AD-4 | Shared types module | DiagnosisObject, EvidenceArtifact, EvidenceGap defined in `models/`. All pipeline nodes import from `models/` |
| AD-9 | Seven-deployment topology | Add `mcp-readonly` Deployment. Backend stays single-process |
| AD-13 | Dual-path knowledge retrieval | Runbook RAG and RHOKP are Story 2.2/2.3 scope. This story only builds the MCP client for cluster queries |
| AD-14 | Monorepo source tree | New pipeline code in `pipeline/`, new models in `models/`, new DB in `db/` |
| AD-15 | MCP timeout → partial evidence | `evidence_gaps` field in DiagnosisObject. Timeout never fails the pipeline |
| AD-19 | Canonical state machine | `queued→diagnosing` and `diagnosing→diagnosed` or `diagnosing→failed` transitions |
| AD-24 | In-process event bus | Pipeline emits stage change events to bus; SSE subscribers receive them |
| AD-25 | Audit log write point #2 | Pipeline audit hook registered at graph construction |

### Technical Requirements

#### LangGraph Graph Definition

The diagnosis pipeline is a LangGraph `StateGraph` with typed state:

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

class DiagnosisState(TypedDict):
    incident_id: str
    root_cause_event: dict
    alerts: list[dict]
    mcp_evidence: list[dict]
    evidence_gaps: list[dict]
    diagnosis: dict | None
    stage: str

builder = StateGraph(DiagnosisState)
builder.add_node("diagnose", diagnose_node)
builder.add_node("finalize", finalize_node)
builder.add_edge("diagnose", "finalize")
builder.add_edge("finalize", END)
builder.set_entry_point("diagnose")

checkpointer = AsyncPostgresSaver(pool)
graph = builder.compile(checkpointer=checkpointer)
```

Key constraints:
- `thread_id` = incident UUID (string, < 255 chars)
- The `diagnose` node is a STUB in this story — it produces a placeholder DiagnosisObject. Story 2.2 replaces it with the full Orchestrator agent
- `finalize` node transitions state, emits events, and marks pipeline complete
- Checkpointer tables are created by `checkpointer.setup()` at app startup — these are `langgraph_*` tables (AD-3 black box)

#### AsyncPostgresSaver Configuration

```python
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def get_checkpointer() -> AsyncPostgresSaver:
    pool = AsyncConnectionPool(
        conninfo=get_db_url(),
        kwargs={"autocommit": True, "row_factory": dict_row},
        min_size=1,
        max_size=3,
    )
    checkpointer = AsyncPostgresSaver(pool)
    return checkpointer
```

CRITICAL: The LangGraph checkpointer uses `psycopg` (v3), NOT `asyncpg`. The application DB uses `asyncpg`. These are two SEPARATE connection pools to the SAME PostgreSQL instance:
- `asyncpg` pool → application schema (incidents, alerts, queue, audit_log)
- `psycopg` pool → LangGraph checkpoint schema (`langgraph_*` tables)

Both connect to the same `POSTGRES_*` env vars. Do NOT attempt to share connections between them — the libraries have incompatible APIs.

#### MCP Python SDK Client

```python
from mcp import Client

MCP_READONLY_URL = "http://mcp-readonly:8080/mcp"

async def query_cluster(tool_name: str, arguments: dict, timeout: float = 30.0) -> dict:
    async with Client(MCP_READONLY_URL) as client:
        try:
            result = await asyncio.wait_for(
                client.call_tool(tool_name, arguments),
                timeout=timeout,
            )
            return {"success": True, "data": result}
        except asyncio.TimeoutError:
            return {
                "success": False,
                "evidence_gap": EvidenceGap(
                    query=f"{tool_name}({arguments})",
                    reason="MCP query timed out",
                    timeout_seconds=timeout,
                ),
            }
```

Key details:
- The `mcp` Python SDK package must be added to `pyproject.toml` dependencies
- `Client("http://...")` uses Streamable HTTP transport automatically
- kubernetes-mcp-server exposes tools: `get_resources`, `get_resource`, `get_logs`, `get_events`, `describe_resource`, etc.
- The `--read-only` flag on the MCP server prevents write operations at the server side
- Connection to `http://mcp-readonly:8080/mcp` — the Kubernetes Service name within the namespace
- Timeout produces `EvidenceGap`, NOT an exception that fails the pipeline (AD-15)

#### Structured Diagnosis Object Model

```python
class EvidenceSource(StrEnum):
    MCP_CLUSTER = "mcp_cluster"
    RUNBOOK = "runbook"         # Story 2.2
    RHOKP = "rhokp"             # Story 2.3
    LEARNING_STORE = "learning_store"  # Story 2.3
    AGENTIC_SKILL = "agentic_skill"    # Story 2.3

class EvidenceArtifact(BaseModel):
    source: EvidenceSource
    query: str
    result: str
    timestamp: datetime

class EvidenceGap(BaseModel):
    query: str
    reason: str
    timeout_seconds: float | None = None

class DiagnosisObject(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    root_cause_component: str    # e.g., "node"
    failure_mode: str            # e.g., "memory-pressure"
    root_cause_code: str         # e.g., "node/memory-pressure"
    causal_chain: list[str]
    affected_resources: list[str]
    evidence: list[EvidenceArtifact]
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    agent_summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def root_cause_hash(self) -> str:
        """Deterministic hash for comparing two diagnoses."""
        import hashlib
        canonical = f"{self.root_cause_component}|{self.failure_mode}|{'|'.join(sorted(self.causal_chain))}"
        return hashlib.sha256(canonical.encode()).hexdigest()
```

Root-cause taxonomy initial codes (extend in later stories):
- `node/memory-pressure`, `node/disk-pressure`, `node/not-ready`, `node/pid-pressure`
- `storage/pvc-stuck-pending`, `storage/volume-mount-failed`, `storage/capacity-exceeded`
- `network/dns-failure`, `network/service-unreachable`, `network/ingress-misconfigured`
- `workload/crash-loop-backoff`, `workload/oom-killed`, `workload/image-pull-failed`
- `platform/etcd-latency`, `platform/api-server-slow`, `platform/scheduler-unschedulable`
- `unknown/unclassified`

#### Dispatcher Integration

The current `dispatch_to_pipeline()` in `pipeline/dispatcher.py` is a stub:
```python
async def dispatch_to_pipeline(item, conn):
    logger.info("Dispatched RCE to diagnosis pipeline", ...)
    await mark_pipeline_complete(conn, item["id"])
```

Replace with:
```python
async def dispatch_to_pipeline(item, conn):
    asyncio.create_task(
        _run_pipeline_task(item)
    )
```

The async task pattern ensures the dispatcher loop continues polling. `mark_pipeline_complete` moves to the graph's finalize node. Do NOT await the pipeline in the dispatcher loop — it blocks the dequeue cycle.

#### Helm Chart: mcp-readonly Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-mcp-readonly
spec:
  replicas: 1
  template:
    spec:
      serviceAccountName: {{ .Release.Name }}-cluster-reader
      containers:
      - name: mcp-readonly
        image: "{{ .Values.mcpReadonly.image.repository }}:{{ .Values.mcpReadonly.image.tag }}"
        args: ["--port", "8080", "--read-only"]
        ports:
        - containerPort: 8080
```

Plus ServiceAccount + ClusterRoleBinding:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Release.Name }}-cluster-reader
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {{ .Release.Name }}-cluster-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-reader
subjects:
- kind: ServiceAccount
  name: {{ .Release.Name }}-cluster-reader
  namespace: {{ .Release.Namespace }}
```

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ~=1.2 | Already in pyproject.toml. Graph definition, node execution |
| langgraph-checkpoint-postgres | >=2.0 | Already in pyproject.toml. AsyncPostgresSaver for checkpoint persistence |
| psycopg[binary] | >=3.0,<4.0 | Already in pyproject.toml. Required by LangGraph checkpointer |
| psycopg-pool | latest | Already in pyproject.toml. Connection pool for LangGraph checkpointer |
| mcp | latest | **NEW — add to pyproject.toml**. MCP Python SDK for Streamable HTTP client |
| asyncpg | latest | Already in pyproject.toml. Application DB (separate from LangGraph psycopg pool) |

**ADD to `pyproject.toml` dependencies:**
```toml
"mcp",
```

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/models/diagnosis.py` | DiagnosisObject, EvidenceArtifact, EvidenceGap, ImmutableDiagnosisArtifact, root-cause taxonomy | NEW |
| `backend/src/pipeline/diagnosis_graph.py` | LangGraph StateGraph definition, nodes, edges | NEW |
| `backend/src/pipeline/runner.py` | Pipeline runner — invokes graph, handles completion/failure | NEW |
| `backend/src/pipeline/mcp_client.py` | Read-only MCP client wrapper with timeout→EvidenceGap | NEW |
| `backend/src/pipeline/audit_hook.py` | LangGraph callback for audit logging (AD-25 write point #2) | NEW |
| `backend/src/db/checkpointer.py` | AsyncPostgresSaver factory and lifecycle | NEW |
| `backend/src/config/mcp_settings.py` | MCP connection settings (URL, timeout, retries) | NEW |
| `charts/openshift-ai-ops/templates/deployment-mcp-readonly.yaml` | kubernetes-mcp-server Deployment | NEW |
| `charts/openshift-ai-ops/templates/service-mcp-readonly.yaml` | MCP readonly Service | NEW |
| `charts/openshift-ai-ops/templates/serviceaccount-cluster-reader.yaml` | ServiceAccount + ClusterRoleBinding | NEW |
| `backend/tests/models/test_diagnosis.py` | DiagnosisObject, hash, taxonomy tests | NEW |
| `backend/tests/pipeline/__init__.py` | Pipeline test package init | NEW |
| `backend/tests/pipeline/test_mcp_client.py` | MCP client timeout/evidence tests | NEW |
| `backend/tests/pipeline/test_diagnosis_graph.py` | LangGraph graph integration tests | NEW |
| `backend/tests/pipeline/test_mcp_integration.py` | MCP Streamable HTTP integration tests | NEW |
| `backend/tests/pipeline/conftest.py` | Mock MCP server fixture, mock LLM fixture | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/models/__init__.py` | Export DiagnosisObject, EvidenceArtifact, EvidenceGap, ImmutableDiagnosisArtifact | UPDATE |
| `backend/src/pipeline/__init__.py` | Update module docstring to reference LangGraph | UPDATE |
| `backend/src/pipeline/dispatcher.py` | Replace `dispatch_to_pipeline()` stub with async graph invocation | UPDATE |
| `backend/src/api/app.py` | Add checkpointer initialization to lifespan | UPDATE |
| `backend/pyproject.toml` | Add `mcp` dependency | UPDATE |
| `charts/openshift-ai-ops/values.yaml` | Add `mcpReadonly` section with image config | UPDATE |

### Dependency Direction (ENFORCED)

```
models/diagnosis.py → nothing (leaf, Pydantic only)
pipeline/mcp_client.py → models/diagnosis.py (EvidenceGap), config/mcp_settings.py
pipeline/diagnosis_graph.py → models/ (DiagnosisObject, state_machine), pipeline/mcp_client.py
pipeline/runner.py → pipeline/diagnosis_graph.py, db/queue.py (mark_pipeline_complete), models/events.py (emit SSE)
pipeline/audit_hook.py → db/audit.py, models/ (for types)
pipeline/dispatcher.py → pipeline/runner.py (replaces stub)
db/checkpointer.py → db/connection.py (get_db_url)
```

- **NEVER**: `models/` imports from `pipeline/`, `api/`, or `db/`
- **NEVER**: `pipeline/` imports from `api/`
- **NEVER**: application code queries `langgraph_*` tables

### Testing Requirements

**Unit tests** (`pytest -m unit`):
- `DiagnosisObject` validates schema: required fields, confidence range 0–1, root_cause_code format
- `root_cause_hash()` is deterministic: same inputs → same hash, different inputs → different hash
- `EvidenceGap` serializes correctly with query, reason, timeout_seconds
- Root-cause taxonomy codes follow slash-delimited format
- `ImmutableDiagnosisArtifact` is frozen (immutable after creation)

**Pipeline tests** (`pytest -m pipeline`):
- LangGraph graph compiles and runs with mocked diagnosis node
- Graph produces a valid `DiagnosisObject` in state
- Incident state transitions: `queued→diagnosing→diagnosed` for success path
- Incident state transitions: `queued→diagnosing→failed` for failure path
- Checkpoint is persisted to PostgreSQL (testcontainers) — verify by inspecting `langgraph_*` tables existentially (table exists, row count > 0, never query schema details)
- After simulated interruption, graph resumes from checkpoint (invoke same thread_id, verify no re-processing)

**MCP integration tests** (`pytest -m pipeline`):
- Mock MCP server returns canned Streamable HTTP responses
- MCP client parses tool results into evidence artifacts
- MCP timeout returns `EvidenceGap` (not an exception)
- Multiple concurrent MCP queries handled correctly

**Mock MCP Server Fixture:**
Create a lightweight ASGI app that mimics the Streamable HTTP transport at `/mcp`. This fixture serves as the foundation for ALL subsequent stories that use MCP. It should:
- Accept MCP `initialize` handshake
- Return canned tool results for `get_resources`, `get_resource`, `describe_resource`
- Support configurable response delays (for timeout testing)
- Run via `httpx` ASGI transport in tests (no real HTTP server needed)

Alternatively, use the `mcp` SDK's in-process `Client(server)` pattern for unit tests where full HTTP is unnecessary.

**Mock LLM Pattern:**
Since the diagnosis node is a STUB in this story (no real LLM calls), mock patterns are not heavily exercised here. However, establish the pattern for Story 2.2:
- LLM calls will be mocked at the `litellm` or `langchain` boundary
- Each test provides deterministic responses
- No real LLM endpoint in CI

### Anti-Patterns / DO NOT

- **DO NOT** query `langgraph_*` tables from application code. They are LangGraph internals (AD-3). If you need to verify checkpoints in tests, check only that the tables exist and contain rows — never assert on schema structure.
- **DO NOT** create a write-capable MCP client. This story is diagnosis-only — `cluster-reader` SA with `--read-only` flag. The read-write MCP is Story 3.x.
- **DO NOT** implement the Orchestrator agent logic. The diagnosis node is a STUB that produces a placeholder DiagnosisObject. Story 2.2 replaces it with the full agent.
- **DO NOT** implement the Skeptic. The graph has no skeptic node in this story. Story 2.4 adds it.
- **DO NOT** implement runbook RAG or RHOKP integration. Story 2.2 adds runbooks; Story 2.3 adds RHOKP + Learning Store.
- **DO NOT** share the asyncpg connection pool with the LangGraph checkpointer. They use different Python database libraries (asyncpg vs psycopg3). Two separate pools to the same PostgreSQL.
- **DO NOT** await the pipeline in the dispatcher loop. The graph runs as an async task — the dispatcher must continue polling for the next dequeue.
- **DO NOT** transition incident state directly. Always use `transition()` from `models/state_machine.py`.
- **DO NOT** add mcp-readwrite Deployment — that's Story 3.x scope.
- **DO NOT** add the `backend/src/agents/` directory. Agent code is Story 2.2 scope. The stub diagnosis node lives in `pipeline/diagnosis_graph.py`.
- **DO NOT** modify existing models (`incident.py`, `state_machine.py`, `root_cause_event.py`). Add new models alongside them.
- **DO NOT** upgrade or change existing dependencies — only ADD the `mcp` package.

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  models/
    diagnosis.py       # NEW: DiagnosisObject, EvidenceArtifact, EvidenceGap
    __init__.py         # UPDATE: export new models
  pipeline/
    diagnosis_graph.py  # NEW: LangGraph StateGraph definition
    runner.py           # NEW: pipeline runner (invokes graph)
    mcp_client.py       # NEW: read-only MCP client
    audit_hook.py       # NEW: LangGraph audit callback (AD-25 #2)
    dispatcher.py       # UPDATE: replace stub with real graph invocation
    __init__.py         # UPDATE: docstring
  db/
    checkpointer.py     # NEW: AsyncPostgresSaver factory
  config/
    mcp_settings.py     # NEW: MCP connection settings
  api/
    app.py              # UPDATE: checkpointer init in lifespan
backend/tests/
  models/
    test_diagnosis.py   # NEW
  pipeline/
    __init__.py         # NEW
    conftest.py         # NEW: mock MCP + mock LLM fixtures
    test_mcp_client.py  # NEW
    test_diagnosis_graph.py  # NEW
    test_mcp_integration.py  # NEW
charts/openshift-ai-ops/
  templates/
    deployment-mcp-readonly.yaml       # NEW
    service-mcp-readonly.yaml          # NEW
    serviceaccount-cluster-reader.yaml # NEW
  values.yaml          # UPDATE: mcpReadonly section
```

### Latest Technology Notes

**LangGraph 1.2.x + langgraph-checkpoint-postgres >=2.0:**
- `AsyncPostgresSaver` requires `psycopg` v3 with `autocommit=True` and `row_factory=dict_row`
- `.setup()` must be called once to create checkpoint tables — call during app lifespan startup
- Thread IDs must be < 255 chars (UUIDs are safe)
- Checkpoints are written at the end of each superstep (each node execution)
- Pipeline mode (`pipeline=True` in `from_conn_string`) enables batching for better performance
- The checkpointer manages its own tables — never modify them
- For async: `AsyncPostgresSaver` with `AsyncConnectionPool` from `psycopg_pool`

**MCP Python SDK (latest):**
- `Client("http://host:port/mcp")` auto-selects Streamable HTTP transport
- For custom timeouts/headers: create `httpx.AsyncClient` and pass via `streamable_http_client(url, http_client=...)`
- kubernetes-mcp-server v0.0.66 with `--port 8080` exposes `/mcp` (Streamable HTTP) and `/sse` (SSE)
- `--read-only` flag prevents write operations at the server level
- Tools available: `get_resources`, `get_resource`, `describe_resource`, `get_logs`, `get_events`, `list_api_resources`
- Pre-1.0 software — pin exact version in Helm chart

**kubernetes-mcp-server v0.0.66:**
- Go-native binary — no Python/Node dependency
- Container image: `ghcr.io/containers/kubernetes-mcp-server` (verify exact tag)
- Uses in-cluster ServiceAccount for authentication — no explicit kubeconfig needed
- `--read-only` flag + `cluster-reader` ClusterRole = defense-in-depth for diagnosis side

### References

- [Source: ARCHITECTURE-SPINE.md#AD-1] — Staged pipeline paradigm (graph nodes = stages)
- [Source: ARCHITECTURE-SPINE.md#AD-2] — RBAC Airlock (cluster-reader for diagnosis)
- [Source: ARCHITECTURE-SPINE.md#AD-3] — Two schema domains (langgraph_* black box)
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types module (DiagnosisObject in models/)
- [Source: ARCHITECTURE-SPINE.md#AD-9] — Seven-deployment topology (add mcp-readonly)
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo source tree layout
- [Source: ARCHITECTURE-SPINE.md#AD-15] — MCP timeout → partial evidence, evidence_gaps
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine (queued→diagnosing→diagnosed)
- [Source: ARCHITECTURE-SPINE.md#AD-24] — In-process asyncio event bus
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit log write point #2 (pipeline audit hook)
- [Source: ARCHITECTURE-SPINE.md#Stack] — LangGraph 1.2.x, kubernetes-mcp-server 0.0.66+, psycopg 3
- [Source: project-context.md#LangGraph] — Staged pipeline paradigm, checkpoints to PostgreSQL, agents internal to stages
- [Source: project-context.md#Testing Rules] — Mock MCP, mock LLM, pipeline test layer
- [Source: project-context.md#Critical Don't-Miss Rules] — Never query langgraph_* tables, RBAC Airlock
- [Source: epics.md#Story 2.1] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 2] — FR-4, FR-5, FR-6, FR-8, FR-10 coverage
- [Source: Story 1.3 dispatcher.py] — Stub dispatch_to_pipeline() to be replaced
- [Source: Story 1.4] — Event bus pattern, SSE plumbing, audit middleware
- [Source: LangGraph docs] — AsyncPostgresSaver, psycopg requirements, checkpoint lifecycle
- [Source: MCP Python SDK docs] — Client(url), streamable_http_client, Streamable HTTP transport
- [Source: kubernetes-mcp-server GitHub] — --port, --read-only flags, Go-native binary

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
