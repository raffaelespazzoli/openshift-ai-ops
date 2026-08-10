# Story 3.4: Human Approval Workflow (Backend API)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call SRE,
I want to review and approve or reject remediation plans that require my judgment,
so that I maintain control over cluster changes while benefiting from AI-prepared context.

## Acceptance Criteria

1. **Given** a remediation plan is queued for human approval **When** the approval API endpoint is queried **Then** it returns full context: diagnosis summary, complete remediation plan, skeptic challenge/response, dry-run results (if available), and blast radius assessment

2. **Given** an authenticated SRE calls the approve endpoint **When** approval is submitted **Then** the approval is recorded with the approver's identity (from OAuth token) and timestamp **And** the incident state transitions from `awaiting_approval` to `executing` via the state machine function **And** the approval is written to the `audit_log` table via the audit middleware

3. **Given** an authenticated SRE calls the reject endpoint **When** rejection is submitted with a reason **Then** the rejection is recorded with the rejector's identity, timestamp, and reason **And** the incident state transitions from `awaiting_approval` to `failed` via the state machine function

4. **Given** a remediation plan with `node` or `cluster` blast radius **When** the minimum review time is configured (e.g., 60 seconds) **Then** the approve action is not available until the minimum review time has elapsed since the plan was queued **And** the minimum review time is configurable and can be disabled

5. **Given** an SRE approves a remediation **When** they also want to adjust future policy for this category **Then** the API supports modifying the policy gate thresholds for the matching severity/blast-radius/confidence combination **And** the policy change is audit-logged

## Tasks / Subtasks

