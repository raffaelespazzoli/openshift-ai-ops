# Story 4.3: Fast-Path Bypass for Known Patterns

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want recurring known issues to be resolved at machine speed without waiting for LLM diagnosis,
so that proven fixes replay instantly while the system still enforces policy controls.

## Acceptance Criteria

1. **Given** a Root-Cause Event is dequeued from the priority queue **When** the queue consumer checks for a fast-path match before dispatching to the diagnosis pipeline **Then** it queries pgvector for Case Records matching the current alert signature above a configurable similarity threshold

2. **Given** a fast-path match is found above the similarity threshold **When** the match is evaluated **Then** only records with successful outcomes (positive cases) are eligible for fast-path replay

3. **Given** an eligible fast-path match exists **When** the fast-path is activated **Then** the proven remediation plan is replayed directly, bypassing the full LLM diagnosis pipeline (orchestrator, skeptic) **And** the incident state shortcuts from `queued` to `diagnosed` (skipping agent work) per AD-19

4. **Given** a fast-path remediation plan **When** it enters the remediation flow **Then** it still passes through the dry-run pre-flight and Policy Gate (Epic 3) — no shortcut to execution

5. **Given** a fast-path match was used **When** the incident is displayed in the UI (Epic 5) **Then** it is visually distinguishable from a full-diagnosis incident (the fast-path badge and similarity score are available in the incident record)

6. **Given** no fast-path match exists above the threshold **When** the check completes **Then** the Root-Cause Event proceeds to the full diagnosis pipeline (Epic 2) as normal

7. **Given** the fast-path similarity threshold **When** it is configured **Then** it is adjustable via Helm values or runtime API configuration

## Tasks / Subtasks

