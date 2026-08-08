# Story 1.0: Project Scaffolding & Shared Contracts

Status: ready-for-dev

## Story

As a developer,
I want the monorepo structure, shared type contracts, database foundation, and test infrastructure established,
so that all subsequent stories have a working development environment and consistent patterns to build on.

## Acceptance Criteria

1. **Given** the project repository is initialized **When** a developer inspects the directory structure **Then** the monorepo layout matches AD-14: `backend/src/{api,pipeline,agents,models,knowledge,db,config}`, `backend/tests/`, `frontend/src/`, `charts/openshift-ai-ops/`, `docs/`

2. **Given** the Python project is configured **When** a developer runs `pip install -e .` in `backend/` **Then** all core dependencies are installed (FastAPI, LangGraph, Pydantic, asyncpg, prometheus-client) **And** dev dependencies include pytest, testcontainers, httpx (for TestClient)

3. **Given** the shared types module at `backend/src/models/` **When** inspected **Then** it defines the Alert and Incident Pydantic models with the canonical incident state machine (`received → correlating → queued → diagnosing → diagnosed → awaiting_approval → executing → observing → resolved | failed`) and a state-machine transition function that all state writes must use

4. **Given** the state machine transition function **When** an invalid transition is attempted (e.g., `received → executing`) **Then** the function raises a typed error and does not modify state

5. **Given** the PostgreSQL database **When** migrations run **Then** the application schema (incidents, alerts, audit_log) is created separately from the `langgraph_*` schema domain per AD-3 **And** the migration tooling (Alembic) is configured and documented

6. **Given** the backend application starts **When** it processes any request or event **Then** all log output is structured JSON to stdout with fields: `timestamp`, `level`, `component` (api|pipeline|agent|db|knowledge), and `request_id` or `incident_id` for correlation

7. **Given** the backend is running **When** a client calls `GET /healthz` **Then** the endpoint returns HTTP 200 with a health status indicating database connectivity

8. **Given** the Helm chart skeleton **When** `helm template` is run **Then** it renders a backend Deployment and a PostgreSQL StatefulSet with PVC-backed storage in a single namespace

9. **Given** the pytest configuration **When** a developer inspects it **Then** test markers are defined for `unit`, `db`, `api`, and `pipeline` **And** `backend/tests/` mirrors `backend/src/` layout (e.g., `tests/models/`, `tests/api/`, `tests/db/`)

10. **Given** the test infrastructure **When** a developer runs `pytest -m db` **Then** a testcontainers fixture spins up PostgreSQL 18 + pgvector, runs migrations, and provides a clean database session per test **And** the fixture is defined in `conftest.py` for reuse across all test modules

11. **Given** the test infrastructure **When** a developer runs `pytest -m api` **Then** a FastAPI TestClient fixture is available backed by the testcontainers database **And** tests can exercise HTTP endpoints end-to-end against a real database

12. **Given** a developer clones the repository **When** they follow the README setup instructions **Then** they can start the backend dev server, see the health check pass, and run the test suite (which passes with the scaffolding tests)

## Tasks / Subtasks

