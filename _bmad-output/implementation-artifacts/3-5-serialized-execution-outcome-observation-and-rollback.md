# Story 3.5: Serialized Execution, Outcome Observation & Rollback

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want remediations executed safely one at a time with automatic outcome monitoring and the option to roll back,
so that the cluster is never subjected to conflicting concurrent changes and I know immediately whether the fix worked.

## Acceptance Criteria

1. **Given** a remediation plan is approved (by policy gate or human) **When** execution begins **Then** a global lock is acquired via PostgreSQL row-level lock (`SELECT FOR UPDATE NOWAIT` on `remediation_locks` table) **And** if the lock cannot be acquired, execution waits until the current remediation completes

2. **Given** a remediation is queued for execution **When** the freshness gate runs before execution **Then** it re-validates that the originating alert is still firing and the diagnosis is still relevant to current cluster state **And** stale remediations (alert resolved during wait, or cluster state changed by a prior fix) are skipped with the diagnosis preserved as an informational case record

3. **Given** a fresh, locked remediation plan **When** it executes **Then** it uses the read-write MCP Server instance exclusively (bound to `cluster-admin` ServiceAccount) **And** execution steps are logged with timestamps to the incident record

4. **Given** execution completes **When** outcome observation begins **Then** the system monitors for the corresponding `resolved` webhook from AlertManager within a configurable timeout **And** it performs post-remediation verification by checking the `affected_resources` from the Structured Diagnosis Object via the read-only MCP Server

5. **Given** the originating alert resolves after execution **When** the outcome is recorded **Then** alert resolution is the primary success signal and direct resource verification is the corroborating signal **And** the outcome includes an `outcome_confidence` field reflecting the strength of corroborating evidence (not just binary success/failure) **And** the incident state transitions from `observing` to `resolved` via the state machine function

6. **Given** the alert does not resolve within the timeout **When** the outcome is recorded **Then** the incident state transitions from `observing` to `failed` via the state machine function

7. **Given** the alert re-fires within a configurable window after a "successful" resolution **When** the re-fire is detected **Then** the Case Record (when created in Epic 4) is retroactively downgraded and the remediation is flagged for review

8. **Given** a configurable cooldown period between remediations **When** the current remediation completes (success or failure) **Then** the global lock is held through outcome observation and the cooldown period before release

9. **Given** a completed remediation (success or failure) **When** an SRE reviews the outcome **Then** the rollback plan from the Remediation Plan is available via the API **And** rollback is human-triggered only — the system never initiates rollback automatically

10. **Given** an SRE triggers rollback **When** the rollback executes **Then** the rollback action is recorded as a failure signal (for the Learning Store in Epic 4) **And** the rollback execution is audit-logged with the actor's identity

## Tasks / Subtasks

