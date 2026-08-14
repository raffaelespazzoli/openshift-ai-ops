# Story 4.1: Case Record Persistence & Vector Embeddings

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want every resolved incident stored as a structured case record with searchable embeddings,
so that the system accumulates operational knowledge and can find similar past incidents for future diagnosis.

## Acceptance Criteria

1. **Given** an incident reaches a terminal state (resolved or failed) **When** the outcome is finalized **Then** a Case Record is persisted containing: alert signature, root-cause code, full Structured Diagnosis Object, Remediation Plan, outcome (success/failure with outcome_confidence), and cluster context (OCP version, topology snapshot)

2. **Given** a Case Record is created **When** it is stored in PostgreSQL **Then** vector embeddings are generated from the alert context and stored in pgvector for similarity search against future alert contexts

3. **Given** a remediation fails or an SRE triggers rollback **When** the Case Record is created **Then** it is stored as a negative case with the failure reason **And** negative cases are excluded from fast-path replay eligibility

4. **Given** a previously "successful" remediation's alert re-fires within the configurable window (detected in Story 3.5) **When** the re-fire is confirmed **Then** the Case Record is retroactively downgraded with reduced outcome_confidence and flagged for review

5. **Given** the Case Record table schema **When** it is inspected **Then** it is owned by the Learning Store module in `db/` per AD-20 **And** correlation (Epic 1) reads case records via pgvector similarity search and relational SQL queries but does not modify the schema

6. **Given** the Learning Store accumulates case records **When** the dataset grows to thousands or more records **Then** pgvector indexes (HNSW) maintain query performance for similarity search

## Tasks / Subtasks