- [ ] Task 1: Approval/Rejection request/response models (AC: #1, #2, #3)
  - [ ] 1.1 Create `backend/src/models/approval.py` with `ApprovalRequest`, `RejectionRequest`, `ApprovalRecord`, `ApprovalContext` models
  - [ ] 1.2 `ApprovalRecord` fields: `id: UUID`, `incident_id: UUID`, `plan_id: UUID`, `action: str` (approved|rejected), `actor: str`, `reason: str | None`, `created_at: datetime`
  - [ ] 1.3 `ApprovalContext` fields: `incident_id: UUID`, `state: str`, `diagnosis_summary: dict`, `remediation_plan: dict`, `skeptic_verdict: dict | None`, `dry_run_result: dict | None`, `blast_radius: str`, `policy_decision: dict | None`, `queued_at: datetime`, `minimum_review_seconds: int | None`, `review_time_remaining: float | None`
  - [ ] 1.4 `RejectionRequest` fields: `reason: str` (required — must explain why)
  - [ ] 1.5 Export from `backend/src/models/__init__.py`

- [ ] Task 2: Approval configuration (AC: #4)
  - [ ] 2.1 Create `backend/src/config/approval_settings.py` with `ApprovalSettings`
  - [ ] 2.2 Settings: `minimum_review_seconds_node: int` (default 60), `minimum_review_seconds_cluster: int` (default 60), `minimum_review_enabled: bool` (default True)
  - [ ] 2.3 Wire env vars: `APPROVAL_MIN_REVIEW_NODE`, `APPROVAL_MIN_REVIEW_CLUSTER`, `APPROVAL_MIN_REVIEW_ENABLED`

- [ ] Task 3: Approval database operations (AC: #1, #2, #3)
  - [ ] 3.1 Create `backend/src/db/approval.py` with `persist_approval_record()`, `load_approval_context()`, `list_awaiting_approval()`
  - [ ] 3.2 `load_approval_context()` joins `incidents`, `remediation_plans`, `immutable_diagnoses`, `remediation_skeptic_reviews`, `dry_run_results`, `policy_decisions` for full approval context
  - [ ] 3.3 Create Alembic migration `011_add_approval_records.py` for `approval_records` table
  - [ ] 3.4 Table schema: `id UUID PK, incident_id UUID FK UNIQUE, plan_id UUID FK, action TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT, created_at TIMESTAMPTZ DEFAULT NOW()`

- [ ] Task 4: Approval API endpoints (AC: #1, #2, #3, #4)
  - [ ] 4.1 Create `backend/src/api/approval.py` with `router = APIRouter()`
  - [ ] 4.2 `GET /api/v1/incidents/{incident_id}/approval` — returns `ApprovalContext` with full decision context
  - [ ] 4.3 `POST /api/v1/incidents/{incident_id}/approve` — approve the remediation plan
  - [ ] 4.4 `POST /api/v1/incidents/{incident_id}/reject` — reject the remediation plan (requires `reason` in body)
  - [ ] 4.5 `GET /api/v1/incidents/awaiting-approval` — list all incidents awaiting approval (for navigation badge count)
  - [ ] 4.6 Minimum review time enforcement: reject approve action with 409 Conflict if review time not elapsed

- [ ] Task 5: State transitions and SSE events (AC: #2, #3)
  - [ ] 5.1 On approve: `transition(IncidentState.AWAITING_APPROVAL, IncidentState.EXECUTING)` via state machine
  - [ ] 5.2 On reject: `transition(IncidentState.AWAITING_APPROVAL, IncidentState.FAILED)` via state machine
  - [ ] 5.3 Emit SSE event `incident.state_changed` on approve/reject
  - [ ] 5.4 Emit SSE event `incident.approval_decision` with action + actor details

- [ ] Task 6: Policy adjustment endpoint (AC: #5)
  - [ ] 6.1 Add `POST /api/v1/policy/adjust` endpoint to `backend/src/api/approval.py`
  - [ ] 6.2 Accept severity, blast_radius, confidence combination and new threshold values
  - [ ] 6.3 Persist adjustment to DB (preparation for Story 6.4's full runtime API)
  - [ ] 6.4 Audit-log the policy change with actor identity

- [ ] Task 7: Helm chart updates (AC: #4)
  - [ ] 7.1 Add `approval` section to `values.yaml` with minimum review time configuration
  - [ ] 7.2 Wire `APPROVAL_*` env vars into backend Deployment template

- [ ] Task 8: Register approval router (AC: #1-#5)
  - [ ] 8.1 Import and register `approval.router` in `api/app.py`

- [ ] Task 9: Tests — unit (AC: #1–#5)
  - [ ] 9.1 `tests/models/test_approval.py` — ApprovalRecord, ApprovalContext, RejectionRequest model validation
  - [ ] 9.2 `tests/api/test_approval.py` — endpoint tests with TestClient: approve (success, already-approved, wrong state), reject (success, missing reason), approval context retrieval, awaiting list, minimum review time enforcement (409 when too early)
  - [ ] 9.3 `tests/api/test_approval.py` — policy adjustment endpoint with audit log verification

- [ ] Task 10: Tests — integration (AC: #2, #3)
  - [ ] 10.1 `tests/db/test_approval.py` — persist_approval_record roundtrip (testcontainers), load_approval_context joins, list_awaiting_approval
  - [ ] 10.2 `tests/api/test_approval.py` (extend) — full flow: create incident in awaiting_approval → approve → verify state is executing; create incident → reject → verify state is failed

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 3.3 (Dry-Run Pre-Flight & Policy Gate):**

Story 3.3 is the direct predecessor — it transitions incidents to `awaiting_approval`:

- **`pipeline/remediation_runner.py`** — After 3.3: runner reads `policy_decision` from graph output. If NOT auto-approved, calls `transition(IncidentState.DIAGNOSED, IncidentState.AWAITING_APPROVAL)`. This story's API picks up from there.
- **`models/policy_gate.py`** — `DryRunResult`, `PolicyDecision`, `PolicyDimension`. The approval context endpoint loads these for display.
- **`db/policy_gate.py`** — `persist_dry_run_result()` and `persist_policy_decision()` write to `dry_run_results` and `policy_decisions` tables. This story READS from these tables.
- **`config/policy_settings.py`** — `PolicyMatrixSettings` with default-deny configuration. This story's policy adjustment endpoint modifies these thresholds at runtime (preparation for Story 6.4).
- **`pipeline/remediation_graph.py`** — `RemediationState` after 3.3 includes: `dry_run_result`, `policy_decision`. These are persisted by the runner.

**Critical flow from 3.3:**
- The policy gate decides `awaiting_approval` when ANY dimension fails or evidence is incomplete. The incident is then in `awaiting_approval` state with all context persisted (plan, dry-run, policy decision) and waiting for a human to approve or reject.
- `policy_decisions.reasoning` field contains a human-readable explanation of why approval is needed.

**From Story 3.2 (Remediation Skeptic):**

- **`db/remediation_skeptic.py`** — `persist_remediation_skeptic_record()` writes to `remediation_skeptic_reviews`. The approval context endpoint loads the skeptic challenge/verdict for display.
- **`models/remediation_skeptic.py`** — `RemediationSkepticChallenge`, `RemediationSkepticVerdict`. Serialized as JSONB in the DB.
- The skeptic assessment (challenge + verdict + reasoning) is critical context for the SRE when deciding to approve or reject.

**From Story 3.1 (Remediation Planner & Structured Plan):**

- **`db/remediation.py`** — `persist_remediation_plan()` writes to `remediation_plans` table. `load_immutable_artifact()` reads from `immutable_diagnoses`. Both are joined in the approval context query.
- **`models/remediation.py`** — `RemediationPlan` with `blast_radius: BlastRadius` (workload|namespace|node|cluster). The minimum review time is keyed on `blast_radius` value.
- Table FK chain: `approval_records.incident_id → incidents.id`, `approval_records.plan_id → remediation_plans.id`.

**From Story 2.4 (ImmutableDiagnosisArtifact):**

- **`immutable_diagnoses` table** — Fields: `id UUID PK, incident_id UUID FK UNIQUE, diagnosis JSONB NOT NULL, skeptic_verdict JSONB NOT NULL, sealed_at TIMESTAMPTZ`. The approval context includes the diagnosis summary extracted from this.
- **`ImmutableDiagnosisArtifact`** fields include: `root_cause_code`, `causal_chain`, `affected_resources`, `evidence`, `evidence_gaps`, `confidence`, `agent_summary`. The approval context surfaces these for the SRE.

**From Epic 1 (API patterns, auth, audit, events):**

- **`api/incidents.py`** — Pattern for REST endpoints: `APIRouter`, `Depends(get_current_user)`, `UserInfo`, `ApiResponse` envelope, `ApiError` for errors.
- **`api/auth.py`** — `get_current_user(request)` extracts `UserInfo` with `username` and `groups` from OAuth token. The approver identity comes from here.
- **`api/audit.py`** — `AuditMiddleware` auto-logs state-changing requests. Approve/reject are POST requests, so they get auto-logged by the middleware. The explicit pipeline audit log (`write_audit_log()`) is for the policy adjustment.
- **`api/event_bus.py`** — `get_event_bus()` returns the singleton event bus for emitting SSE events.
- **`api/app.py`** — Router registration pattern: `app.include_router(router)`. Add approval router here.
- **`models/events.py`** — `EventNames`, `SSEEventData`, `BusEvent`. Use for emitting approval/rejection events.
- **`models/api.py`** — `ApiResponse`, `ApiMeta`, `ApiError`, error codes (`ERROR_NOT_FOUND`, `ERROR_UNAUTHORIZED`). Need to add `ERROR_CONFLICT` for minimum review time violation.

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-12 | OpenShift OAuth | All approval endpoints validate bearer token via `get_current_user()`. Approver identity extracted from token. |
| AD-19 | Canonical state machine | `awaiting_approval → executing` (approve) and `awaiting_approval → failed` (reject) are VALID transitions in `VALID_TRANSITIONS`. Use `transition()` function. |
| AD-25 | Audit logging | Approve/reject auto-logged by AuditMiddleware (POST method). Policy adjustment explicitly audit-logged via `write_audit_log()`. |
| AD-10 | SSE for real-time updates | Emit events on approve/reject so the frontend updates immediately. |
| AD-14 | Monorepo layout | New endpoint file in `api/approval.py`, new models in `models/approval.py`, new DB in `db/approval.py` |
| AD-4 | Shared types module | `ApprovalRecord`, `ApprovalContext` defined in `models/approval.py` |

**Critical constraints:**
- The approve/reject API ONLY works on incidents in `awaiting_approval` state. Any other state returns 409 Conflict.
- Minimum review time applies ONLY to `node` and `cluster` blast radius (not `workload` or `namespace`).
- The policy adjustment endpoint is a FOUNDATION for Story 6.4's full runtime configuration API. Keep it simple: accept new thresholds, persist them, audit-log.
- Rollback is NOT triggered here. That's Story 3.5.
- The approval API does NOT trigger execution. It transitions state to `executing`; the dispatcher (Story 3.5) picks up incidents in `executing` state.

### Technical Requirements

#### Approval Context Query

The approval context endpoint must join multiple tables to provide full SRE decision context:

```python
async def load_approval_context(conn, incident_id: UUID) -> dict | None:
    """Load full approval context for an incident in awaiting_approval state.

    Joins: incidents, remediation_plans, immutable_diagnoses,
           remediation_skeptic_reviews, dry_run_results, policy_decisions.
    """
    row = await conn.fetchrow("""
        SELECT
            i.id, i.state, i.severity, i.created_at, i.updated_at,
            rp.id AS plan_id, rp.plan, rp.blast_radius, rp.estimated_risk, rp.created_at AS plan_created_at,
            id.diagnosis, id.skeptic_verdict AS diagnosis_skeptic_verdict, id.sealed_at,
            dr.step_results, dr.rbac_check_passed, dr.quota_check_passed,
            dr.admission_check_passed, dr.overall_passed AS dry_run_passed,
            pd.dimensions, pd.evidence_complete, pd.evidence_gaps_empty,
            pd.auto_execution_approved, pd.reasoning AS policy_reasoning
        FROM incidents i
        LEFT JOIN remediation_plans rp ON rp.incident_id = i.id
        LEFT JOIN immutable_diagnoses id ON id.incident_id = i.id
        LEFT JOIN dry_run_results dr ON dr.incident_id = i.id
        LEFT JOIN policy_decisions pd ON pd.incident_id = i.id
        WHERE i.id = $1
    """, incident_id)

    if row is None:
        return None

    # Load skeptic reviews separately (multiple rounds possible)
    skeptic_rows = await conn.fetch("""
        SELECT round_number, challenge, response, verdict
        FROM remediation_skeptic_reviews
        WHERE incident_id = $1
        ORDER BY round_number
    """, incident_id)

    # ... assemble ApprovalContext ...
```

#### Approve Endpoint

```python
@router.post("/api/v1/incidents/{incident_id}/approve")
async def approve_remediation(
    request: Request,
    incident_id: uuid.UUID,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Approve a remediation plan for execution.

    Validates:
    - Incident is in awaiting_approval state
    - Minimum review time has elapsed (for node/cluster blast radius)

    On success: transitions to executing, records approval, emits SSE event.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock the incident row for update
            row = await conn.fetchrow(
                "SELECT state, updated_at FROM incidents WHERE id = $1 FOR UPDATE",
                incident_id,
            )

            if row is None:
                # return 404
                ...

            if row["state"] != IncidentState.AWAITING_APPROVAL.value:
                # return 409 Conflict — wrong state
                ...

            # Check minimum review time
            if not _review_time_elapsed(incident_id, row["updated_at"], conn):
                # return 409 Conflict — too early
                ...

            # Transition state
            new_state = transition(
                IncidentState.AWAITING_APPROVAL, IncidentState.EXECUTING
            )
            await conn.execute(
                "UPDATE incidents SET state = $1, updated_at = NOW() WHERE id = $2",
                new_state.value, incident_id,
            )

            # Record approval
            await persist_approval_record(
                conn,
                incident_id=incident_id,
                plan_id=plan_id,
                action="approved",
                actor=user.username,
            )

            # Audit log (explicit pipeline audit for the approval action)
            await write_audit_log(
                conn,
                actor=user.username,
                action="api.remediation.approved",
                target_resource=str(incident_id),
                detail={"plan_id": str(plan_id)},
            )

    # Emit SSE event (outside transaction)
    bus = get_event_bus()
    await bus.emit(EventNames.INCIDENT_STATE_CHANGED, SSEEventData(
        incident_id=str(incident_id),
        stage="approval",
        state="executing",
    ))

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(data={"status": "approved", "new_state": "executing"}, meta=meta).model_dump(mode="json")
```

#### Reject Endpoint

```python
@router.post("/api/v1/incidents/{incident_id}/reject")
async def reject_remediation(
    request: Request,
    incident_id: uuid.UUID,
    body: RejectionRequest,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Reject a remediation plan.

    Requires a reason explaining the rejection.
    Transitions incident to failed state.
    """
    # Similar pattern to approve:
    # 1. Lock incident row FOR UPDATE
    # 2. Verify state is awaiting_approval (409 if not)
    # 3. transition(AWAITING_APPROVAL, FAILED)
    # 4. persist_approval_record(..., action="rejected", reason=body.reason)
    # 5. write_audit_log(actor=user.username, action="api.remediation.rejected", ...)
    # 6. Emit SSE event
```

#### Minimum Review Time Logic

```python
def _get_minimum_review_seconds(blast_radius: str, settings: ApprovalSettings) -> int | None:
    """Return the minimum review seconds for a blast radius, or None if disabled."""
    if not settings.minimum_review_enabled:
        return None

    if blast_radius == BlastRadius.NODE.value:
        return settings.minimum_review_seconds_node
    elif blast_radius == BlastRadius.CLUSTER.value:
        return settings.minimum_review_seconds_cluster

    return None  # No minimum for workload/namespace


def _review_time_elapsed(queued_at: datetime, blast_radius: str, settings: ApprovalSettings) -> bool:
    """Check if the minimum review time has elapsed."""
    min_seconds = _get_minimum_review_seconds(blast_radius, settings)
    if min_seconds is None:
        return True  # No minimum — always elapsed

    elapsed = (datetime.now(timezone.utc) - queued_at).total_seconds()
    return elapsed >= min_seconds
```

#### Policy Adjustment Endpoint

```python
@router.post("/api/v1/policy/adjust")
async def adjust_policy(
    request: Request,
    body: PolicyAdjustmentRequest,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Adjust policy gate thresholds for a specific combination.

    This is a lightweight foundation for Story 6.4's full runtime API.
    Persists to DB; takes effect immediately.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await persist_policy_adjustment(conn, body, actor=user.username)
        await write_audit_log(
            conn,
            actor=user.username,
            action="api.policy.adjusted",
            target_resource="policy_matrix",
            detail=body.model_dump(mode="json"),
        )

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(data={"status": "adjusted"}, meta=meta).model_dump(mode="json")
```

#### Database Table

```sql
CREATE TABLE approval_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
    plan_id UUID NOT NULL REFERENCES remediation_plans(id),
    action TEXT NOT NULL CHECK (action IN ('approved', 'rejected')),
    actor TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approval_records_incident ON approval_records(incident_id);
```

UNIQUE on `incident_id` — one approval decision per incident. Cannot approve then reject the same incident.

#### API Error Codes

Add to `models/api.py`:
```python
ERROR_CONFLICT = "CONFLICT"
```

Use for:
- Approve/reject when incident is NOT in `awaiting_approval` state
- Approve when minimum review time has not elapsed

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.141.x | Already in pyproject.toml. New API endpoints |
| asyncpg | latest | Already in pyproject.toml. Approval persistence |
| pydantic | latest | Already in pyproject.toml. Request/response models |
| httpx | latest | Already in dev deps. TestClient for API tests |

**No new dependencies required.** All packages were added in Epic 1.

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/models/approval.py` | `ApprovalRecord`, `ApprovalContext`, `RejectionRequest`, `PolicyAdjustmentRequest` models | NEW |
| `backend/src/config/approval_settings.py` | `ApprovalSettings` — minimum review time config | NEW |
| `backend/src/api/approval.py` | Approval REST endpoints (approve, reject, context, list, policy adjust) | NEW |
| `backend/src/db/approval.py` | `persist_approval_record()`, `load_approval_context()`, `list_awaiting_approval()`, `persist_policy_adjustment()` | NEW |
| `backend/alembic/versions/011_add_approval_records.py` | Migration: `approval_records` table | NEW |
| `backend/tests/models/test_approval.py` | Model validation tests | NEW |
| `backend/tests/api/test_approval.py` | Endpoint tests (approve, reject, context, list, policy adjust, min review time) | NEW |
| `backend/tests/db/test_approval.py` | Persistence roundtrip tests | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/models/__init__.py` | Export `ApprovalRecord`, `ApprovalContext`, `RejectionRequest` | UPDATE |
| `backend/src/models/api.py` | Add `ERROR_CONFLICT` constant | UPDATE |
| `backend/src/api/app.py` | Import and register `approval.router` | UPDATE |
| `charts/openshift-ai-ops/values.yaml` | Add `approval` config section | UPDATE |
| `charts/openshift-ai-ops/templates/deployment-backend.yaml` | Add `APPROVAL_*` env vars | UPDATE |

### Dependency Direction (ENFORCED)

```
models/approval.py → (nothing — leaf module)
config/approval_settings.py → (nothing — leaf module, reads env vars only)
api/approval.py → models/ (ApprovalRecord, ApprovalContext, IncidentState, etc.), api/auth.py (get_current_user, UserInfo), db/approval.py, db/audit.py, api/event_bus.py, config/approval_settings.py, models/state_machine.py (transition)
db/approval.py → models/approval.py
```

- **NEVER**: `models/` imports from `agents/`, `pipeline/`, `api/`, or `db/`
- **NEVER**: `api/approval.py` imports from `pipeline/` or `agents/`
- **NEVER**: The approval endpoint triggers execution directly — it only transitions state; the dispatcher handles execution dispatch
- **ALLOWED**: `api/approval.py` imports from `db/approval.py` and `db/audit.py`
- **ALLOWED**: `api/approval.py` imports from `config/approval_settings.py`
- **ALLOWED**: `api/approval.py` imports `models/state_machine.py` for `transition()`

### Testing Requirements

**Unit tests** (`pytest -m unit`):
- `ApprovalRecord` validates `action` is one of: "approved", "rejected"
- `RejectionRequest` requires non-empty `reason`
- `ApprovalContext` validates all expected fields present
- Minimum review time logic: elapsed → True; not elapsed → False; disabled → True; workload blast radius → always True

**API integration tests** (`pytest -m api`):
- `GET /api/v1/incidents/{id}/approval` returns full context for awaiting incident
- `GET /api/v1/incidents/{id}/approval` returns 404 for non-existent incident
- `POST /api/v1/incidents/{id}/approve` — success case: incident in `awaiting_approval` → state becomes `executing`
- `POST /api/v1/incidents/{id}/approve` — wrong state: incident in `diagnosing` → 409 Conflict
- `POST /api/v1/incidents/{id}/approve` — too early: node blast radius, < 60s → 409 Conflict with `review_time_remaining` in detail
- `POST /api/v1/incidents/{id}/reject` — success case with reason → state becomes `failed`
- `POST /api/v1/incidents/{id}/reject` — missing reason → 422 Validation Error
- `GET /api/v1/incidents/awaiting-approval` — returns list of incidents in `awaiting_approval` state with count
- `POST /api/v1/policy/adjust` — success case → audit log entry created
- Unauthenticated requests → 401

**DB integration tests** (`pytest -m db`):
- `persist_approval_record()` roundtrip (testcontainers)
- UNIQUE constraint on `incident_id` prevents duplicate approvals
- `load_approval_context()` returns full join data correctly
- `load_approval_context()` returns None for non-existent incident
- `list_awaiting_approval()` returns only incidents in `awaiting_approval` state

**Mock patterns:**
- Use `AUTH_DISABLED=true` for TestClient tests (dev mode bypass)
- Create fixtures that insert incidents in various states (awaiting_approval, diagnosing, executing)
- Create fixture that inserts full context chain: incident → immutable_diagnosis → remediation_plan → dry_run_result → policy_decision
- Override `ApprovalSettings` in tests to test both enabled/disabled minimum review time
- Use `freezegun` or `unittest.mock.patch` to control time for minimum review time tests

### Anti-Patterns / DO NOT

- **DO NOT** trigger remediation execution from the approval endpoint. The endpoint transitions state to `executing`; the dispatcher (Story 3.5) picks up execution. This separation is critical for the global lock architecture (AD-18).
- **DO NOT** allow approval/rejection of incidents NOT in `awaiting_approval` state. Return 409 Conflict with clear explanation.
- **DO NOT** allow approval without minimum review time for node/cluster blast radius (when enabled). Return 409 with `review_time_remaining` in the error detail.
- **DO NOT** allow rejection without a reason. The reason is critical audit context.
- **DO NOT** implement the full runtime configuration API for policy matrix. That's Story 6.4. This story provides a lightweight adjustment endpoint that persists to DB — just enough for the "adjust policy during approval" AC.
- **DO NOT** implement rollback. That's Story 3.5.
- **DO NOT** implement the execution pipeline or global lock. That's Story 3.5.
- **DO NOT** implement the frontend UI for approval. That's Epic 5 (Story 5.4).
- **DO NOT** modify the state machine. Both transitions (`awaiting_approval → executing` and `awaiting_approval → failed`) already exist in `VALID_TRANSITIONS`.
- **DO NOT** modify pipeline code (`pipeline/`, `agents/`). This is an API-only story — all changes are in `api/`, `db/`, `models/`, `config/`.
- **DO NOT** implement SSE subscription endpoints. Those exist in `api/events.py` (Story 1.4). Just emit events via the event bus.
- **DO NOT** implement approval batching (approve all). Keep it per-incident — one approval per request.
- **DO NOT** modify `models/remediation.py`, `models/policy_gate.py`, or any Story 3.1–3.3 models.
- **DO NOT** add `litellm` or any LLM dependency. This is pure REST API logic.
- **DO NOT** implement confirmation modals or time delays in the API. Minimum review time is the server-side enforcement; the UI (Epic 5) handles UX.

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  models/
    approval.py             # NEW: ApprovalRecord, ApprovalContext, RejectionRequest, PolicyAdjustmentRequest
    api.py                  # UPDATE: add ERROR_CONFLICT
    __init__.py             # UPDATE: export new models
  config/
    approval_settings.py    # NEW: ApprovalSettings (minimum review time)
  api/
    approval.py             # NEW: Approval REST endpoints
    app.py                  # UPDATE: register approval router
  db/
    approval.py             # NEW: persist_approval_record, load_approval_context, list_awaiting_approval
backend/alembic/versions/
    011_add_approval_records.py  # NEW migration
backend/tests/
  models/
    test_approval.py             # NEW
  api/
    test_approval.py             # NEW
  db/
    test_approval.py             # NEW
charts/openshift-ai-ops/
  values.yaml                    # UPDATE: add approval section
  templates/
    deployment-backend.yaml      # UPDATE: add APPROVAL_* env vars
```

### Latest Technology Notes

**FastAPI endpoint patterns (from existing codebase):**
- All endpoints use `Depends(get_current_user)` for authentication
- State-changing requests are auto-logged by `AuditMiddleware`
- Error responses use `ApiError` model with appropriate HTTP status codes
- Response envelope: `ApiResponse(data=..., meta=ApiMeta(request_id=...))`.model_dump(mode="json")
- Use `conn.transaction()` for atomic operations (state transition + record persistence)
- Use `SELECT ... FOR UPDATE` to prevent concurrent approval race conditions

**Row-level locking for approval race conditions:**
- Two SREs might try to approve/reject the same incident simultaneously
- `SELECT ... FOR UPDATE` on the incident row prevents this
- First to acquire lock succeeds; second gets the updated state and receives 409 Conflict
- This is NOT the global remediation lock (AD-18) — that's Story 3.5's execution lock

**SSE event emission (from Epic 1 patterns):**
- `get_event_bus()` returns the singleton in-process asyncio event bus (AD-24)
- `bus.emit(EventNames.INCIDENT_STATE_CHANGED, SSEEventData(...))` — subscribing clients receive the event
- Event emission happens AFTER the transaction commits (outside `async with conn.transaction()`)
- If emission fails, the state transition is already committed — eventual consistency is acceptable

**OpenShift OAuth identity (from existing auth module):**
- `UserInfo.username` is the approver identity stored in `approval_records.actor`
- `UserInfo.groups` could be used for RBAC in future (e.g., only certain groups can approve) but is NOT required for this story
- In dev mode (`AUTH_DISABLED=true`), `get_current_user()` returns `UserInfo(username="dev-user")`

### Helm Values Addition

```yaml
approval:
  minimumReviewEnabled: true
  minimumReviewSecondsNode: 60       # Seconds before node-scoped plans can be approved
  minimumReviewSecondsCluster: 60    # Seconds before cluster-scoped plans can be approved
```

### References

- [Source: ARCHITECTURE-SPINE.md#AD-12] — OpenShift OAuth (approver identity from bearer token)
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine (`awaiting_approval → executing | failed`)
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit logging (approve/reject audit-logged)
- [Source: ARCHITECTURE-SPINE.md#AD-10] — SSE for real-time updates (emit on state change)
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout
- [Source: ARCHITECTURE-SPINE.md#AD-18] — Global remediation lock (NOT this story — Story 3.5)
- [Source: epics.md#Story 3.4] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 3] — FR-14 coverage (backend API portion)
- [Source: project-context.md#Security Anti-Patterns] — "Default-deny is the shipping default", "NEVER auto-rollback"
- [Source: Story 3.3 spec] — DryRunResult, PolicyDecision, state transitions to awaiting_approval
- [Source: Story 3.2 spec] — RemediationSkepticChallenge/Verdict, remediation_skeptic_reviews table
- [Source: Story 3.1 spec] — RemediationPlan model, remediation_plans table, BlastRadius enum
- [Source: Story 2.4 spec] — ImmutableDiagnosisArtifact, immutable_diagnoses table
- [Source: api/incidents.py] — REST endpoint pattern (router, get_current_user, ApiResponse envelope)
- [Source: api/auth.py] — UserInfo model (username, groups), get_current_user dependency
- [Source: api/audit.py] — AuditMiddleware auto-logging pattern for state-changing requests
- [Source: api/app.py] — Router registration pattern (app.include_router)
- [Source: models/state_machine.py] — `transition()`, `VALID_TRANSITIONS[AWAITING_APPROVAL] = [EXECUTING, FAILED]`
- [Source: db/audit.py] — `write_audit_log()` function signature and usage

## Code Review Record

### Review Model Used

(to be filled during review)

### Review Findings

(to be filled during review)

### Decisions Needed / Decisions Taken

(to be filled during review)

### Fixes Applied

(to be filled during review)
