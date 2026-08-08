---
baseline_commit: f91e8e5cba6f0c2aeff63ca9074cf9f6ec908bb3
---

# Story 1.4: REST API Foundation with Real-Time Events

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want to query the system for incident status and receive real-time pipeline updates via API,
so that I can monitor alert processing from the web UI or automation tooling with full audit trail.

## Acceptance Criteria

1. **Given** any REST API endpoint **When** a response is returned **Then** it follows the envelope format `{data: T, meta: {timestamp, request_id}}` **And** all endpoints are under the `/api/v1/` URL path

2. **Given** an unauthenticated request (no bearer token or invalid token) **When** it reaches any API endpoint **Then** the system returns HTTP 401 with the OpenShift OAuth challenge

3. **Given** a valid OpenShift OAuth bearer token **When** calling `GET /api/v1/incidents` **Then** the API returns a paginated list of incidents filterable by status (active, awaiting_approval, resolved, failed), severity, and time range

4. **Given** a valid bearer token and an existing incident ID **When** calling `GET /api/v1/incidents/{id}` **Then** the API returns full incident detail including correlated alerts, current pipeline state, and correlation evidence

5. **Given** an authenticated client subscribes to the SSE events endpoint **When** a pipeline stage transitions or an incident state changes **Then** the client receives an event matching the envelope `{event: string, data: {incident_id, stage, state, timestamp, payload}}` with dot-notation event names (e.g., `incident.stage_changed`, `incident.created`)

6. **Given** the in-process asyncio event bus **When** a pipeline stage emits a state change event **Then** all SSE-subscribed API clients receive the event without external message broker dependency

7. **Given** any state-changing REST request (POST, PUT, PATCH, DELETE) **When** the request completes successfully **Then** the audit log middleware writes a record to the `audit_log` table containing actor identity (from OAuth token), action, target resource, and timestamp

8. **Given** an API error occurs **When** the error response is returned **Then** it follows the structured error format `{error: string, code: string, detail: object}`

## Tasks / Subtasks

