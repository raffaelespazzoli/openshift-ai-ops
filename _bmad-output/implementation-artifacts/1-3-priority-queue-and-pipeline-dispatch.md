# Story 1.3: Priority Queue and Pipeline Dispatch

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want Root-Cause Events to be queued by priority and dispatched for processing,
so that the most urgent issues are diagnosed first and the queue survives system restarts.

## Acceptance Criteria

1. **Given** multiple Root-Cause Events in the priority queue **When** the next event is dequeued for processing **Then** the highest urgency × most recent event is selected first

2. **Given** concurrent pipeline workers attempt to dequeue simultaneously **When** they execute the dequeue query **Then** PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` prevents any event from being processed by more than one worker

3. **Given** a `resolved` webhook arrives from AlertManager **When** the corresponding alert's Root-Cause Event is still in `queued` status **Then** the queue entry is cancelled via `UPDATE ... WHERE status = 'queued'` **And** the incident state transitions to `cancelled` if all alerts in the RCE are resolved

4. **Given** the parallelism cap is configured to N concurrent pipelines **When** N diagnosis pipelines are already running **Then** no additional Root-Cause Events are dequeued until a running pipeline completes

5. **Given** a Root-Cause Event has been in the queue beyond its configurable TTL **When** the TTL check runs **Then** the system verifies against the AlertManager API whether the alert is still active **And** removes the entry if the alert is no longer firing

6. **Given** the backend pod crashes and restarts **When** the application recovers **Then** all queued Root-Cause Events are still present in PostgreSQL and processing resumes from where it left off

7. **Given** a sealed Root-Cause Event enters the priority queue **When** it is enqueued **Then** the incident state transitions to `queued` via the state machine function

## Tasks / Subtasks

- [ ] Task 1: Priority queue database schema (AC: #1, #2, #6)
  - [ ] Create Alembic migration adding `priority_queue` table
  - [ ] Table: `id UUID PK`, `root_cause_event_id UUID FK UNIQUE`, `incident_id UUID FK`, `priority_score FLOAT NOT NULL`, `severity VARCHAR(10) NOT NULL`, `status VARCHAR(20) NOT NULL DEFAULT 'queued'` (queued/processing/completed/cancelled), `enqueued_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `dequeued_at TIMESTAMPTZ`, `completed_at TIMESTAMPTZ`, `ttl_expires_at TIMESTAMPTZ`
  - [ ] Create partial index: `CREATE INDEX idx_priority_queue_pending ON priority_queue (priority_score DESC, enqueued_at ASC) WHERE status = 'queued'`
  - [ ] Create index on `root_cause_event_id` for fast cancellation lookup
  - [ ] Add `active_pipelines` table for parallelism tracking: `id UUID PK`, `queue_item_id UUID FK`, `incident_id UUID FK`, `started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `completed_at TIMESTAMPTZ`

- [ ] Task 2: Priority scoring function (AC: #1)
  - [ ] Create `backend/src/pipeline/priority_queue.py` — queue logic module
  - [ ] Implement `calculate_priority_score(severity: str, sealed_at: datetime) -> float`
  - [ ] Score formula: `severity_weight × recency_factor` where severity_weight = {critical: 100, warning: 50, info: 10} and recency_factor = `1.0 / (1.0 + (now - sealed_at).total_seconds() / 3600)` (decays over hours)
  - [ ] Higher score = higher priority (dequeued first)
  - [ ] Severity weights configurable via settings

- [ ] Task 3: Enqueue operation (AC: #7)
  - [ ] Implement `enqueue_rce(root_cause_event_id: UUID, incident_id: UUID, severity: str, sealed_at: datetime, db) -> UUID`
  - [ ] Calculate priority score using the scoring function
  - [ ] Calculate TTL expiry: `now() + configured_ttl_seconds`
  - [ ] Insert row into `priority_queue` table with status='queued'
  - [ ] State transition on incident already handled by correlator (Story 1.2 sets `queued` on seal) — no transition needed here, just verify state is `queued`

- [ ] Task 4: Dequeue operation with row-level locking (AC: #1, #2, #4)
  - [ ] Create `backend/src/db/queue.py` — DB operations for queue
  - [ ] Implement `dequeue_next(db) -> Optional[QueueItem]`
  - [ ] SQL pattern:
    ```sql
    UPDATE priority_queue
    SET status = 'processing', dequeued_at = NOW()
    WHERE id = (
      SELECT id FROM priority_queue
      WHERE status = 'queued'
      ORDER BY priority_score DESC, enqueued_at ASC
      FOR UPDATE SKIP LOCKED
      LIMIT 1
    )
    RETURNING *;
    ```
  - [ ] Before dequeue: check parallelism cap — count active rows in `active_pipelines` where `completed_at IS NULL`
  - [ ] If active count >= configured cap, return None (no dequeue)
  - [ ] On successful dequeue: insert row into `active_pipelines` table

- [ ] Task 5: Resolved-webhook cancellation (AC: #3)
  - [ ] Implement `cancel_queued_rce(root_cause_event_id: UUID, db) -> bool`
  - [ ] SQL: `UPDATE priority_queue SET status = 'cancelled' WHERE root_cause_event_id = $1 AND status = 'queued' RETURNING id`
  - [ ] If cancellation succeeds (row found and updated): transition incident state from `queued` to `cancelled` via state machine function
  - [ ] If row is already `processing` (locked or dequeued): cancellation does NOT happen — the freshness gate (AD-16, Story 3.5) handles this case at execution time
  - [ ] Wire into webhook handler: when a resolved alert arrives, look up its correlation group → get RCE → attempt cancellation
  - [ ] Only cancel if ALL alerts in the RCE are resolved (not just one of many)

- [ ] Task 6: TTL verification (AC: #5)
  - [ ] Implement `check_ttl_expired_items(db) -> list[UUID]`
  - [ ] Query: find queue items where `status = 'queued' AND ttl_expires_at <= NOW()`
  - [ ] For each expired item: verify alert still active by checking `alerts` table status (MVP approach — AlertManager API check is a future enhancement)
  - [ ] If alert is no longer firing: cancel the queue item and transition incident to `cancelled`
  - [ ] If alert is still firing: extend TTL by another TTL period (alert is genuinely stuck, keep in queue)
  - [ ] Run TTL check as part of the periodic dispatcher sweep

- [ ] Task 7: Pipeline completion tracking (AC: #4)
  - [ ] Implement `mark_pipeline_complete(queue_item_id: UUID, db)`
  - [ ] Update `priority_queue` row: `status = 'completed'`, `completed_at = NOW()`
  - [ ] Update `active_pipelines` row: `completed_at = NOW()`
  - [ ] This is called by the pipeline (Epic 2) when a diagnosis pipeline finishes (success or failure)
  - [ ] Expose as an interface that the LangGraph pipeline can call at terminal states

- [ ] Task 8: Dispatcher loop (AC: #1, #4, #6)
  - [ ] Create `backend/src/pipeline/dispatcher.py` — periodic dispatch loop
  - [ ] Implement `run_dispatcher()` — async loop that:
    1. Checks parallelism cap
    2. If capacity available: calls `dequeue_next()`
    3. If item dequeued: transitions incident state `queued → diagnosing` via state machine
    4. Hands off to pipeline (stub: logs "dispatched to diagnosis pipeline" — actual LangGraph integration is Story 2.1)
  - [ ] Dispatcher runs as FastAPI lifespan background task (async loop with configurable poll interval)
  - [ ] Poll interval configurable (default: 5 seconds)
  - [ ] On pod startup: check for items stuck in `processing` (stale from crash) — reset to `queued` if exceeded max processing time

- [ ] Task 9: Integration with correlator sealing (AC: #7)
  - [ ] Modify `backend/src/pipeline/correlator.py` — after sealing an RCE, call `enqueue_rce()`
  - [ ] The seal function already transitions state to `queued` — enqueue happens immediately after
  - [ ] Pass severity (from RCE's highest-severity alert) and sealed_at timestamp to the scoring function

- [ ] Task 10: Integration with webhook handler for cancellation (AC: #3)
  - [ ] Modify `backend/src/api/webhooks.py` — on resolved alert receipt:
    1. Find the correlation group containing this alert's fingerprint
    2. Check if ALL alerts in that group are now resolved
    3. If yes: call `cancel_queued_rce(rce_id)` to attempt queue cancellation
  - [ ] This extends the existing BackgroundTasks chain (after resolved alert recording)

- [ ] Task 11: Configuration (AC: #4, #5)
  - [ ] Add queue settings to `backend/src/config/` settings module:
    - `queue.parallelism_cap`: int (default: 3)
    - `queue.ttl_seconds`: int (default: 3600 — 1 hour)
    - `queue.poll_interval_seconds`: int (default: 5)
    - `queue.stale_processing_timeout_seconds`: int (default: 900 — 15 minutes)
    - `queue.priority_weights.critical`: int (default: 100)
    - `queue.priority_weights.warning`: int (default: 50)
    - `queue.priority_weights.info`: int (default: 10)
  - [ ] Add to Helm `values.yaml`:
    ```yaml
    queue:
      parallelismCap: 3
      ttlSeconds: 3600
      pollIntervalSeconds: 5
      staleProcessingTimeoutSeconds: 900
      priorityWeights:
        critical: 100
        warning: 50
        info: 10
    ```

- [ ] Task 12: Tests — unit (AC: #1, #2, #3, #4, #5)
  - [ ] `tests/pipeline/test_priority_queue.py` — priority scoring: critical > warning > info
  - [ ] `tests/pipeline/test_priority_queue.py` — recency: newer events score higher than older ones at same severity
  - [ ] `tests/pipeline/test_priority_queue.py` — combined: critical+old vs warning+new ordering is correct
  - [ ] `tests/pipeline/test_priority_queue.py` — parallelism cap: dequeue returns None when at capacity
  - [ ] `tests/pipeline/test_priority_queue.py` — TTL expiry: items past TTL are identified
  - [ ] `tests/pipeline/test_priority_queue.py` — cancel: only cancels if status is queued, not processing

- [ ] Task 13: Tests — integration (AC: #1, #2, #3, #4, #6, #7)
  - [ ] `tests/pipeline/test_priority_queue_integration.py` (db-marked) — full enqueue/dequeue cycle with real PostgreSQL
  - [ ] Verify priority ordering: enqueue 3 items (critical, warning, info) → dequeue order is critical first
  - [ ] Verify SKIP LOCKED: simulate concurrent dequeue (two transactions) → each gets a different item
  - [ ] Verify cancellation: enqueue → cancel → dequeue returns None for that item
  - [ ] Verify parallelism cap: enqueue 5 items, set cap=2 → only 2 dequeued, third returns None
  - [ ] Verify crash recovery: enqueue → kill connection → new connection sees items still queued
  - [ ] Verify stale processing recovery: item stuck in `processing` past timeout → reset to `queued` on startup
  - [ ] Verify state transition: dequeue triggers `queued → diagnosing` transition
  - [ ] Verify resolved-webhook full flow: enqueue RCE → resolve all alerts → RCE cancelled

## Dev Notes

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-23 | Priority queue via `SELECT FOR UPDATE SKIP LOCKED` | This IS the queue implementation. Row-level locking for dequeue. Resolved-webhook cancellation via `UPDATE WHERE status = 'queued'`. No in-memory queue, no advisory locks |
| AD-19 | Canonical state machine | Transitions: `queued → diagnosing` on dequeue (normal path), `queued → diagnosed` for fast-path (Story 4.3), `queued → cancelled` on resolved-webhook. ALL via state machine function |
| AD-3 | Application schema | `priority_queue` and `active_pipelines` tables are application schema. NOT `langgraph_*` tables |
| AD-16 | Freshness gate at execution | If a resolved webhook arrives AFTER dequeue (item is `processing`), cancellation does NOT happen. The freshness gate catches stale remediations at execution time (Story 3.5). Preserve diagnostic work for the Learning Store |
| AD-18 | Global remediation lock | The priority queue's parallelism cap limits concurrent DIAGNOSIS pipelines. The global remediation lock (Story 3.5) limits concurrent EXECUTION. These are separate mechanisms at different pipeline stages |
| NFR-2 | Queue persists to PostgreSQL | ALL queue state in PostgreSQL. Pod crash → restart → resume. No in-memory data structures |
| NFR-3 | Handle 100 simultaneous alerts | The queue handles storm traffic by ordering, not rejecting. Parallelism cap prevents resource exhaustion during storms |
| AD-1 | Staged pipeline paradigm | The queue is the buffer between triage (correlation/sealing) and diagnosis (LangGraph pipeline). It decouples these stages |

### Priority Queue Design

The queue uses PostgreSQL as a durable, concurrent work queue. No external message broker needed (the system already has PostgreSQL, and throughput requirements are well within PostgreSQL's capabilities for this pattern).

```
Flow:
  Correlator seals RCE → enqueue(priority_score) → [queue in PostgreSQL]
  Dispatcher polls → dequeue(SKIP LOCKED) → dispatch to diagnosis pipeline
  Resolved webhook → cancel(UPDATE WHERE queued) → incident cancelled
