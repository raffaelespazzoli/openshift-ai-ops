# Adversarial Architecture Review — OpenShift AI Ops Spine (Round 2)

| Field | Value |
|-------|-------|
| Reviewed | 2026-08-06 |
| Spine version | final (2026-08-05, 23 ADs) |
| Prior review | Round 1 (2026-08-05) found 5 holes; spine updated with AD-19 through AD-23 in response |
| Verdict | **FAIL** — 8 structural holes remain; 3 critical, 3 high, 2 medium |

---

## Method

For each finding, two hypothetical epics are constructed that:
- Obey every one of the 23 ADs to the letter.
- Follow all consistency conventions.
- Use only the allowed dependency directions (AD-14 graph).
- Remain within their assigned `backend/src/` packages.

If the two epics can still produce a system that fails at integration, the spine has a hole. This round specifically targets the seams around the five new ADs (AD-19 through AD-23) and the interactions between them and the original 18.

---

## Finding 1 — Pipeline-to-SSE event delivery has no specified mechanism

**Category:** Missing boundary rules  
**Severity:** Critical

### Epic A: "Diagnosis Pipeline Engine"

Implements FR-4, FR-5, FR-8 (diagnosis through skeptic). As LangGraph graph nodes execute, the pipeline produces stage transitions: `diagnosing → diagnosed`, skeptic challenge/response cycles, etc. Per AD-21, these transitions must emit SSE events matching the envelope `{event: "incident.stage_changed", data: {...}}`. This epic emits events by writing them to a `pipeline_events` table in PostgreSQL (AD-3 compliant — application schema). Why? Because `pipeline/` has no dependency on `api/` (AD-14's dependency graph: `pipeline/ → models/, agents/, db/, knowledge/`), so it cannot call any `api/` function to publish events.

### Epic B: "API & UI Layer"

Implements FR-21, FR-33. Serves SSE endpoints per AD-10. Subscribes clients to `/api/v1/incidents/{id}/events`. Expects to push events as they happen. This epic implements SSE by holding an async generator in the FastAPI endpoint that polls a Redis pubsub channel for events. Why? Because `api/ → pipeline/` exists (AD-14), so the API could call a pipeline function to register a callback, but AD-21 says nothing about a callback pattern, and the pipeline has no reference to `api/` to call back.

### Incompatibility

Epic A writes events to PostgreSQL. Epic B listens on Redis. Both are AD-compliant — AD-21 specifies the envelope shape but never specifies:

1. **The transport between pipeline and API for SSE events.** AD-14's dependency graph has `API → PIPELINE` (API calls pipeline) but not `PIPELINE → API` (pipeline pushes to API). There is no specified event bus, callback registration, or shared notification channel.
2. **Whether events are push or pull.** Does the pipeline push events to the API? Does the API poll pipeline state? Does a shared store (DB table, Redis, in-process queue) mediate?
3. **Latency contract.** "Live pipeline stage transitions" (AD-10) implies sub-second delivery, but database polling has inherent latency.

Both epics build AD-21-compliant event shapes that never reach each other.

**AD gap:** AD-21 defines the event *shape* but not the event *transport*. Add: *"Pipeline stages publish events via an in-process async event bus (e.g., `asyncio.Queue` or broadcast channel) defined in `pipeline/events.py`. The API layer subscribes to this bus and fans out to SSE clients. The bus interface is defined in `models/` so both `api/` and `pipeline/` can depend on it without circular imports."*

---

## Finding 2 — AD-19 "only pipeline advances state" contradicts API-driven approval and webhook cancellation

**Category:** Conflicting state-mutation paths / Two owners of one entity  
**Severity:** Critical

### Epic A: "Remediation Execution & Outcome"

Implements FR-15, FR-16. Dequeues incidents in `diagnosed` state (or `awaiting_approval` after approval). Per AD-19, "Only the pipeline engine may advance state; the API layer reads it." This epic implements a LangGraph interrupt node at the policy gate: when human approval is required, the graph pauses (LangGraph checkpoint) at `awaiting_approval`. It resumes only when the pipeline engine detects the approval (by polling a database flag). The pipeline engine then advances state to `executing`. State mutation goes through `pipeline/ → db/`.

### Epic B: "API & Human Approval"

Implements FR-14, FR-33. Exposes `POST /api/v1/incidents/{id}/approve`. When the SRE approves, the API must cause the incident to transition from `awaiting_approval → executing`. Per AD-19, only the pipeline engine may advance state, so this epic sets an `approval_decision` column in the database and trusts that something will pick it up. But it also needs to trigger the pipeline to resume — LangGraph's `graph.update_state()` is the mechanism, which means the API directly calls into the pipeline engine.

Separately, this epic handles `resolved` webhooks (FR-1). AD-23 says "Resolved-webhook cancellation uses `UPDATE ... WHERE status = 'queued'`" — a direct database write from `api/webhooks.py`. But AD-19 says only the pipeline engine advances incident state, and `queued` is a state in the AD-19 state machine.

### Incompatibility

Three contradictions within the spine itself, exploitable by two epics:

1. **Approval resumption.** AD-19 says the API only reads. But resuming a paused LangGraph graph requires calling `graph.update_state()` or `graph.invoke()` — which is a *write* into the pipeline engine. Epic A might poll for approval (adding latency), Epic B might directly resume the graph (violating AD-19). Neither is wrong because the AD is self-contradictory.

2. **Resolved-webhook cancellation.** AD-23 explicitly permits `api/` to write `UPDATE ... WHERE status = 'queued'` to the priority queue. If the priority queue IS the incidents table (filtered by `status='queued'`), AD-23 and AD-19 contradict each other. If the queue is a separate table, the incident's state still reads `queued` after the queue row is cancelled — and no AD says who then changes the incident state.

3. **Incident creation.** The webhook receiver is in `api/` (capability map: "FR-1 Webhook receiver | `api/`"). When a new alert arrives, an incident must be created with state `received`. But AD-19 says only the pipeline advances state. Is creation different from advancement? Unspecified.

**AD gap:** AD-19 needs a mechanism clause: *"The pipeline engine is the sole writer of incident state transitions. The API layer triggers transitions by (a) invoking pipeline entry points for new incidents, (b) updating an `approval_decisions` table that the pipeline polls or subscribes to for human-in-the-loop resumption, and (c) setting a `cancelled` flag on queue rows that the pipeline's freshness gate (AD-16) respects. The API never directly writes `incidents.status`."* Additionally, AD-19 and AD-23 must be reconciled — either the priority queue is a separate table from incidents (clarify), or AD-23's cancellation write is explicitly an exception to AD-19.

---

## Finding 3 — AD-18 conflates two mutually exclusive PostgreSQL locking mechanisms

**Category:** Clashing implementation assumptions  
**Severity:** Critical

### Epic A: "Remediation Execution"

Implements FR-15. Reads AD-18: "a PostgreSQL advisory lock acquired before execution." Implements `pg_advisory_lock(REMEDIATION_LOCK_KEY)` — a global named lock in PostgreSQL shared memory. Fast, lightweight, no table required. Released via `pg_advisory_unlock()` after outcome observation + cooldown. The "survives pod restart" requirement is met because the connection drops on restart and PostgreSQL automatically releases the advisory lock, which is the desired behavior (the new pod can re-acquire).

### Epic B: "Pipeline Engine & Observation"

Implements FR-15, FR-16. Reads AD-18: "The lock is row-level in a dedicated `remediation_locks` table (not an in-memory lock, survives pod restart)." Implements a `remediation_locks` table with a singleton row, acquires via `SELECT ... FOR UPDATE` on that row, released by `UPDATE ... SET locked = false` after cooldown. Justified: AD-18 says "row-level in a dedicated `remediation_locks` table."

### Incompatibility

Advisory locks and row-level locks are fundamentally different PostgreSQL features:

| Property | Advisory lock | Row-level lock in table |
|----------|--------------|------------------------|
| Requires a table | No | Yes |
| Lock scope | Session or transaction | Transaction only |
| Survives pod restart | No (released on disconnect) | Depends on transaction commit |
| `SKIP LOCKED` compatible | No | Yes |
| Visibility to other queries | `pg_locks` system view | `pg_locks` + table query |

AD-18 says "PostgreSQL advisory lock" (sentence 1) then says "row-level in a dedicated `remediation_locks` table" (sentence 3). These are mutually exclusive. Both epics are AD-18 compliant because they each follow one of the two contradictory sentences.

If both ship, the system has two independent locks — neither blocks the other. Serialized execution breaks silently.

**AD gap:** AD-18 must commit to one mechanism. Recommended: *"The global remediation lock is implemented as a singleton row in a `remediation_locks` table. Acquisition uses `SELECT ... FOR UPDATE` (transaction-scoped). The row carries `locked_by` (incident ID), `locked_at` (timestamp), and `cooldown_until` (timestamp). If the pod crashes mid-execution, the transaction rolls back and the lock is automatically released. Cooldown is enforced by checking `cooldown_until > now()` before acquiring."* Remove the advisory lock language.

---

## Finding 4 — Co-occurrence query prescribed by AD-20 is the wrong mechanism for AD-5 layer 5

**Category:** Clashing shared-data shapes  
**Severity:** High

### Epic A: "Learning Store & Fast-Path"

Implements FR-18, FR-19, FR-20. Defines `case_records` table per AD-20 ownership. Stores vector embeddings of the *diagnosis object* (root-cause code + causal chain + evidence summary) for similarity search. The embedding represents "what went wrong and how it was fixed." Indexes with pgvector HNSW on a `diagnosis_embedding` column. Provides a `find_similar_diagnoses(embedding, threshold)` query interface.

### Epic B: "Triage & Correlation"

Implements FR-2, FR-3 (AD-5 layer 5). Needs to answer: "Which alert fingerprints have historically appeared together in the same Root-Cause Event?" This is a set co-occurrence query — given alert fingerprint A, find all fingerprints that have co-occurred with A in past incidents. This requires querying the `grouped_alert_fingerprints` (a list/array field) across case records to find intersection patterns.

AD-20 says: "The correlation layer reads case records for co-occurrence patterns via a read-only query interface (pgvector similarity search)."

So Epic B calls `find_similar_diagnoses()` with... what vector? It doesn't have a diagnosis yet (correlation happens *before* diagnosis). It has an alert fingerprint. It could embed the fingerprint as a vector, but alert fingerprint co-occurrence is a *discrete set-membership* problem ("did these two fingerprints appear in the same group?"), not a *continuous similarity* problem. Vector similarity will return the most *similar-looking* alerts, not the most *co-occurring* ones.

### Incompatibility

Epic A builds an embedding-based similarity API because AD-20 says "pgvector similarity search." Epic B needs a relational co-occurrence API (e.g., `SELECT grouped_fingerprints FROM case_records WHERE $fingerprint = ANY(grouped_fingerprints)`) but AD-20 constrains it to vector search. Epic B either:
- Misuses the vector API (returns wrong results), or
- Adds its own relational query directly to the `case_records` table, violating AD-20's "read-only query interface" constraint by bypassing Epic A's API, or
- Requests a schema change to add an `alert_fingerprints` array column + GIN index, which AD-20 assigns to the Learning Store owner.

None of these paths lead to a clean integration.

**AD gap:** AD-20 prescribes vector similarity as the *only* query mechanism, but co-occurrence is not a similarity problem. Tighten AD-20: *"The Learning Store module exposes two read-only query interfaces: (1) `similarity_search(embedding, threshold)` for fast-path case matching (FR-20) and semantic retrieval, and (2) `co_occurrence_query(alert_fingerprints)` returning historical co-occurrence frequencies for correlation (AD-5 layer 5). The `case_records` table includes a `grouped_alert_fingerprints` array column with a GIN index, owned by the Learning Store schema."*

---

## Finding 5 — Per-agent LLM config has two contradictory sources of truth

**Category:** Configuration ownership conflict  
**Severity:** High

### Epic A: "LLM Integration & Agent Framework"

Implements FR-28, FR-29, FR-30. Reads AD-7: "each agent role has its own LLM client configured via Helm values (endpoint, model, params)." Implements a `LLMConfig` dataclass loaded from environment variables injected by Helm. The orchestrator agent reads `ORCHESTRATOR_LLM_ENDPOINT`, `ORCHESTRATOR_LLM_MODEL`, etc. Config is immutable at runtime. Changes require `helm upgrade` + pod restart.

### Epic B: "Config & Policy Management API"

Implements FR-28, FR-32, FR-33. Reads consistency conventions: "Policy matrix and per-agent LLM config are runtime-mutable via API (changes audit-logged)." Implements `PUT /api/v1/config/llm/{agent_role}` that writes LLM config to a `llm_config` table in PostgreSQL. Agents read from DB at each invocation. Config is live-mutable without restart.

### Incompatibility

Epic A reads config from Helm-injected env vars (startup-time, immutable). Epic B writes config to PostgreSQL (runtime-mutable). When an SRE calls the API to change the orchestrator's model, Epic A's agent ignores it because it read config at startup. When a Helm upgrade changes values, Epic B's database still has the old runtime override.

AD-7 says "Helm values" for the source. The conventions say "runtime-mutable via API." There is no specified:

1. **Source-of-truth precedence.** Does Helm provide defaults and the API provides overrides? Or vice versa?
2. **Config resolution order.** Helm → DB override? DB → Helm fallback?
3. **Staleness detection.** If both exist, how does the agent know which to use?

Both epics are individually AD-compliant yet produce a system where config changes via one path are invisible to the other.

**AD gap:** AD-7 must specify resolution order: *"Per-agent LLM config defaults are set in Helm values. The API layer (`config/`) can override any default at runtime; overrides are stored in PostgreSQL and take precedence over Helm defaults. Agents read effective config (Helm default merged with DB override) at each invocation, not at startup. Helm values serve as the reset-to-defaults mechanism."*

---

## Finding 6 — StructuredDiagnosis vs ImmutableDiagnosisArtifact relationship undefined

**Category:** Clashing shared-data shapes  
**Severity:** High

### Epic A: "Diagnosis Pipeline (Triage through Skeptic)"

Implements FR-4, FR-5, FR-8. Produces a `StructuredDiagnosis` Pydantic model in `models/` containing: `root_cause_code`, `causal_chain`, `affected_resources`, `evidence_artifacts`, `confidence_score`, `evidence_gaps` (per AD-15), `reasoning` (unstructured LLM text per AD-4). The skeptic validates it, possibly triggering re-diagnosis. After skeptic sign-off, Epic A considers the `StructuredDiagnosis` final and passes it downstream.

### Epic B: "Remediation Planning (RBAC Airlock through Policy Gate)"

Implements FR-10, FR-11, FR-12, FR-13. Receives an `ImmutableDiagnosisArtifact` at the RBAC Airlock boundary (AD-2). This epic defines `ImmutableDiagnosisArtifact` in `models/` as a frozen Pydantic model (`model_config = ConfigDict(frozen=True)`) with a content hash for tamper detection. It expects fields: `diagnosis_hash`, `root_cause_code`, `remediation_hints`, `blast_radius_estimate`, `evidence_summary`.

### Incompatibility

AD-4 lists both "Structured Diagnosis Object" and "Immutable Diagnosis Artifact" as typed artifacts in `models/`. The spine never specifies:

1. **Whether these are two types or one.** If two, what is the mapping/transformation? If one, why two names?
2. **The immutability mechanism.** Python Pydantic models can be frozen, but "immutable" could also mean content-hashed, serialized-and-signed, or simply a convention. Two epics will implement different enforcement.
3. **Field alignment.** Epic A's structured diagnosis has `evidence_artifacts` (list of log snippets, metric values). Epic B's immutable artifact expects `evidence_summary` (a prose string). Neither violates AD-4 because AD-4 only mandates the *names* exist in `models/`, not the exact fields.

The RBAC Airlock is the highest-stakes handoff in the system. If the two types have different fields, the remediation planner receives a diagnosis it cannot parse.

**AD gap:** AD-4 must clarify: *"The Structured Diagnosis Object is a mutable working artifact within the diagnosis stage. The Immutable Diagnosis Artifact is a frozen snapshot created at the RBAC Airlock boundary by hashing and freezing the final Structured Diagnosis Object. Both are defined as Pydantic models in `models/`. The Immutable Diagnosis Artifact includes all fields of the Structured Diagnosis Object plus a `diagnosis_hash` (SHA-256 of the canonical JSON serialization) and a `sealed_at` timestamp. No additional fields may be added during freezing."*

---

## Finding 7 — Incident creation boundary: webhook receiver vs pipeline engine

**Category:** Ambiguous entity ownership  
**Severity:** Medium

### Epic A: "API & Webhook Receiver"

Implements FR-1. Receives AlertManager POST at `api/webhooks.py`. Must acknowledge within 500ms (spec assumption). Creates an `incidents` row with `status='received'` and returns 200. The incident exists in the database before the pipeline touches it.

### Epic B: "Triage & Correlation"

Implements FR-2, FR-3. Expects to pick up incidents in `received` state and advance them to `correlating → queued`. Per AD-19, "Only the pipeline engine may advance state." Epic B interprets this as: the pipeline engine creates the incident. So the webhook receiver should enqueue a raw alert payload into a staging table and the pipeline's triage stage creates the incident with `received` state, then immediately advances to `correlating`.

### Incompatibility

Epic A creates incidents from `api/`. Epic B expects the pipeline to create them. The integration question: when the webhook arrives, does the system have an incident (Epic A's model) or a raw alert (Epic B's model)? The downstream pipeline depends on this — if the triage stage expects raw alerts, it cannot process Epic A's pre-created incidents; if it expects incidents, Epic B's staging table is dead code.

AD-19 says "only the pipeline engine may advance state" but is ambiguous about *creation* vs *advancement*. And the 500ms SLA means the webhook handler must return before the pipeline can synchronously create the incident.

**AD gap:** Tighten AD-19: *"The webhook receiver (`api/`) creates the incident row with status `received` and publishes an event. This is the only incident state write performed by `api/`. All subsequent state transitions are performed by the pipeline engine. The webhook receiver returns 200 immediately after the database insert."*

---

## Finding 8 — StageError propagation between stages is deferred but affects cross-stage contracts

**Category:** Missing boundary rules  
**Severity:** Medium

### Epic A: "Diagnosis Pipeline"

Implements FR-4, FR-5. When diagnosis fails (LLM timeout, all evidence gaps, MCP unreachable), this epic produces a `StageError` artifact per consistency conventions: `{stage: "diagnosis", error_code: "llm_timeout", detail: {...}, recoverable: true}`. Per the deferred table, "Error handling conventions per pipeline stage — won't cause cross-stage divergence if built independently." So this epic simply produces the error and lets LangGraph propagate it.

### Epic B: "Remediation Planning"

Implements FR-11, FR-12. This stage expects a `ImmutableDiagnosisArtifact` as input (AD-2). When it receives a `StageError` instead, it has no specification for what to do. Options:
- Crash (unhandled type)
- Skip (move to `failed` state — but which state in AD-19? There's no `diagnosis_failed` state)
- Retry (re-invoke diagnosis — but remediation stage has no authority to retry an earlier stage)

### Incompatibility

The consistency conventions define `StageError` as a typed artifact with a `recoverable` flag but never specify:

1. **Who acts on `recoverable`.** Does the producing stage retry itself? Does the pipeline engine retry? Does the next stage decide?
2. **State machine path for failures.** AD-19's state machine has no error transitions between stages. There's no `diagnosing → diagnosis_failed` or `executing → execution_failed`. Only terminal `failed` exists, reachable only from `observing`.
3. **Error artifact routing.** Does a `StageError` bypass all subsequent stages and jump to a terminal state? Or does each stage need to handle receiving either a success artifact or a `StageError`?

The deferred table says this "won't cause cross-stage divergence," but it will — because Epic A's error output must be Epic B's recognized input, and the state machine must have a valid path for it.

**AD gap:** Either un-defer this or add a minimal convention: *"When a stage produces a `StageError` with `recoverable=true`, the pipeline engine retries the stage up to N times (configurable). When retries are exhausted or `recoverable=false`, the pipeline engine advances the incident to `failed` state directly, skipping all subsequent stages. A `StageError` is never passed as input to the next pipeline stage. The AD-19 state machine gains a `→ failed` edge from every non-terminal state."*

---

## Interaction Analysis: AD-19 × AD-23 Reconciliation Gap

Beyond the eight pair-based findings, a structural tension between AD-19 and AD-23 deserves explicit note. AD-23 says "Resolved-webhook cancellation uses `UPDATE ... WHERE status = 'queued'`." This is a direct database write that changes a row matching the `queued` state from AD-19's state machine. If the priority queue is the incidents table (implied by the shared `queued` state), then AD-23 authorizes `api/` to write incident state — contradicting AD-19. If the priority queue is a *separate* table, then the incident's status column still reads `queued` after the queue row is cancelled, and no AD specifies who/when updates the incident status to reflect cancellation.

**Resolution needed:** Either (a) the priority queue is a separate table from incidents, and AD-19 gains a `queued → cancelled` transition triggered by the pipeline engine polling for cancelled queue entries, or (b) the priority queue IS the incidents table, and AD-23's cancellation write is an explicit exception to AD-19's pipeline-only rule.

---

## Summary of Required Spine Changes

| # | Finding | Severity | Affected ADs | Fix |
|---|---------|----------|-------------|-----|
| 1 | Pipeline-to-SSE event transport unspecified | Critical | AD-14, AD-21 | New AD or tighten AD-21: specify in-process event bus, bus interface in `models/`, `api/` subscribes |
| 2 | AD-19 "only pipeline writes" contradicts approval, webhook cancellation, and incident creation | Critical | AD-19, AD-23 | Tighten AD-19 with mechanism clause; reconcile with AD-23; define API's permitted writes |
| 3 | AD-18 conflates advisory locks and row-level locks | Critical | AD-18 | Rewrite AD-18 to commit to one locking mechanism (recommend row-level lock in `remediation_locks` table) |
| 4 | AD-20 prescribes vector similarity for co-occurrence, which is the wrong query type | High | AD-5, AD-20 | Tighten AD-20: two query interfaces (similarity + co-occurrence); add `grouped_alert_fingerprints` column |
| 5 | Per-agent LLM config: Helm values vs runtime-mutable API | High | AD-7, conventions | Tighten AD-7: Helm = defaults, DB = overrides, agents read effective config at invocation |
| 6 | StructuredDiagnosis vs ImmutableDiagnosisArtifact relationship undefined | High | AD-2, AD-4 | Tighten AD-4: define freezing transformation, hash mechanism, field superset relationship |
| 7 | Incident creation from `api/` vs pipeline-only state writes | Medium | AD-19 | Tighten AD-19: explicitly permit `api/` to create with `received`, no other writes |
| 8 | StageError propagation deferred but affects cross-stage contracts and state machine completeness | Medium | AD-19, conventions | Un-defer: define retry ownership, add `→ failed` edges to state machine from all non-terminal states |
| — | AD-19 × AD-23 interaction (queue table identity) | High | AD-19, AD-23 | Clarify whether priority queue is incidents table or separate; reconcile write ownership |

---

## Verdict: FAIL

Eight structural holes remain in the spine after the AD-19 through AD-23 additions. Three are critical (will break integration), three are high (expensive to fix after epics diverge), and two are medium (friction but recoverable). The new ADs successfully closed the Round 1 findings in principle, but introduced new ambiguities:

- AD-19's "only pipeline writes" rule is too absolute — it conflicts with three legitimate API write paths (creation, approval, cancellation).
- AD-18's locking description is internally contradictory (advisory vs row-level).
- AD-20's query interface prescription doesn't match its consumer's actual needs.
- AD-21 specifies event shapes but not transport, leaving the most critical real-time path unimplemented.

None are design-level flaws. All are closable with tightened language in existing ADs. Recommend addressing all before epic decomposition begins.
