# OpenShift AI Ops — Backend

AI-powered operations assistant for OpenShift. This is the backend service providing alert intake, AI diagnosis pipeline, and remediation orchestration.

## Prerequisites

- Python 3.13+
- PostgreSQL 18 with pgvector extension (for development: use podman/docker)
- Podman or Docker (for running integration tests via testcontainers)

## Setup

### 1. Create and activate a virtual environment

```bash
cd backend/
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

### 3. Database setup

Start a local PostgreSQL container:

```bash
podman run -d --name openshift-ai-ops-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=openshift_ai_ops \
  -p 5432:5432 \
  pgvector/pgvector:pg18
```

### 4. Run migrations

```bash
alembic upgrade head
```

The migration URL is configured via the `DATABASE_URL` environment variable or defaults to the value in `alembic.ini`.

```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/openshift_ai_ops"
alembic upgrade head
```

### 5. Run the dev server

```bash
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/healthz
# {"status": "healthy", "database": "connected"}
```

## Running Tests

### Full test suite

```bash
export DOCKER_HOST=unix:///run/user/$(id -u)/podman/podman.sock
export TESTCONTAINERS_RYUK_DISABLED=true
pytest
```

### Test markers

Run specific test layers using markers:

| Marker | Description | Requires |
|--------|-------------|----------|
| `unit` | Unit tests (mocked dependencies) | Nothing |
| `db` | Database integration tests | Podman/Docker |
| `api` | API integration tests | Podman/Docker |
| `pipeline` | Pipeline integration tests | Podman/Docker |

Examples:

```bash
pytest -m unit          # Fast, no containers needed
pytest -m db            # Database tests (spins up PostgreSQL container)
pytest -m api           # API tests (spins up PostgreSQL + TestClient)
pytest -m "not db"      # Skip database tests
```

### Test infrastructure

- **testcontainers** spins up a `pgvector/pgvector:pg18` container per session
- Alembic migrations run automatically in test setup
- Each test gets a database connection wrapped in a rolled-back transaction for isolation
- FastAPI `async_client` fixture provides an HTTPX async client for endpoint testing

## Project Structure

```
backend/
  src/
    api/            # FastAPI routes, SSE, webhook receiver
    pipeline/       # LangGraph graph definitions
    agents/         # Orchestrator, skeptics, planner
    models/         # Shared typed artifacts — THE contract
    knowledge/      # RAG retrieval
    db/             # PostgreSQL access, migrations
    config/         # Settings, structured logging
  tests/
    models/         # Unit tests for shared types
    api/            # API integration tests
    db/             # Database integration tests
    pipeline/       # Pipeline integration tests
  alembic/          # Migration scripts
  alembic.ini       # Alembic configuration
  pyproject.toml    # Project metadata and dependencies
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `POSTGRES_DB` | `openshift_ai_ops` | Database name |
| `DATABASE_URL` | (from env vars above) | Override for Alembic migrations |