- [x] Task 1: Execution and outcome models (AC: #3, #4, #5, #6, #7)
  - [x] 1.1 Create `backend/src/models/execution.py` with `ExecutionLog`, `ExecutionStepLog`, `OutcomeResult`, `OutcomeConfidence`, `RollbackRecord` models
  - [x] 1.2 `ExecutionStepLog` fields: `step_order: int`, `command: str`, `started_at: datetime`, `completed_at: datetime | None`, `success: bool`, `output: str`, `error: str | None`
  - [x] 1.3 `ExecutionLog` fields: `id: UUID`, `incident_id: UUID`, `plan_id: UUID`, `steps: list[ExecutionStepLog]`, `mcp_calls: list[dict]`, `started_at: datetime`, `completed_at: datetime | None`, `status: str` (running|completed|failed)
  - [x] 1.4 `OutcomeResult` fields: `id: UUID`, `incident_id: UUID`, `alert_resolved: bool`, `resolution_method: str` (webhook|timeout|verification), `resource_verification: dict | None`, `outcome_confidence: float` (0–1), `refire_detected: bool`, `observation_started_at: datetime`, `observation_completed_at: datetime | None`, `timeout_seconds: int`
  - [x] 1.5 `RollbackRecord` fields: `id: UUID`, `incident_id: UUID`, `plan_id: UUID`, `actor: str`, `steps_executed: list[ExecutionStepLog]`, `success: bool`, `created_at: datetime`
  - [x] 1.6 Export from `backend/src/models/__init__.py`

- [x] Task 2: Execution configuration (AC: #1, #4, #7, #8)
  - [x] 2.1 Create `backend/src/config/execution_settings.py` with `ExecutionSettings`
  - [x] 2.2 Settings: `observation_timeout_seconds: int` (default 300), `cooldown_seconds: int` (default 60), `refire_window_seconds: int` (default 600), `lock_poll_interval_seconds: int` (default 5)
  - [x] 2.3 Wire env vars: `EXECUTION_OBSERVATION_TIMEOUT`, `EXECUTION_COOLDOWN_SECONDS`, `EXECUTION_REFIRE_WINDOW`, `EXECUTION_LOCK_POLL_INTERVAL`

- [x] Task 3: Global remediation lock (AC: #1, #8)
  - [x] 3.1 Create `backend/src/db/remediation_lock.py` with `acquire_remediation_lock()`, `release_remediation_lock()`, `is_lock_held()`
  - [x] 3.2 Create Alembic migration for `remediation_locks` table — single row, acquired via `SELECT FOR UPDATE NOWAIT` (AD-18)
  - [x] 3.3 `acquire_remediation_lock(conn, incident_id) -> bool` — tries `SELECT FOR UPDATE NOWAIT`; returns False if lock held by another
  - [x] 3.4 Lock is held on a dedicated connection that stays open through execution + observation + cooldown
  - [x] 3.5 On connection drop (pod crash), PostgreSQL auto-releases the row lock — next pod acquires cleanly

- [x] Task 4: Freshness gate (AC: #2)
  - [x] 4.1 Create `backend/src/pipeline/freshness_gate.py` with `check_freshness(incident_id, artifact) -> FreshnessResult`
  - [x] 4.2 Query AlertManager API (or check for resolved webhook) to verify alert is still firing
  - [x] 4.3 Verify diagnosis is still relevant to current cluster state via read-only MCP
  - [x] 4.4 If stale: skip execution, preserve diagnosis as informational record, release lock

- [x] Task 5: Execution engine (AC: #3)
  - [x] 5.1 Create `backend/src/pipeline/execution_engine.py` with `execute_remediation(plan, mcp_client) -> ExecutionLog`
  - [x] 5.2 Execute each step sequentially via read-write MCP `execute()` method (Story 3.1 stubbed this)
  - [x] 5.3 Log each step with start/end timestamps and MCP call details
  - [x] 5.4 On step failure: stop execution, mark remaining steps as not-executed, return partial log
  - [x] 5.5 Transition incident state from `executing` to `observing` via state machine after execution completes

- [x] Task 6: Outcome observer (AC: #4, #5, #6, #7)
  - [x] 6.1 Create `backend/src/pipeline/outcome_observer.py` with `observe_outcome(incident_id, artifact, execution_log) -> OutcomeResult`
  - [x] 6.2 Monitor for `resolved` webhook via DB polling (check if the alert's resolved status was recorded by the webhook receiver)
  - [x] 6.3 Perform post-remediation verification: query `affected_resources` from the diagnosis via read-only MCP
  - [x] 6.4 Calculate `outcome_confidence`: 1.0 if both webhook + verification pass, 0.7 if webhook only, 0.5 if verification only, 0.2 if timeout
  - [x] 6.5 On timeout: transition incident to `failed`
  - [x] 6.6 On resolve: transition incident to `resolved`

- [x] Task 7: Re-fire detection (AC: #7)
  - [x] 7.1 Add re-fire detection logic to the outcome observer or as a post-observation hook
  - [x] 7.2 After a "resolved" outcome, monitor for the same alert fingerprint re-firing within `refire_window_seconds`
  - [x] 7.3 If re-fire detected: flag the incident for review, set `refire_detected = True` on the outcome

- [x] Task 8: Rollback API (AC: #9, #10)
  - [x] 8.1 Create `backend/src/api/rollback.py` with rollback endpoint
  - [x] 8.2 `POST /api/v1/incidents/{incident_id}/rollback` — execute the rollback plan from the RemediationPlan
  - [x] 8.3 Rollback executes via read-write MCP, same as forward execution
  - [x] 8.4 Record rollback as failure signal for Learning Store
  - [x] 8.5 Audit-log rollback with actor identity
  - [x] 8.6 Register rollback router in `api/app.py`

- [x] Task 9: Add execution + observation nodes to remediation graph (AC: #1–#8)
  - [x] 9.1 Add `freshness_gate` node after `policy_gate`
  - [x] 9.2 Add `execute` node after `freshness_gate`
  - [x] 9.3 Add `observe` node after `execute`
  - [x] 9.4 Update `RemediationState` to include: `freshness_result`, `execution_log`, `outcome_result`
  - [x] 9.5 Conditional edge: if freshness gate fails → skip to END (stale)

- [x] Task 10: Execution dispatcher (AC: #1)
  - [x] 10.1 Create `backend/src/pipeline/execution_dispatcher.py` (or extend `dispatcher.py`) to poll for incidents in `executing` state
  - [x] 10.2 Acquire global lock before dispatching execution
  - [x] 10.3 Handle lock contention: wait and retry with configurable interval
  - [x] 10.4 After execution + observation + cooldown: release lock

- [x] Task 11: Persistence (AC: #3, #4, #5, #10)
  - [x] 11.1 Create `backend/src/db/execution.py` with `persist_execution_log()`, `persist_outcome_result()`, `persist_rollback_record()`
  - [x] 11.2 Create Alembic migration for `execution_logs`, `outcome_results`, `rollback_records` tables
  - [x] 11.3 `execution_logs` table: `id UUID PK, incident_id UUID FK UNIQUE, plan_id UUID FK, steps JSONB NOT NULL, mcp_calls JSONB, started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, status TEXT NOT NULL`
  - [x] 11.4 `outcome_results` table: `id UUID PK, incident_id UUID FK UNIQUE, alert_resolved BOOL NOT NULL, resolution_method TEXT, resource_verification JSONB, outcome_confidence FLOAT NOT NULL, refire_detected BOOL DEFAULT FALSE, observation_started_at TIMESTAMPTZ, observation_completed_at TIMESTAMPTZ, timeout_seconds INT`
  - [x] 11.5 `rollback_records` table: `id UUID PK, incident_id UUID FK, plan_id UUID FK, actor TEXT NOT NULL, steps_executed JSONB, success BOOL NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW()`

- [x] Task 12: Helm chart updates (AC: #1, #4, #8)
  - [x] 12.1 Add `execution` section to `values.yaml` with observation timeout, cooldown, re-fire window
  - [x] 12.2 Wire `EXECUTION_*` env vars into backend Deployment template

- [x] Task 13: Tests — unit (AC: #1–#10)
  - [x] 13.1 `tests/models/test_execution.py` — ExecutionLog, OutcomeResult, RollbackRecord validation
  - [x] 13.2 `tests/pipeline/test_freshness_gate.py` — alert still firing → pass; alert resolved → stale; cluster state changed → stale
  - [x] 13.3 `tests/pipeline/test_execution_engine.py` — execute all steps successfully; step failure stops execution; MCP calls logged
  - [x] 13.4 `tests/pipeline/test_outcome_observer.py` — webhook resolves → resolved with high confidence; timeout → failed; verification pass/fail affects confidence score
  - [x] 13.5 `tests/api/test_rollback.py` — rollback success; rollback on wrong state → 409; audit log created

- [x] Task 14: Tests — integration (AC: #1, #3, #5, #10)
  - [x] 14.1 `tests/db/test_execution.py` — persist_execution_log, persist_outcome_result, persist_rollback_record roundtrip (testcontainers)
  - [x] 14.2 `tests/db/test_remediation_lock.py` — acquire lock, second acquire fails (NOWAIT), release + re-acquire succeeds; connection drop releases lock
  - [x] 14.3 `tests/pipeline/test_remediation_graph.py` (extend) — full graph with all nodes including execution + observation

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 3.4 (Human Approval Workflow — Backend API):**

Story 3.4 transitions incidents to `executing` state — this story picks up from there:

- **`api/approval.py`** — `approve_remediation()` calls `transition(IncidentState.AWAITING_APPROVAL, IncidentState.EXECUTING)`. After this, the incident is in `executing` state and waiting for the execution dispatcher.
- **`db/approval.py`** — `persist_approval_record()` records who approved. This story's execution uses the same incident_id to load the plan and execute.
- **`models/approval.py`** — `ApprovalRecord`, `ApprovalContext`. The rollback API will load approval context to verify the incident has been executed.
- **`config/approval_settings.py`** — `ApprovalSettings`. Not directly used by this story, but minimum review time enforcement happens before execution.

**Critical flow from 3.4:**
- The approve API does NOT trigger execution directly — it only transitions state. This story's execution dispatcher polls for incidents in `executing` state and handles the actual execution.
- The reject API transitions to `failed` — no execution happens. Only approved incidents reach this story.

**From Story 3.3 (Dry-Run Pre-Flight & Policy Gate):**

- **`pipeline/remediation_runner.py`** — After 3.3: runner reads `policy_decision` from graph output. If auto-approved, transitions `diagnosed → executing`. This is the other path to `executing` state (besides human approval).
- **`pipeline/remediation_graph.py`** — Graph structure after 3.3: `entry → plan → skeptic_validation → dry_run → policy_gate → END`. This story extends to: `entry → plan → skeptic_validation → dry_run → policy_gate → freshness_gate → execute → observe → END`.
- **`RemediationState` in `pipeline/remediation_graph.py`** — After 3.3: `incident_id`, `immutable_artifact`, `remediation_plan`, `skeptic_challenge`, `skeptic_verdict`, `dry_run_result`, `policy_decision`, `stage`. This story adds: `freshness_result`, `execution_log`, `outcome_result`.
- **`models/policy_gate.py`** — `PolicyDecision` with `auto_execution_approved` field. When True, execution proceeds without human approval.
- **`pipeline/policy_gate.py`** — `evaluate_policy_gate()` produces the decision. The `auto_execution_approved` flag determines whether the incident goes straight to `executing` or to `awaiting_approval`.

**From Story 3.1 (Remediation Planner & Structured Plan):**

- **`models/remediation.py`** — `RemediationPlan` with `steps: list[RemediationStep]`, `rollback_plan: list[RemediationStep]`, `blast_radius: BlastRadius`. This story executes `steps` and makes `rollback_plan` available for rollback.
- **`RemediationStep`** — `order: int`, `description: str`, `command: str | None`, `resource: str`, `action: str`, `expected_outcome: str`. Steps with `command` are executed via MCP; steps without `command` are informational.
- **`pipeline/mcp_readwrite_client.py`** — `ReadWriteMCPClient` with `query()` and `execute()` methods. Story 3.1 stubbed `execute()` — this story implements its usage for actual cluster mutations.
- **`db/remediation.py`** — `persist_remediation_plan()` and `load_immutable_artifact()`. This story loads the plan from `remediation_plans` for execution.

**From Story 2.4 (ImmutableDiagnosisArtifact):**

- **`models/diagnosis.py`** — `ImmutableDiagnosisArtifact` with `affected_resources: list[str]`. The outcome observer uses these to verify remediation success via read-only MCP.
- **`immutable_diagnoses` table** — Fields include `diagnosis JSONB` with the full diagnosis. The freshness gate reads the diagnosis to check if it's still relevant.

**From Epic 1 (state machine, events, audit, MCP):**

- **`models/state_machine.py`** — Valid transitions used by this story:
  - `executing → observing` (after execution completes)
  - `observing → resolved` (alert resolves)
  - `observing → failed` (alert does not resolve within timeout)
  All three already exist in `VALID_TRANSITIONS`.
- **`pipeline/runner.py`** — `_emit_stage_event()` helper for SSE events. Reuse this pattern in the execution pipeline.
- **`db/audit.py`** — `write_audit_log(conn, actor=..., action=..., target_resource=..., detail=...)`. Use for execution start/complete, rollback.
- **`pipeline/mcp_client.py`** (read-only) — `ReadOnlyMCPClient` for post-remediation verification. Outcome observer uses this to check `affected_resources`.
- **`api/event_bus.py`** — `get_event_bus()` for SSE event emission.

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-2 | RBAC Airlock | Execution uses the read-WRITE MCP Server (`cluster-admin` SA). Post-remediation verification uses the read-ONLY MCP Server (`cluster-reader` SA). These are DIFFERENT MCP clients. |
| AD-16 | Execution-stage freshness gate | MUST re-validate alert is still firing before execution. Stale remediations are skipped. Diagnostic work is preserved. This is a HARD RULE. |
| AD-18 | Global remediation lock | `SELECT FOR UPDATE NOWAIT` on `remediation_locks` table. Single row per namespace. Held through execution + observation + cooldown. Survives pod restart (auto-release on connection drop). No advisory locks, no in-memory locks. |
| AD-19 | Canonical state machine | `executing → observing`, `observing → resolved`, `observing → failed` — all via `transition()`. No direct state column writes. |
| AD-25 | Audit logging | Execution start/complete audit-logged via pipeline audit hook. Rollback audit-logged with actor identity. |
| AD-1 | Agents internal to stages | Execution and observation are NOT agents — they are deterministic pipeline operations. No LLM involved. |
| AD-4 | Shared types module | `ExecutionLog`, `OutcomeResult`, `RollbackRecord` defined in `models/execution.py` |
| AD-10 | SSE for real-time updates | Emit events for execution start/complete, observation start/result, rollback. |
| AD-14 | Monorepo layout | New files follow established pattern: models → pipeline → db → api |

**Critical constraint — "NEVER execute two remediations concurrently" (project-context.md):**
- Global lock via PostgreSQL row-level lock. One at a time, always.
- The lock is held from execution start through observation and cooldown.
- Pod crash releases the lock automatically (PostgreSQL row-level lock semantics).
- Next pod acquires cleanly — no stale locks.

**Critical constraint — "NEVER auto-rollback" (project-context.md):**
- Rollback is human-triggered ONLY via the API endpoint.
- Even if the outcome observer detects failure, the system does NOT roll back automatically.
- Failed remediations stay in `failed` state until an SRE reviews and decides.

### Technical Requirements

#### Global Remediation Lock (AD-18)

```sql
CREATE TABLE remediation_locks (
    id TEXT PRIMARY KEY DEFAULT 'global',
    locked_by UUID,
    locked_at TIMESTAMPTZ,
    incident_id UUID REFERENCES incidents(id)
);

INSERT INTO remediation_locks (id) VALUES ('global');
```

Single-row table. The lock is acquired via `SELECT FOR UPDATE NOWAIT`:

```python
async def acquire_remediation_lock(
    conn: asyncpg.Connection,
    incident_id: uuid.UUID,
) -> bool:
    """Acquire the global remediation lock (AD-18).

    Uses SELECT FOR UPDATE NOWAIT — fails immediately if another
    connection holds the lock. The lock is held as long as the
    connection's transaction remains open.

    Returns True if lock acquired, False if lock is held by another.
    """
    try:
        await conn.execute(
            """
            UPDATE remediation_locks
            SET locked_by = $1, locked_at = NOW(), incident_id = $2
            WHERE id = 'global'
            """,
            incident_id, incident_id,
        )
        await conn.fetchrow(
            "SELECT * FROM remediation_locks WHERE id = 'global' FOR UPDATE NOWAIT"
        )
        return True
    except asyncpg.exceptions.LockNotAvailableError:
        return False
```

**Lock lifecycle:**
1. Execution dispatcher acquires lock (dedicated connection)
2. Execution runs (lock held)
3. Outcome observation runs (lock held)
4. Cooldown period elapses (lock held)
5. Lock released by closing/committing the transaction

**Pod crash behavior:**
- PostgreSQL row-level locks are tied to connections
- When a pod crashes, the connection drops, and PostgreSQL auto-releases the lock
- Next pod acquires cleanly — no stale lock cleanup needed

#### Freshness Gate (AD-16)

```python
@dataclass
class FreshnessResult:
    is_fresh: bool
    alert_still_firing: bool
    diagnosis_still_relevant: bool
    reason: str | None = None

async def check_freshness(
    incident_id: uuid.UUID,
    artifact: ImmutableDiagnosisArtifact,
    conn: asyncpg.Connection,
) -> FreshnessResult:
    """Verify the alert is still firing and diagnosis is still relevant (AD-16).

    Checks:
    1. Has a resolved webhook arrived for this incident's alerts?
    2. Is the diagnosis still relevant to current cluster state?

    If stale: execution is skipped, diagnosis preserved for Learning Store.
    """
    # Check if any resolved webhook was recorded for this incident's alerts
    alert_still_firing = await _check_alert_still_firing(conn, incident_id)

    # Optionally verify cluster state hasn't changed significantly
    diagnosis_still_relevant = True  # Conservative: assume relevant unless proven otherwise

    is_fresh = alert_still_firing and diagnosis_still_relevant

    return FreshnessResult(
        is_fresh=is_fresh,
        alert_still_firing=alert_still_firing,
        diagnosis_still_relevant=diagnosis_still_relevant,
        reason=None if is_fresh else "Alert resolved or diagnosis stale",
    )
```

**Stale handling:**
- Stale remediations are NOT executed — skipped with diagnosis preserved
- The incident transitions to `failed` (not `resolved` — we don't know if the problem is truly fixed)
- The diagnosis is still valuable for the Learning Store (Epic 4) as informational context

#### Execution Engine

```python
async def execute_remediation(
    plan: RemediationPlan,
    mcp_client: ReadWriteMCPClient,
) -> ExecutionLog:
    """Execute a remediation plan step-by-step via the read-write MCP Server.

    Executes steps sequentially. On step failure, stops and returns
    partial log. Steps without a command are logged as informational.
    """
    step_logs: list[ExecutionStepLog] = []
    mcp_calls: list[dict] = []
    started_at = datetime.now(timezone.utc)

    for step in plan.steps:
        if step.command is None:
            step_logs.append(ExecutionStepLog(
                step_order=step.order,
                command="(informational)",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                success=True,
                output="Informational step — no command to execute",
            ))
            continue

        step_start = datetime.now(timezone.utc)
        try:
            result = await mcp_client.execute(
                tool_name="apply_resource",
                arguments={"command": step.command},
            )
            mcp_calls.append({
                "step_order": step.order,
                "tool": "apply_resource",
                "arguments": {"command": step.command},
                "result": result[:500],  # Truncate for storage
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            step_logs.append(ExecutionStepLog(
                step_order=step.order,
                command=step.command,
                started_at=step_start,
                completed_at=datetime.now(timezone.utc),
                success=True,
                output=result,
            ))
        except Exception as e:
            step_logs.append(ExecutionStepLog(
                step_order=step.order,
                command=step.command,
                started_at=step_start,
                completed_at=datetime.now(timezone.utc),
                success=False,
                output="",
                error=str(e),
            ))
            break  # Stop on first failure

    status = "completed" if all(s.success for s in step_logs) else "failed"

    return ExecutionLog(
        incident_id=plan.incident_id,
        plan_id=plan.id,
        steps=step_logs,
        mcp_calls=mcp_calls,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        status=status,
    )
```

#### Outcome Observer

```python
async def observe_outcome(
    incident_id: uuid.UUID,
    artifact: ImmutableDiagnosisArtifact,
    execution_log: ExecutionLog,
    settings: ExecutionSettings | None = None,
) -> OutcomeResult:
    """Observe whether the remediation resolved the problem.

    Primary signal: resolved webhook from AlertManager
    Corroborating signal: direct resource verification via read-only MCP

    outcome_confidence scoring:
    - 1.0: Both webhook resolved AND resource verification passes
    - 0.7: Webhook resolved only (no verification or verification inconclusive)
    - 0.5: Resource verification passes only (no webhook yet — uncommon)
    - 0.2: Timeout — neither signal received
    """
    config = settings or get_execution_settings()
    observation_start = datetime.now(timezone.utc)

    alert_resolved = False
    resource_verification = None

    # Poll for resolved webhook within timeout
    deadline = observation_start + timedelta(seconds=config.observation_timeout_seconds)
    while datetime.now(timezone.utc) < deadline:
        pool = await get_pool()
        async with pool.acquire() as conn:
            alert_resolved = await _check_alert_resolved(conn, incident_id)

        if alert_resolved:
            break

        await asyncio.sleep(config.lock_poll_interval_seconds)

    # Post-remediation verification via read-only MCP
    resource_verification = await _verify_affected_resources(artifact)

    # Calculate outcome_confidence
    webhook_ok = alert_resolved
    verification_ok = resource_verification and resource_verification.get("all_healthy", False)

    if webhook_ok and verification_ok:
        outcome_confidence = 1.0
    elif webhook_ok:
        outcome_confidence = 0.7
    elif verification_ok:
        outcome_confidence = 0.5
    else:
        outcome_confidence = 0.2

    resolution_method = "webhook" if webhook_ok else ("verification" if verification_ok else "timeout")

    return OutcomeResult(
        incident_id=incident_id,
        alert_resolved=alert_resolved,
        resolution_method=resolution_method,
        resource_verification=resource_verification,
        outcome_confidence=outcome_confidence,
        refire_detected=False,  # Set later by re-fire detection
        observation_started_at=observation_start,
        observation_completed_at=datetime.now(timezone.utc),
        timeout_seconds=config.observation_timeout_seconds,
    )
```

#### Re-fire Detection

```python
async def monitor_for_refire(
    incident_id: uuid.UUID,
    settings: ExecutionSettings | None = None,
) -> bool:
    """Monitor for alert re-fire within the configured window.

    Called after a successful resolution. Runs as a background task
    or periodic check. If re-fire detected, flags the incident.
    """
    config = settings or get_execution_settings()
    deadline = datetime.now(timezone.utc) + timedelta(seconds=config.refire_window_seconds)

    while datetime.now(timezone.utc) < deadline:
        pool = await get_pool()
        async with pool.acquire() as conn:
            refired = await _check_alert_refired(conn, incident_id)

        if refired:
            # Flag the incident for review
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE outcome_results
                    SET refire_detected = TRUE
                    WHERE incident_id = $1
                    """,
                    incident_id,
                )
            return True

        await asyncio.sleep(config.lock_poll_interval_seconds)

    return False
```

#### Rollback API

```python
@router.post("/api/v1/incidents/{incident_id}/rollback")
async def trigger_rollback(
    request: Request,
    incident_id: uuid.UUID,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Trigger rollback of a completed remediation.

    Executes the rollback_plan from the RemediationPlan.
    Rollback is always a failure signal for the Learning Store.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Verify incident is in a terminal state (resolved or failed)
        row = await conn.fetchrow(
            "SELECT state FROM incidents WHERE id = $1", incident_id
        )
        if row is None:
            # 404
            ...

        state = IncidentState(row["state"])
        if state not in (IncidentState.RESOLVED, IncidentState.FAILED):
            # 409 Conflict — can only roll back completed remediations
            ...

        # Load the remediation plan with rollback steps
        plan_row = await conn.fetchrow(
            "SELECT plan FROM remediation_plans WHERE incident_id = $1",
            incident_id,
        )
        if plan_row is None:
            # 404 — no plan found
            ...

        plan = RemediationPlan.model_validate(plan_row["plan"])
        if not plan.rollback_plan:
            # 409 — no rollback steps available
            ...

    # Execute rollback via read-write MCP
    mcp_client = ReadWriteMCPClient()
    rollback_log = await _execute_rollback(plan.rollback_plan, mcp_client)

    # Persist rollback record
    async with pool.acquire() as conn:
        async with conn.transaction():
            record = RollbackRecord(
                incident_id=incident_id,
                plan_id=plan.id,
                actor=user.username,
                steps_executed=rollback_log,
                success=all(s.success for s in rollback_log),
            )
            await persist_rollback_record(conn, record)

            # Audit log the rollback
            await write_audit_log(
                conn,
                actor=user.username,
                action="api.remediation.rollback",
                target_resource=str(incident_id),
                detail={
                    "plan_id": str(plan.id),
                    "success": record.success,
                    "steps_executed": len(rollback_log),
                },
            )

    # Emit SSE event
    bus = get_event_bus()
    await bus.emit(EventNames.INCIDENT_STAGE_CHANGED, SSEEventData(
        incident_id=incident_id,
        stage="rollback",
        state="completed" if record.success else "failed",
    ))

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(
        data={"status": "rollback_completed", "success": record.success},
        meta=meta,
    ).model_dump(mode="json")
```

#### Remediation Graph Update

```python
class RemediationState(TypedDict):
    incident_id: str
    immutable_artifact: dict
    remediation_plan: dict | None
    skeptic_challenge: dict | None
    skeptic_verdict: dict | None
    dry_run_result: dict | None
    policy_decision: dict | None
    freshness_result: dict | None       # NEW (Story 3.5)
    execution_log: dict | None           # NEW (Story 3.5)
    outcome_result: dict | None          # NEW (Story 3.5)
    stage: str


async def freshness_gate_node(state: RemediationState) -> dict:
    """Freshness gate — verifies alert still firing before execution (AD-16)."""
    from .freshness_gate import check_freshness

    incident_id = uuid.UUID(state["incident_id"])
    artifact = ImmutableDiagnosisArtifact.model_validate(state["immutable_artifact"])

    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await check_freshness(incident_id, artifact, conn)

    return {
        "freshness_result": {
            "is_fresh": result.is_fresh,
            "alert_still_firing": result.alert_still_firing,
            "diagnosis_still_relevant": result.diagnosis_still_relevant,
            "reason": result.reason,
        },
    }


async def execute_node(state: RemediationState) -> dict:
    """Execute the remediation plan via read-write MCP (Story 3.5)."""
    from .execution_engine import execute_remediation

    plan = RemediationPlan.model_validate(state["remediation_plan"])
    mcp_client = ReadWriteMCPClient()

    execution_log = await execute_remediation(plan, mcp_client)

    return {
        "execution_log": execution_log.model_dump(mode="json"),
    }


async def observe_node(state: RemediationState) -> dict:
    """Observe remediation outcome (Story 3.5)."""
    from .outcome_observer import observe_outcome

    incident_id = uuid.UUID(state["incident_id"])
    artifact = ImmutableDiagnosisArtifact.model_validate(state["immutable_artifact"])
    execution_log = ExecutionLog.model_validate(state["execution_log"])

    outcome = await observe_outcome(incident_id, artifact, execution_log)

    return {
        "outcome_result": outcome.model_dump(mode="json"),
    }


def should_execute(state: RemediationState) -> str:
    """Conditional edge: skip execution if freshness gate fails."""
    freshness = state.get("freshness_result", {})
    if freshness.get("is_fresh", False):
        return "execute"
    return "end_stale"


# Graph structure (Story 3.5 — FINAL for Epic 3):
#   entry → plan → skeptic_validation → dry_run → policy_gate
#         → freshness_gate → {execute | end_stale}
#         → observe → END
```

#### Execution Dispatcher Architecture

The execution dispatcher is separate from the diagnosis dispatcher because execution has fundamentally different concurrency semantics (global lock, serialized, cooldown). Options:

1. **Extend existing dispatcher** — add a second polling path for `executing` state incidents alongside the diagnosis queue polling.
2. **Separate execution loop** — a dedicated background task that polls for `executing` incidents.

Use option 2 for clean separation:

```python
async def run_execution_dispatcher() -> None:
    """Background loop for dispatching remediation execution.

    Polls for incidents in 'executing' state. Acquires the global
    remediation lock before proceeding. Only one execution at a time.
    """
    settings = get_execution_settings()

    while True:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                # Find the oldest incident in 'executing' state
                row = await conn.fetchrow("""
                    SELECT i.id, rp.plan, rp.id AS plan_id
                    FROM incidents i
                    JOIN remediation_plans rp ON rp.incident_id = i.id
                    WHERE i.state = 'executing'
                    ORDER BY i.updated_at ASC
                    LIMIT 1
                """)

                if row is None:
                    await asyncio.sleep(settings.lock_poll_interval_seconds)
                    continue

            # Attempt to acquire global lock and execute
            await _execute_with_lock(row, settings)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Execution dispatcher error")

        await asyncio.sleep(settings.lock_poll_interval_seconds)
```

#### Database Tables

```sql
-- Global remediation lock (AD-18)
CREATE TABLE remediation_locks (
    id TEXT PRIMARY KEY DEFAULT 'global',
    locked_by UUID,
    locked_at TIMESTAMPTZ,
    incident_id UUID REFERENCES incidents(id)
);
INSERT INTO remediation_locks (id) VALUES ('global');

-- Execution logs
CREATE TABLE execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
    plan_id UUID NOT NULL REFERENCES remediation_plans(id),
    steps JSONB NOT NULL,
    mcp_calls JSONB,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_execution_logs_incident ON execution_logs(incident_id);

-- Outcome results
CREATE TABLE outcome_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
    alert_resolved BOOLEAN NOT NULL,
    resolution_method TEXT,
    resource_verification JSONB,
    outcome_confidence FLOAT NOT NULL,
    refire_detected BOOLEAN NOT NULL DEFAULT FALSE,
    observation_started_at TIMESTAMPTZ,
    observation_completed_at TIMESTAMPTZ,
    timeout_seconds INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_outcome_results_incident ON outcome_results(incident_id);

-- Rollback records
CREATE TABLE rollback_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id),
    plan_id UUID NOT NULL REFERENCES remediation_plans(id),
    actor TEXT NOT NULL,
    steps_executed JSONB,
    success BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_rollback_records_incident ON rollback_records(incident_id);
```

Note: `rollback_records` does NOT have UNIQUE on `incident_id` — an SRE could roll back, retry, and roll back again (unlikely but not architecturally forbidden).

#### Alembic Migration Numbering

Stories 3.1–3.4 use migrations 008–011. This story's migration(s) should be numbered 012+. Since Stories 3.1–3.4 are `ready-for-dev` (not yet implemented), the actual latest migration in the codebase is 007. The dev agent should check the latest migration number at implementation time and number accordingly.

Expected migration for this story:
- `012_add_execution_tables.py` — creates `remediation_locks`, `execution_logs`, `outcome_results`, `rollback_records` tables (or adjust number based on what exists when implemented)

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ~=1.2 | Already in pyproject.toml. Graph node orchestration |
| asyncpg | latest | Already in pyproject.toml. Lock acquisition, persistence |
| pydantic | latest | Already in pyproject.toml. ExecutionLog, OutcomeResult models |
| fastapi | 0.141.x | Already in pyproject.toml. Rollback API endpoint |

**No new dependencies required.** All packages were added in Epic 1/2. Execution, observation, and rollback are pure pipeline/API logic — no LLM, no new libraries.

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/models/execution.py` | `ExecutionLog`, `ExecutionStepLog`, `OutcomeResult`, `RollbackRecord` models | NEW |
| `backend/src/config/execution_settings.py` | `ExecutionSettings` — timeout, cooldown, re-fire window config | NEW |
| `backend/src/pipeline/freshness_gate.py` | Freshness gate — verify alert still firing before execution | NEW |
| `backend/src/pipeline/execution_engine.py` | Step-by-step execution via read-write MCP | NEW |
| `backend/src/pipeline/outcome_observer.py` | Outcome observation — webhook monitoring + resource verification | NEW |
| `backend/src/pipeline/execution_dispatcher.py` | Background loop for dispatching execution with global lock | NEW |
| `backend/src/db/remediation_lock.py` | `acquire_remediation_lock()`, `release_remediation_lock()` | NEW |
| `backend/src/db/execution.py` | `persist_execution_log()`, `persist_outcome_result()`, `persist_rollback_record()` | NEW |
| `backend/src/api/rollback.py` | Rollback API endpoint | NEW |
| `backend/alembic/versions/012_add_execution_tables.py` | Migration: remediation_locks, execution_logs, outcome_results, rollback_records | NEW |
| `backend/tests/models/test_execution.py` | Model validation tests | NEW |
| `backend/tests/pipeline/test_freshness_gate.py` | Freshness gate unit tests | NEW |
| `backend/tests/pipeline/test_execution_engine.py` | Execution engine unit tests (mocked MCP) | NEW |
| `backend/tests/pipeline/test_outcome_observer.py` | Outcome observer unit tests | NEW |
| `backend/tests/api/test_rollback.py` | Rollback API endpoint tests | NEW |
| `backend/tests/db/test_execution.py` | Execution persistence roundtrip tests | NEW |
| `backend/tests/db/test_remediation_lock.py` | Lock acquisition/release tests | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/models/__init__.py` | Export `ExecutionLog`, `ExecutionStepLog`, `OutcomeResult`, `RollbackRecord` | UPDATE |
| `backend/src/pipeline/remediation_graph.py` | Add `freshness_gate`, `execute`, `observe` nodes; conditional edge; update `RemediationState` | UPDATE |
| `backend/src/pipeline/remediation_runner.py` | Handle execution completion — state transitions, persistence, SSE events | UPDATE |
| `backend/src/api/app.py` | Register rollback router | UPDATE |
| `charts/openshift-ai-ops/values.yaml` | Add `execution` config section | UPDATE |
| `charts/openshift-ai-ops/templates/deployment-backend.yaml` | Add `EXECUTION_*` env vars | UPDATE |
| `backend/tests/pipeline/test_remediation_graph.py` | Extend for freshness_gate + execute + observe nodes | UPDATE |

### Dependency Direction (ENFORCED)

```
models/execution.py → (nothing — leaf module)
config/execution_settings.py → (nothing — leaf module, reads env vars only)
pipeline/freshness_gate.py → db/ (query alert status), models/ (ImmutableDiagnosisArtifact)
pipeline/execution_engine.py → pipeline/mcp_readwrite_client.py, models/ (RemediationPlan, ExecutionLog)
pipeline/outcome_observer.py → pipeline/mcp_client.py (read-only), db/, models/ (OutcomeResult, ImmutableDiagnosisArtifact)
pipeline/execution_dispatcher.py → db/remediation_lock.py, pipeline/execution_engine.py, pipeline/outcome_observer.py, config/execution_settings.py
db/remediation_lock.py → (nothing — pure DB operations)
db/execution.py → models/execution.py
api/rollback.py → models/ (RemediationPlan, RollbackRecord, IncidentState), api/auth.py (get_current_user), db/execution.py, db/audit.py, pipeline/mcp_readwrite_client.py
```

- **NEVER**: `models/` imports from `agents/`, `pipeline/`, `api/`, or `db/`
- **NEVER**: Execution engine uses the read-only MCP. It MUST use the read-write MCP (`cluster-admin` SA).
- **NEVER**: Outcome observer uses the read-write MCP for verification. Verification is read-only — use `ReadOnlyMCPClient`.
- **NEVER**: The system auto-initiates rollback. Rollback is human-triggered via API only.
- **NEVER**: Execute two remediations concurrently. Global lock enforces serialization.
- **ALLOWED**: `pipeline/execution_engine.py` imports from `pipeline/mcp_readwrite_client.py`
- **ALLOWED**: `pipeline/outcome_observer.py` imports from `pipeline/mcp_client.py` (read-only)
- **ALLOWED**: `api/rollback.py` imports from `db/execution.py` and `db/audit.py`

### Testing Requirements

**Unit tests** (`pytest -m unit`):
- `ExecutionLog` validates `status` is one of: running, completed, failed
- `ExecutionStepLog` validates `step_order >= 1`
- `OutcomeResult.outcome_confidence` must be 0–1
- `RollbackRecord` validates `actor` is non-empty
- Freshness gate: alert still firing → fresh; alert resolved → stale
- Freshness gate: stale remediation returns `is_fresh=False`
- Execution engine: all steps succeed → status "completed"; step failure → status "failed" and remaining steps skipped
- Execution engine: informational steps (no command) logged as success
- Execution engine: MCP calls recorded in `mcp_calls` list
- Outcome observer: webhook + verification → confidence 1.0
- Outcome observer: webhook only → confidence 0.7
- Outcome observer: verification only → confidence 0.5
- Outcome observer: timeout → confidence 0.2, incident to `failed`
- Outcome observer: alert resolved → incident to `resolved`

**API tests** (`pytest -m api`):
- `POST /api/v1/incidents/{id}/rollback` — success: incident in resolved/failed state → rollback executes, audit log created
- `POST /api/v1/incidents/{id}/rollback` — wrong state: incident in `executing` → 409 Conflict
- `POST /api/v1/incidents/{id}/rollback` — no rollback plan → 409 Conflict
- `POST /api/v1/incidents/{id}/rollback` — unauthenticated → 401
- Rollback records are persisted correctly

**DB integration tests** (`pytest -m db`):
- `persist_execution_log()` roundtrip (testcontainers)
- `persist_outcome_result()` roundtrip (testcontainers)
- `persist_rollback_record()` roundtrip (testcontainers)
- `acquire_remediation_lock()` succeeds on first call
- `acquire_remediation_lock()` fails (NOWAIT) when lock already held by another connection
- Lock release (transaction commit/close) → subsequent acquire succeeds
- Connection drop → lock auto-released by PostgreSQL

**Pipeline integration tests** (`pytest -m pipeline`):
- Remediation graph with all nodes: plan → skeptic → dry_run → policy_gate → freshness_gate → execute → observe
- Freshness gate stale → execution skipped (conditional edge to END)
- Runner transitions incident through executing → observing → resolved/failed
- Event bus receives stage_changed events for execution + observation

**Mock patterns:**
- Mock `ReadWriteMCPClient.execute()` for execution tests — return success/failure responses
- Mock `ReadOnlyMCPClient.query()` for verification — return healthy/unhealthy resource states
- Mock resolved webhook detection — control via DB fixture (insert/not-insert resolved alert record)
- For lock tests: use two separate asyncpg connections to test lock contention (testcontainers)
- Override `ExecutionSettings` in tests for fast timeouts (1s observation, 0s cooldown)
- Use `asyncio.sleep` mocking for timeout tests to avoid real waits

### Anti-Patterns / DO NOT

- **DO NOT** auto-rollback. Rollback is ALWAYS human-triggered via the API endpoint. Even if outcome observation detects failure, the system enters `failed` state and waits for SRE review.
- **DO NOT** execute two remediations concurrently. Global lock (`SELECT FOR UPDATE NOWAIT`) enforces serialization (AD-18). One at a time, always.
- **DO NOT** use advisory locks or in-memory locks. Row-level lock in PostgreSQL only (AD-18).
- **DO NOT** use the read-only MCP for execution. Execution MUST use the read-write MCP (`cluster-admin` SA). Only verification uses the read-only MCP.
- **DO NOT** implement Case Record creation. That's Epic 4 (Story 4.1). This story produces the outcome — Epic 4 persists it as a Case Record.
- **DO NOT** implement fast-path bypass. That's Epic 4 (Story 4.3). This story handles normal execution flow.
- **DO NOT** implement the frontend UI for execution monitoring. That's Epic 5 (Story 5.3/5.4).
- **DO NOT** modify the state machine. All needed transitions already exist: `executing → observing`, `observing → resolved`, `observing → failed`.
- **DO NOT** use an LLM for execution, observation, or freshness checks. These are pure deterministic operations.
- **DO NOT** implement automatic retry on execution failure. A failed execution stays in `failed` state. An SRE reviews and decides next steps (rollback, manual fix, etc.).
- **DO NOT** bypass the freshness gate. Even for auto-approved (policy gate) remediations, the freshness gate runs. Always.
- **DO NOT** modify `models/remediation.py`, `models/policy_gate.py`, `models/diagnosis.py`, or any earlier story models.
- **DO NOT** modify `pipeline/skeptic_validation.py`, `pipeline/remediation_skeptic_validation.py`, or `pipeline/policy_gate.py`.
- **DO NOT** implement re-fire detection as a blocking operation in the execution flow. It runs as a post-observation background task or periodic check. The outcome (resolved/failed) is committed before re-fire monitoring begins.
- **DO NOT** hold the global lock during rollback. Rollback is a separate API action, not part of the execution pipeline. It should acquire its own lock if needed (or share the global lock pattern).

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  models/
    execution.py                # NEW: ExecutionLog, OutcomeResult, RollbackRecord
    __init__.py                 # UPDATE: export new models
  config/
    execution_settings.py       # NEW: ExecutionSettings (timeout, cooldown, re-fire)
  pipeline/
    freshness_gate.py           # NEW: Freshness gate (AD-16)
    execution_engine.py         # NEW: Step-by-step execution via MCP
    outcome_observer.py         # NEW: Outcome monitoring + verification
    execution_dispatcher.py     # NEW: Background loop with global lock
    remediation_graph.py        # UPDATE: add freshness_gate + execute + observe nodes
    remediation_runner.py       # UPDATE: handle execution completion
  db/
    remediation_lock.py         # NEW: Global lock acquire/release (AD-18)
    execution.py                # NEW: persist execution logs, outcomes, rollbacks
  api/
    rollback.py                 # NEW: Rollback API endpoint
    app.py                      # UPDATE: register rollback router
backend/alembic/versions/
    012_add_execution_tables.py # NEW migration
backend/tests/
  models/
    test_execution.py                  # NEW
  pipeline/
    test_freshness_gate.py             # NEW
    test_execution_engine.py           # NEW
    test_outcome_observer.py           # NEW
    test_remediation_graph.py          # UPDATE: extend for all nodes
  api/
    test_rollback.py                   # NEW
  db/
    test_execution.py                  # NEW
    test_remediation_lock.py           # NEW
charts/openshift-ai-ops/
  values.yaml                          # UPDATE: add execution section
  templates/
    deployment-backend.yaml            # UPDATE: add EXECUTION_* env vars
```

### Latest Technology Notes

**PostgreSQL row-level locks (`SELECT FOR UPDATE NOWAIT`):**
- Row-level locks are held for the duration of the transaction
- `NOWAIT` causes immediate failure if the lock is already held — no deadlock risk
- Locks are automatically released when the connection drops (pod crash) — no stale lock cleanup needed
- The lock is on a dedicated row in `remediation_locks` — no contention with regular table operations
- For this pattern, the executing connection must keep its transaction open through execution + observation + cooldown

**kubernetes-mcp-server v0.0.66+ — write operations:**
- `apply_resource` — apply YAML manifests (kubectl apply equivalent)
- `delete_resource` — delete resources (kubectl delete equivalent)
- `patch_resource` — patch resources (kubectl patch equivalent)
- Same Streamable HTTP transport as read-only instance
- The `execute()` method on `ReadWriteMCPClient` (stubbed in Story 3.1) delegates to these MCP tools
- Write operations require the `cluster-admin` ServiceAccount

**AlertManager webhook detection for outcome observation:**
- The webhook receiver (Story 1.1) already records resolved webhooks in the `alerts` table
- Outcome observation checks this table to detect if the alert resolved
- The webhook receiver sets `status = 'resolved'` when a resolved webhook arrives
- No need for a separate AlertManager API call — leverage the existing webhook integration

**Helm Values Addition:**

```yaml
execution:
  observationTimeoutSeconds: 300       # How long to wait for alert resolution
  cooldownSeconds: 60                  # Cooldown between remediations
  refireWindowSeconds: 600             # Window to detect alert re-fire after resolution
  lockPollIntervalSeconds: 5           # How often to poll for lock availability
```

### References

- [Source: ARCHITECTURE-SPINE.md#AD-2] — RBAC Airlock (execution uses cluster-admin SA; verification uses cluster-reader SA)
- [Source: ARCHITECTURE-SPINE.md#AD-16] — Execution-stage freshness gate (re-validate before execution)
- [Source: ARCHITECTURE-SPINE.md#AD-18] — Global remediation lock (`SELECT FOR UPDATE NOWAIT` on `remediation_locks`)
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine (`executing → observing → resolved | failed`)
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit logging (execution + rollback audit-logged)
- [Source: ARCHITECTURE-SPINE.md#AD-10] — SSE for real-time updates (emit events for execution stages)
- [Source: ARCHITECTURE-SPINE.md#Pipeline Flow] — Executor → Outcome Observer → Case Record/Flag for review
- [Source: epics.md#Story 3.5] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 3] — FR-15 (serialized execution), FR-16 (outcome observation), FR-17 (rollback) coverage
- [Source: project-context.md#Pipeline Paradigm Violations] — "NEVER execute two remediations concurrently"
- [Source: project-context.md#Security Anti-Patterns] — "NEVER auto-rollback", "NEVER bypass the policy gate"
- [Source: project-context.md#Operational Gotchas] — "Resolved webhook during in-flight pipeline does NOT cancel it — freshness gate catches it at execution"
- [Source: Story 3.4 spec] — Approve endpoint transitions to `executing`; this story's dispatcher picks up
- [Source: Story 3.3 spec] — Policy gate auto-approve transitions to `executing`; graph structure post-3.3
- [Source: Story 3.1 spec] — RemediationPlan model, ReadWriteMCPClient (execute() stubbed), remediation graph
- [Source: Story 2.4 spec] — ImmutableDiagnosisArtifact (affected_resources for verification)
- [Source: models/state_machine.py] — `VALID_TRANSITIONS`: `executing → [observing]`, `observing → [resolved, failed]`
- [Source: pipeline/runner.py] — `_emit_stage_event()` pattern for SSE events
- [Source: db/audit.py] — `write_audit_log()` function signature
- [Source: pipeline/mcp_client.py] — ReadOnlyMCPClient pattern for verification
- [Source: pipeline/mcp_readwrite_client.py] — ReadWriteMCPClient.execute() stub from Story 3.1

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (via Cursor)

### Debug Log References

No significant environment issues. Largest story in Epic 3 by file count (24 files, 2981 insertions). The execution dispatcher required careful lock lifecycle management — PostgreSQL row-level locks tied to connection lifetime needed explicit connection management patterns.

### Implementation Plan

Followed story task sequence: models → config → global lock → freshness gate → execution engine → outcome observer → re-fire detection → rollback API → graph integration → execution dispatcher → persistence → Helm chart → tests. Red-green-refactor applied throughout.

### Completion Notes List

- **Task 1:** Created `models/execution.py` with `ExecutionLog`, `ExecutionStepLog`, `OutcomeResult`, `OutcomeConfidence`, `RollbackRecord` Pydantic models. Exported from `models/__init__.py`.
- **Task 2:** Created `config/execution_settings.py` with `ExecutionSettings` — observation timeout (300s), cooldown (60s), re-fire window (600s), lock poll interval (5s). Wired `EXECUTION_*` env vars.
- **Task 3:** Created `db/remediation_lock.py` with `acquire_remediation_lock()` using `SELECT FOR UPDATE NOWAIT` (AD-18), `release_remediation_lock()`. Created migration `013_add_execution_tables.py` with `remediation_locks` single-row table + seed insert. Lock auto-releases on connection drop (pod crash).
- **Task 4:** Created `pipeline/freshness_gate.py` with `check_freshness()` (AD-16). Checks alert still firing via correlated alerts query. Stale remediations skipped with diagnosis preserved.
- **Task 5:** Created `pipeline/execution_engine.py` with `execute_remediation()`. Sequential step execution via `ReadWriteMCPClient.execute()`. Step failure stops execution, remaining steps skipped. MCP calls logged with timestamps.
- **Task 6:** Created `pipeline/outcome_observer.py` with `observe_outcome()`. Polls for resolved webhook within timeout. Post-remediation verification via read-only MCP. Confidence scoring: 1.0 (webhook+verification), 0.7 (webhook only), 0.5 (verification only), 0.2 (timeout).
- **Task 7:** Added `monitor_for_refire()` as post-observation background task. Monitors same fingerprint within `refire_window_seconds`. Updates `outcome_results.refire_detected` on detection.
- **Task 8:** Created `api/rollback.py` with `POST /api/v1/incidents/{id}/rollback`. Verifies incident in terminal state, loads rollback plan, executes via read-write MCP, records as failure signal. Audit-logged with actor identity.
- **Task 9:** Updated `pipeline/remediation_graph.py` with `freshness_gate_node`, `execute_node`, `observe_node`. Added conditional edge: stale → skip to END. Final graph: `plan → skeptic → dry_run → policy_gate → freshness_gate → {execute | end_stale} → observe → END`.
- **Task 10:** Created `pipeline/execution_dispatcher.py` with `run_execution_dispatcher()`. Polls for `executing` incidents, acquires global lock, runs full cycle (freshness → execute → observe → cooldown → release). Recovery for stranded `observing` incidents on restart.
- **Task 11:** Created `db/execution.py` with `persist_execution_log()`, `persist_outcome_result()`, `persist_rollback_record()`. Tables: `execution_logs`, `outcome_results`, `rollback_records` in migration 013.
- **Task 12:** Added `execution` section to `values.yaml`. Wired `EXECUTION_*` env vars in deployment template.
- **Tasks 13–14:** 4 dispatcher test classes, 5 model test classes, 4 engine test classes, 3 freshness test classes, 2 observer test classes, 3 lock test classes, 3 DB execution test classes, 4 rollback API test classes. All pass.

## File List

| File | Action | Description |
|------|--------|-------------|
| `backend/src/models/execution.py` | NEW | ExecutionLog, ExecutionStepLog, OutcomeResult, RollbackRecord models |
| `backend/src/models/__init__.py` | MODIFIED | Export new execution models |
| `backend/src/config/execution_settings.py` | NEW | ExecutionSettings (timeout, cooldown, re-fire window config) |
| `backend/src/pipeline/freshness_gate.py` | NEW | Freshness gate — verify alert still firing (AD-16) |
| `backend/src/pipeline/execution_engine.py` | NEW | Step-by-step execution via read-write MCP |
| `backend/src/pipeline/outcome_observer.py` | NEW | Outcome observation — webhook monitoring + resource verification |
| `backend/src/pipeline/execution_dispatcher.py` | NEW | Background loop with global lock, execution lifecycle |
| `backend/src/db/remediation_lock.py` | NEW | Global remediation lock acquire/release (AD-18) |
| `backend/src/db/execution.py` | NEW | persist_execution_log, persist_outcome_result, persist_rollback_record |
| `backend/src/api/rollback.py` | NEW | Rollback API endpoint (human-triggered only) |
| `backend/src/api/app.py` | MODIFIED | Register rollback router |
| `backend/src/pipeline/remediation_graph.py` | MODIFIED | Added freshness_gate, execute, observe nodes; conditional edge |
| `backend/src/pipeline/remediation_runner.py` | MODIFIED | Handle execution completion |
| `backend/alembic/versions/013_add_execution_tables.py` | NEW | Migration: remediation_locks, execution_logs, outcome_results, rollback_records |
| `charts/openshift-ai-ops/values.yaml` | MODIFIED | Added execution config section |
| `charts/openshift-ai-ops/templates/deployment-backend.yaml` | MODIFIED | Added EXECUTION_* env vars |
| `backend/tests/models/test_execution.py` | NEW | Model validation tests (5 test classes) |
| `backend/tests/pipeline/test_freshness_gate.py` | NEW | Freshness gate unit tests (3 test classes) |
| `backend/tests/pipeline/test_execution_engine.py` | NEW | Execution engine unit tests (4 test classes) |
| `backend/tests/pipeline/test_outcome_observer.py` | NEW | Outcome observer unit tests (2 test classes) |
| `backend/tests/pipeline/test_execution_dispatcher.py` | NEW | Execution dispatcher tests (4 test classes) |
| `backend/tests/api/test_rollback.py` | NEW | Rollback API endpoint tests (4 test classes) |
| `backend/tests/db/test_execution.py` | NEW | Execution persistence roundtrip tests (3 test classes) |
| `backend/tests/db/test_remediation_lock.py` | NEW | Lock acquisition/release/contention tests (3 test classes) |
| `backend/tests/pipeline/test_remediation_graph.py` | MODIFIED | Extended for full graph with all nodes |

## Change Log

- 2026-08-11: Story 3.5 implementation — Serialized Execution, Outcome Observation & Rollback. Global lock (AD-18), freshness gate (AD-16), execution engine, outcome observer with confidence scoring, re-fire detection, rollback API. 24 files, 2981 insertions. 4 review rounds.

## Code Review Record

### Review Round 1 — 2026-08-11
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6

#### Findings
- [x] [Review][Patch] Lock ordering unsafe — `acquire_remediation_lock()` could deadlock with concurrent callers. **Fixed**: enforced consistent lock acquisition order with `NOWAIT` and explicit error handling.
- [x] [Review][Patch] Missing state re-check — execution dispatcher didn't re-verify incident state after acquiring the lock, allowing race conditions. **Fixed**: added `SELECT state FROM incidents WHERE id = $1` check after lock acquisition.
- [x] [Review][Patch] Resource verification heuristic too naive — `_verify_affected_resources()` used overly simple string matching. **Fixed**: added `_content_indicates_unhealthy()` with keyword-based heuristic for error detection.
- [x] [Review][Patch] Missing dispatcher tests — execution dispatcher had no test coverage. **Fixed**: added `test_execution_dispatcher.py` with 4 test classes (296 lines).

### Review Round 2 — 2026-08-11
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6

#### Findings
- [x] [Review][Patch] Graph coupled to execution — remediation graph nodes directly called execution engine, creating tight coupling. **Fixed**: decoupled graph from execution; graph produces the plan, dispatcher handles execution separately.
- [x] [Review][Patch] Correlated alert logic incorrect — freshness gate checked only the primary alert, not correlated siblings. **Fixed**: `_check_alert_still_firing()` now queries all correlated alerts for the incident.
- [x] [Review][Patch] Rollback missing lock + proof — rollback API didn't acquire the global lock and lacked success/failure proof in the response. **Fixed**: rollback now acquires the remediation lock and returns step-by-step execution proof.

### Review Round 3 — 2026-08-11
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6

#### Findings
- [x] [Review][Patch] Execution cycle not crash-safe — if the pod crashed during outcome observation, the incident would be stranded in `observing` state with the lock released. **Fixed**: added `_recover_stranded_observing()` to the dispatcher startup that detects and re-observes stranded incidents.
- [x] [Review][Patch] Test settings invalid — test execution settings used 0s timeouts causing immediate timeout. **Fixed**: test settings use valid small values (1s observation, 1s cooldown).

### Review Round 4 — 2026-08-11
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6

#### Findings
- [x] [Review][Patch] Recovery lock contention — `_recover_stranded_observing()` could race with a normal execution cycle trying to lock the same incident. **Fixed**: recovery uses `NOWAIT` lock attempt and skips if contended.
- [x] [Review][Patch] Outcome transition not atomic — state transition to `resolved`/`failed` happened outside the persistence transaction. **Fixed**: state transition and outcome persistence now in a single `conn.transaction()` block.
- [x] [Review][Patch] Rollback durability gap — rollback record persistence didn't include the rollback step details. **Fixed**: `persist_rollback_record()` now includes full step execution logs.
- [x] [Review][Patch] Outcome observer test assertion fragile — test mocked time incorrectly causing flaky behavior. **Fixed**: test now patches `asyncio.sleep` for deterministic timeout behavior.