- [ ] Task 1: Add fast-path DB query for eligible case records (AC: #1, #2)
  - [ ] 1.1 Add `search_fast_path_candidates(conn, query_embedding, threshold, top_k) -> list[dict]` to `backend/src/db/case_records.py`
  - [ ] 1.2 Query filters: `fast_path_eligible = TRUE`, `outcome = 'success'`, `alert_signature_embedding IS NOT NULL`, similarity above threshold
  - [ ] 1.3 Return columns: `id`, `alert_signature`, `root_cause_code`, `outcome`, `outcome_confidence`, `ocp_version`, `created_at`, `diagnosis_object`, `remediation_plan`, `similarity`
  - [ ] 1.4 Order by cosine similarity (best match first), limit `top_k`

- [ ] Task 2: DB migration — add fast-path fields to incidents table (AC: #5)
  - [ ] 2.1 Create Alembic migration to add: `fast_path BOOLEAN DEFAULT FALSE`, `fast_path_similarity FLOAT`, `fast_path_case_record_id UUID REFERENCES case_records(id)`
  - [ ] 2.2 Migration number: check latest migration file and increment (currently 014; 4.1 plans 015, 4.2 plans 016 — so this should be 017. Verify before creating.)
  - [ ] 2.3 Add `CREATE INDEX idx_incidents_fast_path ON incidents(fast_path) WHERE fast_path = TRUE`

- [ ] Task 3: DB operations for fast-path metadata (AC: #5)
  - [ ] 3.1 Add `record_fast_path(conn, incident_id, case_record_id, similarity) -> None` to `backend/src/db/incidents.py`
  - [ ] 3.2 Updates `fast_path`, `fast_path_similarity`, `fast_path_case_record_id` on the incident row
  - [ ] 3.3 Extend `get_incident_detail()` to return fast-path fields

- [ ] Task 4: Add fast-path threshold to KnowledgeSettings (AC: #7)
  - [ ] 4.1 Add `learning_store_fast_path_threshold: float = 0.90` to `KnowledgeSettings` in `backend/src/config/knowledge_settings.py`
  - [ ] 4.2 Add env var loading: `LEARNING_STORE_FAST_PATH_THRESHOLD`
  - [ ] 4.3 Helm values: add `fastPathThreshold: 0.90` to `learningStore` section in `values.yaml`
  - [ ] 4.4 Wire env var in `deployment-backend.yaml`

- [ ] Task 5: Fast-path check and runner module (AC: #1, #2, #3, #4, #6)
  - [ ] 5.1 Create `backend/src/pipeline/fast_path.py` with `check_fast_path(item, conn) -> FastPathMatch | None`
  - [ ] 5.2 Build alert signature from item's alert data (reuse pattern from Story 4.1's `build_alert_signature()`)
  - [ ] 5.3 Generate embedding via `embed_texts()` from `knowledge/embeddings.py`
  - [ ] 5.4 Query `search_fast_path_candidates()` with the fast-path threshold
  - [ ] 5.5 Apply `apply_temporal_decay()` to each candidate for ranking by effective confidence
  - [ ] 5.6 Return the best match (highest effective confidence above threshold) or None
  - [ ] 5.7 Create `run_fast_path_pipeline(item, match) -> bool` — the full fast-path flow
  - [ ] 5.8 Transition all incidents QUEUED → DIAGNOSED via state machine
  - [ ] 5.9 Create synthetic `ImmutableDiagnosisArtifact` from the case record's `diagnosis_object`
  - [ ] 5.10 Persist the artifact to `immutable_diagnoses` table
  - [ ] 5.11 Replay the case record's `remediation_plan` as a new `RemediationPlan` for this incident
  - [ ] 5.12 Persist the plan to `remediation_plans` table
  - [ ] 5.13 Record fast-path metadata on the incident (`record_fast_path()`)
  - [ ] 5.14 Transition DIAGNOSED → PLANNING
  - [ ] 5.15 Run `run_dry_run_preflight(plan, artifact)` (reuse existing from `pipeline/dry_run.py`)
  - [ ] 5.16 Run `evaluate_policy_gate(plan, artifact, dry_run_result)` (reuse existing from `pipeline/policy_gate.py`)
  - [ ] 5.17 Persist dry-run result and policy decision
  - [ ] 5.18 Transition based on policy decision: PLANNING → AWAITING_APPROVAL or EXECUTING
  - [ ] 5.19 Persist audit log entry for fast-path activation
  - [ ] 5.20 Mark queue item complete
  - [ ] 5.21 Emit SSE events for each stage (fast-path skip, dry-run, policy gate)
  - [ ] 5.22 On any failure: log, fall back to normal diagnosis pipeline (return False)

- [ ] Task 6: Hook fast-path into dispatcher (AC: #1, #6)
  - [ ] 6.1 In `run_dispatcher()` main loop, after `dequeue_next()` and before `_transition_incidents_to_diagnosing()`, call `check_fast_path(item, conn)`
  - [ ] 6.2 If match found: spawn `run_fast_path_pipeline(item, match)` as async task (same pattern as `dispatch_to_pipeline`)
  - [ ] 6.3 If no match: continue with existing diagnosis pipeline dispatch
  - [ ] 6.4 Fast-path check failures are non-fatal — fall back to normal pipeline

- [ ] Task 7: Extend incident API to expose fast-path data (AC: #5)
  - [ ] 7.1 Update `get_incident_detail_endpoint()` in `api/incidents.py` to include `fast_path`, `fast_path_similarity`, `fast_path_case_record_id` in the response
  - [ ] 7.2 Update `list_incidents_endpoint()` to include `fast_path` flag in list items

- [ ] Task 8: Tests — unit (AC: #1–#7)
  - [ ] 8.1 `tests/pipeline/test_fast_path.py` — `check_fast_path()`: match found above threshold returns `FastPathMatch`, no match returns None, only `fast_path_eligible=True` records considered, only `outcome='success'` records considered, temporal decay applied to ranking
  - [ ] 8.2 `tests/pipeline/test_fast_path.py` — `run_fast_path_pipeline()`: success path (full flow from QUEUED to AWAITING_APPROVAL/EXECUTING), state transitions verified, artifacts persisted, fast-path metadata recorded, SSE events emitted, queue item completed
  - [ ] 8.3 `tests/pipeline/test_fast_path.py` — failure fallback: embedding failure returns None, DB query failure returns None, artifact persistence failure returns False (fall back to normal pipeline)
  - [ ] 8.4 `tests/pipeline/test_dispatcher.py` (extend) — fast-path check integrated: match found skips diagnosis dispatch, no match continues to normal dispatch
  - [ ] 8.5 `tests/db/test_case_records.py` (extend) — `search_fast_path_candidates()`: returns only eligible records, filters by outcome, respects similarity threshold, returns diagnosis_object and remediation_plan data
  - [ ] 8.6 `tests/api/test_incidents.py` (extend) — incident detail includes fast-path fields, list includes fast-path flag

- [ ] Task 9: Tests — integration (AC: #1, #3, #4)
  - [ ] 9.1 `tests/pipeline/test_fast_path.py` — end-to-end: insert case record with embedding → dequeue → fast-path match → verify state transitions and artifact persistence (testcontainers)
  - [ ] 9.2 `tests/db/test_case_records.py` — `search_fast_path_candidates()` roundtrip: persist case record with embedding → search → verify similarity filter and data returned

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 4.2 (Temporal Decay & Version Relevance) — DIRECT PREDECESSOR:**

Story 4.2 refines the temporal decay calculation used to rank case record results. Relevant to 4.3:

- **`knowledge/learning_store.py`** — `apply_temporal_decay()` computes `effective_confidence = base_confidence × decay_factor(age) × version_relevance`. After 4.2, this function uses configurable weights from `KnowledgeSettings`. Fast-path uses this function to rank candidate matches by effective confidence.
- **`knowledge/learning_store.py`** — `query_learning_store()` queries pgvector, applies temporal decay, returns ranked `CaseRecordSummary` list. Fast-path needs a DIFFERENT query (with `fast_path_eligible` and `diagnosis_object`/`remediation_plan` data), so it does NOT reuse `query_learning_store()` directly. It reuses `apply_temporal_decay()` only.
- **`config/knowledge_settings.py`** — `KnowledgeSettings` extended by 4.2 with `version_relevance_same_major`, `version_relevance_different_major`, `version_relevance_minor_penalty_per_version`. Fast-path adds `learning_store_fast_path_threshold`.
- **`db/learning_store_config.py`** (new in 4.2) — runtime config override table. Fast-path threshold can be overridden at runtime through this same mechanism.
- **Anti-pattern from 4.2**: "DO NOT implement fast-path bypass logic. That is Story 4.3's scope." — **This story IS 4.3.** It is authorized to implement the fast-path bypass.

**From Story 4.1 (Case Record Persistence & Vector Embeddings) — CRITICAL DEPENDENCY:**

Story 4.1 builds the WRITE side of the Learning Store. Fast-path REQUIRES these to exist:

- **`pipeline/case_record_writer.py`** — `create_case_record(incident_id)` assembles incident data, generates embeddings, persists to `case_records`. The `build_alert_signature()` function constructs the text that gets embedded — fast-path needs the same function to build the query embedding.
- **`db/case_records.py`** (extended by 4.1) — adds `persist_case_record()`, `downgrade_case_record()`, `get_case_record_by_incident()`. The existing `search_similar_cases()` is the READ query template — fast-path adds `search_fast_path_candidates()` with additional filters.
- **Migration `015_extend_case_records.py`** (4.1) — adds `incident_id`, `diagnosis_object JSONB`, `remediation_plan JSONB`, `outcome_details JSONB`, `fast_path_eligible BOOLEAN`. Fast-path REQUIRES `diagnosis_object`, `remediation_plan`, and `fast_path_eligible` columns.
- **`models/case_record.py`** — `CaseRecord` (full model added by 4.1) with `diagnosis_object`, `remediation_plan`, `fast_path_eligible` fields.

**HARD DEPENDENCY**: Story 4.3 cannot function without Story 4.1's migration and write path. Without case records containing `diagnosis_object` and `remediation_plan`, there is nothing to replay.

**From Story 4.0 (Manifest Generation Pipeline Stage):**

Story 4.0 adds `manifest_path` and `manifest_generation_failed` to `RemediationStep`. If 4.0 runs before 4.3:
- The replayed remediation plan from the case record MAY contain steps with `manifest_path` fields (if the original plan had manifest artifacts). These paths will point to temp files that no longer exist.
- The fast-path runner MUST clear `manifest_path` on all replayed steps (set to None) and set `manifest_generation_failed = False`. Manifest generation will re-run in the dry-run stage if 4.0's manifest_generation node exists in the remediation graph.
- If 4.0 has NOT run, `RemediationStep` won't have these fields and no action is needed.

**From Story 3.5 (Serialized Execution, Outcome Observation & Rollback):**

Story 3.5 built the execution cycle. Once fast-path transitions an incident to AWAITING_APPROVAL or EXECUTING, the existing execution dispatcher picks it up. No changes needed to the execution flow.

- **`pipeline/execution_dispatcher.py`** — polls for incidents in EXECUTING state. Works unchanged for fast-path incidents.
- **`pipeline/freshness_gate.py`** — re-validates alert is still firing before execution. Works unchanged.
- **`pipeline/outcome_observer.py`** — monitors for resolution. Works unchanged.

**From Story 3.3 (Dry-Run Pre-Flight & Policy Gate):**

These functions are REUSED by the fast-path runner:

- **`pipeline/dry_run.py`** — `run_dry_run_preflight(plan, artifact, mcp_client)` returns `DryRunResult`. Takes a `RemediationPlan` and `ImmutableDiagnosisArtifact`. Fast-path calls this directly.
- **`pipeline/policy_gate.py`** — `evaluate_policy_gate(plan, artifact, dry_run, settings, alert_severity)` returns `PolicyDecision`. Fast-path calls this directly.
- **`db/policy_gate.py`** — `persist_dry_run_result()`, `persist_policy_decision()`. Fast-path reuses these for persistence.

**From Story 3.4 (Human Approval Workflow Backend API):**

- **`api/approval.py`** — approve/reject endpoints work unchanged for fast-path incidents in AWAITING_APPROVAL.

**From Story 2.4 (Diagnosis Skeptic & Immutable Handoff):**

- **`models/diagnosis.py`** — `ImmutableDiagnosisArtifact` with `root_cause_component`, `failure_mode`, `causal_chain`, `affected_resources`, `evidence`, `evidence_gaps`, `confidence`, `skeptic_verdict`, `sealed_at`. Fast-path creates a synthetic one from the case record's `diagnosis_object`.
- **`db/diagnosis.py`** — persistence of immutable diagnoses. Fast-path needs to persist the replayed diagnosis.

**From Epic 1 (foundation patterns):**

- **`models/state_machine.py`** — `QUEUED → DIAGNOSED` transition already exists (line 32). This is the fast-path shortcut path. Also `DIAGNOSED → PLANNING`, `PLANNING → AWAITING_APPROVAL`, `PLANNING → EXECUTING`.
- **`pipeline/dispatcher.py`** — the main dispatch loop is THE hook point. After `dequeue_next()`, before `_transition_incidents_to_diagnosing()`.
- **`db/queue.py`** — `mark_pipeline_complete()` marks queue items done. Used by fast-path after completing.
- **`api/event_bus.py`** — `get_event_bus()` for SSE events.
- **`pipeline/runner.py`** — `_emit_stage_event()` pattern for SSE. Fast-path follows the same pattern.

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-19 | Canonical state machine | Fast-path uses the existing `queued → diagnosed` transition (already defined in VALID_TRANSITIONS). All state changes through the `transition()` function. |
| AD-1 | Staged pipeline paradigm | Fast-path is a conditional bypass at the dispatch level, not a new paradigm. It reuses existing dry-run and policy gate stages. |
| AD-2 | RBAC Airlock | Fast-path creates a synthetic ImmutableDiagnosisArtifact from the case record. The diagnosis is read-only once persisted. Remediation still uses the read-write MCP. |
| AD-20 | Case Record schema owned by Learning Store | Fast-path READS from `case_records` — no schema changes. Read queries go through `db/case_records.py`. |
| AD-4 | Shared types module | `FastPathMatch` model defined in `models/`. ImmutableDiagnosisArtifact and RemediationPlan reused from existing models. |
| AD-14 | Monorepo layout | New files follow established pattern. |
| AD-25 | Audit logging | Fast-path activation is audit-logged via pipeline audit hook. |
| AD-24 | Event bus | SSE events emitted for fast-path stage transitions. |

**Critical constraints from project-context.md:**

- **"NEVER bypass the policy gate."** — Fast-path remediations STILL pass through dry-run and policy gate. No shortcut to execution.
- **"NEVER skip the skeptic."** — Fast-path skips the skeptic for the CURRENT incident because the diagnosis AND plan are replays of a previously skeptic-validated incident. The original plan survived skeptic validation in its original incident.
- **"Default-deny is the shipping default."** — The policy gate default requires human approval. Fast-path does not change this.
- **"Unhappy Path & Failure Mode Discipline"** — Fast-path check is best-effort. Any failure falls back to normal diagnosis pipeline. Embedding failures, DB query failures, artifact persistence failures are all handled gracefully.
- **"SSE event emission is best-effort"** — All SSE calls wrapped in try/except.

### Technical Requirements

#### Fast-Path Flow (Complete)

```
Dispatcher dequeues item
  ├─ check_fast_path(item, conn)
  │   ├─ Build alert signature from item's alerts
  │   ├─ Generate embedding via embed_texts()
  │   ├─ Query search_fast_path_candidates() with fast-path threshold
  │   ├─ Apply apply_temporal_decay() to each candidate
  │   ├─ Return best match (highest effective_confidence) or None
  │   │
  │   ├─ Match found → dispatch_fast_path(item, match)
  │   │   ├─ Transition incidents: QUEUED → DIAGNOSED
  │   │   ├─ Create synthetic ImmutableDiagnosisArtifact from case record
  │   │   ├─ Persist to immutable_diagnoses table
  │   │   ├─ Replay RemediationPlan from case record
  │   │   ├─ Persist to remediation_plans table
  │   │   ├─ Record fast-path metadata on incident
  │   │   ├─ Transition: DIAGNOSED → PLANNING
  │   │   ├─ Run run_dry_run_preflight(plan, artifact)
  │   │   ├─ Run evaluate_policy_gate(plan, artifact, dry_run)
  │   │   ├─ Persist dry-run result and policy decision
  │   │   ├─ Transition: PLANNING → AWAITING_APPROVAL or EXECUTING
  │   │   ├─ Audit log: fast-path activation
  │   │   ├─ Mark queue item complete
  │   │   └─ Emit SSE events
  │   │
  │   └─ No match → continue to normal diagnosis pipeline
  │
  └─ Normal: _transition_incidents_to_diagnosing → dispatch_to_pipeline
```

#### FastPathMatch Model

```python
class FastPathMatch(BaseModel):
    """Result of a fast-path lookup — the matched case record."""

    case_record_id: uuid.UUID
    alert_signature: str
    root_cause_code: str
    similarity: float = Field(ge=0.0, le=1.0)
    effective_confidence: float = Field(ge=0.0)
    ocp_version: str
    diagnosis_object: dict
    remediation_plan: dict
```

Defined in `pipeline/fast_path.py` (internal to the module, not in `models/` — it's a transient pipeline artifact, not a stage-boundary contract).

#### Fast-Path DB Query

```python
async def search_fast_path_candidates(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    threshold: float = 0.90,
    top_k: int = 3,
) -> list[dict]:
    """Search for fast-path-eligible case records above the similarity threshold.

    Filters for successful outcomes with fast_path_eligible = TRUE.
    Returns full diagnosis_object and remediation_plan for replay.
    """
    rows = await conn.fetch(
        """
        SELECT id, alert_signature, root_cause_code, outcome,
               outcome_confidence, ocp_version, created_at,
               diagnosis_object, remediation_plan,
               1 - (alert_signature_embedding <=> $1::vector) AS similarity
        FROM case_records
        WHERE fast_path_eligible = TRUE
          AND outcome = 'success'
          AND alert_signature_embedding IS NOT NULL
          AND diagnosis_object IS NOT NULL
          AND remediation_plan IS NOT NULL
          AND 1 - (alert_signature_embedding <=> $1::vector) > $2
        ORDER BY alert_signature_embedding <=> $1::vector
        LIMIT $3
        """,
        str(query_embedding),
        threshold,
        top_k,
    )
    return [dict(row) for row in rows]
```

#### Synthetic ImmutableDiagnosisArtifact Construction

The case record's `diagnosis_object` JSONB column stores the full diagnosis that was originally created during the first incident. To replay it:

```python
def _build_synthetic_artifact(
    match: FastPathMatch,
    incident_id: uuid.UUID,
) -> ImmutableDiagnosisArtifact:
    """Build a synthetic diagnosis artifact from a case record for fast-path replay.

    The artifact preserves the original diagnosis content but assigns
    a new ID and links to the current incident.
    """
    diag = match.diagnosis_object.copy()
    diag["id"] = str(uuid.uuid4())
    diag["diagnosis_object_id"] = diag.get("id", str(uuid.uuid4()))
    diag["sealed_at"] = datetime.now(timezone.utc).isoformat()
    return ImmutableDiagnosisArtifact.model_validate(diag)
```

#### Replayed RemediationPlan Construction

```python
def _build_replayed_plan(
    match: FastPathMatch,
    incident_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
) -> RemediationPlan:
    """Build a replayed remediation plan from a case record for fast-path.

    Creates a new plan with the same steps, blast radius, rollback,
    risk, and preconditions as the proven original.
    """
    plan_data = match.remediation_plan.copy()
    plan_data["id"] = str(uuid.uuid4())
    plan_data["incident_id"] = str(incident_id)
    plan_data["diagnosis_id"] = str(diagnosis_id)
    plan_data["created_at"] = datetime.now(timezone.utc).isoformat()

    # Clear stale manifest paths from previous executions (Story 4.0)
    for step in plan_data.get("steps", []):
        step.pop("manifest_path", None)
        step.pop("manifest_generation_failed", None)

    return RemediationPlan.model_validate(plan_data)
```

#### Dispatcher Integration

In `run_dispatcher()` main loop:

```python
item = await dequeue_next(conn)
if item:
    # Fast-path check before full diagnosis pipeline
    fast_path_match = None
    try:
        from .fast_path import check_fast_path
        fast_path_match = await check_fast_path(item, conn)
    except Exception:
        logger.warning(
            "Fast-path check failed — proceeding with normal pipeline",
            extra={"incident_id": str(item["incident_id"])},
        )

    if fast_path_match:
        task = asyncio.create_task(
            _run_fast_path_task(item, fast_path_match)
        )
        _inflight_tasks.add(task)
        _inflight_items[task] = item
        task.add_done_callback(_task_done)
    else:
        # Existing diagnosis pipeline dispatch
        success = await _transition_incidents_to_diagnosing(
            conn, item["root_cause_event_id"], item["incident_id"]
        )
        if success:
            await dispatch_to_pipeline(item, conn)
        # ... existing retry logic ...
```

#### Incident Fast-Path Metadata

DB migration:

```sql
ALTER TABLE incidents ADD COLUMN fast_path BOOLEAN DEFAULT FALSE;
ALTER TABLE incidents ADD COLUMN fast_path_similarity FLOAT;
ALTER TABLE incidents ADD COLUMN fast_path_case_record_id UUID REFERENCES case_records(id);
CREATE INDEX idx_incidents_fast_path ON incidents(fast_path) WHERE fast_path = TRUE;
```

Record function in `db/incidents.py`:

```python
async def record_fast_path(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
    case_record_id: uuid.UUID,
    similarity: float,
) -> None:
    """Record fast-path metadata on an incident."""
    await conn.execute(
        """
        UPDATE incidents
        SET fast_path = TRUE,
            fast_path_similarity = $2,
            fast_path_case_record_id = $3,
            updated_at = NOW()
        WHERE id = $1
        """,
        incident_id,
        similarity,
        case_record_id,
    )
```

#### Alert Signature Construction

Fast-path needs to build the same alert signature text that `create_case_record()` (Story 4.1) uses for embedding, so the similarity query is apples-to-apples. Import and reuse `build_alert_signature()` from `pipeline/case_record_writer.py`:

```python
from .case_record_writer import build_alert_signature
```

If Story 4.1 is not yet implemented and `case_record_writer.py` doesn't exist, implement a local version with the same logic:

```python
def build_alert_signature(alerts: list[dict]) -> str:
    parts = []
    for alert in sorted(alerts, key=lambda a: a.get("name", a.get("labels", {}).get("alertname", ""))):
        name = alert.get("name", alert.get("labels", {}).get("alertname", ""))
        labels = alert.get("labels", {})
        namespace = labels.get("namespace", "")
        severity = labels.get("severity", "")
        summary = alert.get("annotations", {}).get("summary", "")
        parts.append(f"{name} {namespace} {severity} {summary}")
    return " | ".join(parts)
```

#### Configuration

`KnowledgeSettings` extension:

```python
learning_store_fast_path_threshold: float = 0.90
```

`from_env()`:
```python
learning_store_fast_path_threshold=float(
    os.environ.get("LEARNING_STORE_FAST_PATH_THRESHOLD", "0.90")
),
```

Helm `values.yaml`:
```yaml
learningStore:
  decayHalfLifeDays: 90
  similarityThreshold: 0.75
  fastPathThreshold: 0.90
```

`deployment-backend.yaml`:
```yaml
- name: LEARNING_STORE_FAST_PATH_THRESHOLD
  value: "{{ .Values.learningStore.fastPathThreshold }}"
```

If Story 4.2's runtime config API is implemented, the fast-path threshold becomes runtime-configurable by adding `"fast_path_threshold"` to the `VALID_CONFIG_KEYS` frozenset in `api/learning_store_config.py`.

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| asyncpg | latest | Already in pyproject.toml. DB queries |
| pydantic | latest | Already in pyproject.toml. FastPathMatch model |
| pgvector | latest | Already in pyproject.toml. Vector similarity search |

**No new dependencies required.** All packages were added in Epics 1–2.

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/pipeline/fast_path.py` | Fast-path check, matching, and pipeline runner | NEW |
| `backend/alembic/versions/017_add_fast_path_fields.py` | Migration: add fast_path, fast_path_similarity, fast_path_case_record_id to incidents | NEW |
| `backend/tests/pipeline/test_fast_path.py` | Fast-path check and runner unit tests | NEW |
| `backend/tests/db/test_fast_path.py` | Fast-path DB query tests (testcontainers) | NEW |

**IMPORTANT migration numbering**: Story 4.1 plans `015_extend_case_records.py`, Story 4.2 plans `016_add_learning_store_config.py`. If both ran first, this migration is `017`. If ordering differs, check `backend/alembic/versions/` for the latest migration file before creating.

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/db/case_records.py` | Add `search_fast_path_candidates()` query with eligibility filters and full data return | UPDATE |
| `backend/src/db/incidents.py` | Add `record_fast_path()` function; extend `get_incident_detail()` to return fast-path fields | UPDATE |
| `backend/src/pipeline/dispatcher.py` | Add fast-path check in `run_dispatcher()` before diagnosis dispatch; add `_run_fast_path_task()` wrapper | UPDATE |
| `backend/src/config/knowledge_settings.py` | Add `learning_store_fast_path_threshold` field and env var | UPDATE |
| `backend/src/api/incidents.py` | Include `fast_path`, `fast_path_similarity`, `fast_path_case_record_id` in detail and list responses | UPDATE |
| `charts/openshift-ai-ops/values.yaml` | Add `fastPathThreshold: 0.90` to `learningStore` section | UPDATE |
| `charts/openshift-ai-ops/templates/deployment-backend.yaml` | Add `LEARNING_STORE_FAST_PATH_THRESHOLD` env var | UPDATE |
| `backend/tests/pipeline/test_dispatcher.py` | Extend with fast-path integration tests | UPDATE |
| `backend/tests/api/test_incidents.py` | Extend with fast-path field assertions | UPDATE |

### Dependency Direction (ENFORCED)

```
pipeline/fast_path.py → models/ (ImmutableDiagnosisArtifact, RemediationPlan, state_machine)
                       → db/ (case_records, incidents, remediation, diagnosis, policy_gate, queue, audit)
                       → knowledge/ (embeddings, learning_store)
                       → config/ (knowledge_settings, logging)
                       → pipeline/ (dry_run, policy_gate, runner [_emit_stage_event pattern], audit_hook)
                       → api/ (event_bus — for SSE)

db/case_records.py → config/logging (logger only)
db/incidents.py → config/logging, models/state_machine
config/knowledge_settings.py → (nothing — leaf config module)
```

- **NEVER**: `models/` imports from `pipeline/`, `api/`, or `db/`
- **NEVER**: `config/` imports from `pipeline/`, `api/`, or `db/`
- **NEVER**: Fast-path modifies the `search_similar_cases()` function. It adds a NEW query function alongside it.
- **NEVER**: Fast-path bypasses the policy gate. The dry-run and policy gate MUST run.
- **NEVER**: Fast-path modifies the case record. It only READS from case_records.
- **NEVER**: Fast-path creates or modifies LangGraph graph definitions. It is a dispatch-level bypass.
- **ALLOWED**: `pipeline/fast_path.py` imports from `pipeline/dry_run.py` and `pipeline/policy_gate.py`
- **ALLOWED**: `pipeline/fast_path.py` imports from `db/remediation.py` (`persist_remediation_plan`)
- **ALLOWED**: `pipeline/fast_path.py` imports from `pipeline/case_record_writer.py` (`build_alert_signature`)

### Testing Requirements

**Unit tests** (`pytest -m unit`):

`tests/pipeline/test_fast_path.py` — `check_fast_path()`:
- Valid match above threshold → returns `FastPathMatch` with correct fields
- No candidates above threshold → returns None
- Empty case_records table → returns None
- Multiple candidates → returns highest effective_confidence (after temporal decay)
- Candidate with `outcome='failure'` → excluded
- Candidate with `fast_path_eligible=False` → excluded
- Candidate with `diagnosis_object=None` → excluded
- Candidate with `remediation_plan=None` → excluded
- Embedding generation failure → returns None (non-fatal)
- DB query failure → returns None (non-fatal)

`tests/pipeline/test_fast_path.py` — `run_fast_path_pipeline()`:
- Success path: incidents transition QUEUED→DIAGNOSED→PLANNING→AWAITING_APPROVAL (policy gate denies auto)
- Success path with auto-approve: PLANNING→EXECUTING (policy gate approves)
- State transitions verified via state machine
- ImmutableDiagnosisArtifact persisted to `immutable_diagnoses`
- RemediationPlan persisted to `remediation_plans`
- Fast-path metadata recorded on incident (`fast_path=True`, similarity, case_record_id)
- Dry-run result persisted
- Policy decision persisted
- Queue item marked complete
- SSE events emitted for each stage
- Audit log written
- Stale manifest_path cleared from replayed steps

`tests/pipeline/test_fast_path.py` — failure fallback:
- Artifact persistence failure → returns False (caller falls back to normal pipeline)
- State transition failure → returns False
- Dry-run failure → still persists result, continues to policy gate
- Policy gate failure → transitions to FAILED

`tests/pipeline/test_dispatcher.py` (extend):
- Fast-path match → `_run_fast_path_task` spawned, `dispatch_to_pipeline` NOT called
- No fast-path match → normal `dispatch_to_pipeline` called
- Fast-path check raises exception → normal pipeline proceeds (non-fatal)

`tests/db/test_fast_path.py`:
- `search_fast_path_candidates()` with eligible record → returns record with similarity
- `search_fast_path_candidates()` with ineligible record (`fast_path_eligible=False`) → empty
- `search_fast_path_candidates()` with failed outcome → empty
- `search_fast_path_candidates()` with similarity below threshold → empty
- `search_fast_path_candidates()` returns `diagnosis_object` and `remediation_plan` JSONB
- `record_fast_path()` sets all three fields on the incident

`tests/api/test_incidents.py` (extend):
- Incident detail includes `fast_path`, `fast_path_similarity`, `fast_path_case_record_id`
- Non-fast-path incident has `fast_path=False`, null similarity and case_record_id
- Incident list includes `fast_path` flag

**Mock patterns:**
- Mock `embed_texts()` to return a deterministic 1536-dimension vector
- Mock `embed_texts()` to raise `Exception` for failure tests
- Mock `search_fast_path_candidates()` to return canned case record data
- Mock `run_dry_run_preflight()` to return a passing `DryRunResult`
- Mock `evaluate_policy_gate()` to return auto-approve/deny `PolicyDecision`
- Use `tmp_path` pytest fixture for any file-based artifacts
- Mock SSE event bus to verify events emitted
- For DB integration tests: use testcontainers PostgreSQL + pgvector

### Anti-Patterns / DO NOT

- **DO NOT** bypass the policy gate for fast-path remediations. The AC explicitly states: "it still passes through the dry-run pre-flight and Policy Gate (Epic 3) — no shortcut to execution." This is a security requirement.
- **DO NOT** modify the existing `search_similar_cases()` query. It is used by the Learning Store enrichment path (Epic 2). Fast-path adds a NEW query function `search_fast_path_candidates()` with different filters and return columns.
- **DO NOT** modify `query_learning_store()` in `learning_store.py`. Fast-path uses `apply_temporal_decay()` directly but builds its own query pipeline.
- **DO NOT** create a new LangGraph graph or node for fast-path. Fast-path is a dispatch-level bypass that reuses existing functions (dry_run, policy_gate) directly — no graph overhead.
- **DO NOT** modify the state machine transitions. `QUEUED → DIAGNOSED` already exists (line 32 of `state_machine.py`). No new transitions needed.
- **DO NOT** modify `pipeline/runner.py` (diagnosis pipeline runner). Fast-path bypasses it entirely.
- **DO NOT** modify `pipeline/remediation_runner.py` (remediation pipeline runner). Fast-path runs dry-run and policy gate directly, not through the graph.
- **DO NOT** modify `pipeline/remediation_graph.py`. Fast-path does not use the remediation graph.
- **DO NOT** modify the execution dispatcher, freshness gate, outcome observer, or rollback API. These work unchanged for fast-path incidents.
- **DO NOT** modify `models/diagnosis.py`, `models/remediation.py`, `models/execution.py`, or any model from a previous story.
- **DO NOT** auto-approve fast-path remediations. The policy gate default is human-approval-required. Fast-path does not change this.
- **DO NOT** make the fast-path check blocking or slow. If embedding or DB query takes too long, fall back to normal pipeline. The check should be fast (single embedding + single vector query).
- **DO NOT** persist case records for fast-path incidents. Case record creation (Story 4.1) already runs after execution — it will create a new case record for the fast-path incident's execution outcome.
- **DO NOT** count fast-path as a separate pipeline task type. It reuses the existing `_inflight_tasks` tracking and `active_pipelines` parallelism cap.
- **DO NOT** clear `manifest_path` from rollback steps in the replayed plan — only clear from forward `steps`. Rollback steps are created fresh if triggered.

### Project Structure Notes

All new/modified files align with AD-14 monorepo layout:
```
backend/src/
  config/
    knowledge_settings.py            # UPDATE: add fast_path_threshold
  pipeline/
    fast_path.py                     # NEW: fast-path check and runner
    dispatcher.py                    # UPDATE: hook fast-path before diagnosis
  db/
    case_records.py                  # UPDATE: add search_fast_path_candidates()
    incidents.py                     # UPDATE: add record_fast_path(), extend get_incident_detail()
  api/
    incidents.py                     # UPDATE: include fast-path fields in responses
backend/alembic/versions/
    017_add_fast_path_fields.py      # NEW migration (verify number before creating)
backend/tests/
  pipeline/
    test_fast_path.py                # NEW: comprehensive fast-path tests
    test_dispatcher.py               # UPDATE: extend with fast-path integration
  db/
    test_fast_path.py                # NEW: DB query tests (testcontainers)
  api/
    test_incidents.py                # UPDATE: extend with fast-path field assertions
charts/openshift-ai-ops/
    values.yaml                      # UPDATE: add fastPathThreshold
    templates/deployment-backend.yaml # UPDATE: add env var
```

Estimated file count: 4 new + 8 modified = 12 files total (well within the 25-file story size limit).

### Latest Technology Notes

**pgvector 0.8.x — filtered vector search:**
- The fast-path query adds `WHERE fast_path_eligible = TRUE AND outcome = 'success'` before the vector similarity clause. This is a filtered vector search.
- For small tables (hundreds to low thousands of records), the planner may choose a sequential scan with filter. This is fine at MVP scale.
- For larger tables, enable `hnsw.iterative_scan = 'relaxed_order'` at query time for better recall on filtered queries. Consider adding a partial HNSW index: `CREATE INDEX ON case_records USING hnsw (alert_signature_embedding vector_cosine_ops) WHERE fast_path_eligible = TRUE AND outcome = 'success'`.
- The existing HNSW index from migration 005 covers all records. Adding a partial index for fast-path-eligible records would improve query performance but is premature optimization at MVP scale.

**Embedding generation latency:**
- The fast-path check generates an embedding on every dequeue. At `embed_texts()` typical latency (50-200ms for a single text), this adds minimal overhead.
- If the embedding service is down, `check_fast_path()` catches the exception and returns None — the incident proceeds through the normal pipeline.
- Embedding caching is NOT implemented here. Epic 6 (semantic cache) may add this later.

**Fast-path threshold tuning:**
- Default threshold: 0.90 (high bar — must be very similar to a past successful case)
- The threshold is higher than the general learning store threshold (0.75) because fast-path bypasses the entire LLM diagnosis pipeline
- Too low: false-positive fast-paths apply wrong fixes. Too high: fast-path never triggers.
- The threshold is configurable via Helm values and (if 4.2 is implemented) via runtime API

### References

- [Source: epics.md#Story 4.3] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 4] — FR-20 (fast-path bypass), FR-18 (case records — 4.1), FR-19 (temporal decay — 4.2)
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine; QUEUED → DIAGNOSED transition exists
- [Source: ARCHITECTURE-SPINE.md#AD-1] — Staged pipeline paradigm; fast-path is a conditional bypass
- [Source: ARCHITECTURE-SPINE.md#AD-2] — RBAC Airlock; diagnosis artifact is read-only
- [Source: ARCHITECTURE-SPINE.md#AD-20] — Case Record schema owned by Learning Store
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit logging for fast-path activation
- [Source: project-context.md#Security Anti-Patterns] — "NEVER bypass the policy gate" — fast-path goes through dry-run and policy gate
- [Source: project-context.md#Unhappy Path & Failure Mode Discipline] — Fast-path failures are non-fatal
- [Source: project-context.md#Pipeline Paradigm Violations] — "NEVER skip the skeptic" — fast-path replays a previously skeptic-validated plan
- [Source: models/state_machine.py#L31-L34] — QUEUED → DIAGNOSED transition for fast-path
- [Source: pipeline/dispatcher.py#L452-L484] — Main dispatch loop (hook point)
- [Source: db/case_records.py] — search_similar_cases() (template for fast-path query)
- [Source: knowledge/learning_store.py] — apply_temporal_decay() for ranking, query_learning_store() (read path)
- [Source: knowledge/embeddings.py] — embed_texts() for embedding generation
- [Source: pipeline/dry_run.py] — run_dry_run_preflight() reused by fast-path
- [Source: pipeline/policy_gate.py] — evaluate_policy_gate() reused by fast-path
- [Source: pipeline/remediation_runner.py] — _handle_policy_decision() pattern, _persist_policy_artifacts() pattern
- [Source: db/remediation.py] — persist_remediation_plan(), load_immutable_artifact()
- [Source: db/policy_gate.py] — persist_dry_run_result(), persist_policy_decision()
- [Source: db/queue.py] — mark_pipeline_complete()
- [Source: pipeline/audit_hook.py] — pipeline_audit_log() for audit entries
- [Source: config/knowledge_settings.py] — KnowledgeSettings with learning_store_similarity_threshold
- [Source: charts/values.yaml] — learningStore section for Helm config
- [Source: charts/templates/deployment-backend.yaml] — env var injection pattern
- [Source: Story 4.1 spec] — Case record persistence, build_alert_signature(), migration 015
- [Source: Story 4.2 spec] — Temporal decay refinement, configurable weights, runtime config API
- [Source: Story 4.0 spec] — manifest_path/manifest_generation_failed on RemediationStep
- [Source: Story 3.3 spec] — dry_run and policy gate functions
- [Source: Story 3.5 spec] — execution dispatcher, outcome observer (work unchanged for fast-path)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Code Review Record

### Review Model Used

(Must differ from dev model to prevent self-review blind spots)

### Review Findings

### Decisions Needed / Decisions Taken

### Fixes Applied