- [ ] Task 1: Create monorepo directory structure (AC: #1)
  - [ ] Create `backend/src/{api,pipeline,agents,models,knowledge,db,config}/` with `__init__.py` files
  - [ ] Create `backend/tests/{models,api,db,pipeline}/` with `__init__.py` files
  - [ ] Create `frontend/src/` placeholder
  - [ ] Create `charts/openshift-ai-ops/{templates}/` with `values.yaml`
  - [ ] Create `docs/` directory
- [ ] Task 2: Python project setup (AC: #2)
  - [ ] Create `backend/pyproject.toml` with dependencies and dev dependencies
  - [ ] Pin versions: FastAPI~=0.141.1, langgraph~=1.2, pydantic~=2.x, asyncpg, prometheus-client~=0.25.x
  - [ ] Dev deps: pytest, pytest-asyncio, testcontainers[postgres], httpx, alembic
  - [ ] Add `langgraph-checkpoint-postgres` (requires psycopg[binary] and psycopg-pool)
  - [ ] Verify `pip install -e .` works cleanly
- [ ] Task 3: Shared types module — models/ (AC: #3, #4)
  - [ ] Create `backend/src/models/incident.py` with Incident Pydantic model
  - [ ] Create `backend/src/models/alert.py` with Alert Pydantic model
  - [ ] Create `backend/src/models/state_machine.py` with canonical state machine
  - [ ] Implement `transition(current_state, target_state) -> new_state` function
  - [ ] Define `InvalidTransitionError` typed error
  - [ ] Define valid transitions map (adjacency list)
  - [ ] Export all models from `backend/src/models/__init__.py`
- [ ] Task 4: Database foundation (AC: #5)
  - [ ] Create `backend/src/db/` module with asyncpg connection management
  - [ ] Configure Alembic in `backend/` with migrations directory
  - [ ] Create initial migration: `incidents` table, `alerts` table, `audit_log` table
  - [ ] Schema must NOT create `langgraph_*` tables (LangGraph owns those via `checkpointer.setup()`)
  - [ ] Document migration usage in README
- [ ] Task 5: Structured JSON logging (AC: #6)
  - [ ] Create `backend/src/config/logging.py` structured logger
  - [ ] JSON output to stdout: `{timestamp, level, component, request_id|incident_id, message}`
  - [ ] Component enum: api, pipeline, agent, db, knowledge
  - [ ] Integrate with FastAPI middleware for request_id propagation
- [ ] Task 6: Health check endpoint (AC: #7)
  - [ ] Create `backend/src/api/health.py` with `GET /healthz`
  - [ ] Check database connectivity via asyncpg
  - [ ] Return `{"status": "healthy", "database": "connected"}` on success
  - [ ] Return 503 with `{"status": "unhealthy", "database": "disconnected"}` on failure
- [ ] Task 7: FastAPI application entrypoint (AC: #6, #7)
  - [ ] Create `backend/src/api/app.py` with FastAPI application factory
  - [ ] Wire structured logging middleware
  - [ ] Wire health check router
  - [ ] Add `/api/v1/` prefix preparation (empty router for now)
- [ ] Task 8: Helm chart skeleton (AC: #8)
  - [ ] Create `charts/openshift-ai-ops/Chart.yaml`
  - [ ] Create `charts/openshift-ai-ops/values.yaml` with defaults
  - [ ] Create `templates/deployment-backend.yaml`
  - [ ] Create `templates/statefulset-postgresql.yaml` with PVC
  - [ ] Create `templates/service-backend.yaml` and `templates/service-postgresql.yaml`
  - [ ] Verify `helm template .` renders without errors
- [ ] Task 9: Test infrastructure (AC: #9, #10, #11)
  - [ ] Create `backend/tests/conftest.py` with session-scoped testcontainers fixture
  - [ ] Use `pgvector/pgvector:pg18` container image
  - [ ] Run Alembic migrations in fixture setup
  - [ ] Create `CREATE EXTENSION IF NOT EXISTS vector` in fixture
  - [ ] Provide async session fixture (per-test rollback)
  - [ ] Create FastAPI TestClient fixture backed by test database
  - [ ] Define pytest markers in `pyproject.toml`: unit, db, api, pipeline
  - [ ] Create `backend/pytest.ini` or pytest section in `pyproject.toml`
- [ ] Task 10: Scaffolding tests (AC: #10, #11, #12)
  - [ ] `tests/models/test_state_machine.py` — valid transitions pass, invalid raise error
  - [ ] `tests/db/test_migrations.py` — migrations run, tables exist, pgvector extension active
  - [ ] `tests/api/test_health.py` — health endpoint returns 200 with DB connected
  - [ ] Verify full test suite passes with `pytest`
- [ ] Task 11: README and developer documentation (AC: #12)
  - [ ] Write `backend/README.md` with setup instructions
  - [ ] Document: virtualenv setup, `pip install -e .`, DB setup, run dev server, run tests
  - [ ] Document test markers and how to run specific test layers

## Dev Notes

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-3 | Two schema domains | Application schema separate from `langgraph_*`. Do NOT create LangGraph tables — those are created by `checkpointer.setup()` at runtime |
| AD-4 | Shared types in `models/` | ALL stage-boundary artifacts defined here. `models/` imports nothing else. Everything else imports from it |
| AD-14 | Monorepo layout | Exact directory structure is mandatory. See structure below |
| AD-19 | Canonical state machine | States: `received → correlating → queued → diagnosing → diagnosed → awaiting_approval → executing → observing → resolved \| failed`. All writes via transition function |
| AD-24 | Event bus interface in `models/` | Define the emit/subscribe contract shape in `models/` (stub only — implementation in later stories) |
| AD-25 | Audit log schema | `audit_log` table in initial migration |

### Required Directory Structure

```
openshift-ai-ops/
  backend/
    src/
      api/            # FastAPI routes, SSE, webhook receiver
      pipeline/       # LangGraph graph definitions (empty stubs)
      agents/         # Orchestrator, skeptics, planner (empty stubs)
      models/         # Shared typed artifacts — THE contract
      knowledge/      # RAG retrieval (empty stubs)
      db/             # PostgreSQL access, migrations
      config/         # Settings, structured logging
    tests/
      models/
      api/
      db/
      pipeline/
    pyproject.toml
    alembic.ini
    alembic/
      versions/
  frontend/
    src/              # Placeholder only in this story
  charts/
    openshift-ai-ops/
      Chart.yaml
      values.yaml
      templates/
  docs/
```

### Dependency Direction (ENFORCED)

- `models/` is a leaf — depends on NOTHING
- `db/` depends on `models/`
- `knowledge/` depends on `db/`
- `agents/` depends on `models/`, `knowledge/`, `db/`
- `pipeline/` depends on `models/`, `agents/`, `db/`, `knowledge/`
- `api/` depends on `models/`, `pipeline/`, `db/`
- `agents/` NEVER imports from `api/` or `pipeline/`

### Technology Stack (Pinned Versions)

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | ~=0.141.1 | REST API + SSE + webhook receiver |
| langgraph | ~=1.2 | Agent pipeline runtime |
| langgraph-checkpoint-postgres | latest 1.x | PostgreSQL checkpoint persistence |
| pydantic | ~=2.x | Typed models for all artifacts |
| asyncpg | latest | Async PostgreSQL driver |
| psycopg[binary] | 3.x | Required by langgraph-checkpoint-postgres |
| psycopg-pool | latest | Connection pooling for LangGraph |
| prometheus-client | ~=0.25.x | Metrics exposition |
| alembic | latest | Database migrations |
| uvicorn | latest | ASGI server |

**Dev dependencies:**

| Package | Purpose |
|---------|---------|
| pytest | Test runner |
| pytest-asyncio | Async test support |
| testcontainers[postgres] | Spin up PostgreSQL in tests |
| httpx | FastAPI TestClient (async) |

### State Machine Implementation Details

Valid transitions (adjacency list):
```python
VALID_TRANSITIONS = {
    "received": ["correlating"],
    "correlating": ["queued"],
    "queued": ["diagnosing", "diagnosed", "cancelled"],  # diagnosed = fast-path shortcut
    "diagnosing": ["diagnosed", "failed"],
    "diagnosed": ["awaiting_approval", "executing"],
    "awaiting_approval": ["executing", "failed"],  # failed = rejection
    "executing": ["observing"],
    "observing": ["resolved", "failed"],
}
# "resolved" and "failed" are terminal states — no outgoing transitions
# "cancelled" is terminal (resolved-webhook cancellation per AD-23)
```

State-write ownership:
- **API-permitted:** `received` (webhook creates), `awaiting_approval → executing` or `→ failed` (approval/rejection), `queued → cancelled` (resolved-webhook)
- **Pipeline-only:** all other transitions

### Database Schema (Initial Migration)

```sql
-- incidents table
CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state VARCHAR(20) NOT NULL DEFAULT 'received',
    severity VARCHAR(10),  -- critical, warning, info
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- alerts table
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id),
    fingerprint VARCHAR(64) NOT NULL,
    labels JSONB NOT NULL DEFAULT '{}',
    annotations JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(10) NOT NULL,  -- firing, resolved
    fired_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- audit_log table (AD-25)
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_resource VARCHAR(255),
    detail JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- pgvector extension (needed for future stories)
CREATE EXTENSION IF NOT EXISTS vector;
```

**DO NOT create `langgraph_*` tables.** LangGraph manages its own schema via `AsyncPostgresSaver.setup()` — it creates `checkpoints`, `checkpoint_writes`, and `checkpoint_migrations` tables in its own namespace. This is a black box per AD-3.

### Testcontainers Setup Pattern

```python
# backend/tests/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg18", driver=None) as postgres:
        yield postgres

@pytest.fixture(scope="session")
def db_url(postgres_container):
    return postgres_container.get_connection_url()
```

- Use `pgvector/pgvector:pg18` image (PostgreSQL 18 + pgvector pre-installed)
- Session-scoped: one container per test session
- Per-test fixtures: wrap in transaction + rollback for isolation
- Run Alembic migrations in session-scoped fixture before tests execute
- FastAPI TestClient: use httpx.AsyncClient with the app, override DB dependency

### Structured Logging Format

Every log line is a JSON object to stdout:
```json
{"timestamp": "2026-08-08T14:30:00Z", "level": "INFO", "component": "api", "request_id": "uuid", "message": "Health check passed"}
```

- Use Python's `logging` module with a custom JSON formatter
- Component values are constrained: `api`, `pipeline`, `agent`, `db`, `knowledge`
- `request_id` for API calls (generated per request via middleware)
- `incident_id` for pipeline processing (propagated through context)
- NO print statements anywhere — structured logger only

### Helm Chart Skeleton

Minimal but valid chart that renders with `helm template`:
- `Chart.yaml`: name=openshift-ai-ops, version=0.1.0
- `values.yaml`: image tags, replica counts, PostgreSQL credentials, PVC size
- Backend Deployment: single replica, container port 8000
- PostgreSQL StatefulSet: single replica, PVC for data persistence
- Services: ClusterIP for both backend and PostgreSQL
- Single namespace deployment per AD-9

### Naming Conventions

- Python modules: `snake_case` (e.g., `state_machine.py`, `audit_log.py`)
- Database tables/columns: `snake_case`
- API endpoints: kebab-case paths (e.g., `/healthz`, `/api/v1/incidents`)
- Environment variables: `UPPER_SNAKE_CASE`
- Entity IDs: UUIDs
- Dates: ISO 8601 with timezone everywhere

### Anti-Patterns to Avoid

- **Do NOT** create any `langgraph_*` tables in migrations
- **Do NOT** write state directly to incident.state column — always use the transition function
- **Do NOT** use in-memory data structures for anything that must survive restart
- **Do NOT** use print() — structured logger only
- **Do NOT** put models in any module other than `models/`
- **Do NOT** create circular imports — respect dependency direction
- **Do NOT** add any API endpoints beyond `/healthz` — API foundation is Story 1.4
- **Do NOT** add frontend code — that's Epic 5

### Project Structure Notes

- This story establishes the canonical project structure. All subsequent stories build on it.
- `frontend/src/` is a placeholder — populated in Epic 5
- `pipeline/`, `agents/`, `knowledge/` get `__init__.py` only — populated in Epic 2
- The event bus interface shape (emit/subscribe) should be stubbed in `models/events.py` for later implementation

### References

- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout
- [Source: ARCHITECTURE-SPINE.md#AD-3] — Two schema domains
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types module
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit log ownership
- [Source: project-context.md#Testing Rules] — Test infrastructure requirements
- [Source: project-context.md#Technology Stack] — Pinned versions
- [Source: epics.md#Story 1.0] — Story requirements and acceptance criteria

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
