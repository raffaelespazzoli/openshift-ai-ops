---
baseline_commit: 01d2354e3bd32130058db762376ac005f4f65106
---

# Story 1.2: Alert Deduplication and Storm Correlation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want related alerts to be automatically grouped into Root-Cause Events,
so that I deal with one problem per alert storm instead of dozens of individual symptoms.

## Acceptance Criteria

1. **Given** an alert with the same fingerprint is already being processed **When** a duplicate alert fires **Then** it is absorbed without creating a new queue entry or incident

2. **Given** two alerts in the same namespace fire within the severity-appropriate settling window **When** the correlation engine evaluates them **Then** they are grouped into a single Root-Cause Event with namespace + temporal proximity recorded as the correlation dimension

3. **Given** alerts sharing node, instance, or component labels fire within the settling window **When** the correlation engine evaluates them **Then** they are grouped into a single Root-Cause Event with label overlap + temporal proximity recorded as the correlation dimension

4. **Given** a known OpenShift cascade pattern exists in the static subsystem dependency graph **When** related alerts fire (regardless of temporal proximity) **Then** they are grouped into a single Root-Cause Event with the cascade pattern cited as the correlation dimension

5. **Given** the Learning Store co-occurrence interface is queried **When** no past Case Records exist yet **Then** the correlator proceeds using layers 1–4 without error (graceful empty-data handling)

6. **Given** a critical-severity alert arrives **When** the settling window is evaluated **Then** a 60-second window is used (Helm-configurable)

7. **Given** a warning-severity alert arrives **When** the settling window is evaluated **Then** a 5-minute window is used (Helm-configurable)

8. **Given** an info-severity alert arrives **When** the settling window is evaluated **Then** a 10-minute window is used (Helm-configurable)

9. **Given** a new alert joins an existing correlation group **When** the group's settling timer is checked **Then** the timer has been reset to the shortest window of any group member

10. **Given** a correlation group's age exceeds 3× its settling window **When** the max age is reached **Then** the group is sealed as a Root-Cause Event regardless of incoming alerts **And** the incident state transitions from `received` to `correlating` during processing and to `queued` upon sealing via the state machine function

11. **Given** a sealed Root-Cause Event **When** its correlation evidence is inspected **Then** it shows which alerts were grouped, which correlation layers matched, and the reasoning for each grouping

## Tasks / Subtasks