```

### Priority Scoring Formula

```python
def calculate_priority_score(severity: str, sealed_at: datetime) -> float:
    """Higher score = dequeued first.
    
    Combines severity weight with recency. Critical alerts always outrank
    warning/info unless extremely old. Recency decays over hours so a 
    1-hour-old critical still beats a just-arrived info.
    """
    SEVERITY_WEIGHTS = {
        "critical": 100,
        "warning": 50,
        "info": 10,
    }
    weight = SEVERITY_WEIGHTS.get(severity, 50)
    age_seconds = (datetime.now(timezone.utc) - sealed_at).total_seconds()
    recency = 1.0 / (1.0 + age_seconds / 3600)
    return weight * recency
```

This ensures:
- Critical alerts are always dequeued before warning/info (100 × recency ≫ 50 × recency)
- Among same-severity items, most recent wins (higher recency factor)
- A critical alert ages out gradually but still beats warning for ~2 hours

### Dequeue SQL Pattern (CRITICAL)

```sql
-- Atomic claim: UPDATE + subquery in one statement
-- No race condition possible — SKIP LOCKED ensures disjoint claims
UPDATE priority_queue
SET status = 'processing', dequeued_at = NOW()
WHERE id = (
    SELECT id FROM priority_queue
    WHERE status = 'queued'
    ORDER BY priority_score DESC, enqueued_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING *;
```

Key performance requirements:
- **Partial index** on `(priority_score DESC, enqueued_at ASC) WHERE status = 'queued'` keeps the hot path fast regardless of total table size
- The index only contains pending items — completed/cancelled items exit the index automatically
- Under NFR-3's 100-alert storm scenario, the queue accumulates items gracefully; the parallelism cap controls dispatch rate

### Resolved-Webhook Cancellation

When a `resolved` webhook arrives:
1. Webhook handler records the resolved alert (Story 1.1 logic)
2. Background task looks up the alert's correlation group
3. Checks if ALL alerts in the group are now resolved
4. If yes: attempts `UPDATE priority_queue SET status = 'cancelled' WHERE root_cause_event_id = $1 AND status = 'queued'`

**Critical edge case:** If the item is already `processing` (dequeued but diagnosis not yet complete):
- The `WHERE status = 'queued'` clause means the UPDATE affects zero rows
- The item continues through the pipeline
- The freshness gate (AD-16, Story 3.5) catches it at execution time
- Diagnostic work is preserved for the Learning Store (not wasted)

This is intentional per AD-16: "A resolved webhook arriving during an in-flight pipeline does NOT cancel the pipeline."

### Parallelism Cap Implementation

```python
async def check_capacity(db) -> bool:
    """Returns True if there is capacity to start another pipeline."""
    count = await db.fetchval(
        "SELECT COUNT(*) FROM active_pipelines WHERE completed_at IS NULL"
    )
    return count < settings.queue.parallelism_cap
```

The parallelism cap:
- Prevents resource exhaustion during alert storms
- Limits concurrent LLM calls (cost control)
- Is configurable per-deployment via Helm values
- Does NOT reject alerts — they stay queued and are processed as capacity frees up

### Stale Processing Recovery (Pod Crash)

On pod startup, the dispatcher checks for items stuck in `processing`:

```python
async def recover_stale_items(db):
    """Reset items stuck in 'processing' from a previous pod lifecycle."""
    timeout = settings.queue.stale_processing_timeout_seconds
    await db.execute("""
        UPDATE priority_queue 
        SET status = 'queued', dequeued_at = NULL
        WHERE status = 'processing'
          AND dequeued_at < NOW() - INTERVAL '$1 seconds'
    """, timeout)
    # Also clean up orphaned active_pipelines entries
    await db.execute("""
        DELETE FROM active_pipelines
        WHERE completed_at IS NULL
          AND started_at < NOW() - INTERVAL '$1 seconds'
    """, timeout)
```

This handles the case where a pod crashes mid-diagnosis. The item returns to the queue and will be re-dispatched. LangGraph checkpoints (Epic 2) handle resuming the actual diagnosis work.

### TTL Verification (MVP Approach)

For MVP, TTL verification checks the `alerts` table directly rather than calling the AlertManager API:

```python
async def check_alert_still_firing(incident_id: UUID, db) -> bool:
    """Check if at least one alert in the incident is still firing."""
    return await db.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM alerts 
            WHERE incident_id = $1 AND status = 'firing'
        )
    """, incident_id)
```

Future enhancement: query AlertManager's `/api/v1/alerts` endpoint for real-time status. For MVP, the resolved webhook mechanism is the primary cancellation path; TTL is a safety net for cases where resolved webhooks were missed.

### State Machine Transitions in This Story

```python
# On dequeue (dispatcher hands to pipeline):
transition(incident, "queued", "diagnosing")

# On resolved-webhook cancellation:
transition(incident, "queued", "cancelled")

# Fast-path shortcut (Story 4.3 — not implemented here, but queue must support it):
# transition(incident, "queued", "diagnosed")
```

Valid transitions from `queued` (defined in Story 1.0):
```python
"queued": ["diagnosing", "diagnosed", "cancelled"]
```

### Dispatcher Background Loop

```python
async def dispatcher_loop():
    """Background task: polls queue and dispatches to diagnosis pipeline.
    
    Runs as a FastAPI lifespan task — starts on app startup, stops on shutdown.
    """
    while True:
        try:
            if await check_capacity(db):
                item = await dequeue_next(db)
                if item:
                    await transition(item.incident_id, "queued", "diagnosing")
                    await dispatch_to_pipeline(item)  # Stub until Story 2.1
        except Exception as e:
            logger.error("Dispatcher error", exc_info=e, component="pipeline")
        await asyncio.sleep(settings.queue.poll_interval_seconds)
```

The dispatcher:
- Runs indefinitely as a background task in the FastAPI lifespan
- Polls on a configurable interval (default 5s) — NOT event-driven
- Checks capacity before attempting dequeue (avoids unnecessary locking)
- Handles errors gracefully without crashing the loop
- On dispatch: calls a stub function that logs the dispatch (actual LangGraph integration is Story 2.1)

### Pipeline Dispatch Stub

Story 2.1 (LangGraph Diagnosis Pipeline) will implement the actual pipeline invocation. For this story, `dispatch_to_pipeline` is a stub:

```python
async def dispatch_to_pipeline(item: QueueItem):
    """Dispatch a dequeued RCE to the diagnosis pipeline.
    
    STUB: Logs dispatch. Real implementation in Story 2.1.
    """
    logger.info(
        "Dispatched RCE to diagnosis pipeline",
        component="pipeline",
        incident_id=str(item.incident_id),
        root_cause_event_id=str(item.root_cause_event_id),
        priority_score=item.priority_score,
    )
```

Story 2.1 will replace this stub with LangGraph graph invocation.

### Database Interaction Pattern

Reuse the async DB layer from Story 1.0:
- All new tables in application schema (NOT `langgraph_*`)
- Use asyncpg for async queries
- Dequeue uses transactions — the `UPDATE ... RETURNING` pattern is atomic
- Partial index is essential for performance under load

### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/pipeline/priority_queue.py` | Priority scoring, enqueue/cancel logic | NEW |
| `backend/src/pipeline/dispatcher.py` | Background dispatch loop | NEW |
| `backend/src/db/queue.py` | DB operations for priority queue (SQL queries) | NEW |
| `backend/tests/pipeline/test_priority_queue.py` | Unit tests for priority scoring and queue logic | NEW |
| `backend/tests/pipeline/test_priority_queue_integration.py` | Integration tests with real PostgreSQL | NEW |

### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/pipeline/correlator.py` | After sealing RCE, call `enqueue_rce()` | UPDATE |
| `backend/src/api/webhooks.py` | Add resolved-webhook → queue cancellation logic | UPDATE |
| `backend/src/api/app.py` | Register dispatcher as lifespan background task | UPDATE |
| `backend/src/models/__init__.py` | Export QueueItem model if created as Pydantic | UPDATE |
| `charts/openshift-ai-ops/values.yaml` | Add queue configuration section | UPDATE |
| `backend/src/config/` settings | Add queue config dataclass/settings | UPDATE |

### Dependency Direction (ENFORCED)

- `pipeline/priority_queue.py` — depends on `config/` (settings), `db/queue` (persistence), `models/` (state machine)
- `pipeline/dispatcher.py` — depends on `pipeline/priority_queue` (dequeue), `models/` (state transitions), `config/` (poll interval)
- `db/queue.py` — depends on `models/` (QueueItem type if defined there)
- `api/webhooks.py` — depends on `pipeline/priority_queue` (cancel function), `db/correlation` (group lookup)
- `pipeline/correlator.py` — depends on `pipeline/priority_queue` (enqueue function)

### Technology Stack (Relevant to This Story)

| Package | Version | Usage in This Story |
|---------|---------|---------------------|
| FastAPI | ~=0.141.1 | Lifespan background task for dispatcher loop |
| Pydantic | ~=2.x | QueueItem model (if needed) |
| asyncpg | latest | Async DB queries with `FOR UPDATE SKIP LOCKED` |
| pytest | latest (dev) | Test runner with `unit`, `pipeline`, `db` markers |
| testcontainers | latest (dev) | PostgreSQL fixture for integration tests |

### Anti-Patterns to Avoid

- **Do NOT use in-memory queues** — all state must be in PostgreSQL (NFR-2). No `asyncio.Queue`, no `collections.deque`, no Python-level data structures for queue state
- **Do NOT use advisory locks** — use row-level locks (`FOR UPDATE SKIP LOCKED`) per AD-23
- **Do NOT cancel in-flight pipelines** — if an item is already `processing`, the resolved webhook does nothing to it. The freshness gate (AD-16) handles stale remediations at execution time
- **Do NOT implement the diagnosis pipeline** — that's Story 2.1. This story dispatches with a stub function
- **Do NOT implement the fast-path check** — that's Story 4.3. The queue supports the `queued → diagnosed` transition but doesn't implement the matching logic
- **Do NOT implement the global remediation lock** — that's Story 3.5 (AD-18). The parallelism cap here limits DIAGNOSIS concurrency, not execution concurrency
- **Do NOT emit SSE events** — that's Story 1.4. The dispatcher just logs dispatch
- **Do NOT skip the state machine function** — `queued → diagnosing` and `queued → cancelled` must go through `transition()`
- **Do NOT hardcode configuration** — parallelism cap, TTL, poll interval, and priority weights must come from configuration (Helm-configurable)
- **Do NOT poll more frequently than necessary** — 5s default is fine. Sub-second polling creates unnecessary DB load. Event-driven dispatch (triggered by enqueue) is a future optimization if needed
- **Do NOT create a separate worker process** — the dispatcher runs in the same FastAPI process (AD-9)

### Testing Strategy

**Unit tests** (`pytest -m unit`):
- Priority scoring: critical(100) > warning(50) > info(10) with same recency
- Priority scoring: newer events beat older events at same severity
- Priority scoring: critical + 30min old still beats warning + brand new
- Parallelism cap logic: returns False when at capacity, True when below
- TTL expiry identification: items past TTL detected correctly
- Cancellation logic: only affects `queued` status items

**Integration tests** (`pytest -m db`):
- Full enqueue → dequeue cycle: item returned with correct fields
- Priority ordering: 3 items at different severities dequeued in correct order
- SKIP LOCKED concurrency: two concurrent transactions each get different items
- Cancellation: queued item cancellable, processing item NOT cancellable
- Parallelism cap: cap=2, enqueue 5 → only 2 dequeued, third returns None
- Pod crash recovery: stale `processing` items reset to `queued` on startup
- State machine transitions verified: `queued → diagnosing`, `queued → cancelled`
- Full resolved-webhook flow: enqueue → resolve all alerts → RCE cancelled

### Previous Story Intelligence

From Story 1.2 (direct dependency):
- Correlator seals RCEs and transitions incidents to `queued` state
- After sealing, this story's `enqueue_rce()` is called to add to the priority queue
- RCE contains severity (from highest-severity alert), sealed_at timestamp, and correlation evidence
- Correlation groups are in `correlation_groups` table with `alert_group_members` join table
- The correlator's `seal_expired_groups()` function is where enqueue integration hooks in

From Story 1.1:
- Webhook handler uses `BackgroundTasks` pattern — resolved-webhook cancellation integrates here
- Resolved alerts are recorded via `record_resolved_alert(fingerprint, resolved_at)` 
- The resolved alert lookup path: fingerprint → alert row → incident → correlation group → RCE → queue item
- All webhook processing runs in background tasks after HTTP 200 response

From Story 1.0:
- State machine in `models/state_machine.py` — `queued → diagnosing`, `queued → diagnosed`, `queued → cancelled` are valid transitions
- Test infrastructure with testcontainers is in `conftest.py`
- Structured JSON logging configured — use component `pipeline` for dispatcher/queue logs
- FastAPI lifespan hook available for background tasks (standard FastAPI pattern)
- Alembic migrations in `backend/alembic/versions/`

### Configuration Structure

```yaml
# charts/openshift-ai-ops/values.yaml (additions)
queue:
  parallelismCap: 3
  ttlSeconds: 3600
  pollIntervalSeconds: 5
  staleProcessingTimeoutSeconds: 900
  priorityWeights:
    critical: 100
    warning: 50
    info: 10
```

These map to environment variables → `backend/src/config/` settings (same pattern as correlation config from Story 1.2).

### Project Structure Notes

- Priority queue logic lives in `pipeline/` per AD-14 and the Capability→Architecture Map (FR-3 → `pipeline/` + `db/`)
- DB operations in `db/queue.py` per the established pattern from `db/incidents.py` (Story 1.1) and `db/correlation.py` (Story 1.2)
- Dispatcher is `pipeline/dispatcher.py` — the dispatch loop is a pipeline concern, not API
- The dispatcher is registered as a lifespan background task in `api/app.py` (the app startup hook)
- Tests mirror source: `tests/pipeline/` for queue and dispatcher tests

### References

- [Source: ARCHITECTURE-SPINE.md#AD-23] — Priority queue via `SELECT FOR UPDATE SKIP LOCKED`, resolved-webhook cancellation
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine (`queued → diagnosing | diagnosed | cancelled`)
- [Source: ARCHITECTURE-SPINE.md#AD-16] — Freshness gate at execution — resolved-webhook during in-flight pipeline does NOT cancel
- [Source: ARCHITECTURE-SPINE.md#AD-18] — Global remediation lock (separate from parallelism cap)
- [Source: ARCHITECTURE-SPINE.md#AD-3] — Application schema (queue tables are NOT `langgraph_*`)
- [Source: ARCHITECTURE-SPINE.md#AD-9] — Single Python process (dispatcher runs in-process)
- [Source: ARCHITECTURE-SPINE.md#AD-1] — Staged pipeline (queue is buffer between triage and diagnosis stages)
- [Source: project-context.md#Critical Don't-Miss Rules] — Never use in-memory queues, never write state directly
- [Source: project-context.md#Testing Rules] — pytest markers, testcontainers, mock patterns
- [Source: epics.md#Story 1.3] — Story requirements and acceptance criteria
- [Source: epics.md#FR-3] — Priority queue ordering, TTL, parallelism cap
- [Source: epics.md#NFR-2] — Queue persistence to PostgreSQL (not in-memory)
- [Source: epics.md#NFR-3] — Handle 100 simultaneous alerts, configurable parallelism cap
- [Source: 1-2-alert-deduplication-and-storm-correlation.md] — Correlator sealing produces RCEs for this queue
- [Source: 1-1-receive-and-acknowledge-alertmanager-webhooks.md] — Resolved alert recording, BackgroundTasks pattern
- [Source: 1-0-project-scaffolding-and-shared-contracts.md] — State machine, DB schema, test infrastructure, lifespan hooks

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