- [ ] Task 1: Expand CaseRecord model (AC: #1, #3)
  - [ ] 1.1 Create full `CaseRecord` Pydantic model in `backend/src/models/case_record.py` alongside existing `CaseRecordSummary`
  - [ ] 1.2 Fields: `id: UUID`, `incident_id: UUID`, `alert_signature: str`, `root_cause_code: str`, `diagnosis_object: dict` (full DiagnosisObject JSON), `remediation_plan: dict` (full RemediationPlan JSON), `outcome: str` ("success"|"failure"), `outcome_confidence: float` (0–1), `outcome_details: dict` (full OutcomeResult JSON), `ocp_version: str`, `cluster_context: dict` (OCP version + topology snapshot), `diagnosis_summary: str`, `remediation_summary: str`, `fast_path_eligible: bool` (True for successes, False for failures/rollbacks), `created_at: datetime`
  - [ ] 1.3 Export `CaseRecord` from `backend/src/models/__init__.py`

- [ ] Task 2: Database migration — extend case_records table (AC: #1, #3, #5)
  - [ ] 2.1 Create Alembic migration to add missing columns to `case_records`: `incident_id UUID REFERENCES incidents(id) UNIQUE`, `diagnosis_object JSONB`, `remediation_plan JSONB`, `outcome_details JSONB`, `fast_path_eligible BOOLEAN DEFAULT TRUE`
  - [ ] 2.2 Migration number: check the latest migration file and increment (currently `014_add_diagnosis_object_id.py`)
  - [ ] 2.3 Columns are NULLable (backward-compatible with the empty table created by migration 005)

- [ ] Task 3: DB write operations (AC: #1, #3, #4)
  - [ ] 3.1 Add `persist_case_record(conn, case_record, embedding) -> UUID` to `backend/src/db/case_records.py`
  - [ ] 3.2 Add `downgrade_case_record(conn, incident_id, new_confidence, reason) -> bool` for re-fire/rollback
  - [ ] 3.3 Add `get_case_record_by_incident(conn, incident_id) -> dict | None` for re-fire downgrade lookup
  - [ ] 3.4 `persist_case_record()` inserts all fields including `alert_signature_embedding` vector

- [ ] Task 4: Case record creation service (AC: #1, #2, #3)
  - [ ] 4.1 Create `backend/src/pipeline/case_record_writer.py` with `create_case_record(incident_id) -> CaseRecord | None`
  - [ ] 4.2 Load incident data: alerts (for signature), immutable diagnosis, remediation plan, outcome result, execution log
  - [ ] 4.3 Build alert signature string from alert labels/annotations/name for embedding
  - [ ] 4.4 Generate vector embedding via `embed_texts()` from existing `knowledge/embeddings.py`
  - [ ] 4.5 Determine `fast_path_eligible`: True only if outcome is "success" AND no rollback exists AND refire_detected is False
  - [ ] 4.6 Obtain cluster context: OCP version from environment/config, topology snapshot from recent MCP query (or cached)
  - [ ] 4.7 Persist via `db/case_records.py`
  - [ ] 4.8 Handle embedding failures gracefully: persist the case record without the embedding vector (it can be backfilled later) rather than failing the whole operation

- [ ] Task 5: Hook into execution dispatcher — case record after outcome (AC: #1, #2, #3)
  - [ ] 5.1 In `_run_execution_cycle()` in `execution_dispatcher.py`, after outcome is persisted and state transitioned, call `create_case_record(incident_id)`
  - [ ] 5.2 Case record creation is best-effort — embedding or persistence failures are logged but do not crash the execution cycle or affect incident state
  - [ ] 5.3 Also hook into `_run_recovery_observation()` for stranded incident recovery path
  - [ ] 5.4 Emit SSE event `incident.case_record_created` after successful case record creation

- [ ] Task 6: Hook into re-fire detection — downgrade case record (AC: #4)
  - [ ] 6.1 In `monitor_for_refire()` in `outcome_observer.py`, after setting `refire_detected = TRUE`, also call `downgrade_case_record()`
  - [ ] 6.2 Downgrade sets `outcome_confidence` to `0.2` (same as timeout-level confidence) and marks `fast_path_eligible = FALSE`
  - [ ] 6.3 Downgrade is best-effort — failure logged but does not crash the re-fire monitor

- [ ] Task 7: Hook into rollback API — negative case record (AC: #3)
  - [ ] 7.1 In `trigger_rollback()` in `api/rollback.py`, after rollback completes, downgrade the case record
  - [ ] 7.2 Set `fast_path_eligible = FALSE` (rollback is a failure signal per Story 3.5)
  - [ ] 7.3 If no case record exists yet for this incident (edge case: rollback triggered before case record creation completes), skip the downgrade

- [ ] Task 8: Tests — unit (AC: #1–#4)
  - [ ] 8.1 `tests/models/test_case_record.py` — CaseRecord model validation: outcome constrained to "success"/"failure", outcome_confidence 0–1, fast_path_eligible defaults
  - [ ] 8.2 `tests/pipeline/test_case_record_writer.py` — create_case_record: success path (all data loaded, embedding generated, persisted), failure case (outcome="failure" → fast_path_eligible=False), embedding failure (record persisted without vector), missing data graceful handling
  - [ ] 8.3 `tests/db/test_case_records_write.py` — persist_case_record roundtrip (testcontainers), downgrade_case_record reduces confidence and sets fast_path_eligible=False, get_case_record_by_incident returns correct record

- [ ] Task 9: Tests — integration (AC: #1, #2, #5, #6)
  - [ ] 9.1 `tests/pipeline/test_execution_dispatcher.py` (extend) — verify case record created after successful outcome observation
  - [ ] 9.2 `tests/db/test_case_records_write.py` — pgvector similarity search against a persisted embedding (roundtrip: embed → persist → search → verify similarity)
  - [ ] 9.3 Verify re-fire detection triggers case record downgrade
  - [ ] 9.4 Verify rollback triggers case record downgrade

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 4.0 (Manifest Generation Pipeline Stage):**

Story 4.0 adds a manifest-generation phase between planning and dry-run. It is currently in `backlog` (not yet implemented). Story 4.1 does NOT depend on 4.0 — case record persistence captures whatever remediation plan shape exists. If 4.0 runs first and adds `manifest_path` to `RemediationStep`, the case record's `remediation_plan` JSONB field will transparently contain it. No coordination needed.

**From Story 3.5 (Serialized Execution, Outcome Observation & Rollback) — CRITICAL:**

This is the direct predecessor for 4.1. Story 3.5 built the full execution cycle that this story hooks into:

- **`pipeline/execution_dispatcher.py`** — `_run_execution_cycle()` is THE hook point. After lines 206–218 (where `persist_outcome_result()` and `transition_incident_state()` complete), insert the case record creation call. Also hook `_run_recovery_observation()` at lines 329–336 (same pattern).
- **`pipeline/outcome_observer.py`** — `monitor_for_refire()` is where re-fire downgrade hooks in. After the `UPDATE outcome_results SET refire_detected = TRUE` at line 126–133, add the case record downgrade call.
- **`api/rollback.py`** — After rollback persistence and audit log at lines 534–557 (in the `trigger_rollback()` function), add the case record downgrade.
- **`models/execution.py`** — `OutcomeResult` has `outcome_confidence`, `alert_resolved`, `resolution_method`, `refire_detected`. These feed the case record.
- **`db/execution.py`** — `persist_outcome_result()` and `load_execution_log()` are used by the dispatcher. The case record writer needs `load_execution_log()` too.
- **`config/execution_settings.py`** — `refire_window_seconds` governs the re-fire window. No changes needed.

**From Story 2.4 (Diagnosis Skeptic & Immutable Handoff):**

- **`models/diagnosis.py`** — `ImmutableDiagnosisArtifact` contains `root_cause_component`, `failure_mode`, `affected_resources`, `evidence`, `evidence_gaps`, `confidence`. The case record stores the full diagnosis object.
- **`db/diagnosis.py`** — `load_immutable_artifact()` loads from `immutable_diagnoses` table. Case record writer uses this.
- **Dual-ID semantics** (resolved in Epic 3 retro): `ImmutableDiagnosisArtifact` has both `id` (persistence PK) and `diagnosis_object_id` (provenance). The case record stores the full JSONB — both IDs are preserved.

**From Story 2.3 (Knowledge Integration):**

- **`knowledge/embeddings.py`** — `embed_texts([text]) -> list[list[float]]` generates 1536-dimension embeddings via OpenAI-compatible endpoint. Case record writer uses this to generate `alert_signature_embedding`. Already async, already uses `AsyncOpenAI` client.
- **`knowledge/learning_store.py`** — `query_learning_store()` and `apply_temporal_decay()` are the READ side. Already functional and tested. This story builds the WRITE side that populates what they query.
- **`db/case_records.py`** — `search_similar_cases()` is the READ query. Already written with pgvector cosine distance. This story adds the WRITE functions.

**From Story 1.2 (Alert Correlation):**

- **`db/correlation.py`** — Layer 5 of the correlator queries `case_records` for co-occurrence patterns. This is a read-only consumer. Story 4.1 writes must not break this query (it uses `alert_signature` and `root_cause_code` columns that already exist).

**From Epic 1 (foundation patterns):**

- **`db/connection.py`** — `get_pool()` for asyncpg connection pool
- **`db/audit.py`** — `write_audit_log()` for audit entries
- **`models/state_machine.py`** — `TERMINAL_STATES` = `{resolved, failed}` — triggers for case record creation
- **`api/event_bus.py`** — `get_event_bus()` for SSE events

**From Epic 3 Retrospective (2026-08-14):**

Key insights:
- Unhappy-path failures were the dominant review finding across all Epic 3 stories. A new "Unhappy Path & Failure Mode Discipline" section was added to `project-context.md`. This story MUST follow those rules.
- Case record creation must be best-effort — it must NEVER crash the execution cycle. SSE emission must NEVER crash the caller. Wrap in try/except per the new discipline rules.
- Transaction atomicity: case record persistence should be in its own transaction, NOT bundled with the outcome persistence (they are separate concerns with different failure modes).

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-3 | Two schema domains | Case records are application schema (NOT `langgraph_*`). Migrations owned by application. |
| AD-4 | Shared types module | Full `CaseRecord` model defined in `models/case_record.py`. All modules import from it. |
| AD-20 | Case Record schema owned by Learning Store | `db/case_records.py` owns the schema. Correlation layer reads only. Schema changes require a migration owned by `db/`. |
| AD-14 | Monorepo layout | New files follow established pattern: models → pipeline → db |
| AD-1 | Staged pipeline | Case record creation is NOT a pipeline stage — it's a post-pipeline side effect. No LangGraph node needed. |
| AD-13 | Dual-path knowledge retrieval | Embeddings use the same OpenAI-compatible endpoint as runbook RAG. No new embedding infrastructure. |

**Critical constraints from project-context.md:**

- **"NEVER store vectors outside pgvector"** — case record embeddings go into the existing `case_records.alert_signature_embedding` column.
- **"NEVER auto-rollback"** — rollback is human-triggered only. Case record downgrade on rollback happens via the existing API endpoint.
- **"Unhappy Path & Failure Mode Discipline"** — case record creation is best-effort. Embedding failures, DB failures, and missing data must not crash the execution cycle or affect incident state.

### Technical Requirements

#### CaseRecord Model (Full)

```python
class CaseRecord(BaseModel):
    """Full Case Record for Learning Store persistence (AD-4, AD-20)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    alert_signature: str
    root_cause_code: str
    diagnosis_object: dict
    remediation_plan: dict
    outcome: str  # "success" | "failure"
    outcome_confidence: float = Field(ge=0.0, le=1.0)
    outcome_details: dict
    ocp_version: str
    cluster_context: dict = Field(default_factory=dict)
    diagnosis_summary: str = ""
    remediation_summary: str = ""
    fast_path_eligible: bool = True
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("outcome")
    @classmethod
    def _validate_outcome(cls, v: str) -> str:
        if v not in ("success", "failure"):
            raise ValueError(f"outcome must be 'success' or 'failure', got: {v!r}")
        return v
```

#### Alert Signature Construction

The alert signature is a normalized text string built from alert metadata for embedding:

```python
def build_alert_signature(alerts: list[dict]) -> str:
    """Build a deterministic alert signature for embedding.

    Combines alert names, labels, and annotations into a
    searchable text string for pgvector similarity matching.
    """
    parts = []
    for alert in sorted(alerts, key=lambda a: a.get("name", "")):
        name = alert.get("name", "")
        labels = alert.get("labels", {})
        namespace = labels.get("namespace", "")
        severity = labels.get("severity", "")
        summary = alert.get("annotations", {}).get("summary", "")
        parts.append(f"{name} {namespace} {severity} {summary}")
    return " | ".join(parts)
```

#### Database Migration

```sql
-- 015_extend_case_records.py
ALTER TABLE case_records ADD COLUMN incident_id UUID UNIQUE REFERENCES incidents(id);
ALTER TABLE case_records ADD COLUMN diagnosis_object JSONB;
ALTER TABLE case_records ADD COLUMN remediation_plan JSONB;
ALTER TABLE case_records ADD COLUMN outcome_details JSONB;
ALTER TABLE case_records ADD COLUMN fast_path_eligible BOOLEAN DEFAULT TRUE;

CREATE INDEX idx_case_records_incident ON case_records(incident_id);
CREATE INDEX idx_case_records_fast_path ON case_records(fast_path_eligible) WHERE fast_path_eligible = TRUE;
```

All new columns are NULLable for backward compatibility (the table was created empty by migration 005).

#### Case Record Writer

```python
async def create_case_record(incident_id: uuid.UUID) -> CaseRecord | None:
    """Create and persist a Case Record after incident resolution.

    Assembles all incident data (diagnosis, plan, outcome, cluster context),
    generates vector embeddings, and persists to case_records.

    Best-effort: failures are logged but never propagated to the caller.
    The execution cycle and incident state are never affected by case
    record creation failures.
    """
    try:
        pool = await get_pool()

        # Load all incident artifacts
        async with pool.acquire() as conn:
            alerts = await _load_incident_alerts(conn, incident_id)
            artifact = await _load_diagnosis(conn, incident_id)
            plan = await _load_remediation_plan(conn, incident_id)
            outcome = await _load_outcome(conn, incident_id)
            rollback_exists = await _check_rollback_exists(conn, incident_id)

        if artifact is None or outcome is None:
            logger.warning(
                "Missing required artifacts for case record",
                extra={"incident_id": str(incident_id)},
            )
            return None

        # Build alert signature for embedding
        alert_signature = build_alert_signature(alerts)

        # Generate embedding (best-effort)
        embedding = None
        try:
            embeddings = await embed_texts([alert_signature])
            if embeddings:
                embedding = embeddings[0]
        except Exception:
            logger.warning(
                "Embedding generation failed — persisting without vector",
                extra={"incident_id": str(incident_id)},
            )

        # Determine outcome and fast-path eligibility
        is_success = outcome.get("alert_resolved", False)
        refire_detected = outcome.get("refire_detected", False)
        fast_path_eligible = is_success and not rollback_exists and not refire_detected

        case_record = CaseRecord(
            incident_id=incident_id,
            alert_signature=alert_signature,
            root_cause_code=_extract_root_cause_code(artifact),
            diagnosis_object=artifact,
            remediation_plan=plan or {},
            outcome="success" if is_success else "failure",
            outcome_confidence=outcome.get("outcome_confidence", 0.2),
            outcome_details=outcome,
            ocp_version=_get_ocp_version(),
            cluster_context=_build_cluster_context(),
            diagnosis_summary=_summarize_diagnosis(artifact),
            remediation_summary=_summarize_plan(plan),
            fast_path_eligible=fast_path_eligible,
        )

        async with pool.acquire() as conn:
            await persist_case_record(conn, case_record, embedding)

        logger.info(
            "Case record created",
            extra={
                "incident_id": str(incident_id),
                "outcome": case_record.outcome,
                "fast_path_eligible": fast_path_eligible,
                "has_embedding": embedding is not None,
            },
        )

        return case_record

    except Exception:
        logger.exception(
            "Case record creation failed — non-fatal",
            extra={"incident_id": str(incident_id)},
        )
        return None
```

#### Execution Dispatcher Hook Point

In `_run_execution_cycle()` (execution_dispatcher.py), after the outcome is persisted and state transitioned (around line 233):

```python
    # --- EXISTING CODE (outcome persistence + state transition) ---
    # async with pool.acquire() as conn:
    #     async with conn.transaction():
    #         await persist_outcome_result(conn, outcome)
    #         await transition_incident_state(...)

    # --- NEW: Case record creation (best-effort, Story 4.1) ---
    try:
        from .case_record_writer import create_case_record
        case_record = await create_case_record(incident_id)
        if case_record:
            await _emit_execution_event(incident_id, "learning_store", "case_record_created")
    except Exception:
        logger.warning(
            "Case record creation failed — non-fatal",
            extra={"incident_id": str(incident_id)},
        )

    # --- EXISTING CODE (re-fire monitor, cooldown) ---
```

#### Re-fire Downgrade Hook

In `monitor_for_refire()` (outcome_observer.py), after setting `refire_detected = TRUE`:

```python
    if refired:
        # EXISTING: flag in outcome_results
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE outcome_results SET refire_detected = TRUE WHERE incident_id = $1",
                incident_id,
            )

        # NEW: downgrade case record (Story 4.1)
        try:
            from ..db.case_records import downgrade_case_record
            pool = await get_pool()
            async with pool.acquire() as conn:
                await downgrade_case_record(
                    conn, incident_id,
                    new_confidence=0.2,
                    reason="alert re-fired within monitoring window",
                )
        except Exception:
            logger.warning(
                "Case record downgrade failed on re-fire — non-fatal",
                extra={"incident_id": str(incident_id)},
            )
```

#### Rollback Downgrade Hook

In `trigger_rollback()` (api/rollback.py), after the rollback record is persisted:

```python
    # EXISTING: persist rollback record and audit log
    # ...

    # NEW: downgrade case record (Story 4.1)
    try:
        from ..db.case_records import downgrade_case_record
        async with pool.acquire() as conn:
            await downgrade_case_record(
                conn, incident_id,
                new_confidence=0.2,
                reason=f"rollback triggered by {user.username}",
            )
    except Exception:
        logger.warning(
            "Case record downgrade failed on rollback — non-fatal",
            extra={"incident_id": str(incident_id)},
        )
```

#### pgvector Notes (Latest — 2026)

The project uses pgvector 0.8.x with HNSW indexing on PostgreSQL 18:
- The existing HNSW index from migration 005 uses `vector_cosine_ops` with default `m=16`, `ef_construction=64`
- For production tuning: consider `ef_construction=200` and `halfvec` for storage efficiency (2x reduction), but current 1536-dimension `vector` type works fine at our scale
- `hnsw.iterative_scan = 'relaxed_order'` improves recall for filtered queries (e.g., `WHERE fast_path_eligible = TRUE AND outcome = 'success'`)
- At thousands of records, default parameters are fine. At millions+, increase `maintenance_work_mem` for index rebuilds and consider `halfvec`
- `CREATE INDEX CONCURRENTLY` recommended for production index builds on populated tables

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| asyncpg | latest | Already in pyproject.toml. DB persistence |
| pydantic | latest | Already in pyproject.toml. CaseRecord model |
| openai | latest | Already in pyproject.toml. Embedding generation via `embed_texts()` |

**No new dependencies required.** All packages were added in Epic 1/2. Case record persistence and embedding use existing infrastructure.

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/pipeline/case_record_writer.py` | Case record creation service — assembles data, generates embeddings, persists | NEW |
| `backend/alembic/versions/015_extend_case_records.py` | Migration: add incident_id, diagnosis_object, remediation_plan, outcome_details, fast_path_eligible to case_records | NEW |
| `backend/tests/models/test_case_record.py` | CaseRecord model validation tests | NEW |
| `backend/tests/pipeline/test_case_record_writer.py` | Case record creation unit tests (mocked embedding + DB) | NEW |
| `backend/tests/db/test_case_records_write.py` | Case record persistence + downgrade roundtrip tests (testcontainers) | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/models/case_record.py` | Add full `CaseRecord` model alongside existing `CaseRecordSummary` | UPDATE |
| `backend/src/models/__init__.py` | Export `CaseRecord` | UPDATE |
| `backend/src/db/case_records.py` | Add `persist_case_record()`, `downgrade_case_record()`, `get_case_record_by_incident()` | UPDATE |
| `backend/src/pipeline/execution_dispatcher.py` | Hook case record creation after outcome persistence | UPDATE |
| `backend/src/pipeline/outcome_observer.py` | Hook case record downgrade on re-fire detection | UPDATE |
| `backend/src/api/rollback.py` | Hook case record downgrade on rollback | UPDATE |
| `backend/tests/pipeline/test_execution_dispatcher.py` | Verify case record created after outcome | UPDATE |

### Dependency Direction (ENFORCED)

```
models/case_record.py → (nothing — leaf module per AD-4)
pipeline/case_record_writer.py → models/ (CaseRecord), db/case_records.py, db/connection.py, knowledge/embeddings.py, config/
db/case_records.py → models/case_record.py (CaseRecord for type reference)
pipeline/execution_dispatcher.py → pipeline/case_record_writer.py (lazy import, best-effort call)
pipeline/outcome_observer.py → db/case_records.py (downgrade call)
api/rollback.py → db/case_records.py (downgrade call)
```

- **NEVER**: `models/` imports from `agents/`, `pipeline/`, `api/`, or `db/`
- **NEVER**: Case record creation crashes the execution cycle. It is ALWAYS best-effort with try/except.
- **NEVER**: Case record creation modifies incident state. Incident state is governed by the state machine; case records are a side effect.
- **NEVER**: Embed or persist case records synchronously blocking the execution pipeline lock. If embedding is slow, it does NOT extend the lock hold time — case record creation runs AFTER the lock is released (after cooldown).
- **ALLOWED**: `pipeline/case_record_writer.py` imports from `knowledge/embeddings.py` (embedding generation)
- **ALLOWED**: `pipeline/case_record_writer.py` imports from `db/case_records.py` (persistence)
- **ALLOWED**: `db/case_records.py` grows with write operations alongside existing read operations

### Testing Requirements

**Unit tests** (`pytest -m unit`):
- `CaseRecord` validates `outcome` is "success" or "failure"
- `CaseRecord` validates `outcome_confidence` is 0–1
- `CaseRecord` defaults `fast_path_eligible` to True
- `build_alert_signature()` produces deterministic, sorted output from alert metadata
- `create_case_record()` with resolved outcome → success case record, `fast_path_eligible=True`
- `create_case_record()` with failed outcome → failure case record, `fast_path_eligible=False`
- `create_case_record()` with rollback present → `fast_path_eligible=False`
- `create_case_record()` with embedding failure → case record persisted without vector (warning logged)
- `create_case_record()` with missing diagnosis → returns None (warning logged, no crash)

**DB integration tests** (`pytest -m db`):
- `persist_case_record()` roundtrip with full data + embedding (testcontainers)
- `persist_case_record()` without embedding (NULL vector) — succeeds
- `downgrade_case_record()` reduces `outcome_confidence` and sets `fast_path_eligible=False`
- `get_case_record_by_incident()` returns correct record
- `search_similar_cases()` (existing) returns the newly persisted record when queried with a similar embedding
- `downgrade_case_record()` on non-existent record → no error (returns False)

**Pipeline integration tests** (`pytest -m pipeline`):
- Extend `test_execution_dispatcher.py`: after mock outcome observation, verify `create_case_record` was called
- Re-fire detection → verify `downgrade_case_record` was called

**Mock patterns:**
- Mock `embed_texts()` to return a deterministic 1536-dimension vector (e.g., `[0.1] * 1536`)
- Mock `embed_texts()` to raise `Exception` for embedding-failure tests
- Mock DB queries for incident artifacts using fixture data matching the real schema
- Override `_get_ocp_version()` in tests to return a fixed version string
- For downgrade tests: pre-insert a case record, then downgrade and verify field changes

### Anti-Patterns / DO NOT

- **DO NOT** make case record creation blocking or crash-prone. It runs AFTER the incident reaches its terminal state. Failures are logged, never propagated. The execution cycle is unaffected.
- **DO NOT** create a LangGraph node for case record persistence. This is a post-pipeline side effect, not a pipeline stage. No checkpoint needed — the incident state is already terminal.
- **DO NOT** hold the global remediation lock during case record creation. The lock covers execution → observation → cooldown only. Case record creation runs after the lock is released.
- **DO NOT** modify the existing `search_similar_cases()` query in `db/case_records.py`. The read path is correct and tested. Only add write operations.
- **DO NOT** modify `learning_store.py` or `apply_temporal_decay()`. Those are Epic 4.2's responsibility (temporal decay refinement). The existing implementation is sufficient for queries.
- **DO NOT** implement fast-path bypass logic. That's Story 4.3. This story only persists case records and makes them searchable.
- **DO NOT** modify the `case_records` HNSW index. Migration 005 already created it correctly. Only add supplementary indexes for new columns.
- **DO NOT** store embeddings outside pgvector. No FAISS, no Pinecone, no separate vector store.
- **DO NOT** generate embeddings synchronously in the request path. The case record writer is called from the execution dispatcher background loop, which is already async.
- **DO NOT** modify `models/execution.py`, `models/remediation.py`, `models/diagnosis.py`, or any earlier story models.
- **DO NOT** modify `pipeline/remediation_graph.py` or any LangGraph graph definitions.
- **DO NOT** create a separate REST API endpoint for case records in this story. The read API is Story 4.3's scope (fast-path needs to query it). Case record creation is internal pipeline logic.

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  models/
    case_record.py               # UPDATE: add full CaseRecord model
    __init__.py                  # UPDATE: export CaseRecord
  pipeline/
    case_record_writer.py        # NEW: case record creation service
    execution_dispatcher.py      # UPDATE: hook case record creation
    outcome_observer.py          # UPDATE: hook re-fire downgrade
  db/
    case_records.py              # UPDATE: add write operations
  api/
    rollback.py                  # UPDATE: hook rollback downgrade
backend/alembic/versions/
    015_extend_case_records.py   # NEW migration
backend/tests/
  models/
    test_case_record.py                  # NEW
  pipeline/
    test_case_record_writer.py           # NEW
    test_execution_dispatcher.py         # UPDATE: extend
  db/
    test_case_records_write.py           # NEW
```

### Latest Technology Notes

**pgvector 0.8.x on PostgreSQL 18 (current — August 2026):**
- HNSW index with `vector_cosine_ops` is the correct choice for cosine similarity search
- At current scale (hundreds to low thousands of records), default `m=16` and `ef_construction=64` are adequate
- For filtered queries (e.g., `WHERE fast_path_eligible = TRUE`), enable `hnsw.iterative_scan = 'relaxed_order'` at query time for better recall
- `halfvec` type (float16) offers 2x storage reduction with negligible recall loss — consider for production optimization but not required at MVP scale
- The existing `vector(1536)` type supports up to 2000 dimensions for HNSW — 1536 (text-embedding-3-small) is within limits
- `CREATE INDEX CONCURRENTLY` should be used for any index builds on populated tables in production

**OpenAI embeddings API (current):**
- `AsyncOpenAI` client is already used in `knowledge/embeddings.py`
- Batch embedding: the API accepts arrays of strings, reducing round trips
- Error handling: embedding failures should NOT block case record creation. Persist without vector and backfill later if needed
- Rate limiting: not a concern at case-record-creation frequency (one per incident resolution, not bulk)

### References

- [Source: ARCHITECTURE-SPINE.md#AD-3] — Two schema domains; case records are application schema
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types module; CaseRecord defined in `models/`
- [Source: ARCHITECTURE-SPINE.md#AD-20] — Case Record schema owned by Learning Store module in `db/`
- [Source: ARCHITECTURE-SPINE.md#AD-13] — Dual-path knowledge retrieval; embeddings via OpenAI-compatible endpoint
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout
- [Source: epics.md#Story 4.1] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 4] — FR-18 (case record persistence), FR-19 (temporal decay — 4.2), FR-20 (fast-path — 4.3)
- [Source: project-context.md#Data Model Violations] — "NEVER store vectors outside pgvector"
- [Source: project-context.md#Unhappy Path & Failure Mode Discipline] — Best-effort SSE, atomic transactions, degraded outcome signals
- [Source: project-context.md#Security Anti-Patterns] — "NEVER auto-rollback" (rollback is human-triggered)
- [Source: Story 3.5 spec] — ExecutionLog, OutcomeResult, monitor_for_refire(), execution_dispatcher hooks
- [Source: Story 2.4 spec] — ImmutableDiagnosisArtifact (diagnosis data for case records)
- [Source: Story 2.3 spec] — embed_texts() for vector embedding generation
- [Source: Story 1.2 spec] — Correlation layer 5 reads case_records (read-only consumer)
- [Source: migration 005] — case_records table already exists with HNSW index
- [Source: db/case_records.py] — search_similar_cases() read query (do not modify)
- [Source: knowledge/learning_store.py] — query_learning_store() + apply_temporal_decay() (do not modify)
- [Source: knowledge/embeddings.py] — embed_texts() embedding generation
- [Source: pipeline/execution_dispatcher.py] — _run_execution_cycle() hook point at lines 204–236
- [Source: pipeline/outcome_observer.py] — monitor_for_refire() hook point at lines 120–138
- [Source: api/rollback.py] — trigger_rollback() hook point
- [Source: epic-3-retro-2026-08-14.md] — Unhappy-path discipline rule, Epic 4 readiness assessment

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