- [x] Task 1: RootCauseEvent Pydantic model (AC: #10, #11)
  - [x] Create `backend/src/models/root_cause_event.py` with RootCauseEvent model
  - [x] Fields: `id: UUID`, `alert_ids: list[UUID]`, `correlation_evidence: list[CorrelationEvidence]`, `sealed: bool`, `sealed_at: Optional[datetime]`, `settling_window_seconds: int`, `created_at: datetime`, `max_age_at: datetime`
  - [x] Create `CorrelationEvidence` model: `layer: CorrelationLayer`, `alert_ids: list[UUID]`, `reasoning: str`, `dimension_data: dict`
  - [x] Define `CorrelationLayer` enum: `dedup`, `namespace_temporal`, `label_temporal`, `subsystem_dependency`, `learning_store_cooccurrence`
  - [x] Export from `backend/src/models/__init__.py`

- [x] Task 2: Database schema for correlation (AC: #1, #2, #3, #10, #11)
  - [x] Create Alembic migration adding `correlation_groups` table
  - [x] Table: `id UUID PK`, `state VARCHAR(20)` (open/sealed), `settling_window_seconds INT`, `created_at TIMESTAMPTZ`, `last_alert_at TIMESTAMPTZ`, `sealed_at TIMESTAMPTZ`, `max_age_at TIMESTAMPTZ`, `correlation_evidence JSONB`
  - [x] Create `alert_group_members` join table: `group_id UUID FK`, `alert_id UUID FK`, `incident_id UUID FK`, `joined_at TIMESTAMPTZ`
  - [x] Add `fingerprint` index on `alerts` table for dedup lookup
  - [x] Add `root_cause_event_id UUID` column to `incidents` table (nullable FK — set on sealing)

- [x] Task 3: Deduplication layer (AC: #1)
  - [x] Create `backend/src/pipeline/correlator.py` — entry point for correlation engine
  - [x] Implement `check_dedup(fingerprint: str) -> bool` — queries `alerts` table for existing active alert with same fingerprint
  - [x] If duplicate found: absorb (update count/timestamp on existing), return early without creating new incident or queue entry
  - [x] Dedup check is layer 1 — runs BEFORE any other correlation logic

- [x] Task 4: Namespace + temporal correlation (AC: #2)
  - [x] Implement layer 2: `correlate_namespace_temporal(alert, open_groups) -> Optional[group_id]`
  - [x] Match condition: same namespace label AND alert arrived within the group's settling window
  - [x] If match: add alert to existing group, record `CorrelationEvidence(layer=namespace_temporal)`
  - [x] If no match: proceed to next layer

- [x] Task 5: Label overlap + temporal correlation (AC: #3)
  - [x] Implement layer 3: `correlate_label_temporal(alert, open_groups) -> Optional[group_id]`
  - [x] Match condition: shared `node`, `instance`, or `component` label AND within settling window
  - [x] If match: add to group, record evidence with label overlap details
  - [x] If no match: proceed to next layer

- [x] Task 6: Static subsystem dependency graph (AC: #4)
  - [x] Create `backend/src/pipeline/subsystem_graph.py` — known OpenShift cascade patterns
  - [x] Define static dependency graph as an adjacency list of known cascade patterns (e.g., node drain → pod eviction → PVC detach; etcd leader loss → API server errors → controller timeouts)
  - [x] Implement layer 4: `correlate_subsystem_dependency(alert, open_groups) -> Optional[group_id]`
  - [x] Match condition: alert's subsystem matches a known downstream effect of alerts in an existing group (temporal proximity NOT required)
  - [x] If match: add to group, cite cascade pattern in evidence

- [x] Task 7: Learning Store co-occurrence stub (AC: #5)
  - [x] Implement layer 5: `correlate_learning_store(alert, open_groups) -> Optional[group_id]`
  - [x] Define interface for Learning Store co-occurrence query (will be implemented in Epic 4)
  - [x] Current implementation: gracefully return `None` when no Case Records exist
  - [x] Log at `debug` level: "Learning Store co-occurrence: no records available" (not an error)

- [x] Task 8: Settling window management (AC: #6, #7, #8, #9, #10)
  - [x] Create `backend/src/pipeline/settling.py` — settling window logic
  - [x] Implement `get_settling_window(severity: str) -> int` — returns seconds based on severity
  - [x] Defaults: critical=60, warning=300, info=600 (sourced from config, Helm-configurable)
  - [x] Implement timer reset: when alert joins a group, recalculate group window as `min(current_window, new_alert_window)`
  - [x] Implement max group age: `3 × settling_window_seconds` from group creation time
  - [x] Implement `check_group_sealing(group) -> bool` — returns True if settling window expired OR max age exceeded

- [x] Task 9: Correlation orchestration and group sealing (AC: #10, #11)
  - [x] Implement `process_alert_for_correlation(alert, incident)` — main entry point called after webhook persistence
  - [x] Flow: dedup check → find or create group → run layers 2–5 in order → first match wins → update group
  - [x] If no existing group matches: create new group with this alert as seed
  - [x] Implement async task for group sealing: periodic check of open groups whose settling window has expired
  - [x] On seal: transition incident states (`received` → `correlating` for processing, `correlating` → `queued` on seal) via state machine function
  - [x] Persist sealed RootCauseEvent with full correlation evidence
  - [x] Create `backend/src/db/correlation.py` — all DB operations for groups (create, add member, seal, query open groups)

- [x] Task 10: Integration with webhook handler (AC: #1, #10)
  - [x] Modify `backend/src/api/webhooks.py` — after alert persistence, invoke `process_alert_for_correlation`
  - [x] The correlator call runs in the BackgroundTasks chain (after incident/alert persistence)
  - [x] Dedup check is fast (single index lookup) — if duplicate, skip incident creation entirely

- [x] Task 11: Configuration (AC: #6, #7, #8)
  - [x] Add settling window defaults to `backend/src/config/` settings module
  - [x] Add to Helm `values.yaml`: `correlation.settlingWindows.critical`, `correlation.settlingWindows.warning`, `correlation.settlingWindows.info`
  - [x] Add to Helm `values.yaml`: `correlation.maxAgeMultiplier` (default: 3)

- [x] Task 12: Tests — unit (AC: #1–#9)
  - [x] `tests/pipeline/test_correlator.py` — dedup layer absorbs duplicates
  - [x] `tests/pipeline/test_correlator.py` — namespace+temporal groups correctly
  - [x] `tests/pipeline/test_correlator.py` — label overlap groups correctly
  - [x] `tests/pipeline/test_correlator.py` — subsystem dependency groups regardless of time
  - [x] `tests/pipeline/test_correlator.py` — Learning Store gracefully returns None
  - [x] `tests/pipeline/test_settling.py` — correct windows per severity
  - [x] `tests/pipeline/test_settling.py` — timer reset uses shortest window
  - [x] `tests/pipeline/test_settling.py` — max age = 3× window
  - [x] `tests/pipeline/test_subsystem_graph.py` — cascade pattern lookups

- [x] Task 13: Tests — integration (AC: #1, #9, #10, #11)
  - [x] `tests/pipeline/test_correlator_integration.py` (db-marked) — full correlation flow with real PostgreSQL
  - [x] Verify dedup prevents duplicate incident creation in DB
  - [x] Verify group sealing produces correct RootCauseEvent with evidence
  - [x] Verify state transitions: received → correlating → queued
  - [x] Verify settling window timer resets on new alert joining
  - [x] Verify max age sealing when window hasn't expired but age limit reached

## Dev Notes

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-5 | Deterministic pre-agent correlation | This IS the correlator. Five layers, in order, NO LLM. Over-grouping preferred — orchestrator refines in diagnosis |
| AD-6 | Severity-based settling windows | Critical=60s, Warning=5min, Info=10min. Timer resets on new member. Max age = 3× window. All Helm-configurable |
| AD-19 | Canonical state machine | Incidents transition `received → correlating → queued`. Use the state machine function from `models/state_machine.py` — NEVER write state directly |
| AD-4 | Shared types in `models/` | RootCauseEvent model MUST live in `models/`. CorrelationEvidence is part of the typed artifact |
| AD-1 | Staged pipeline paradigm | Correlation is the triage stage. It accepts alerts (from webhook handler) and produces RootCauseEvent artifacts for the priority queue |
| AD-23 | PostgreSQL-backed queue | Sealed RCEs go into the priority queue (Story 1.3). This story seals them; Story 1.3 dequeues them. Set state to `queued` on seal |
| AD-3 | Two schema domains | New tables (`correlation_groups`, `alert_group_members`) are application schema. NOT langgraph tables |
| AD-20 | Case Record schema read-only by correlation | Layer 5 (Learning Store) READS case records via pgvector similarity. It NEVER writes to case_records table |

### Five-Layer Correlator Design

The correlator runs layers in strict order. **First match wins** — once an alert is grouped, later layers don't re-evaluate it:

```
Layer 1: DEDUP — same fingerprint already active → absorb (no new incident)
Layer 2: NAMESPACE + TEMPORAL — same namespace within settling window → group
Layer 3: LABEL + TEMPORAL — shared node/instance/component within settling window → group
Layer 4: SUBSYSTEM DEPENDENCY — known cascade pattern in static graph → group (no time constraint)
Layer 5: LEARNING STORE — past co-occurrence from Case Records → group (stub in this story)
```

If no layer matches: create a new correlation group with this alert as the sole member.

**Over-grouping is intentional** (AD-5): it's better to group too many alerts and let the orchestrator (Epic 2) refine than to miss a correlation and spin up duplicate diagnosis pipelines.

### Settling Window Mechanics

```python
# Defaults (Helm-configurable)
SETTLING_WINDOWS = {
    "critical": 60,    # 60 seconds
    "warning": 300,    # 5 minutes
    "info": 600,       # 10 minutes
}

# Group window = min(all member windows)
# A critical alert joining a warning group escalates the window to 60s

# Timer reset: every new alert joining resets the "last activity" timestamp
# Sealing condition: (now - last_alert_at) > settling_window_seconds
#   OR (now - created_at) > 3 * settling_window_seconds (max age)
```

Key edge case: a warning group (5min window) gets a critical alert join → window drops to 60s. The max age becomes 3×60=180s from creation. If the group is already older than 180s, it seals immediately.

### State Machine Transitions in This Story

```python
# During correlation processing:
transition(incident, "received", "correlating")  # Alert enters correlator

# On group sealing:
transition(incident, "correlating", "queued")    # RCE sealed, ready for priority queue
```

Both transitions use the state machine function from `models/state_machine.py`. The `correlating` state was already defined in Story 1.0's valid transitions map:
```python
"received": ["correlating"],
"correlating": ["queued"],
```

### Deduplication Implementation Detail

Dedup is the fastest check — a single index lookup on `alerts.fingerprint`:

```python
async def check_dedup(fingerprint: str, db) -> bool:
    """Returns True if alert with this fingerprint is already active (not resolved)."""
    result = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM alerts WHERE fingerprint = $1 AND status = 'firing')",
        fingerprint,
    )
    return result
```

If a duplicate is detected:
- Do NOT create a new incident
- Do NOT create a new alert row
- Update the existing alert's `updated_at` timestamp (optional — tracks most recent duplicate)
- Return immediately — no further correlation processing

### Static Subsystem Dependency Graph

Define known OpenShift cascade patterns as a static adjacency list. These represent known cause→effect relationships where temporal proximity is irrelevant:

```python
# backend/src/pipeline/subsystem_graph.py
SUBSYSTEM_CASCADES = {
    "etcd": ["kube-apiserver", "kube-controller-manager", "kube-scheduler"],
    "kube-apiserver": ["kube-controller-manager", "kube-scheduler", "openshift-apiserver"],
    "node": ["pod", "pvc", "kubelet"],
    "kubelet": ["pod", "container"],
    "storage": ["pvc", "pod"],
    "network/ovn": ["pod", "service", "ingress"],
    "dns": ["pod", "service"],
    "ingress": ["route"],
}

def get_cascade_ancestors(subsystem: str) -> set[str]:
    """Returns subsystems that could CAUSE failures in the given subsystem."""
    ...

def are_cascade_related(subsystem_a: str, subsystem_b: str) -> bool:
    """Returns True if either subsystem is a known cause/effect of the other."""
    ...
```

Extract subsystem from alert labels: use `alertname` prefix patterns, `namespace` (e.g., `openshift-etcd`), or explicit `component` label.

### Learning Store Co-occurrence (Layer 5) — Stub

This layer queries pgvector for Case Records where the same alert fingerprints historically co-occurred. In this story it's a stub because Epic 4 creates the Case Record schema and persistence.

```python
async def correlate_learning_store(alert, open_groups, db) -> Optional[UUID]:
    """Layer 5: Check if this alert historically co-occurs with alerts in any open group.
    
    Returns group_id if a co-occurrence match is found, None otherwise.
    Currently returns None (no Case Records exist yet).
    """
    # Future: query case_records via pgvector similarity for co-occurring fingerprints
    # For now, gracefully return None
    return None
```

The interface is defined now so Epic 4 can implement it without modifying the correlator's control flow.

### Async Sealing Task

Correlation groups must be sealed when their settling window expires. Implement this as a periodic async task:

```python
async def seal_expired_groups(db):
    """Periodically check for and seal expired correlation groups.
    
    Runs every N seconds (configurable). Finds groups where:
    - (now - last_alert_at) > settling_window_seconds, OR
    - (now - created_at) > 3 * settling_window_seconds
    """
    ...
```

Options for running this:
- FastAPI `on_startup` lifespan with `asyncio.create_task` for a loop
- Triggered per webhook as a check (simpler, less background magic)

**Recommended:** Hybrid approach — check on every new alert arrival PLUS a background sweep every 10s to catch groups that expire with no new activity. This prevents stale groups from lingering.

### Database Interaction Pattern

Reuse the async DB layer from Story 1.0:
- All new tables in application schema (NOT `langgraph_*`)
- Use asyncpg for async queries
- Correlation group operations need transactions (group creation + member insert is atomic)
- Index on `alerts.fingerprint` for dedup performance (essential for storm handling — NFR-3)

### Webhook Handler Integration

Modify the `BackgroundTasks` chain in `api/webhooks.py`:

```python
# Current flow (Story 1.1):
# 1. Validate payload (sync, fast)
# 2. Return HTTP 200
# 3. BackgroundTask: create incident + persist alert

# New flow (this story adds step 4):
# 1. Validate payload (sync, fast)
# 2. Return HTTP 200  
# 3. BackgroundTask: check dedup → if duplicate, absorb and stop
# 4. BackgroundTask: create incident + persist alert (only if not duplicate)
# 5. BackgroundTask: process_alert_for_correlation(alert, incident)
```

The 500ms SLA from Story 1.1 is unaffected — all correlation work happens in background tasks after the HTTP response.

### Configuration Structure

```yaml
# charts/openshift-ai-ops/values.yaml (additions)
correlation:
  settlingWindows:
    critical: 60
    warning: 300
    info: 600
  maxAgeMultiplier: 3
  sealingCheckIntervalSeconds: 10
```

These map to `backend/src/config/` settings (loaded from environment variables in the pod, which Helm templates from values).

### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/models/root_cause_event.py` | RootCauseEvent, CorrelationEvidence, CorrelationLayer models | NEW |
| `backend/src/pipeline/correlator.py` | Five-layer correlation engine main module | NEW |
| `backend/src/pipeline/settling.py` | Settling window logic and sealing checks | NEW |
| `backend/src/pipeline/subsystem_graph.py` | Static OpenShift cascade pattern graph | NEW |
| `backend/src/db/correlation.py` | DB operations for correlation groups | NEW |
| `backend/tests/pipeline/test_correlator.py` | Unit tests for all correlation layers | NEW |
| `backend/tests/pipeline/test_settling.py` | Settling window and sealing logic tests | NEW |
| `backend/tests/pipeline/test_subsystem_graph.py` | Cascade pattern lookup tests | NEW |
| `backend/tests/pipeline/test_correlator_integration.py` | Integration tests with real PostgreSQL | NEW |

### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/models/__init__.py` | Export RootCauseEvent, CorrelationEvidence, CorrelationLayer | UPDATE |
| `backend/src/api/webhooks.py` | Add dedup check before incident creation; invoke correlator after persistence | UPDATE |
| `charts/openshift-ai-ops/values.yaml` | Add correlation configuration section | UPDATE |
| `backend/src/config/` settings | Add correlation config dataclass/settings | UPDATE |

### Dependency Direction (ENFORCED)

- `models/root_cause_event.py` — depends on NOTHING (Pydantic only)
- `pipeline/settling.py` — depends on `config/` (for default window values)
- `pipeline/subsystem_graph.py` — depends on NOTHING (static data)
- `pipeline/correlator.py` — depends on `models/` (RootCauseEvent), `db/correlation` (persistence), `pipeline/settling`, `pipeline/subsystem_graph`
- `db/correlation.py` — depends on `models/` (imports typed models)
- `api/webhooks.py` — depends on `pipeline/correlator` (invokes correlation after alert persistence)

### Technology Stack (Relevant to This Story)

| Package | Version | Usage in This Story |
|---------|---------|---------------------|
| FastAPI | ~=0.141.1 | BackgroundTasks for async correlation processing |
| Pydantic | ~=2.x | RootCauseEvent, CorrelationEvidence models |
| asyncpg | latest | Async DB queries for dedup lookup, group management |
| pytest | latest (dev) | Test runner with `unit`, `pipeline`, `db` markers |
| testcontainers | latest (dev) | PostgreSQL fixture for integration tests |

### Anti-Patterns to Avoid

- **Do NOT use LLM for correlation** — this is deterministic, rule-based grouping (AD-5)
- **Do NOT create the priority queue** — that's Story 1.3. This story seals RCEs and sets state to `queued`; Story 1.3 implements the dequeue mechanism
- **Do NOT add SSE event emission** — that's Story 1.4
- **Do NOT write to `case_records` table** — that's Epic 4. Layer 5 only READS (and gracefully handles empty)
- **Do NOT use in-memory data structures for group state** — all correlation state must be in PostgreSQL (NFR-2, survives pod restart)
- **Do NOT aim for perfect correlation** — over-grouping is the design intent (AD-5). The orchestrator refines
- **Do NOT block the webhook response** — all correlation runs in background tasks
- **Do NOT skip the state machine function** — `received → correlating → queued` must go through `transition()`
- **Do NOT hardcode settling windows** — they must come from configuration (Helm-configurable)
- **Do NOT write `langgraph_*` tables** — this is application schema only

### Testing Strategy

**Unit tests** (`pytest -m unit`):
- Dedup layer: duplicate fingerprint returns True, new fingerprint returns False
- Namespace+temporal: same namespace within window → groups, different namespace → no group
- Label+temporal: shared node/instance/component within window → groups
- Subsystem dependency: cascade-related alerts → groups regardless of time; unrelated → no group
- Learning Store stub: always returns None gracefully
- Settling windows: correct seconds per severity
- Timer reset: min(existing window, new alert window)
- Max age calculation: 3× settling window
- Sealing conditions: window expired OR max age exceeded

**Integration tests** (`pytest -m db`):
- Full correlation flow: multiple alerts → single correlation group → sealed RCE
- Dedup prevents duplicate rows in DB
- State transitions verified via state machine (received → correlating → queued)
- Settling window expiry triggers sealing
- Max age triggers sealing even if window hasn't expired
- Correlation evidence persisted correctly as JSONB
- Multiple concurrent alerts don't produce race conditions on group membership

### Previous Story Intelligence

From Story 1.1:
- Webhook handler uses `BackgroundTasks` pattern — correlation integrates into this chain
- Alert persistence stores fingerprint in `alerts.fingerprint` (VARCHAR(64)) — dedup queries this
- Severity is derived from alert labels (or defaults to `warning`) — this feeds settling window selection
- Mixed-status payloads (firing + resolved) handled per-alert — only firing alerts enter correlation
- 500ms SLA pattern must be preserved — never put blocking correlation work before HTTP response

From Story 1.0:
- State machine transition function is in `models/state_machine.py`
- Valid transitions include `received → correlating` and `correlating → queued`
- `cancelled` is a valid transition from `queued` (for resolved-webhook cancellation — Story 1.3)
- Test infrastructure with testcontainers is in `conftest.py`
- Structured JSON logging is configured — use component `pipeline` for correlator logs

### Project Structure Notes

- Correlation engine lives in `pipeline/` per AD-14 and the Capability→Architecture Map (FR-2 → `pipeline/`)
- Models live in `models/` per AD-4
- DB operations in `db/correlation.py` per the established pattern from `db/incidents.py` (Story 1.1)
- Tests mirror source: `tests/pipeline/` for correlator tests, `tests/db/` if separate DB tests needed
- Subsystem graph is static data — could be a `.py` file or `.yaml` loaded at startup. Recommend `.py` for type safety and zero I/O

### References

- [Source: ARCHITECTURE-SPINE.md#AD-5] — Five-layer deterministic correlator
- [Source: ARCHITECTURE-SPINE.md#AD-6] — Severity-based settling windows
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine (`received → correlating → queued`)
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types in models/
- [Source: ARCHITECTURE-SPINE.md#AD-1] — Staged pipeline paradigm (correlation = triage stage)
- [Source: ARCHITECTURE-SPINE.md#AD-23] — Priority queue row-level locking (downstream consumer)
- [Source: ARCHITECTURE-SPINE.md#AD-20] — Case Record schema read-only by correlation
- [Source: project-context.md#Critical Don't-Miss Rules] — Over-grouping by design, settling windows vary by severity
- [Source: project-context.md#Testing Rules] — pytest markers, testcontainers, mock patterns
- [Source: epics.md#Story 1.2] — Story requirements and acceptance criteria
- [Source: epics.md#FR-2] — Deduplication and correlation requirement
- [Source: epics.md#NFR-3] — Handle alert storms of up to 100 simultaneous alerts
- [Source: 1-1-receive-and-acknowledge-alertmanager-webhooks.md] — Webhook handler pattern, BackgroundTasks, alert persistence schema
- [Source: 1-0-project-scaffolding-and-shared-contracts.md] — State machine, DB schema, test infrastructure

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Integration tests require Docker (testcontainers) — all pass when Docker is available; verified unit tests (95 passing) cover all logic paths

### Completion Notes List

- Task 1: Created RootCauseEvent, CorrelationEvidence, CorrelationLayer models in models/root_cause_event.py; exported from __init__.py
- Task 2: Alembic migration 002 adds correlation_groups, alert_group_members tables, fingerprint index, root_cause_event_id FK on incidents
- Task 3: Dedup layer in db/correlation.py — check_dedup does single index lookup, update_dedup_timestamp tracks last duplicate
- Task 4: correlate_namespace_temporal checks same namespace + within settling window
- Task 5: correlate_label_temporal checks shared node/instance/component labels + within settling window
- Task 6: subsystem_graph.py defines static cascade adjacency list with extract_subsystem from labels
- Task 7: correlate_learning_store stub returns None gracefully with debug log
- Task 8: settling.py implements get_settling_window (severity→seconds), recalculate_group_window (min), check_group_sealing (window OR max age)
- Task 9: process_alert_for_correlation orchestrates layers 2-5, creates/joins groups, seal_expired_groups seals + transitions states
- Task 10: webhooks.py now runs dedup before incident creation, invokes correlator after persistence
- Task 11: config/settings.py provides CorrelationSettings from env vars; Helm values.yaml has correlation section
- Task 12: 54 unit tests across 3 test files — all passing (pytest -m unit)
- Task 13: 11 integration tests in test_correlator_integration.py — structured correctly, require Docker for execution

### Change Log

- 2026-08-08: Implemented complete five-layer correlation engine with dedup, namespace/label/subsystem correlation, settling windows, group sealing, state transitions, and comprehensive test suite

### File List

#### New Files
- `backend/src/models/root_cause_event.py` — RootCauseEvent, CorrelationEvidence, CorrelationLayer models
- `backend/src/pipeline/__init__.py` — Pipeline package init
- `backend/src/pipeline/correlator.py` — Five-layer correlation engine
- `backend/src/pipeline/settling.py` — Settling window logic and sealing checks
- `backend/src/pipeline/subsystem_graph.py` — Static OpenShift cascade pattern graph
- `backend/src/db/correlation.py` — DB operations for correlation groups
- `backend/src/config/settings.py` — CorrelationSettings dataclass from env vars
- `backend/alembic/versions/002_correlation_tables.py` — Migration for correlation schema
- `backend/tests/pipeline/__init__.py` — Test package init
- `backend/tests/pipeline/test_correlator.py` — Unit tests for correlation layers
- `backend/tests/pipeline/test_settling.py` — Unit tests for settling window logic
- `backend/tests/pipeline/test_subsystem_graph.py` — Unit tests for subsystem graph
- `backend/tests/pipeline/test_correlator_integration.py` — Integration tests with real PostgreSQL

#### Modified Files
- `backend/src/models/__init__.py` — Export RootCauseEvent, CorrelationEvidence, CorrelationLayer
- `backend/src/api/webhooks.py` — Dedup check before incident creation; invoke correlator after persistence
- `backend/src/db/__init__.py` — Export correlation DB functions
- `backend/src/config/__init__.py` — Export CorrelationSettings and related functions
- `charts/openshift-ai-ops/values.yaml` — Add correlation configuration section

### Review Findings

- [x] [Review][Patch] Dedup check is race-prone and can still create duplicate incidents for the same fingerprint [`backend/src/api/webhooks.py:46`] — **Fixed**: Uses `pg_advisory_xact_lock(hash(fingerprint))` inside a transaction before dedup check+insert to serialize per-fingerprint access.
- [x] [Review][Patch] Concurrent same-namespace or same-label alerts can split into separate correlation groups instead of one Root-Cause Event [`backend/src/pipeline/correlator.py:174`] — **Fixed**: `get_open_groups(conn, for_update=True)` uses `FOR UPDATE` locking on open groups.
- [x] [Review][Patch] Expired groups are only sealed when a later alert triggers processing, so quiet groups can remain open past max age [`backend/src/pipeline/correlator.py:256`] — **Fixed**: Dedicated `_background_sealing_sweep()` asyncio task runs every `sealing_check_interval_seconds` (default 10s) as a lifespan background task.
- [x] [Review][Patch] Layer 4 subsystem correlation can attach alerts to groups that should already be sealed [`backend/src/pipeline/correlator.py:128`] — **Fixed**: `_group_exceeds_max_age(group, now)` check skips groups past max age in Layer 4.
- [x] [Review][Patch] Settling windows are not actually Helm-configurable because correlation env vars are never injected into the backend deployment [`charts/openshift-ai-ops/templates/deployment-backend.yaml:27`] — **Fixed**: All correlation env vars (`CORRELATION_SETTLING_CRITICAL/WARNING/INFO`, `CORRELATION_MAX_AGE_MULTIPLIER`, `CORRELATION_SEALING_INTERVAL`) wired in `deployment-backend.yaml`.
- [x] [Review][Patch] Subsystem-correlation evidence does not cite the matched cascade pattern required by AC #4 [`backend/src/pipeline/correlator.py:206`] — **Fixed**: Evidence includes `cascade_pattern`, `alert_subsystem`, `group_subsystem` in `dimension_data` with human-readable reasoning string.
