---
baseline_commit: c251eb79bfbfb636ec1af8e9b2475fa8ae0ad3fd
---

# Story 4.2: Temporal Decay & Version Relevance

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want the system to naturally favor recent, version-relevant fixes over old ones,
so that stale knowledge from previous cluster versions doesn't mislead diagnosis or remediation.

## Acceptance Criteria

1. **Given** a Case Record with a known age and OCP version **When** its effective confidence is calculated at query time **Then** it applies the formula: `effective_confidence = base_confidence × decay_factor(age) × version_relevance(OCP_version_then vs OCP_version_now)`

2. **Given** a Case Record from a different OCP major version than the current cluster **When** its version relevance is calculated **Then** it carries reduced version relevance compared to a record from the same major version

3. **Given** a Case Record that is several months old **When** its decay factor is calculated **Then** its effective confidence is lower than an identical record created recently

4. **Given** the decay parameters (decay rate, version relevance weights) **When** they are configured **Then** they are adjustable via Helm values or runtime API configuration

5. **Given** a similarity search against the Learning Store **When** results are ranked **Then** effective confidence (with temporal decay applied) is used for ranking, not raw base confidence

## Tasks / Subtasks

- [x] Task 1: Extend KnowledgeSettings with version relevance weights (AC: #1, #2, #4)
  - [x] 1.1 Add `version_relevance_same_major: float = 1.0` to `KnowledgeSettings` in `backend/src/config/knowledge_settings.py`
  - [x] 1.2 Add `version_relevance_different_major: float = 0.5` to `KnowledgeSettings`
  - [x] 1.3 Add `version_relevance_minor_penalty_per_version: float = 0.02` to `KnowledgeSettings`
  - [x] 1.4 Add env var loading: `LEARNING_STORE_VERSION_RELEVANCE_SAME_MAJOR`, `LEARNING_STORE_VERSION_RELEVANCE_DIFFERENT_MAJOR`, `LEARNING_STORE_VERSION_RELEVANCE_MINOR_PENALTY`
  - [x] 1.5 Helm values: add to `learningStore` section in `values.yaml` and wire env vars in `deployment-backend.yaml`

- [x] Task 2: Refine `apply_temporal_decay()` with configurable weights (AC: #1, #2, #3)
  - [x] 2.1 Modify `apply_temporal_decay()` in `backend/src/knowledge/learning_store.py` to accept optional `version_relevance_weights` dict parameter
  - [x] 2.2 Replace hardcoded 1.0/0.5 version relevance with configurable `version_relevance_same_major` and `version_relevance_different_major` from `KnowledgeSettings`
  - [x] 2.3 Add minor version distance penalty: within the same major, reduce by `minor_penalty_per_version × abs(case_minor - current_minor)`, clamped to floor of `version_relevance_different_major`
  - [x] 2.4 Extract version relevance calculation into a standalone `compute_version_relevance()` function for testability
  - [x] 2.5 Maintain backward compatibility: existing callers with `decay_half_life_days` parameter still work

- [x] Task 3: Add runtime API configuration for decay parameters (AC: #4)
  - [x] 3.1 Create DB migration `016_add_learning_store_config.py` with `learning_store_config` table: `key TEXT PRIMARY KEY`, `value TEXT NOT NULL`, `updated_at TIMESTAMPTZ`, `updated_by TEXT`
  - [x] 3.2 Create `backend/src/db/learning_store_config.py` with `get_config(conn, key) -> str | None`, `set_config(conn, key, value, actor) -> None`, `get_all_config(conn) -> dict[str, str]`
  - [x] 3.3 Create `backend/src/api/learning_store_config.py` with GET/PUT endpoints under `/api/v1/config/learning-store`
  - [x] 3.4 GET returns effective config (Helm defaults merged with DB overrides)
  - [x] 3.5 PUT updates specific config keys in DB, audit-logged via existing AuditMiddleware
  - [x] 3.6 On startup, load DB overrides and apply to the singleton `KnowledgeSettings` instance
  - [x] 3.7 Register router in `api/app.py`

- [x] Task 4: Update Helm chart with new defaults (AC: #4)
  - [x] 4.1 Add `versionRelevanceSameMajor: 1.0`, `versionRelevanceDifferentMajor: 0.5`, `versionRelevanceMinorPenalty: 0.02` to `learningStore` section in `values.yaml`
  - [x] 4.2 Add corresponding env vars to `deployment-backend.yaml`

- [x] Task 5: Tests — unit (AC: #1–#5)
  - [x] 5.1 `tests/knowledge/test_temporal_decay.py` — `compute_version_relevance()`: same major+minor=1.0, same major different minor with penalty, different major uses configured weight, minor penalty clamps to floor
  - [x] 5.2 `tests/knowledge/test_temporal_decay.py` — `apply_temporal_decay()` with configurable weights: version_relevance_different_major=0.3 gives lower score than default 0.5, custom half-life changes decay curve
  - [x] 5.3 `tests/knowledge/test_learning_store.py` (extend) — query_learning_store results ranked by effective_confidence with new weights
  - [x] 5.4 `tests/api/test_learning_store_config.py` — GET returns merged config, PUT updates DB and returns effective config, PUT audit-logged, GET after PUT reflects override

- [x] Task 6: Tests — integration (AC: #4)
  - [x] 6.1 `tests/db/test_learning_store_config.py` — set_config/get_config roundtrip (testcontainers), get_all_config returns all keys, set_config updates existing key
  - [x] 6.2 Verify startup config loading: DB override takes precedence over env default

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 4.1 (Case Record Persistence & Vector Embeddings) — DIRECT PREDECESSOR:**

Story 4.1 builds the WRITE side of the Learning Store. It creates:

- **`pipeline/case_record_writer.py`** — `create_case_record(incident_id)` assembles incident data, generates embeddings via `embed_texts()`, persists to `case_records` table. Case records include `ocp_version` and `outcome_confidence` — the two inputs to temporal decay.
- **`db/case_records.py`** (extended) — adds `persist_case_record()`, `downgrade_case_record()`, `get_case_record_by_incident()`. The existing `search_similar_cases()` is READ-ONLY and must not be modified by this story (Story 4.1 explicitly says so).
- **Migration `015_extend_case_records.py`** — adds `incident_id`, `diagnosis_object`, `remediation_plan`, `outcome_details`, `fast_path_eligible` columns to `case_records`. **IMPORTANT**: If 4.1 runs first, the migration numbering here must be `016_*`. If 4.2 runs first, it can use `015_*`. Check the latest migration before creating.
- **Anti-patterns from 4.1**: "DO NOT modify `learning_store.py` or `apply_temporal_decay()`. Those are Epic 4.2's responsibility (temporal decay refinement)." — **This story IS 4.2.** It is authorized to modify `learning_store.py`.

**From Story 4.0 (Manifest Generation Pipeline Stage):**

Story 4.0 is also `ready-for-dev`. It adds manifest generation between skeptic and dry-run. It has no overlap with Story 4.2 — different files, different concern. No coordination needed.

**From Story 3.5 (Serialized Execution, Outcome Observation & Rollback):**

Story 3.5 built the execution cycle that eventually triggers case record creation (via 4.1). Relevant to 4.2:

- **`config/execution_settings.py`** — `refire_window_seconds` governs re-fire detection window. No changes needed.
- **`pipeline/outcome_observer.py`** — after re-fire detection, calls `downgrade_case_record()` (added by 4.1) to reduce `outcome_confidence` to 0.2. This downgraded confidence feeds directly into temporal decay calculations in 4.2.

**From Story 2.3 (Knowledge Integration):**

- **`knowledge/learning_store.py`** — the READ side. Contains `apply_temporal_decay()` (current target for refinement) and `query_learning_store()` (already ranks by effective_confidence). THIS is the primary file this story modifies.
- **`knowledge/embeddings.py`** — `embed_texts()` for embedding generation. Not modified by this story.
- **`db/case_records.py`** — `search_similar_cases()` returns raw cosine similarity results. NOT modified by this story.

**From Epic 1 (foundation patterns):**

- **`config/knowledge_settings.py`** — `KnowledgeSettings` dataclass with `learning_store_decay_half_life_days: 90.0` and `learning_store_similarity_threshold: 0.75`. THIS is extended by this story with version relevance weights.
- **`api/app.py`** — registers routers via `app.include_router(...)`. This story adds a new router for learning store config.
- **`api/audit.py`** — `AuditMiddleware` automatically logs state-changing requests. Config updates are audit-logged automatically.

**From Epic 3 Retrospective:**

- Unhappy-path discipline: any config loading from DB must handle DB failures gracefully (fall back to Helm defaults). Config API failures return structured errors.

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-7 | Helm values seed → runtime API mutations to DB → restart merge | Decay config follows this pattern: env vars provide defaults, DB overrides take precedence, config reloaded on restart |
| AD-20 | Case Record schema owned by Learning Store | Config table is owned by the Learning Store module in `db/`. API endpoints in `api/`. |
| AD-25 | Audit logging | Config changes via API are audit-logged by the existing AuditMiddleware |
| AD-14 | Monorepo layout | New files follow established patterns |
| AD-3 | Two schema domains | Config table is application schema (NOT `langgraph_*`) |

**Critical constraints from project-context.md:**

- **"Configuration Layers"**: "Helm values seed initial config" → "Runtime API overrides persist to DB" → "On restart: Helm defaults load first, then DB overrides apply" → "DB always wins" → "All config changes are audit-logged."
- **"Unhappy Path & Failure Mode Discipline"**: DB config loading must handle failures gracefully (fall back to Helm defaults). Config API failures return structured errors per the API envelope.
- **"URL-path versioning"**: all REST routes under `/api/v1/`. Config routes: `/api/v1/config/learning-store`.
- **"API response envelope"**: every response wraps in `{data: T, meta: {timestamp, request_id}}`.

### Technical Requirements

#### Current `apply_temporal_decay()` — What Exists (DO NOT break)

```python
def apply_temporal_decay(
    case: dict,
    current_ocp_version: str = "4",
    decay_half_life_days: float | None = None,
) -> float:
    effective_half_life = (
        decay_half_life_days if decay_half_life_days is not None
        else _get_decay_half_life_days()
    )
    age_days = (datetime.now(timezone.utc) - case["created_at"]).days
    decay_factor = math.exp(-0.693 * age_days / effective_half_life)

    case_major = case["ocp_version"].split(".")[0]
    current_major = current_ocp_version.split(".")[0]
    version_relevance = 1.0 if case_major == current_major else 0.5

    return case["outcome_confidence"] * decay_factor * version_relevance
```

#### Refined Version — What This Story Produces

```python
def compute_version_relevance(
    case_ocp_version: str,
    current_ocp_version: str,
    same_major_weight: float = 1.0,
    different_major_weight: float = 0.5,
    minor_penalty_per_version: float = 0.02,
) -> float:
    """Compute version relevance between case and current cluster OCP versions.

    Same major version: starts at same_major_weight, reduced by
    minor_penalty_per_version for each minor version apart, clamped
    to different_major_weight as floor.

    Different major version: returns different_major_weight directly.
    """
    case_parts = case_ocp_version.split(".")
    current_parts = current_ocp_version.split(".")
    case_major = case_parts[0]
    current_major = current_parts[0]

    if case_major != current_major:
        return different_major_weight

    case_minor = int(case_parts[1]) if len(case_parts) > 1 else 0
    current_minor = int(current_parts[1]) if len(current_parts) > 1 else 0
    minor_distance = abs(current_minor - case_minor)

    relevance = same_major_weight - (minor_penalty_per_version * minor_distance)
    return max(relevance, different_major_weight)


def apply_temporal_decay(
    case: dict,
    current_ocp_version: str = "4",
    decay_half_life_days: float | None = None,
) -> float:
    """Compute effective confidence with temporal decay and version relevance.

    Formula: effective_confidence = base_confidence × decay_factor(age)
             × version_relevance(OCP_version_then vs OCP_version_now)
    """
    settings = get_knowledge_settings()
    effective_half_life = (
        decay_half_life_days if decay_half_life_days is not None
        else settings.learning_store_decay_half_life_days
    )
    age_days = (datetime.now(timezone.utc) - case["created_at"]).days
    decay_factor = math.exp(-0.693 * age_days / effective_half_life)

    version_relevance = compute_version_relevance(
        case["ocp_version"],
        current_ocp_version,
        same_major_weight=settings.version_relevance_same_major,
        different_major_weight=settings.version_relevance_different_major,
        minor_penalty_per_version=settings.version_relevance_minor_penalty_per_version,
    )

    return case["outcome_confidence"] * decay_factor * version_relevance
```

#### KnowledgeSettings Extension

```python
@dataclass(frozen=True)
class KnowledgeSettings:
    # ... existing fields ...
    learning_store_decay_half_life_days: float = 90.0
    learning_store_similarity_threshold: float = 0.75
    version_relevance_same_major: float = 1.0
    version_relevance_different_major: float = 0.5
    version_relevance_minor_penalty_per_version: float = 0.02

    @classmethod
    def from_env(cls) -> KnowledgeSettings:
        return cls(
            # ... existing env loading ...
            version_relevance_same_major=float(
                os.environ.get("LEARNING_STORE_VERSION_RELEVANCE_SAME_MAJOR", "1.0")
            ),
            version_relevance_different_major=float(
                os.environ.get("LEARNING_STORE_VERSION_RELEVANCE_DIFFERENT_MAJOR", "0.5")
            ),
            version_relevance_minor_penalty_per_version=float(
                os.environ.get("LEARNING_STORE_VERSION_RELEVANCE_MINOR_PENALTY", "0.02")
            ),
        )
```

#### Runtime API Configuration

DB schema (migration):
```sql
CREATE TABLE learning_store_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT DEFAULT ''
);
```

Valid config keys (validated at the API layer):
```python
VALID_CONFIG_KEYS = frozenset({
    "decay_half_life_days",
    "similarity_threshold",
    "version_relevance_same_major",
    "version_relevance_different_major",
    "version_relevance_minor_penalty_per_version",
})
```

API endpoints:

```
GET  /api/v1/config/learning-store
  → Returns effective config (Helm defaults + DB overrides)
  → Response: {data: {decay_half_life_days: 90.0, ...}, meta: {...}}

PUT  /api/v1/config/learning-store
  → Body: {decay_half_life_days: 45.0, version_relevance_different_major: 0.3}
  → Persists each key/value to learning_store_config table
  → Reloads the KnowledgeSettings singleton with new values
  → Response: {data: {<effective merged config>}, meta: {...}}
  → Audit-logged automatically by AuditMiddleware
```

Config loading priority (AD-7 pattern):
1. Helm values → env vars → `KnowledgeSettings.from_env()` → base defaults
2. DB overrides → `learning_store_config` table → applied on top
3. On restart: env vars load first, then DB overrides applied
4. Runtime API PUT → writes to DB + reloads singleton → immediate effect

#### Startup Config Override Loading

In `api/app.py` lifespan (after `_init_pgvector()`):

```python
async def _load_learning_store_overrides() -> None:
    """Load runtime config overrides from DB (AD-7 layered override)."""
    try:
        from ..db.learning_store_config import get_all_config
        pool = await get_pool()
        async with pool.acquire() as conn:
            overrides = await get_all_config(conn)
        if overrides:
            from ..config.knowledge_settings import apply_overrides
            apply_overrides(overrides)
            logger.info(
                "Learning store config overrides loaded from DB",
                extra={"keys": list(overrides.keys())},
            )
    except Exception:
        logger.warning("Failed to load learning store config overrides — using defaults")
```

#### Config Override Application

In `config/knowledge_settings.py`, add a function that reconstructs the singleton with overrides:

```python
def apply_overrides(overrides: dict[str, str]) -> None:
    """Apply runtime DB overrides to the cached settings.

    Rebuilds the singleton with override values applied on top
    of the current env-based defaults.
    """
    global _knowledge_settings
    base = _knowledge_settings or KnowledgeSettings.from_env()
    field_map = {
        "decay_half_life_days": ("learning_store_decay_half_life_days", float),
        "similarity_threshold": ("learning_store_similarity_threshold", float),
        "version_relevance_same_major": ("version_relevance_same_major", float),
        "version_relevance_different_major": ("version_relevance_different_major", float),
        "version_relevance_minor_penalty_per_version": (
            "version_relevance_minor_penalty_per_version", float
        ),
    }
    kwargs = {}
    for field_name in KnowledgeSettings.__dataclass_fields__:
        kwargs[field_name] = getattr(base, field_name)
    for key, value in overrides.items():
        if key in field_map:
            attr_name, cast = field_map[key]
            kwargs[attr_name] = cast(value)
    _knowledge_settings = KnowledgeSettings(**kwargs)
```

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| asyncpg | latest | Already in pyproject.toml. DB config read/write |
| pydantic | latest | Already in pyproject.toml. API request/response models |
| fastapi | latest | Already in pyproject.toml. Config API endpoints |

**No new dependencies required.** All packages were added in Epic 1.

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/alembic/versions/015_add_learning_store_config.py` | Migration: `learning_store_config` table for runtime overrides | NEW |
| `backend/src/db/learning_store_config.py` | DB operations: get_config, set_config, get_all_config | NEW |
| `backend/src/api/learning_store_config.py` | API endpoints: GET/PUT `/api/v1/config/learning-store` | NEW |
| `backend/tests/knowledge/test_temporal_decay.py` | Comprehensive tests for `compute_version_relevance()` and refined `apply_temporal_decay()` | NEW |
| `backend/tests/api/test_learning_store_config.py` | Config API endpoint tests | NEW |
| `backend/tests/db/test_learning_store_config.py` | Config DB operations tests (testcontainers) | NEW |

**IMPORTANT migration numbering**: If Story 4.1 has been implemented first and created migration `015_extend_case_records.py`, this migration must be `016_add_learning_store_config.py`. Check `backend/alembic/versions/` for the latest migration file before creating.

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/knowledge/learning_store.py` | Extract `compute_version_relevance()`, refine `apply_temporal_decay()` with configurable weights from `KnowledgeSettings` | UPDATE |
| `backend/src/config/knowledge_settings.py` | Add `version_relevance_same_major`, `version_relevance_different_major`, `version_relevance_minor_penalty_per_version` fields + `apply_overrides()` function | UPDATE |
| `backend/src/api/app.py` | Register `learning_store_config.router`, add `_load_learning_store_overrides()` to lifespan | UPDATE |
| `charts/openshift-ai-ops/values.yaml` | Add `versionRelevanceSameMajor`, `versionRelevanceDifferentMajor`, `versionRelevanceMinorPenalty` to `learningStore` section | UPDATE |
| `charts/openshift-ai-ops/templates/deployment-backend.yaml` | Add env vars for new config keys | UPDATE |
| `backend/tests/knowledge/test_learning_store.py` | Extend existing tests to verify configurable weights are used | UPDATE |

### Dependency Direction (ENFORCED)

```
config/knowledge_settings.py → (nothing — leaf config module)
knowledge/learning_store.py → config/knowledge_settings.py, db/case_records.py, knowledge/embeddings.py, models/case_record.py
db/learning_store_config.py → config/logging.py (logger only)
api/learning_store_config.py → db/learning_store_config.py, config/knowledge_settings.py, models/api.py
api/app.py → api/learning_store_config.py (router import)
```

- **NEVER**: `models/` imports from `api/`, `pipeline/`, `db/`, or `config/`
- **NEVER**: `config/` imports from `api/`, `pipeline/`, or `db/`
- **NEVER**: Modify `db/case_records.py` `search_similar_cases()` — the READ path is correct and tested (Story 4.1 explicitly protects it)
- **NEVER**: Modify `pipeline/case_record_writer.py` or any execution/outcome code
- **NEVER**: Modify `models/case_record.py` — `CaseRecordSummary` is stable and sufficient
- **ALLOWED**: `knowledge/learning_store.py` imports from `config/knowledge_settings.py` (already does)
- **ALLOWED**: `api/learning_store_config.py` imports from `db/learning_store_config.py` and `config/knowledge_settings.py`

### Testing Requirements

**Unit tests** (`pytest -m unit`):

`tests/knowledge/test_temporal_decay.py` — `compute_version_relevance()`:
- Same major AND minor version (e.g., `4.15.0` vs `4.15.0`) → returns `same_major_weight` (1.0)
- Same major, 1 minor apart (e.g., `4.14.0` vs `4.15.0`) → returns `1.0 - 0.02 = 0.98`
- Same major, 10 minors apart (e.g., `4.5.0` vs `4.15.0`) → returns `1.0 - 0.20 = 0.80`
- Same major, 30+ minors apart → clamped to `different_major_weight` floor (0.5)
- Different major version (e.g., `3.11.0` vs `4.15.0`) → returns `different_major_weight` (0.5)
- Custom weights: `different_major_weight=0.3` → different major returns 0.3
- Custom minor penalty: `minor_penalty_per_version=0.05` → 5 minors apart = 0.75
- Edge cases: version strings without minor (e.g., `"4"` vs `"4.15"`) → handled gracefully

`tests/knowledge/test_temporal_decay.py` — `apply_temporal_decay()` with new weights:
- Same behavior as before with default weights (backward compatibility)
- Custom `version_relevance_different_major=0.3` via patched settings → lower score for cross-major
- Minor version penalty applied correctly through settings
- Decay factor unchanged (exponential half-life formula)

`tests/knowledge/test_learning_store.py` (extend existing):
- `query_learning_store` with two cases: one same-version recent, one different-major old → ranking reflects both decay and version relevance
- Configurable weights change ranking order when version penalty is increased

`tests/api/test_learning_store_config.py`:
- GET `/api/v1/config/learning-store` → returns effective config with all keys, 200
- PUT `/api/v1/config/learning-store` with `{decay_half_life_days: 45}` → updates DB, returns merged config, 200
- PUT with invalid key → 422 validation error
- PUT with non-numeric value for float field → 422 validation error
- GET after PUT → reflects the override
- Multiple PUTs → latest wins

**DB integration tests** (`pytest -m db`):

`tests/db/test_learning_store_config.py`:
- `set_config(conn, "decay_half_life_days", "45.0", "test-user")` → persisted
- `get_config(conn, "decay_half_life_days")` → returns "45.0"
- `get_all_config(conn)` → returns all keys
- `set_config` on existing key → updates value and `updated_at`
- `get_config` for non-existent key → returns None

**Mock patterns:**
- Patch `get_knowledge_settings()` to return custom `KnowledgeSettings` with different weights
- Use `reset_knowledge_settings()` in test teardown to clear cached singleton
- Use FastAPI `TestClient` for API endpoint tests
- Use `tmp_path` or equivalent for isolated DB tests (testcontainers)

### Anti-Patterns / DO NOT

- **DO NOT** modify `db/case_records.py` `search_similar_cases()`. The READ query is correct, tested, and explicitly protected by Story 4.1. Temporal decay is applied in Python after query results return — this is the correct pattern at current scale.
- **DO NOT** push temporal decay into the SQL query. Computing decay in Python (post-query) is correct for the current data volume (thousands of records). SQL-based decay would require storing OCP version parsing logic in the DB and is premature optimization.
- **DO NOT** modify `models/case_record.py`. The `CaseRecordSummary` model is stable. The `effective_confidence` field is already populated by `query_learning_store()` after applying temporal decay.
- **DO NOT** modify `pipeline/case_record_writer.py` or any execution/outcome pipeline code. This story is READ-SIDE refinement only.
- **DO NOT** implement fast-path bypass logic. That is Story 4.3's scope. This story only refines how existing case records are scored and ranked.
- **DO NOT** modify the existing test assertions that check hardcoded values (e.g., `result < 0.5` for different major). Instead, add NEW tests that verify configurable weights while preserving existing tests for backward compatibility.
- **DO NOT** create a new Pydantic model for config — use simple dict/dataclass patterns consistent with other config modules in the project.
- **DO NOT** require authentication for the config API in this story — the existing `AuditMiddleware` + OpenShift OAuth already covers this (all endpoints require bearer token per AD-12).
- **DO NOT** implement config versioning or rollback. Simple key-value override is sufficient for MVP.
- **DO NOT** add version_relevance logic to the correlation engine (Epic 1). Temporal decay applies only in the Learning Store query path.

### Project Structure Notes

All new/modified files align with AD-14 monorepo layout:
```
backend/src/
  config/
    knowledge_settings.py           # UPDATE: add version relevance fields + apply_overrides()
  knowledge/
    learning_store.py               # UPDATE: extract compute_version_relevance(), refine apply_temporal_decay()
  db/
    learning_store_config.py        # NEW: config DB operations
  api/
    app.py                          # UPDATE: register config router, load overrides on startup
    learning_store_config.py        # NEW: config API endpoints
backend/alembic/versions/
    015_add_learning_store_config.py # NEW migration (or 016 if 4.1 ran first)
backend/tests/
  knowledge/
    test_temporal_decay.py          # NEW: comprehensive decay + version relevance tests
    test_learning_store.py          # UPDATE: extend with configurable weight tests
  api/
    test_learning_store_config.py   # NEW: config API tests
  db/
    test_learning_store_config.py   # NEW: config DB roundtrip tests
charts/openshift-ai-ops/
    values.yaml                     # UPDATE: add version relevance defaults
    templates/deployment-backend.yaml # UPDATE: add env vars
```

Estimated file count: 5 new + 6 modified = 11 files total (well within the 25-file story size limit).

### Latest Technology Notes

**pgvector 0.8.x — temporal decay at query time:**
- Temporal decay is computed in Python after `search_similar_cases()` returns results. This is correct because:
  - The decay formula requires the CURRENT OCP version (runtime context, not stored in DB)
  - Python-side computation is simple and fast at current scale (top-k results, typically <10)
  - SQL-based decay would require complex version parsing in PostgreSQL
- At millions of records, consider a materialized view or a periodic batch job that pre-computes `effective_confidence` for filtering. Not needed at MVP scale.

**Config override pattern (AD-7):**
- The project uses the pattern: Helm → env vars → `from_env()` → frozen dataclass singleton
- Runtime overrides reconstruct the singleton with DB values applied on top
- `reset_knowledge_settings()` exists for test isolation
- New `apply_overrides()` follows the same pattern — reconstructs with overrides

**Version string parsing:**
- OCP versions follow semver: `4.15.3`, `4.14.0`, `3.11.0`
- The parsing handles versions with or without minor/patch components
- Production clusters always have major.minor at minimum

### References

- [Source: epics.md#Story 4.2] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 4] — FR-19 (temporal decay), FR-18 (case record persistence — 4.1), FR-20 (fast-path — 4.3)
- [Source: ARCHITECTURE-SPINE.md#AD-7] — Layered override: Helm seed → runtime API → DB wins on restart
- [Source: ARCHITECTURE-SPINE.md#AD-20] — Case Record schema owned by Learning Store module
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit logging for config changes
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout
- [Source: project-context.md#Configuration Layers] — Helm defaults → runtime API → DB overrides → audit-logged
- [Source: project-context.md#Unhappy Path & Failure Mode Discipline] — Graceful degradation on DB failures
- [Source: knowledge/learning_store.py] — Current `apply_temporal_decay()` and `query_learning_store()` implementations
- [Source: config/knowledge_settings.py] — Current `KnowledgeSettings` with `learning_store_decay_half_life_days`
- [Source: db/case_records.py] — `search_similar_cases()` READ query (do NOT modify)
- [Source: models/case_record.py] — `CaseRecordSummary` with `effective_confidence` field
- [Source: charts/openshift-ai-ops/values.yaml] — `learningStore.decayHalfLifeDays: 90`
- [Source: charts/openshift-ai-ops/templates/deployment-backend.yaml] — env var injection for learning store settings
- [Source: api/app.py] — Router registration pattern, lifespan startup hooks
- [Source: api/audit.py] — AuditMiddleware for automatic state-change logging
- [Source: tests/knowledge/test_learning_store.py] — Existing test patterns for temporal decay and query_learning_store
- [Source: Story 4.1 spec] — Anti-pattern: "DO NOT modify learning_store.py — that's 4.2's job"
- [Source: Story 3.5 spec] — Re-fire downgrade sets outcome_confidence to 0.2 (feeds into decay)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (Cursor)

### Debug Log References

None — clean implementation with no blocking issues.

### Completion Notes List

- Extended `KnowledgeSettings` with `version_relevance_same_major`, `version_relevance_different_major`, and `version_relevance_minor_penalty_per_version` fields with env var loading (Task 1)
- Extracted `compute_version_relevance()` as standalone testable function; refined `apply_temporal_decay()` to use configurable weights from `KnowledgeSettings` singleton — backward compatible with existing callers (Task 2)
- Created `learning_store_config` table (migration 016), DB operations module, and REST API endpoints (GET/PUT `/api/v1/config/learning-store`) following AD-7 layered override pattern (Task 3)
- Added `_load_learning_store_overrides()` to app lifespan startup; registered config router (Task 3)
- Updated Helm `values.yaml` with `versionRelevanceSameMajor`, `versionRelevanceDifferentMajor`, `versionRelevanceMinorPenalty` and wired corresponding env vars in `deployment-backend.yaml` (Task 4)
- 18 unit tests for `compute_version_relevance()` and `apply_temporal_decay()` — all passing (Task 5)
- 14 existing learning store tests pass unchanged — backward compatibility confirmed (Task 5)
- 7 API integration tests and 8 DB integration tests created (require testcontainers/Docker for CI) (Tasks 5-6)
- Full unit test suite: 724 passed, 4 pre-existing failures unrelated to this story

### File List

**New files:**
- `backend/alembic/versions/016_add_learning_store_config.py`
- `backend/src/db/learning_store_config.py`
- `backend/src/api/learning_store_config.py`
- `backend/tests/knowledge/test_temporal_decay.py`
- `backend/tests/api/test_learning_store_config.py`
- `backend/tests/db/test_learning_store_config.py`

**Modified files:**
- `backend/src/config/knowledge_settings.py`
- `backend/src/knowledge/learning_store.py`
- `backend/src/api/app.py`
- `charts/openshift-ai-ops/values.yaml`
- `charts/openshift-ai-ops/templates/deployment-backend.yaml`
- `backend/tests/knowledge/test_learning_store.py`

## Change Log

- 2026-08-14: Story 4.2 implemented — temporal decay with configurable version relevance weights, runtime config API, Helm chart updates, comprehensive test coverage

## Senior Developer Review (AI)

**Review Date:** 2026-08-14
**Review Outcome:** Approve (with minor patches applied)

### Action Items

- [x] [HIGH] ZeroDivisionError if `decay_half_life_days` set to 0 via API — added range validation in PUT endpoint (min 1.0) and defensive floor clamp in `apply_temporal_decay()`
- [x] [LOW] `ConfigUpdateRequest` Pydantic model defined but never used — removed dead code, removed unused `pydantic` import
- [x] [LOW] PUT endpoint multi-key writes not wrapped in transaction — deferred (pre-existing pattern, <5 keys, extremely low risk)

### Review Follow-ups (AI)

- [x] [AI-Review] Add range validation for config values in PUT endpoint (decay_half_life_days >= 1.0, relevance weights 0-1)
- [x] [AI-Review] Remove unused ConfigUpdateRequest model and pydantic import
- [x] [AI-Review] Add defensive floor clamp (max(half_life, 1.0)) in apply_temporal_decay

## Code Review Record

### Review Model Used

Claude Opus 4.6 (Cursor) — same session (autonomous review)

### Review Findings

| # | Source | Title | Severity | Bucket |
|---|--------|-------|----------|--------|
| 1 | blind+edge | ZeroDivisionError if `decay_half_life_days` set to 0 via API | HIGH | patch (fixed) |
| 2 | blind | `ConfigUpdateRequest` model defined but never used | LOW | patch (fixed) |
| 3 | blind | PUT multi-key writes not wrapped in transaction | LOW | defer |
| 4 | edge | Non-integer OCP minor version would raise ValueError | LOW | dismiss |
| 5 | edge | Future `created_at` could amplify confidence (clock skew) | LOW | dismiss |
| 6 | auditor | Task 2.1 literal says "dict parameter" but impl reads from settings | LOW | dismiss |

**Summary:** 2 patch (fixed), 1 deferred, 3 dismissed.

### Decisions Needed / Decisions Taken

None — no ambiguous design questions found. All findings had unambiguous fixes.

### Fixes Applied

1. Added `_VALUE_CONSTRAINTS` dict with range bounds for all config keys (decay_half_life_days: 1-3650, others: 0-1)
2. Added range validation logic in PUT endpoint after numeric check
3. Added `effective_half_life = max(effective_half_life, 1.0)` floor clamp in `apply_temporal_decay()`
4. Removed unused `ConfigUpdateRequest` class and `pydantic.BaseModel` import
5. Added `test_zero_half_life_clamped_to_floor` unit test
6. Added `test_put_zero_half_life_returns_422` and `test_put_negative_half_life_returns_422` API tests