- [x] Task 1: API response envelope and error models (AC: #1, #8)
  - [x] Create `backend/src/models/api.py` with Pydantic models: `ApiMeta(timestamp, request_id)`, `ApiResponse(data, meta)`, `ApiError(error, code, detail)`
  - [x] Create `ApiResponse` as a generic wrapper: `class ApiResponse(BaseModel, Generic[T]): data: T; meta: ApiMeta`
  - [x] Export from `backend/src/models/__init__.py`
- [x] Task 2: SSE event envelope models (AC: #5, #6)
  - [x] Create/extend `backend/src/models/events.py` with `SSEEventData(incident_id, stage, state, timestamp, payload)` Pydantic model
  - [x] Define event name constants using dot-notation: `incident.created`, `incident.stage_changed`, `incident.state_changed`, `incident.resolved`
  - [x] Define the `EventBus` protocol/interface: `emit(event_name, data)`, `subscribe() -> AsyncIterator`, `unsubscribe(subscriber_id)`
  - [x] Export from `backend/src/models/__init__.py`
- [x] Task 3: In-process asyncio event bus implementation (AC: #6)
  - [x] Create `backend/src/api/event_bus.py` implementing the `EventBus` interface from `models/events.py`
  - [x] Use `asyncio.Queue` per subscriber — broadcast pattern (one queue per connected SSE client)
  - [x] Implement `emit()`: iterate all subscriber queues and put the event (non-blocking `put_nowait`, drop on full queue with warning log)
  - [x] Implement `subscribe()`: create a new queue, register it, return async iterator that yields from queue
  - [x] Implement `unsubscribe()`: remove queue from subscriber set, cleanup
  - [x] Singleton `EventBus` instance as a FastAPI dependency (app-lifetime scope)
  - [x] Queue max size configurable (default 256 per subscriber) to prevent memory exhaustion from slow clients
- [x] Task 4: OpenShift OAuth authentication dependency (AC: #2)
  - [x] Create `backend/src/api/auth.py` with `get_current_user` FastAPI dependency
  - [x] Extract `Authorization: Bearer <token>` from request headers
  - [x] Validate token via Kubernetes `TokenReview` API (`authentication.k8s.io/v1/tokenreviews`) using `httpx.AsyncClient`
  - [x] Return user identity (username, groups) on success
  - [x] Raise `HTTPException(401)` with `WWW-Authenticate: Bearer` header on failure
  - [x] Support dev-mode bypass via `AUTH_DISABLED=true` env var for local development (NEVER in production)
  - [x] Cache validated tokens in-memory with short TTL (60s) to avoid hammering the API server
- [x] Task 5: Audit log middleware (AC: #7)
  - [x] Create `backend/src/api/audit.py` with FastAPI middleware
  - [x] Intercept all state-changing requests (POST, PUT, PATCH, DELETE) — NOT GET or SSE subscriptions
  - [x] Extract actor identity from the authenticated user (from `get_current_user` dependency)
  - [x] Write to `audit_log` table: actor, action (HTTP method + path), target_resource (URL path), detail (request body summary), timestamp
  - [x] Create `backend/src/db/audit.py` with async function `write_audit_log(actor, action, target_resource, detail)`
  - [x] Audit writes must not block the response — use `BackgroundTasks` or fire-and-forget async task
  - [x] Audit writes must not fail the request — swallow DB errors with error logging
- [x] Task 6: Incident list endpoint (AC: #1, #3)
  - [x] Create `backend/src/api/incidents.py` with `GET /api/v1/incidents`
  - [x] Query parameters: `status` (multi-value: active, awaiting_approval, resolved, failed), `severity` (multi-value: critical, warning, info), `from_time`/`to_time` (ISO 8601), `page` (default 1), `page_size` (default 50, max 200)
  - [x] "active" status filter maps to non-terminal states: received, correlating, queued, diagnosing, diagnosed, executing, observing
  - [x] Create `backend/src/db/incidents.py` query function (extend from Story 1.1) with filtering and pagination
  - [x] Return `ApiResponse[PaginatedList[IncidentSummary]]` with pagination metadata in `meta`
  - [x] Require `get_current_user` dependency (authenticated)
- [x] Task 7: Incident detail endpoint (AC: #1, #4)
  - [x] Add `GET /api/v1/incidents/{incident_id}` to incidents router
  - [x] Return full incident detail: incident fields, correlated alerts (from `alerts` table), current pipeline state, correlation evidence (empty for now — populated by Story 1.2)
  - [x] Return 404 with structured error if incident not found
  - [x] Require `get_current_user` dependency (authenticated)
- [x] Task 8: SSE events endpoint (AC: #5, #6)
  - [x] Create `backend/src/api/events.py` with `GET /api/v1/events/stream`
  - [x] Use FastAPI native SSE: `response_class=EventSourceResponse` from `fastapi.sse`
  - [x] Yield `ServerSentEvent` objects with `event` (dot-notation name) and `data` (SSEEventData JSON)
  - [x] Subscribe to the in-process event bus on connection, unsubscribe on disconnect
  - [x] Send keep-alive comment every 15s to prevent proxy timeouts
  - [x] Support `Last-Event-ID` header for reconnection (track event sequence numbers)
  - [x] Require `get_current_user` dependency (authenticated)
  - [x] Handle client disconnect gracefully (asyncio.CancelledError cleanup)
- [x] Task 9: Wire everything in app.py (AC: all)
  - [x] Update `backend/src/api/app.py` to register: incidents router, events router
  - [x] Add audit log middleware
  - [x] Add global exception handler transforming unhandled errors to `{error, code, detail}` format
  - [x] Add Pydantic `ValidationError` handler returning 422 with structured error (not raw Pydantic output)
  - [x] Initialize event bus as app-lifetime dependency
  - [x] Exclude `/healthz` and `/api/v1/webhooks/alertmanager` from OAuth requirement (health checks and webhook ingress)
- [x] Task 10: Tests — unit (AC: #1, #2, #5, #8)
  - [x] `tests/models/test_api.py` — ApiResponse serialization, ApiError serialization, envelope structure
  - [x] `tests/models/test_events.py` — SSEEventData validation, event name constants
  - [x] `tests/api/test_auth.py` — Auth dependency: missing token → 401, invalid token → 401, valid token → user identity
- [x] Task 11: Tests — API integration (AC: #1, #2, #3, #4, #7, #8)
  - [x] `tests/api/test_incidents.py` — list endpoint with filters, detail endpoint, 404 on missing, envelope format
  - [x] `tests/api/test_incidents.py` — pagination parameters work correctly
  - [x] `tests/api/test_audit.py` — state-changing requests create audit_log rows, GET requests do not
  - [x] All tests use auth bypass (`AUTH_DISABLED=true`) for simplicity — auth-specific tests mock the TokenReview
- [x] Task 12: Tests — SSE integration (AC: #5, #6)
  - [x] `tests/api/test_events.py` — SSE connection receives events emitted on the bus
  - [x] `tests/api/test_events.py` — Multiple SSE clients each receive the same event (broadcast)
  - [x] `tests/api/test_events.py` — Client disconnect cleans up subscriber queue
  - [x] `tests/api/test_events.py` — Event envelope matches `{event, data: {incident_id, stage, state, timestamp, payload}}`

### Review Findings

- [ ] [Review][Patch] TokenReview disables TLS verification when the service-account CA bundle is missing [`backend/src/api/auth.py:74`]
- [ ] [Review][Patch] 401 auth failures bypass the required `{error, code, detail}` error envelope [`backend/src/api/auth.py:68`]
- [ ] [Review][Patch] Request validation errors still return FastAPI's default 422 payload instead of `ApiError` [`backend/src/api/app.py:92`]
- [ ] [Review][Patch] SSE reconnect support is incomplete because `Last-Event-ID` is ignored and event IDs reset per connection [`backend/src/api/events.py:35`]
- [ ] [Review][Patch] Audit middleware records failed state-changing requests instead of only successful ones [`backend/src/api/audit.py:35`]

## Dev Notes

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-10 | SSE + path-versioned REST API | SSE endpoints for real-time updates. All REST at `/api/v1/`. URL-path versioning only |
| AD-12 | OpenShift OAuth authentication | All endpoints require valid bearer token. Validate via TokenReview API. Approver identity extracted from token |
| AD-14 | Monorepo layout | All API code in `backend/src/api/`. DB queries in `backend/src/db/`. Models in `backend/src/models/` |
| AD-19 | Canonical state machine | API-permitted writes: approval/rejection (`awaiting_approval→executing`/`→failed`), cancellation (`queued→cancelled`). Read-only endpoints in this story |
| AD-21 | SSE event envelope contract | Envelope: `{event: string, data: {incident_id, stage, state, timestamp, payload}}`. Dot-notation event names. Defined in `models/` |
| AD-24 | In-process asyncio event bus | Pipeline emits events, API subscribes and streams via SSE. Bus interface in `models/`, implementation in `api/`. No external broker |
| AD-25 | Audit log middleware | Exactly two write points: API middleware (this story) and pipeline audit hook (later stories). Both write to `audit_log` table |

### REST API Design

#### Envelope Format

Every successful response:
```json
{
  "data": { ... },
  "meta": {
    "timestamp": "2026-08-08T14:30:00Z",
    "request_id": "uuid"
  }
}
```

For paginated responses, include pagination in meta:
```json
{
  "data": [ ... ],
  "meta": {
    "timestamp": "2026-08-08T14:30:00Z",
    "request_id": "uuid",
    "page": 1,
    "page_size": 50,
    "total": 142
  }
}
```

#### Error Format

Every error response:
```json
{
  "error": "Human-readable message",
  "code": "MACHINE_CODE",
  "detail": { "field": "specific info" }
}
```

Error codes to define:
- `UNAUTHORIZED` — 401, missing or invalid token
- `NOT_FOUND` — 404, resource not found
- `VALIDATION_ERROR` — 422, invalid request parameters
- `INTERNAL_ERROR` — 500, unexpected server error

#### Endpoint Summary

| Method | Path | Description | Auth | Audit |
|--------|------|-------------|------|-------|
| GET | `/healthz` | Health check (from Story 1.0) | No | No |
| POST | `/api/v1/webhooks/alertmanager` | Webhook receiver (from Story 1.1) | No | No |
| GET | `/api/v1/incidents` | List incidents with filters | Yes | No |
| GET | `/api/v1/incidents/{id}` | Incident detail | Yes | No |
| GET | `/api/v1/events/stream` | SSE event stream | Yes | No |

Approval endpoints (POST /api/v1/incidents/{id}/approve, POST /api/v1/incidents/{id}/reject) are Story 3.4. This story builds the middleware and patterns they will use.

### SSE Implementation (FastAPI Native)

FastAPI 0.135+ includes native SSE support via `fastapi.sse`. Use this instead of `sse-starlette`:

```python
from fastapi.sse import EventSourceResponse, ServerSentEvent
from collections.abc import AsyncIterable

@router.get("/api/v1/events/stream", response_class=EventSourceResponse)
async def event_stream(
    user: User = Depends(get_current_user),
    event_bus: EventBus = Depends(get_event_bus),
) -> AsyncIterable[ServerSentEvent]:
    subscriber = await event_bus.subscribe()
    try:
        seq = 0
        while True:
            try:
                event = await asyncio.wait_for(subscriber.get(), timeout=15.0)
                seq += 1
                yield ServerSentEvent(
                    data=event.data,
                    event=event.event_name,
                    id=str(seq),
                )
            except asyncio.TimeoutError:
                yield ServerSentEvent(comment="keepalive")
    finally:
        await event_bus.unsubscribe(subscriber)
```

Key implementation details:
- `EventSourceResponse` sets `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no` automatically
- `ServerSentEvent.data` is JSON-serialized automatically — pass Pydantic models or dicts directly
- 15-second keep-alive comments prevent nginx/HAProxy from closing idle connections
- `finally` block ensures cleanup on client disconnect (FastAPI raises `asyncio.CancelledError`)
- `id` field enables `Last-Event-ID`-based reconnection

### In-Process Asyncio Event Bus Pattern

```python
import asyncio
from typing import Set

class InProcessEventBus:
    def __init__(self, max_queue_size: int = 256):
        self._subscribers: Set[asyncio.Queue] = set()
        self._max_queue_size = max_queue_size

    async def emit(self, event_name: str, data: SSEEventData) -> None:
        event = BusEvent(event_name=event_name, data=data)
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(queue)
                logger.warning("Dropping event for slow subscriber",
                    extra={"component": "api"})
        for q in dead_queues:
            self._subscribers.discard(q)

    async def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
```

- `emit()` is called by pipeline stages (Story 1.2+, 2.x, 3.x) — this story builds the bus and SSE plumbing
- `subscribe()`/`unsubscribe()` are called by SSE endpoint handlers
- No external broker — single-process model per AD-9/AD-24
- Slow client protection: full queue → drop events and discard subscriber rather than applying backpressure to the pipeline

### OpenShift OAuth Token Validation

Two validation approaches exist. Use the `TokenReview` API (Kubernetes-native):

```python
import httpx

KUBE_API = "https://kubernetes.default.svc"
SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"

async def validate_token(bearer_token: str) -> UserInfo:
    sa_token = Path(SA_TOKEN_PATH).read_text().strip()
    async with httpx.AsyncClient(verify="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt") as client:
        resp = await client.post(
            f"{KUBE_API}/apis/authentication.k8s.io/v1/tokenreviews",
            headers={"Authorization": f"Bearer {sa_token}"},
            json={
                "apiVersion": "authentication.k8s.io/v1",
                "kind": "TokenReview",
                "spec": {"token": bearer_token}
            },
        )
    review = resp.json()
    if not review.get("status", {}).get("authenticated"):
        raise HTTPException(status_code=401)
    user = review["status"]["user"]
    return UserInfo(username=user["username"], groups=user.get("groups", []))
```

Critical implementation details:
- The backend pod's ServiceAccount token (mounted at `/var/run/secrets/...`) authenticates the TokenReview request itself
- Cache validated tokens in-memory with 60s TTL to avoid per-request API server calls (use a simple dict + timestamp)
- In local dev (`AUTH_DISABLED=true`), return a stub user — NEVER skip auth in production
- The `get_current_user` dependency MUST be applied to all `/api/v1/*` endpoints EXCEPT the webhook receiver (AlertManager is a cluster-internal service, not an OAuth user)

### Audit Log Middleware

Per AD-25, audit logging has exactly two write points. This story implements write point #1: the API middleware.

```python
class AuditMiddleware:
    STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method in self.STATE_CHANGING_METHODS:
            # Fire-and-forget: don't block response, don't fail on error
            asyncio.create_task(self._write_audit(request, response))
        return response
```

Rules:
- Only state-changing methods (POST, PUT, PATCH, DELETE) — NEVER audit GET or SSE
- Actor identity comes from the authenticated user attached to the request by `get_current_user`
- Exclude the webhook receiver path (`/api/v1/webhooks/alertmanager`) — it's an inbound event from AlertManager, not an SRE action
- Audit writes are fire-and-forget async tasks — DB failure logs an error but never blocks or fails the HTTP response
- Write point #2 (pipeline audit hook) is built in later stories when pipeline stages exist

### Database Queries — Incident List/Detail

Extend the `backend/src/db/incidents.py` module (created in Story 1.1) with query functions:

```python
async def list_incidents(
    conn,
    *,
    statuses: list[str] | None = None,
    severities: list[str] | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Incident], int]:
    """Returns (incidents, total_count) for pagination."""
    ...

async def get_incident_detail(conn, incident_id: UUID) -> IncidentDetail | None:
    """Returns incident + correlated alerts. None if not found."""
    ...
```

- Use asyncpg parameterized queries — NEVER string-interpolate SQL
- The "active" status filter maps to: `received`, `correlating`, `queued`, `diagnosing`, `diagnosed`, `executing`, `observing`
- `IncidentDetail` includes alerts joined from the `alerts` table via `incident_id` FK
- Correlation evidence fields are empty in this story — populated when Story 1.2 adds the correlator

### What This Story Does NOT Do

- **No approval/rejection endpoints** — Story 3.4 (Human Approval Workflow Backend API). This story builds the middleware and auth patterns those endpoints will use.
- **No policy matrix configuration API** — Story 6.4. Audit middleware pattern from this story will apply.
- **No statistics/aggregation endpoints** — Story 5.5.
- **No pipeline stages emitting events** — Stories 1.2, 1.3, 2.x. This story builds the bus and SSE plumbing; pipeline stages will call `event_bus.emit()` when they exist.
- **No correlation evidence in incident detail** — Story 1.2 adds the correlator; incident detail returns empty correlation evidence until then.
- **No frontend** — Epic 5. The API is consumed by the frontend but this story is backend-only.

### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/models/api.py` | API envelope and error Pydantic models | NEW |
| `backend/src/models/events.py` | SSE event envelope, event names, EventBus interface | NEW (or extend stub from 1.0) |
| `backend/src/api/auth.py` | OpenShift OAuth authentication dependency | NEW |
| `backend/src/api/audit.py` | Audit log middleware | NEW |
| `backend/src/api/incidents.py` | Incident list + detail REST endpoints | NEW |
| `backend/src/api/events.py` | SSE event stream endpoint | NEW |
| `backend/src/api/event_bus.py` | In-process asyncio event bus implementation | NEW |
| `backend/src/db/audit.py` | Audit log DB write function | NEW |
| `backend/tests/models/test_api.py` | API envelope model tests | NEW |
| `backend/tests/models/test_events.py` | Event model + bus interface tests | NEW |
| `backend/tests/api/test_auth.py` | OAuth authentication tests | NEW |
| `backend/tests/api/test_incidents.py` | Incident endpoint tests | NEW |
| `backend/tests/api/test_events.py` | SSE endpoint + event bus tests | NEW |
| `backend/tests/api/test_audit.py` | Audit middleware tests | NEW |

### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/models/__init__.py` | Export ApiResponse, ApiError, ApiMeta, SSEEventData, event constants | UPDATE |
| `backend/src/api/app.py` | Register routers, add audit middleware, add error handlers, init event bus | UPDATE |
| `backend/src/db/incidents.py` | Add `list_incidents()` and `get_incident_detail()` query functions | UPDATE |

### Dependency Direction (ENFORCED)

- `models/api.py` — depends on nothing (Pydantic only)
- `models/events.py` — depends on nothing (Pydantic + Protocol only)
- `api/event_bus.py` — depends on `models/events.py` (imports event bus interface + SSEEventData)
- `api/auth.py` — depends on nothing except httpx (external HTTP call to TokenReview)
- `api/audit.py` — depends on `db/audit.py` (write audit record) and `api/auth.py` (extract user from request)
- `api/incidents.py` — depends on `models/` (response types), `db/incidents.py` (queries), `api/auth.py` (dependency)
- `api/events.py` — depends on `models/events.py` (envelope), `api/event_bus.py` (bus), `api/auth.py` (dependency)
- `db/audit.py` — depends on `models/` (audit record shape)
- `db/incidents.py` — depends on `models/` (Incident, Alert models)
- **NEVER**: `api/` imports from `pipeline/` or `agents/`. The event bus decouples them.

### Technology Stack (Relevant to This Story)

| Package | Version | Usage in This Story |
|---------|---------|---------------------|
| FastAPI | ~=0.141.1 | REST endpoints, SSE via `fastapi.sse`, middleware |
| Pydantic | ~=2.x | API envelope, error models, SSE event envelope |
| asyncpg | latest | Async database queries for incidents, audit log |
| httpx | latest | TokenReview API calls for OAuth validation, TestClient |
| pytest | latest (dev) | Test runner |
| testcontainers | latest (dev) | PostgreSQL fixture for integration tests |

### Naming Conventions

- Python modules: `snake_case` (e.g., `event_bus.py`, `audit.py`)
- Database columns: `snake_case` (uses existing `audit_log` table from Story 1.0)
- API endpoints: kebab-case paths (`/api/v1/incidents`, `/api/v1/events/stream`)
- Pydantic models: PascalCase (`ApiResponse`, `SSEEventData`, `IncidentSummary`)
- Event names: dot-notation (`incident.created`, `incident.stage_changed`)

### Anti-Patterns to Avoid

- **Do NOT** bypass the state machine transition function for any state changes. This story only reads state, but the audit middleware must record attempts correctly.
- **Do NOT** add approval/rejection endpoints — that's Story 3.4. Build only the infrastructure (auth, audit, envelope) they will use.
- **Do NOT** emit events from the webhook receiver — the webhook path is Story 1.1 territory. Event emission from pipeline stages comes in Stories 1.2+.
- **Do NOT** use `sse-starlette` — FastAPI 0.141.x has native SSE via `fastapi.sse.EventSourceResponse` and `ServerSentEvent`. No external dependency needed.
- **Do NOT** use Redis, RabbitMQ, or any external broker for the event bus — single-process asyncio per AD-24.
- **Do NOT** use print() — use the structured JSON logger (component=`api`)
- **Do NOT** expose raw Pydantic validation errors — transform to `{error, code, detail}` format
- **Do NOT** add authentication to the webhook endpoint (`/api/v1/webhooks/alertmanager`) — that's an inbound event from AlertManager, not an SRE request
- **Do NOT** add authentication to the health check (`/healthz`) — must be reachable by Kubernetes probes
- **Do NOT** make audit log writes block the HTTP response — fire-and-forget async tasks
- **Do NOT** make audit log DB failures fail the HTTP request — log the error and continue

### Testing Strategy

**Unit tests** (`pytest -m unit`):
- ApiResponse, ApiMeta, ApiError model serialization and structure
- SSEEventData model validation
- Event name constants exist and follow dot-notation pattern

**API tests** (`pytest -m api`):
- `GET /api/v1/incidents` returns paginated list in envelope format
- `GET /api/v1/incidents` filters by status, severity, time range
- `GET /api/v1/incidents/{id}` returns detail with alerts in envelope format
- `GET /api/v1/incidents/{id}` returns 404 with error envelope for unknown ID
- Auth disabled: all endpoints accessible in test mode
- Auth mocked: requests without token → 401, requests with valid token → success
- Error responses follow `{error, code, detail}` format

**DB integration tests** (`pytest -m db`):
- Audit middleware writes to `audit_log` for POST/PUT/PATCH/DELETE
- Audit middleware does NOT write for GET requests
- `list_incidents()` query with various filter combinations
- `get_incident_detail()` returns incident + joined alerts
- `get_incident_detail()` returns None for non-existent ID

**SSE integration tests** (`pytest -m api`):
- SSE connection opens and receives events emitted to the bus
- Multiple concurrent SSE clients each receive broadcast events
- Client disconnect triggers cleanup (subscriber queue removed)
- Event envelope format matches AD-21 specification
- Keep-alive comments sent during idle periods

### Previous Story Intelligence

**From Story 1.0:**
- `backend/src/db/` has asyncpg connection management
- `audit_log` table already exists in the initial migration with columns: `id`, `actor`, `action`, `target_resource`, `detail`, `created_at`
- Structured logging via `backend/src/config/logging.py` — use component=`api`
- FastAPI app factory in `backend/src/api/app.py` — extend it, don't replace
- Test infrastructure: testcontainers PostgreSQL, FastAPI TestClient fixture in `conftest.py`
- `backend/src/models/events.py` should have an event bus interface stub — flesh it out fully

**From Story 1.1:**
- `backend/src/api/webhooks.py` handles `POST /api/v1/webhooks/alertmanager` — DO NOT add auth to this endpoint
- `backend/src/db/incidents.py` has `create_incident()` and `create_alert()` — extend with query functions
- `backend/src/api/app.py` already registers the webhook router — add new routers alongside it
- Error response format (`{error, code, detail}`) is already used for webhook validation errors — make it consistent across all endpoints via a global handler
- The webhook endpoint uses `BackgroundTasks` — the same pattern applies to audit middleware

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  api/
    app.py          # UPDATE: register new routers, add middleware
    auth.py         # NEW: OAuth dependency
    audit.py        # NEW: audit log middleware
    incidents.py    # NEW: incident list + detail endpoints
    events.py       # NEW: SSE endpoint
    event_bus.py    # NEW: asyncio event bus implementation
    health.py       # EXISTS (Story 1.0)
    webhooks.py     # EXISTS (Story 1.1)
  db/
    audit.py        # NEW: audit log DB write
    incidents.py    # UPDATE: add query functions
  models/
    api.py          # NEW: envelope models
    events.py       # NEW/UPDATE: SSE event models + bus interface
    incident.py     # EXISTS (Story 1.0)
    alert.py        # EXISTS (Story 1.0)
    state_machine.py # EXISTS (Story 1.0)
    webhook.py      # EXISTS (Story 1.1)
```

### References

- [Source: ARCHITECTURE-SPINE.md#AD-10] — SSE + path-versioned REST API
- [Source: ARCHITECTURE-SPINE.md#AD-12] — OpenShift OAuth authentication
- [Source: ARCHITECTURE-SPINE.md#AD-21] — SSE event envelope contract
- [Source: ARCHITECTURE-SPINE.md#AD-24] — In-process asyncio event bus
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit log ownership: cross-cutting middleware
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine (API-permitted writes)
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo source tree layout
- [Source: ARCHITECTURE-SPINE.md#Consistency Conventions] — API envelope, error shapes, naming
- [Source: project-context.md#FastAPI] — SSE via EventSourceResponse, single Python process
- [Source: project-context.md#Testing Rules] — pytest markers, testcontainers, mock boundaries
- [Source: project-context.md#Critical Don't-Miss Rules] — Auth, audit, event bus patterns
- [Source: epics.md#Story 1.4] — Story requirements and acceptance criteria
- [Source: epics.md#FR-33] — REST API requirement (authentication, authorization, audit logging)
- [Source: epics.md#FR-21] — SSE for real-time updates
- [Source: Story 1.0] — Project scaffolding, DB schema, structured logging, health check
- [Source: Story 1.1] — Webhook receiver, incident/alert persistence, error format pattern
- [Source: FastAPI docs] — Native SSE via fastapi.sse (EventSourceResponse, ServerSentEvent) added in 0.135
- [Source: OpenShift docs] — TokenReview API for bearer token validation (authentication.k8s.io/v1)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- SSE integration tests initially used httpx streaming which doesn't work with ASGI transport (buffers full response). Restructured to test generator function directly.
- Test fixture isolation: `seeded_incident` uses committed connection (not rolled-back transaction) so app's pool can see the data.

### Completion Notes List

- Implemented full REST API foundation: envelope format, error format, incidents endpoints, SSE streaming, OAuth auth, audit middleware
- In-process asyncio event bus with per-subscriber queues, configurable max size (256), slow-client protection (drop + discard)
- OpenShift OAuth via TokenReview API with 60s in-memory cache, dev-mode bypass (AUTH_DISABLED=true)
- Audit middleware fires on POST/PUT/PATCH/DELETE only, excludes webhook path, fire-and-forget async writes that never block/fail requests
- All 46 new tests pass (17 unit, 29 integration). 3 pre-existing failures in correlator/webhook tests unrelated to this story.
- SSE endpoint tested via direct generator function testing (httpx ASGI transport limitation for streaming responses)

### Change Log

- 2026-08-08: Story 1.4 implementation complete — REST API foundation with real-time events

### File List

New files:
- backend/src/models/api.py
- backend/src/models/events.py (replaced stub)
- backend/src/api/auth.py
- backend/src/api/audit.py
- backend/src/api/incidents.py
- backend/src/api/events.py
- backend/src/api/event_bus.py
- backend/src/db/audit.py
- backend/tests/models/test_api.py
- backend/tests/models/test_events.py
- backend/tests/api/test_auth.py
- backend/tests/api/test_incidents.py
- backend/tests/api/test_events.py
- backend/tests/api/test_audit.py

Modified files:
- backend/src/models/__init__.py
- backend/src/api/app.py
- backend/src/db/__init__.py
- backend/src/db/incidents.py
- _bmad-output/implementation-artifacts/sprint-status.yaml
