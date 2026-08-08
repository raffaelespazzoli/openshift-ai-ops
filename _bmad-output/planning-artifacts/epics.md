---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - prds/prd-openshift-ai-ops-2026-08-02/prd.md
  - architecture/architecture-openshift-ai-ops-2026-08-03/ARCHITECTURE-SPINE.md
  - ux-designs/ux-openshift-ai-ops-2026-08-02/DESIGN.md
  - ux-designs/ux-openshift-ai-ops-2026-08-02/EXPERIENCE.md
  - ../../brainstorming/brainstorm-openshift-ai-ops-tool-2026-08-02/architecture-one-pager.md
  - ../../specs/spec-openshift-ai-ops/SPEC.md
  - ../../specs/spec-openshift-ai-ops/glossary.md
---

# OpenShift AI Ops - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for OpenShift AI Ops, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR-1: The system can receive HTTP POST webhooks from AlertManager carrying `firing` and `resolved` alert payloads (acknowledge within 500ms, dequeue resolved alerts, reject malformed with 400).
FR-2: The system can deduplicate repeated firings of the same alert and correlate related alerts into single Root-Cause Events based on label intersection, temporal proximity, and known cascade patterns from the Learning Store.
FR-3: The system can order incoming Root-Cause Events by urgency × recency, with configurable TTL verification and parallelism cap.
FR-4: The Orchestrator can form initial hypotheses from alert metadata and contextual knowledge, dispatch to Specialists, synthesize partial findings, handle unclaimed alerts as generalist, and enforce a completeness gate before Skeptic handoff.
FR-5: The system can produce schema-enforced Structured Diagnosis Objects with root-cause codes from a controlled taxonomy, evidence arrays of concrete artifacts, and deterministic comparison via root-cause hash.
FR-6: The system can retrieve relevant operational knowledge from curated sources (runbooks via pgvector RAG, RHOKP via okp-mcp, Learning Store) and execute domain-specific agentic skills as callable tools during diagnosis.
FR-7: Specialist agents can self-select alerts matching their domain expertise via label-matching rules and produce domain-specific diagnoses. [POST-MVP — SHOULD]
FR-8: A Skeptic agent can challenge a Structured Diagnosis Object in one round of structured debate. Unchanged root-cause hash = pass; changed hash = one re-challenge, then pass regardless.
FR-9: A Skeptic agent can challenge a Remediation Plan in one round of structured debate, evaluating steps, blast radius, rollback feasibility, preconditions, and risk.
FR-10: The system can produce an immutable diagnosis artifact that crosses the RBAC boundary to remediation. The remediation planner cannot re-diagnose or re-interpret.
FR-11: The remediation planner can produce a structured plan: `{steps, blast_radius, rollback_plan, estimated_risk, preconditions}` from the Immutable Diagnosis Artifact.
FR-12: The system can validate a remediation plan via server-side dry-run (`oc apply --dry-run=server`), admission webhook checks, and RBAC/quota confirmation.
FR-13: The system can evaluate a remediation plan against a configurable three-dimensional policy matrix (severity × blast radius × confidence). All three dimensions must pass for auto-execution; evidence artifacts required per causal chain element.
FR-14: An on-call SRE can review and approve or reject a remediation plan with full context (diagnosis, plan, skeptic, dry-run, blast radius). Optional minimum review time for node/cluster blast radius.
FR-15: The system can execute approved remediation plans one at a time with a global lock and configurable cooldown, re-validating alert is still firing before execution.
FR-16: The system can observe whether the original alert resolves after execution (webhook + direct resource verification via read-only MCP Server), with re-fire detection and outcome_confidence scoring.
FR-17: An SRE can trigger rollback of a completed remediation using the rollback plan. Rollback is never automatic; triggered rollback is a failure signal in the Learning Store.
FR-18: The system can persist a structured Case Record for every completed incident (alert signature, root-cause code, diagnosis, plan, outcome, cluster context) with vector embeddings.
FR-19: The system can reduce effective confidence of older Case Records via temporal decay: `effective_confidence = base_confidence × decay_factor(age) × version_relevance(OCP_version)`.
FR-20: The system can bypass the full LLM diagnosis pipeline when a high-similarity past success exists in pgvector. Fast-path remediations still pass through the Policy Gate.
FR-21: The system can provide a standalone web-based UI for incident management (list with filtering), diagnosis review, and remediation approval, independent of OpenShift Console availability.
FR-22: The system can present an operational summary dashboard (total incidents, auto-remediated vs. human-approved, MTTR, fast-path percentage, success/failure ratio) filterable by time range.
FR-23: The system can provide a Console dynamic plugin integrating key views into the OpenShift Console. [POST-MVP — SHOULD]
FR-24: The system can accept simulated alert payloads for evaluation without triggering real remediation; results stored separately from production Case Records.
FR-25: The system can compare diagnosis and remediation outputs against a human-validated answer key, scoring diagnosis accuracy, remediation appropriateness, and time-to-response per domain.
FR-26: The system can gate auto-remediation enablement per domain based on eval harness results. Passing produces a recommendation report; an SRE explicitly relaxes the Policy Matrix.
FR-27: An SRE team can deploy the complete system with a single `helm install` into a single namespace (backend, frontend, PostgreSQL+pgvector, 2 MCP Servers, Solr, okp-mcp). No CRDs, no OLM.
FR-28: An SRE team can configure different LLM endpoints, models, and parameters for each agent role (orchestrator, specialists, skeptics, planner). No dependency on OpenShift AI.
FR-29: The system can handle LLM unavailability gracefully with configurable exponential backoff, fast-path fallback, and clear UI status.
FR-30: The system can dynamically route LLM requests to different models based on estimated task complexity (simple → cheaper models, complex → frontier models).
FR-31: The system can cache and reuse LLM responses for semantically similar queries (semantic cache), with invalidation when cluster state changes.
FR-32: An SRE team can configure the auto-remediation policy matrix via Helm values or runtime API. Default requires human approval for all. Changes are audit-logged.
FR-33: The system can expose a versioned REST API serving all data and actions required by UI surfaces with authentication, authorization, and audit logging.

### NonFunctional Requirements

NFR-1 (Security): RBAC Airlock — diagnosis uses `cluster-reader` SA + `--read-only` MCP; remediation uses `cluster-admin` SA + separate MCP. No cross-access. Diagnosis-side agentic skills are read-only. All remediation actions audit-logged. LLM credentials in Kubernetes Secrets only.
NFR-2 (Reliability): LangGraph checkpoints persisted to PostgreSQL — workflows resume from last checkpoint on pod restart. Priority Queue persists to PostgreSQL (not in-memory). Graceful degradation when cluster is partially degraded (partial data from MCP, not fatal).
NFR-3 (Performance): Alert intake within 1 second. Handle alert storms of up to 100 simultaneous alerts. Configurable parallelism cap. Learning Store scales to thousands-to-millions of Case Records (pgvector IVFFlat/HNSW indexing).
NFR-4 (Observability): Prometheus metrics for intake rate, queue depth, diagnosis latency, execution count, fast-path hit rate, LLM call latency, error rates. Structured JSON logging for all pipeline stages. LangGraph execution traces queryable for debugging.

### Additional Requirements

- AD-1: Every pipeline stage has typed input/output contracts defined in the shared types module (`backend/src/models/`). Agent orchestration lives inside stages, never between them.
- AD-2: Two ServiceAccounts — `cluster-reader` (diagnosis MCP, `--read-only`) and `cluster-admin` (remediation MCP). Default is `cluster-admin` for remediation; Helm-configurable for tighter RBAC.
- AD-3: Two schema domains in PostgreSQL — LangGraph owns `langgraph_*` tables (black box); everything else is application schema with application-owned migrations.
- AD-4: All stage-boundary artifacts (RootCauseEvent, DiagnosisObject, ImmutableDiagnosisArtifact, RemediationPlan, CaseRecord) defined in `backend/src/models/`. Structured schema fields coexist with unstructured text fields.
- AD-5: Deterministic pre-agent alert correlation (no LLM). Five-layer correlator: dedup → namespace+temporal → label+temporal → static subsystem dependency graph → Learning Store co-occurrence.
- AD-6: Severity-based correlation settling windows: Critical=60s, Warning=5min, Info=10min (Helm-configurable). Timer resets on each new alert joining. Max group age = 3× settling window.
- AD-7: Per-agent LLM config with layered override: Helm values seed → runtime API mutations to DB → on restart, Helm loads then DB overrides apply. All config changes audit-logged.
- AD-9: Seven-deployment pod topology in a single namespace: backend, frontend, postgresql, mcp-readonly, mcp-readwrite, solr, okp-mcp. MCP communication via Streamable HTTP transport.
- AD-10: SSE endpoints for live pipeline stage transitions and incident state changes. Frontend subscribes on detail view, falls back to polling on connection drop.
- AD-11: In-process `/metrics` endpoint via prometheus-client. ServiceMonitor in Helm chart. Structured JSON logging. LangGraph tracing.
- AD-12: REST API validates bearer tokens against OpenShift OAuth server. Frontend uses OpenShift OAuth flow.
- AD-13: Dual-path knowledge retrieval: (1) Runbooks bundled at build time, chunked/embedded into pgvector, retrieved via similarity search. (2) RHOKP via Solr container + okp-mcp via MCP streamable-http.
- AD-14: Monorepo source tree layout: `backend/src/{api,pipeline,agents,models,knowledge,db,config}`, `backend/tests/`, `frontend/src/`, `charts/openshift-ai-ops/`, `docs/`.
- AD-15: MCP timeouts produce partial-evidence with explicit `evidence_gaps` field. Skeptic must challenge gaps. Policy Gate blocks auto-execution when gaps exist.
- AD-16: Execution-stage freshness gate — re-validates alert still firing and diagnosis still relevant before execution. Stale remediations skipped; diagnostic work preserved.
- AD-17: Semantic cache entries carry cluster-context fingerprint (OCP version + topology hash). Valid only when current fingerprint matches.
- AD-18: Global remediation lock via PostgreSQL row-level lock (`SELECT FOR UPDATE NOWAIT`) on `remediation_locks` table. Held through execution + observation + cooldown.
- AD-19: Canonical incident state machine: `received → correlating → queued → diagnosing → diagnosed → awaiting_approval → executing → observing → resolved | failed`. State-write ownership split between API-permitted and pipeline-only.
- AD-20: Case Record table schema owned by Learning Store module (`db/`). Correlation reads via pgvector similarity and relational SQL queries but does not modify schema.
- AD-21: SSE event envelope: `{event: string, data: {incident_id, stage, state, timestamp, payload}}`. Event names use dot-notation.
- AD-22: Semantic cache is a middleware in `knowledge/`, intercepting LLM calls before they reach the endpoint. Storage via `db/`.
- AD-23: Priority queue uses PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` for dequeue. Resolved-webhook cancellation via `UPDATE ... WHERE status = 'queued'`.
- AD-24: Pipeline→API event delivery via in-process asyncio event bus. Pipeline emits, API subscribes. Bus interface defined in `models/`.
- AD-25: Audit logging at two write points: API middleware (state-changing REST requests) and pipeline audit hook (internal state transitions). Both write to `audit_log` table.

### UX Design Requirements

UX-DR1: Implement 5 pipeline step semantic tokens (completed/success, active/info, awaiting/warning, failed/danger, skipped/disabled) mapping to PatternFly status variants for ProgressStepper visualization.
UX-DR2: Implement confidence badge as PatternFly Label (compact) with three tiers — high (success green), medium (warning gold), low (danger red) — for diagnosis confidence and dry-run results.
UX-DR3: Implement navigation approval badge using PatternFly NotificationBadge inline in the "Incidents" nav item showing count of items in `awaiting` state. Hidden when count is 0.
UX-DR4: Implement fast-path badge using PatternFly Label (info, compact) with "Fast-Path" text. Shown in incident list rows and detail view breadcrumb.
UX-DR5: Dark mode as default theme. Support both dark and light themes via PatternFly's built-in theme toggle. No custom dark-mode tokens.
UX-DR6: Console shell layout — horizontal masthead (top) + vertical navigation (left sidebar). Two nav items: Incidents (with approval badge) and Statistics. Matches OpenShift Console for plugin migration.
UX-DR7: Incidents list view using PatternFly DataList (expandable). RCE group headers show: RCE label, correlated alert count badge, highest severity Label, time since first alert. Expand reveals individual alert rows. Click alert row → full-page detail.
UX-DR8: Firing/Resolved toggle using PatternFly ToggleGroup in Toolbar. Two states: Firing (default), Resolved. Resolved adds time-range dropdown (1h, 6h, 24h, 7d). Toggle persists in URL query params.
UX-DR9: Severity filter using PatternFly Select (checkbox variant) in Toolbar. Multi-select: critical, warning, info. Default: all selected. Persists in URL query params.
UX-DR10: Pipeline visualization using PatternFly ProgressStepper (horizontal, center-aligned). Six stages with icon + label + state. Click stage to expand content panel below (accordion — one at a time). Active stage auto-expands on load.
UX-DR11: Stage content panels using DescriptionList + Card with specific content per stage: Triage (alert payload, correlation reasoning, priority), Diagnosis (root-cause code, causal chain, affected resources, evidence, agent summary, confidence), Skeptic (challenge, response, verdict), Remediation (steps, blast radius, rollback, dry-run, preconditions, approve/reject buttons), Execution (log, MCP calls, duration, status), Outcome (resolution status, TTR, verification, case record link).
UX-DR12: Approval action using PatternFly Button — Approve (primary) and Reject (danger) in Remediation stage content when state is `awaiting`. Single-click action, no confirmation modal for standard blast radius.
UX-DR13: Breadcrumb navigation using PatternFly Breadcrumb on detail view: "Incidents > {Alert Name}". Click "Incidents" returns to list preserving filter state.
UX-DR14: Statistics summary cards using PatternFly Card (compact). Five cards: total incidents, auto-resolved %, success/failure ratio, MTTR, fast-path hit rate. Each shows current value + trend indicator.
UX-DR15: Statistics charts using PatternFly Charts (line for alerts/diagnoses/resolutions over time, area for MTTR). Time-range selector (day/week/month).
UX-DR16: Empty state using PatternFly EmptyState with check-circle success icon: "No active alerts." No call-to-action.
UX-DR17: Loading state using PatternFly Skeleton matching expected layout shape for initial page load and async pipeline stage data.
UX-DR18: Keyboard shortcuts for power users: j/k (list navigation), Enter (open detail), Backspace/Esc (return to list), 1–6 (jump to pipeline stage), a (approve when awaiting).
UX-DR19: Accessibility — WCAG 2.2 AA. Pipeline states via aria-label (not color alone). DataList expansion announced. Approve/Reject with aria-describedby linking to plan summary. Keyboard nav of pipeline stages via arrow keys. Focus management on navigation transitions. Charts with aria-label text summaries.
UX-DR20: State patterns — specific treatments for: cold app load (Skeleton rows), no firing alerts (EmptyState), alert storm (collapsed groups, severity sort), pipeline in progress (spinner, auto-refresh 5s), awaiting approval (auto-expand remediation, approve/reject prominent), fast-path resolved (skip diagnosis/skeptic/remediation stages as "skipped"), diagnosis failed (show versioned re-attempt), remediation failed (show failed execution, rollback available), LLM unavailable (failed diagnosis with fast-path option), statistics empty (dashes, "no data"), API error (EmptyState danger with retry).
UX-DR21: Real-time updates via SSE subscription on incident detail views. Auto-refresh every 5s while any stage is active. Fall back to polling on connection drop.
UX-DR22: URL-persisted filter state — Firing/Resolved toggle and severity filter persist in URL query params. Breadcrumb back-navigation preserves filter state.

### FR Coverage Map

FR-1: Epic 1 — Webhook Receiver (alert intake)
FR-2: Epic 1 — Alert Deduplication and Correlation
FR-3: Epic 1 — Priority Queue
FR-4: Epic 2 — Orchestrator Agent (diagnosis)
FR-5: Epic 2 — Structured Diagnosis Output
FR-6: Epic 2 — Knowledge Retrieval and Operational Tools
FR-7: POST-MVP — Domain Specialist Agents (excluded from MVP epics)
FR-8: Epic 2 — Diagnosis Skeptic
FR-9: Epic 3 — Remediation Skeptic
FR-10: Epic 2 — Immutable Diagnosis Handoff
FR-11: Epic 3 — Structured Remediation Plan
FR-12: Epic 3 — Dry-Run Pre-Flight
FR-13: Epic 3 — Policy Gate
FR-14: Epic 3 (backend API) + Epic 5 (approval UI) — Human Approval Workflow
FR-15: Epic 3 — Serialized Execution
FR-16: Epic 3 — Outcome Observation
FR-17: Epic 3 — Rollback
FR-18: Epic 4 — Case Record Persistence
FR-19: Epic 4 — Temporal Decay
FR-20: Epic 4 — Vector DB Fast-Path
FR-21: Epic 5 — Standalone Web Application
FR-22: Epic 5 — Summary Dashboard
FR-23: POST-MVP — OpenShift Console Plugin (excluded from MVP epics)
FR-24: Epic 7 — Simulated Alert Injection
FR-25: Epic 7 — Accuracy Measurement
FR-26: Epic 7 — Auto-Remediation Trust Gate
FR-27: Epic 1 (chart skeleton) — Helm Chart Deployment
FR-28: Epic 6 — Per-Agent LLM Configuration
FR-29: Epic 6 — LLM Resilience
FR-30: Epic 6 — Complexity-Based Model Routing
FR-31: Epic 6 — Semantic Cache
FR-32: Epic 6 — Policy Matrix Configuration
FR-33: Epic 1 (API scaffolding) + Epic 5 (complete API) — REST API

NFR-1: Epic 1 (audit middleware), Epic 2 (read-only MCP/RBAC), Epic 3 (read-write MCP/RBAC, audit logging)
NFR-2: Epic 1 (queue persistence), Epic 2 (LangGraph checkpoints)
NFR-3: Epic 1 (intake latency, storm handling), Epic 4 (pgvector scaling)
NFR-4: Epic 1 (structured logging setup), distributed across all epics (metrics)

## Epic List

### Epic 1: Project Foundation & Alert Intake
The system receives AlertManager webhooks, deduplicates storm traffic, correlates related alerts into Root-Cause Events via a deterministic five-layer correlator, and maintains a PostgreSQL-backed Priority Queue for downstream processing. This epic establishes the monorepo structure, shared types module, database schema, canonical incident state machine, Helm chart skeleton, REST API scaffolding, and structured logging — the foundation all subsequent epics build on.
**FRs covered:** FR-1, FR-2, FR-3, FR-27 (chart skeleton), FR-33 (API scaffolding)
**NFRs addressed:** NFR-1 (audit middleware), NFR-2 (queue persistence), NFR-3 (intake latency, storm handling), NFR-4 (logging setup)
**Key ADs:** AD-3, AD-4, AD-5, AD-6, AD-14, AD-19, AD-23, AD-25

### Epic 2: AI Diagnosis Pipeline
Root-Cause Events are diagnosed by an AI orchestrator that queries the cluster via the read-only MCP Server, retrieves knowledge from OpenShift runbooks (pgvector RAG), RHOKP (via okp-mcp), and the Learning Store, invokes agentic skills as callable tools, and produces Structured Diagnosis Objects with root-cause codes from a controlled taxonomy. Every diagnosis survives a mandatory round of adversarial challenge from a Skeptic agent before becoming an Immutable Diagnosis Artifact that crosses the RBAC Airlock.
**FRs covered:** FR-4, FR-5, FR-6, FR-8, FR-10
**NFRs addressed:** NFR-1 (read-only MCP/RBAC), NFR-2 (LangGraph checkpoints)
**Key ADs:** AD-1, AD-2 (read-only side), AD-13, AD-15

### Epic 3: Remediation, Execution & Outcome
Validated diagnoses produce structured remediation plans (steps, blast radius, rollback, risk, preconditions) that are adversarially challenged by a Remediation Skeptic, validated via server-side dry-run, and evaluated against a configurable three-dimensional Policy Gate. Approved plans execute one at a time under a global PostgreSQL row-level lock with configurable cooldown. The system observes whether the originating alert resolves, performs post-remediation verification, and supports human-triggered rollback.
**FRs covered:** FR-9, FR-11, FR-12, FR-13, FR-14 (backend API), FR-15, FR-16, FR-17
**NFRs addressed:** NFR-1 (read-write MCP/RBAC, audit logging)
**Key ADs:** AD-2 (write side), AD-16, AD-18, AD-25

### Epic 4: Learning Store & Fast-Path
Every resolved incident is stored as a Case Record with vector embeddings in pgvector. Temporal decay reduces confidence of older or version-mismatched records. When a new alert matches a past successful Case Record above a configurable similarity threshold, the proven remediation is replayed directly — bypassing the full LLM diagnosis pipeline while still passing through the Policy Gate. The system gets faster, cheaper, and less LLM-dependent with every incident.
**FRs covered:** FR-18, FR-19, FR-20
**NFRs addressed:** NFR-3 (pgvector scaling)
**Key ADs:** AD-3, AD-20

### Epic 5: Operational Web UI & Approval Workflow
SREs manage incidents, review AI diagnoses, approve or reject remediations, and view operational metrics through a standalone PatternFly web application with Console shell layout (masthead + sidebar). The UI provides incident list with expandable RCE groups, full pipeline visualization via ProgressStepper, stage-specific content panels, real-time SSE updates, summary dashboard with statistics cards and time-series charts, and accessibility compliance (WCAG 2.2 AA). Works independently of OpenShift Console availability.
**FRs covered:** FR-14 (approval UI), FR-21, FR-22, FR-33 (complete API)
**UX-DRs covered:** UX-DR1 through UX-DR22 (all)
**Key ADs:** AD-10, AD-12, AD-21, AD-24

### Epic 6: LLM Configuration & Optimization
Teams configure per-agent LLM endpoints and models with layered override (Helm seed → runtime API → restart merge). Complexity-based model routing directs simple alerts to cheaper/faster models and complex multi-hop failures to frontier models. A semantic cache with cluster-context fingerprint invalidation reduces LLM cost and latency. The system handles LLM unavailability gracefully with exponential backoff and fast-path fallback. Policy matrix is configurable via Helm values or runtime API with audit-logged changes.
**FRs covered:** FR-28, FR-29, FR-30, FR-31, FR-32
**Key ADs:** AD-7, AD-17, AD-22

### Epic 7: Eval Harness & Trust Building
Teams validate diagnostic accuracy on simulated alert scenarios processed through the full diagnosis pipeline without executing remediation. Results are compared against human-validated answer keys, scoring diagnosis accuracy, remediation appropriateness, and time-to-response per domain. Auto-remediation enablement per domain is gated on eval harness results — passing produces a recommendation report that an SRE uses to explicitly relax the Policy Matrix.
**FRs covered:** FR-24, FR-25, FR-26

---

## Epic 1: Project Foundation & Alert Intake

The system receives AlertManager webhooks, deduplicates storm traffic, correlates related alerts into Root-Cause Events via a deterministic five-layer correlator, and maintains a PostgreSQL-backed Priority Queue for downstream processing. This epic establishes the monorepo structure, shared types module, database schema, canonical incident state machine, Helm chart skeleton, REST API scaffolding, and structured logging — the foundation all subsequent epics build on.

### Stories

| Story | Title | Dependency | Summary |
|-------|-------|------------|---------|
| 1.0 | Project Scaffolding & Shared Contracts | None | Monorepo layout, shared types, DB foundation, Helm skeleton, test infrastructure |
| 1.1 | Receive and Acknowledge AlertManager Webhooks | 1.0 | Webhook endpoint with 500ms SLA, payload validation, incident creation |
| 1.2 | Alert Deduplication and Storm Correlation | 1.1 | Five-layer deterministic correlator, settling windows, RCE sealing |
| 1.3 | Priority Queue and Pipeline Dispatch | 1.2 | PostgreSQL-backed priority queue, dequeue, TTL, resolved cancellation |
| 1.4 | REST API Foundation with Real-Time Events | 1.1 | REST endpoints, SSE, OAuth, audit logging |

### Story 1.0: Project Scaffolding & Shared Contracts

As a developer,
I want the monorepo structure, shared type contracts, database foundation, and test infrastructure established,
So that all subsequent stories have a working development environment and consistent patterns to build on.

**Acceptance Criteria:**

**Given** the project repository is initialized
**When** a developer inspects the directory structure
**Then** the monorepo layout matches AD-14: `backend/src/{api,pipeline,agents,models,knowledge,db,config}`, `backend/tests/`, `frontend/src/`, `charts/openshift-ai-ops/`, `docs/`

**Given** the Python project is configured
**When** a developer runs `pip install -e .` in `backend/`
**Then** all core dependencies are installed (FastAPI, LangGraph, Pydantic, asyncpg, prometheus-client)
**And** dev dependencies include pytest, testcontainers, httpx (for TestClient)

**Given** the shared types module at `backend/src/models/`
**When** inspected
**Then** it defines the Alert and Incident Pydantic models with the canonical incident state machine (`received → correlating → queued → diagnosing → diagnosed → awaiting_approval → executing → observing → resolved | failed`) and a state-machine transition function that all state writes must use

**Given** the state machine transition function
**When** an invalid transition is attempted (e.g., `received → executing`)
**Then** the function raises a typed error and does not modify state

**Given** the PostgreSQL database
**When** migrations run
**Then** the application schema (incidents, alerts, audit_log) is created separately from the `langgraph_*` schema domain per AD-3
**And** the migration tooling (Alembic or equivalent) is configured and documented

**Given** the backend application starts
**When** it processes any request or event
**Then** all log output is structured JSON to stdout with fields: `timestamp`, `level`, `component` (api|pipeline|agent|db|knowledge), and `request_id` or `incident_id` for correlation

**Given** the backend is running
**When** a client calls `GET /healthz`
**Then** the endpoint returns HTTP 200 with a health status indicating database connectivity

**Given** the Helm chart skeleton
**When** `helm template` is run
**Then** it renders a backend Deployment and a PostgreSQL StatefulSet with PVC-backed storage in a single namespace

**Given** the pytest configuration
**When** a developer inspects it
**Then** test markers are defined for `unit`, `db`, `api`, and `pipeline`
**And** `backend/tests/` mirrors `backend/src/` layout (e.g., `tests/models/`, `tests/api/`, `tests/db/`)

**Given** the test infrastructure
**When** a developer runs `pytest -m db`
**Then** a testcontainers fixture spins up PostgreSQL 18 + pgvector, runs migrations, and provides a clean database session per test
**And** the fixture is defined in `conftest.py` for reuse across all test modules

**Given** the test infrastructure
**When** a developer runs `pytest -m api`
**Then** a FastAPI TestClient fixture is available backed by the testcontainers database
**And** tests can exercise HTTP endpoints end-to-end against a real database

**Given** a developer clones the repository
**When** they follow the README setup instructions
**Then** they can start the backend dev server, see the health check pass, and run the test suite (which passes with the scaffolding tests)

### Story 1.1: Receive and Acknowledge AlertManager Webhooks

As an SRE,
I want AlertManager webhooks to be received and acknowledged by the system,
So that alert data enters the pipeline for processing without impacting AlertManager's performance.

**Acceptance Criteria:**

**Given** AlertManager sends a valid firing alert webhook payload
**When** the POST request reaches the webhook receiver endpoint
**Then** the system acknowledges with HTTP 200 within 500ms
**And** an incident record is created in the `received` state in PostgreSQL via the canonical state machine transition function

**Given** AlertManager sends a malformed or invalid webhook payload
**When** the POST request reaches the webhook receiver endpoint
**Then** the system rejects with HTTP 400
**And** the error is logged as structured JSON with timestamp, level, component, and request details

**Given** AlertManager sends a `resolved` webhook payload
**When** the POST request reaches the webhook receiver endpoint
**Then** the system acknowledges with HTTP 200
**And** the resolved status is recorded for downstream dequeue processing

**Given** the webhook endpoint
**When** load tested with concurrent requests
**Then** the 500ms acknowledgment SLA holds under burst traffic

**Given** a valid firing alert is received
**When** the incident is created
**Then** the alert fingerprint, labels, annotations, and firing timestamp are persisted alongside the incident record

### Story 1.2: Alert Deduplication and Storm Correlation

As an SRE,
I want related alerts to be automatically grouped into Root-Cause Events,
So that I deal with one problem per alert storm instead of dozens of individual symptoms.

**Acceptance Criteria:**

**Given** an alert with the same fingerprint is already being processed
**When** a duplicate alert fires
**Then** it is absorbed without creating a new queue entry or incident

**Given** two alerts in the same namespace fire within the severity-appropriate settling window
**When** the correlation engine evaluates them
**Then** they are grouped into a single Root-Cause Event with namespace + temporal proximity recorded as the correlation dimension

**Given** alerts sharing node, instance, or component labels fire within the settling window
**When** the correlation engine evaluates them
**Then** they are grouped into a single Root-Cause Event with label overlap + temporal proximity recorded as the correlation dimension

**Given** a known OpenShift cascade pattern exists in the static subsystem dependency graph
**When** related alerts fire (regardless of temporal proximity)
**Then** they are grouped into a single Root-Cause Event with the cascade pattern cited as the correlation dimension

**Given** the Learning Store co-occurrence interface is queried
**When** no past Case Records exist yet
**Then** the correlator proceeds using layers 1–4 without error (graceful empty-data handling)

**Given** a critical-severity alert arrives
**When** the settling window is evaluated
**Then** a 60-second window is used (Helm-configurable)

**Given** a warning-severity alert arrives
**When** the settling window is evaluated
**Then** a 5-minute window is used (Helm-configurable)

**Given** an info-severity alert arrives
**When** the settling window is evaluated
**Then** a 10-minute window is used (Helm-configurable)

**Given** a new alert joins an existing correlation group
**When** the group's settling timer is checked
**Then** the timer has been reset to the shortest window of any group member

**Given** a correlation group's age exceeds 3× its settling window
**When** the max age is reached
**Then** the group is sealed as a Root-Cause Event regardless of incoming alerts
**And** the incident state transitions from `received` to `correlating` during processing and to `queued` upon sealing via the state machine function

**Given** a sealed Root-Cause Event
**When** its correlation evidence is inspected
**Then** it shows which alerts were grouped, which correlation layers matched, and the reasoning for each grouping

### Story 1.3: Priority Queue and Pipeline Dispatch

As an SRE,
I want Root-Cause Events to be queued by priority and dispatched for processing,
So that the most urgent issues are diagnosed first and the queue survives system restarts.

**Acceptance Criteria:**

**Given** multiple Root-Cause Events in the priority queue
**When** the next event is dequeued for processing
**Then** the highest urgency × most recent event is selected first

**Given** concurrent pipeline workers attempt to dequeue simultaneously
**When** they execute the dequeue query
**Then** PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` prevents any event from being processed by more than one worker

**Given** a `resolved` webhook arrives from AlertManager
**When** the corresponding alert's Root-Cause Event is still in `queued` status
**Then** the queue entry is cancelled via `UPDATE ... WHERE status = 'queued'`
**And** the incident state transitions to `cancelled` if all alerts in the RCE are resolved

**Given** the parallelism cap is configured to N concurrent pipelines
**When** N diagnosis pipelines are already running
**Then** no additional Root-Cause Events are dequeued until a running pipeline completes

**Given** a Root-Cause Event has been in the queue beyond its configurable TTL
**When** the TTL check runs
**Then** the system verifies against the AlertManager API whether the alert is still active
**And** removes the entry if the alert is no longer firing

**Given** the backend pod crashes and restarts
**When** the application recovers
**Then** all queued Root-Cause Events are still present in PostgreSQL and processing resumes from where it left off

**Given** a sealed Root-Cause Event enters the priority queue
**When** it is enqueued
**Then** the incident state transitions to `queued` via the state machine function

### Story 1.4: REST API Foundation with Real-Time Events

As an SRE,
I want to query the system for incident status and receive real-time pipeline updates via API,
So that I can monitor alert processing from the web UI or automation tooling with full audit trail.

**Acceptance Criteria:**

**Given** any REST API endpoint
**When** a response is returned
**Then** it follows the envelope format `{data: T, meta: {timestamp, request_id}}`
**And** all endpoints are under the `/api/v1/` URL path

**Given** an unauthenticated request (no bearer token or invalid token)
**When** it reaches any API endpoint
**Then** the system returns HTTP 401 with the OpenShift OAuth challenge

**Given** a valid OpenShift OAuth bearer token
**When** calling `GET /api/v1/incidents`
**Then** the API returns a paginated list of incidents filterable by status (active, awaiting_approval, resolved, failed), severity, and time range

**Given** a valid bearer token and an existing incident ID
**When** calling `GET /api/v1/incidents/{id}`
**Then** the API returns full incident detail including correlated alerts, current pipeline state, and correlation evidence

**Given** an authenticated client subscribes to the SSE events endpoint
**When** a pipeline stage transitions or an incident state changes
**Then** the client receives an event matching the envelope `{event: string, data: {incident_id, stage, state, timestamp, payload}}` with dot-notation event names (e.g., `incident.stage_changed`, `incident.created`)

**Given** the in-process asyncio event bus
**When** a pipeline stage emits a state change event
**Then** all SSE-subscribed API clients receive the event without external message broker dependency

**Given** any state-changing REST request (POST, PUT, PATCH, DELETE)
**When** the request completes successfully
**Then** the audit log middleware writes a record to the `audit_log` table containing actor identity (from OAuth token), action, target resource, and timestamp

**Given** an API error occurs
**When** the error response is returned
**Then** it follows the structured error format `{error: string, code: string, detail: object}`

---

## Epic 2: AI Diagnosis Pipeline

Root-Cause Events are diagnosed by an AI orchestrator that queries the cluster via the read-only MCP Server, retrieves knowledge from OpenShift runbooks (pgvector RAG), RHOKP (via okp-mcp), and the Learning Store, invokes agentic skills as callable tools, and produces Structured Diagnosis Objects with root-cause codes from a controlled taxonomy. Every diagnosis survives a mandatory round of adversarial challenge from a Skeptic agent before becoming an Immutable Diagnosis Artifact that crosses the RBAC Airlock.

### Story 2.1: LangGraph Diagnosis Pipeline & MCP Integration

As an SRE,
I want a persistent agent pipeline that securely queries the cluster in read-only mode,
So that diagnosis work survives pod restarts and never risks modifying the cluster being diagnosed.

**Acceptance Criteria:**

**Given** a Root-Cause Event is dequeued from the priority queue
**When** it enters the diagnosis pipeline
**Then** LangGraph processes it as a directed graph with the diagnosis stage as a node
**And** the incident state transitions from `queued` to `diagnosing` via the state machine function

**Given** the LangGraph runtime is configured
**When** a pipeline checkpoint is written
**Then** it is persisted to PostgreSQL in the `langgraph_*` schema domain (black box — no application queries against these tables)

**Given** the backend pod crashes mid-diagnosis
**When** the pod restarts
**Then** the LangGraph pipeline resumes from the last persisted checkpoint without re-processing completed stages

**Given** the diagnosis pipeline needs cluster state
**When** it queries the cluster
**Then** it connects to the read-only MCP Server instance via Streamable HTTP transport
**And** the MCP Server is bound to the `cluster-reader` ServiceAccount with the `--read-only` flag

**Given** the Structured Diagnosis Object model is defined
**When** a diagnosis is produced
**Then** it conforms to the schema: `{root_cause_component, failure_mode, causal_chain: [...], affected_resources: [...], evidence: [...], evidence_gaps: [...], confidence: float}`
**And** root-cause codes come from the controlled taxonomy using slash-delimited format (e.g., `node/memory-pressure`, `storage/pvc-stuck-pending`)

**Given** two Structured Diagnosis Objects
**When** they are compared
**Then** deterministic comparison is available via root-cause hash (field diff of root_cause_component + failure_mode + sorted causal_chain)

**Given** an MCP Server query times out
**When** the diagnosis pipeline handles the timeout
**Then** it produces a partial-evidence continuation with the timed-out query listed in the `evidence_gaps` field
**And** diagnosis continues with available data rather than failing the pipeline

### Story 2.2: Orchestrator Agent & Runbook-Enriched Diagnosis

As an SRE,
I want an AI orchestrator to diagnose root causes using cluster data and OpenShift runbooks,
So that I receive structured, evidence-backed diagnoses without manually correlating symptoms across tools.

**Acceptance Criteria:**

**Given** a Root-Cause Event enters the diagnosis stage
**When** the Orchestrator agent processes it
**Then** it forms an initial subsystem hypothesis from the alert metadata (labels, annotations, alert name) and contextual knowledge

**Given** the Orchestrator has formed a hypothesis
**When** it investigates the root cause
**Then** it queries the cluster via the read-only MCP Server to gather evidence (resource states, logs, metrics)
**And** each piece of evidence is recorded as a concrete Evidence Artifact in the diagnosis (specific log line, metric value, or resource state — not free-text rationale)

**Given** OpenShift runbooks are bundled at container build time
**When** the diagnosis pipeline starts
**Then** runbooks have been chunked, embedded, and stored in pgvector for similarity search

**Given** the Orchestrator is diagnosing a Root-Cause Event
**When** it retrieves knowledge
**Then** it performs pgvector similarity search against runbook embeddings using the alert context and injects the top-k matching chunks into its reasoning context

**Given** the Orchestrator has completed its investigation
**When** it produces a Structured Diagnosis Object
**Then** the object includes a confidence score (0–1) reflecting the strength and completeness of supporting evidence

**Given** the Orchestrator is preparing to hand off to the Skeptic
**When** the completeness gate is evaluated
**Then** it verifies that the diagnosis addresses all correlated alerts in the Root-Cause Event and that no gathered evidence was left unexamined
**And** the diagnosis does not pass the completeness gate until all alerts are accounted for

**Given** an alert type that no Specialist claims (MVP has no specialists)
**When** the Orchestrator handles it as generalist of last resort
**Then** it flags a coverage gap in the diagnosis metadata ("no specialist covers this alert type") for visibility in the UI

**Given** conflicting evidence or multiple possible root causes
**When** the Orchestrator synthesizes a diagnosis
**Then** it produces a single diagnosis with a rationale for the selected root cause
**And** rejected alternative hypotheses are preserved in the audit trail

### Story 2.3: RHOKP, Learning Store & Agentic Skills Integration

As an SRE,
I want diagnosis enriched with Red Hat platform knowledge, past incident experience, and executable operational skills,
So that the system leverages all available knowledge sources for deeper, more accurate root-cause analysis.

**Acceptance Criteria:**

**Given** the RHOKP Solr instance is deployed with 600k+ Red Hat knowledge base documents
**When** the Orchestrator needs platform-level guidance during diagnosis
**Then** it queries RHOKP via the okp-mcp MCP server using Streamable HTTP transport
**And** uses the `search_portal` tool for multi-query search with reciprocal rank fusion and `get_document` for full content retrieval with BM25-scored passage extraction

**Given** past Case Records exist in the Learning Store (populated by Epic 4)
**When** the Orchestrator diagnoses a new Root-Cause Event
**Then** it queries pgvector for Case Records matching the current alert signature via embedding similarity
**And** relevant past diagnoses and outcomes inform the current investigation

**Given** no past Case Records exist yet (fresh deployment)
**When** the Learning Store is queried
**Then** the query returns empty results gracefully and diagnosis proceeds with other knowledge sources

**Given** agentic skills are available (e.g., cluster-update checks, token discovery, node diagnostics)
**When** the Orchestrator determines a skill is relevant during diagnosis
**Then** it invokes the skill as a callable tool
**And** the skill executes under the `cluster-reader` ServiceAccount (read-only enforcement)

**Given** a skill that requires write access exists
**When** the Orchestrator attempts to use it during diagnosis
**Then** the skill is classified as remediation-only and is unavailable — the invocation is blocked

**Given** the Orchestrator uses multiple knowledge sources during diagnosis
**When** the Structured Diagnosis Object is produced
**Then** the evidence array distinguishes the source of each artifact (MCP cluster query, runbook, RHOKP, Learning Store, agentic skill)

### Story 2.4: Diagnosis Skeptic & Immutable Handoff

As an SRE,
I want every diagnosis to survive adversarial challenge before I act on it,
So that I can trust the system's conclusions are robust, not hallucinated or incomplete.

**Acceptance Criteria:**

**Given** the Orchestrator produces a Structured Diagnosis Object that passes the completeness gate
**When** it is submitted to the Diagnosis Skeptic
**Then** the Skeptic produces a structured challenge containing: alternative hypotheses, evidence gaps, and logical weaknesses in the diagnosis

**Given** the Skeptic has issued a challenge
**When** the Orchestrator responds to the challenge
**Then** the response addresses each point in the challenge with evidence or reasoning

**Given** the Orchestrator's response to the Skeptic challenge
**When** the root-cause hash is compared before and after the challenge response
**Then** if the hash is unchanged, the diagnosis passes validation

**Given** the root-cause hash changes after the first challenge
**When** the diagnosis is fundamentally altered
**Then** the new diagnosis is re-challenged exactly one additional round
**And** after the second round, the diagnosis passes regardless of hash change (no infinite loops)

**Given** the Skeptic challenge and response
**When** the validation completes
**Then** both the challenge and response are persisted as part of the incident's audit trail

**Given** a diagnosis that passes Skeptic validation
**When** it is finalized
**Then** it becomes an Immutable Diagnosis Artifact — a read-only object that is persisted for audit and cannot be modified

**Given** an Immutable Diagnosis Artifact
**When** it crosses the RBAC Airlock to the remediation side
**Then** the remediation planner receives it as read-only input and cannot re-diagnose, re-interpret, or modify any field

**Given** the Skeptic must evaluate a diagnosis with non-empty `evidence_gaps`
**When** it reviews the diagnosis
**Then** it explicitly challenges the evidence gaps as a required part of its structured challenge

**Given** the diagnosis passes Skeptic validation
**When** the incident state is updated
**Then** it transitions from `diagnosing` to `diagnosed` via the state machine function

---

## Epic 3: Remediation, Execution & Outcome

Validated diagnoses produce structured remediation plans (steps, blast radius, rollback, risk, preconditions) that are adversarially challenged by a Remediation Skeptic, validated via server-side dry-run, and evaluated against a configurable three-dimensional Policy Gate. Approved plans execute one at a time under a global PostgreSQL row-level lock with configurable cooldown. The system observes whether the originating alert resolves, performs post-remediation verification, and supports human-triggered rollback.

### Story 3.1: Remediation Planner & Structured Plan

As an SRE,
I want the system to produce a structured remediation plan from the validated diagnosis,
So that I can review concrete steps, understand the blast radius, and have a rollback procedure before anything is executed.

**Acceptance Criteria:**

**Given** an Immutable Diagnosis Artifact from Epic 2
**When** it crosses the RBAC Airlock to the remediation side
**Then** the remediation planner receives it as read-only input and cannot modify, re-diagnose, or re-interpret any field

**Given** the remediation planner processes the Immutable Diagnosis Artifact
**When** it produces a Remediation Plan
**Then** the plan conforms to the schema: `{steps: [...], blast_radius: workload|namespace|node|cluster, rollback_plan: [...], estimated_risk: low|medium|high|critical, preconditions}`

**Given** the remediation planner needs to determine fix steps
**When** it queries the cluster for current state
**Then** it connects to the read-write MCP Server instance via Streamable HTTP (bound to `cluster-admin` ServiceAccount)

**Given** a remediation plan is produced
**When** the rollback procedure is evaluated
**Then** a rollback plan is included when feasible (e.g., revert a patch, uncordon a node)

**Given** a remediation plan is produced
**When** preconditions are evaluated
**Then** the plan enumerates RBAC permissions, quota availability, and resource prerequisites needed for execution

**Given** the remediation planner completes
**When** the plan is finalized
**Then** it is persisted to PostgreSQL as part of the incident record

### Story 3.2: Remediation Skeptic

As an SRE,
I want every remediation plan to survive adversarial challenge,
So that I can trust the proposed fix won't cause unintended damage or miss critical preconditions.

**Acceptance Criteria:**

**Given** a Remediation Plan is produced by the planner
**When** it is submitted to the Remediation Skeptic
**Then** the Skeptic evaluates: plan steps for correctness, blast radius assessment accuracy, rollback feasibility, precondition completeness, and estimated risk appropriateness

**Given** the Skeptic produces a structured challenge
**When** the planner responds
**Then** the plan hash is compared before and after the response

**Given** the plan hash is unchanged after the challenge response
**When** stability is assessed
**Then** the plan passes validation

**Given** the plan hash changes fundamentally after the first challenge
**When** the re-challenge protocol is triggered
**Then** the revised plan is re-challenged exactly one additional round
**And** after the second round, the plan passes regardless of hash change (no infinite loops)

**Given** the Skeptic challenge and planner response
**When** the validation completes
**Then** both the challenge and response are persisted as part of the incident's audit trail

### Story 3.3: Dry-Run Pre-Flight & Policy Gate

As an SRE,
I want remediation plans validated against the live cluster before execution and evaluated against my configured policy thresholds,
So that permission errors are caught early and only trusted remediations execute without my approval.

**Acceptance Criteria:**

**Given** a Remediation Plan passes Skeptic validation
**When** dry-run pre-flight executes
**Then** `oc apply --dry-run=server` validates resource manifests against the live API server
**And** admission webhook checks are exercised
**And** RBAC and quota checks confirm the remediation ServiceAccount has sufficient permissions

**Given** dry-run pre-flight results are available
**When** they are recorded
**Then** they are persisted alongside the plan for display in the approval UI

**Given** a validated Remediation Plan with dry-run results
**When** the Policy Gate evaluates it
**Then** it checks three dimensions: alert severity (from AlertManager) × blast radius (from plan) × diagnosis confidence (from Structured Diagnosis)
**And** all three dimensions must pass their configured thresholds for auto-execution

**Given** the diagnosis has non-empty `evidence_gaps` (from MCP timeouts)
**When** the Policy Gate evaluates the plan
**Then** auto-execution is blocked regardless of other matrix dimensions

**Given** the diagnosis lacks at least one concrete evidence artifact per element in the causal chain
**When** the Policy Gate evaluates the plan
**Then** auto-execution is blocked regardless of other matrix dimensions

**Given** all three policy dimensions pass threshold and evidence requirements are met
**When** the Policy Gate renders its decision
**Then** the plan proceeds to auto-execution
**And** the incident state transitions from `diagnosed` to `executing` via the state machine function

**Given** any policy dimension fails threshold or evidence is incomplete
**When** the Policy Gate renders its decision
**Then** the plan is queued for human approval with full context (diagnosis, plan, skeptic assessments, dry-run results)
**And** the incident state transitions from `diagnosed` to `awaiting_approval` via the state machine function

### Story 3.4: Human Approval Workflow (Backend API)

As an on-call SRE,
I want to review and approve or reject remediation plans that require my judgment,
So that I maintain control over cluster changes while benefiting from AI-prepared context.

**Acceptance Criteria:**

**Given** a remediation plan is queued for human approval
**When** the approval API endpoint is queried
**Then** it returns full context: diagnosis summary, complete remediation plan, skeptic challenge/response, dry-run results (if available), and blast radius assessment

**Given** an authenticated SRE calls the approve endpoint
**When** approval is submitted
**Then** the approval is recorded with the approver's identity (from OAuth token) and timestamp
**And** the incident state transitions from `awaiting_approval` to `executing` via the state machine function
**And** the approval is written to the `audit_log` table via the audit middleware

**Given** an authenticated SRE calls the reject endpoint
**When** rejection is submitted with a reason
**Then** the rejection is recorded with the rejector's identity, timestamp, and reason
**And** the incident state transitions from `awaiting_approval` to `failed` via the state machine function

**Given** a remediation plan with `node` or `cluster` blast radius
**When** the minimum review time is configured (e.g., 60 seconds)
**Then** the approve action is not available until the minimum review time has elapsed since the plan was queued
**And** the minimum review time is configurable and can be disabled

**Given** an SRE approves a remediation
**When** they also want to adjust future policy for this category
**Then** the API supports modifying the policy gate thresholds for the matching severity/blast-radius/confidence combination
**And** the policy change is audit-logged

### Story 3.5: Serialized Execution, Outcome Observation & Rollback

As an SRE,
I want remediations executed safely one at a time with automatic outcome monitoring and the option to roll back,
So that the cluster is never subjected to conflicting concurrent changes and I know immediately whether the fix worked.

**Acceptance Criteria:**

**Given** a remediation plan is approved (by policy gate or human)
**When** execution begins
**Then** a global lock is acquired via PostgreSQL row-level lock (`SELECT FOR UPDATE NOWAIT` on `remediation_locks` table)
**And** if the lock cannot be acquired, execution waits until the current remediation completes

**Given** a remediation is queued for execution
**When** the freshness gate runs before execution
**Then** it re-validates that the originating alert is still firing and the diagnosis is still relevant to current cluster state
**And** stale remediations (alert resolved during wait, or cluster state changed by a prior fix) are skipped with the diagnosis preserved as an informational case record

**Given** a fresh, locked remediation plan
**When** it executes
**Then** it uses the read-write MCP Server instance exclusively (bound to `cluster-admin` ServiceAccount)
**And** execution steps are logged with timestamps to the incident record

**Given** execution completes
**When** outcome observation begins
**Then** the system monitors for the corresponding `resolved` webhook from AlertManager within a configurable timeout
**And** it performs post-remediation verification by checking the `affected_resources` from the Structured Diagnosis Object via the read-only MCP Server

**Given** the originating alert resolves after execution
**When** the outcome is recorded
**Then** alert resolution is the primary success signal and direct resource verification is the corroborating signal
**And** the outcome includes an `outcome_confidence` field reflecting the strength of corroborating evidence (not just binary success/failure)
**And** the incident state transitions from `observing` to `resolved` via the state machine function

**Given** the alert does not resolve within the timeout
**When** the outcome is recorded
**Then** the incident state transitions from `observing` to `failed` via the state machine function

**Given** the alert re-fires within a configurable window after a "successful" resolution
**When** the re-fire is detected
**Then** the Case Record (when created in Epic 4) is retroactively downgraded and the remediation is flagged for review

**Given** a configurable cooldown period between remediations
**When** the current remediation completes (success or failure)
**Then** the global lock is held through outcome observation and the cooldown period before release

**Given** a completed remediation (success or failure)
**When** an SRE reviews the outcome
**Then** the rollback plan from the Remediation Plan is available via the API
**And** rollback is human-triggered only — the system never initiates rollback automatically

**Given** an SRE triggers rollback
**When** the rollback executes
**Then** the rollback action is recorded as a failure signal (for the Learning Store in Epic 4)
**And** the rollback execution is audit-logged with the actor's identity

---

## Epic 4: Learning Store & Fast-Path

Every resolved incident is stored as a Case Record with vector embeddings in pgvector. Temporal decay reduces confidence of older or version-mismatched records. When a new alert matches a past successful Case Record above a configurable similarity threshold, the proven remediation is replayed directly — bypassing the full LLM diagnosis pipeline while still passing through the Policy Gate. The system gets faster, cheaper, and less LLM-dependent with every incident.

### Story 4.1: Case Record Persistence & Vector Embeddings

As an SRE,
I want every resolved incident stored as a structured case record with searchable embeddings,
So that the system accumulates operational knowledge and can find similar past incidents for future diagnosis.

**Acceptance Criteria:**

**Given** an incident reaches a terminal state (resolved or failed)
**When** the outcome is finalized
**Then** a Case Record is persisted containing: alert signature, root-cause code, full Structured Diagnosis Object, Remediation Plan, outcome (success/failure with outcome_confidence), and cluster context (OCP version, topology snapshot)

**Given** a Case Record is created
**When** it is stored in PostgreSQL
**Then** vector embeddings are generated and stored in pgvector for similarity search against future alert contexts

**Given** a remediation fails or an SRE triggers rollback
**When** the Case Record is created
**Then** it is stored as a negative case with the failure reason
**And** negative cases are excluded from fast-path replay eligibility

**Given** a previously "successful" remediation's alert re-fires within the configurable window (detected in Story 3.5)
**When** the re-fire is confirmed
**Then** the Case Record is retroactively downgraded with reduced outcome_confidence and flagged for review

**Given** the Case Record table schema
**When** it is inspected
**Then** it is owned by the Learning Store module in `db/` per AD-20
**And** correlation (Epic 1) reads case records via pgvector similarity search and relational SQL queries but does not modify the schema

**Given** the Learning Store accumulates case records
**When** the dataset grows to thousands or more records
**Then** pgvector indexes (IVFFlat or HNSW) maintain query performance for similarity search

### Story 4.2: Temporal Decay & Version Relevance

As an SRE,
I want the system to naturally favor recent, version-relevant fixes over old ones,
So that stale knowledge from previous cluster versions doesn't mislead diagnosis or remediation.

**Acceptance Criteria:**

**Given** a Case Record with a known age and OCP version
**When** its effective confidence is calculated at query time
**Then** it applies the formula: `effective_confidence = base_confidence × decay_factor(age) × version_relevance(OCP_version_then vs OCP_version_now)`

**Given** a Case Record from a different OCP major version than the current cluster
**When** its version relevance is calculated
**Then** it carries reduced version relevance compared to a record from the same major version

**Given** a Case Record that is several months old
**When** its decay factor is calculated
**Then** its effective confidence is lower than an identical record created recently

**Given** the decay parameters (decay rate, version relevance weights)
**When** they are configured
**Then** they are adjustable via Helm values or runtime API configuration

**Given** a similarity search against the Learning Store
**When** results are ranked
**Then** effective confidence (with temporal decay applied) is used for ranking, not raw base confidence

### Story 4.3: Fast-Path Bypass for Known Patterns

As an SRE,
I want recurring known issues to be resolved at machine speed without waiting for LLM diagnosis,
So that proven fixes replay instantly while the system still enforces policy controls.

**Acceptance Criteria:**

**Given** a Root-Cause Event is dequeued from the priority queue
**When** the queue consumer checks for a fast-path match before dispatching to the diagnosis pipeline
**Then** it queries pgvector for Case Records matching the current alert signature above a configurable similarity threshold

**Given** a fast-path match is found above the similarity threshold
**When** the match is evaluated
**Then** only records with successful outcomes (positive cases) are eligible for fast-path replay

**Given** an eligible fast-path match exists
**When** the fast-path is activated
**Then** the proven remediation plan is replayed directly, bypassing the full LLM diagnosis pipeline (orchestrator, skeptic)
**And** the incident state shortcuts from `queued` to `diagnosed` (skipping agent work) per AD-19

**Given** a fast-path remediation plan
**When** it enters the remediation flow
**Then** it still passes through the dry-run pre-flight and Policy Gate (Epic 3) — no shortcut to execution

**Given** a fast-path match was used
**When** the incident is displayed in the UI (Epic 5)
**Then** it is visually distinguishable from a full-diagnosis incident (the fast-path badge and similarity score are available in the incident record)

**Given** no fast-path match exists above the threshold
**When** the check completes
**Then** the Root-Cause Event proceeds to the full diagnosis pipeline (Epic 2) as normal

**Given** the fast-path similarity threshold
**When** it is configured
**Then** it is adjustable via Helm values or runtime API configuration

---

## Epic 5: Operational Web UI & Approval Workflow

SREs manage incidents, review AI diagnoses, approve or reject remediations, and view operational metrics through a standalone PatternFly web application with Console shell layout (masthead + sidebar). The UI provides incident list with expandable RCE groups, full pipeline visualization via ProgressStepper, stage-specific content panels, real-time SSE updates, summary dashboard with statistics cards and time-series charts, and accessibility compliance (WCAG 2.2 AA). Works independently of OpenShift Console availability.

### Story 5.1: Frontend Scaffolding & App Shell

As an SRE,
I want a standalone web application with the same look and feel as the OpenShift Console,
So that the tool feels familiar and will migrate seamlessly to a Console plugin in the future.

**Acceptance Criteria:**

**Given** the frontend project is initialized
**When** a developer inspects the structure
**Then** it is a React 19 + TypeScript 7 application using PatternFly 6 (`@patternfly/react-core`) in `frontend/src/`

**Given** the application loads
**When** the shell renders
**Then** it displays a horizontal masthead (top) and vertical navigation sidebar (left) matching the OpenShift Console layout per UX-DR6
**And** the sidebar contains two nav items: "Incidents" and "Statistics"

**Given** the application loads for the first time
**When** the theme is applied
**Then** dark mode is the default theme per UX-DR5
**And** a PatternFly theme toggle is available in the masthead to switch between dark and light modes
**And** no custom dark-mode tokens or hex colors are used — all theming is via PatternFly CSS custom properties

**Given** an unauthenticated user accesses the application
**When** the page loads
**Then** the frontend initiates the OpenShift OAuth flow per AD-12
**And** all subsequent API calls include the bearer token in the Authorization header

**Given** the frontend makes an API call
**When** the response is received
**Then** it correctly handles the `{data: T, meta: {timestamp, request_id}}` envelope format
**And** error responses in `{error, code, detail}` format are parsed and displayed appropriately

**Given** the Helm chart
**When** the frontend deployment is added
**Then** it includes an nginx container serving the built React application as static assets
**And** the Deployment is configured for the single namespace per AD-9

### Story 5.2: Incidents List View

As an SRE,
I want to see all active incidents organized by root-cause groups with filtering,
So that I can quickly scan the current state of the cluster and focus on what needs my attention.

**Acceptance Criteria:**

**Given** the Incidents view loads with active incidents
**When** the DataList renders
**Then** incidents are grouped by Root-Cause Event as expandable rows per UX-DR7
**And** each RCE group header shows: RCE label, correlated alert count badge, highest severity Label (PatternFly `Label` with `danger`/`warning`/`info` variant), and time since first alert
**And** groups are collapsed by default, sorted by highest severity first

**Given** an RCE group header
**When** the user clicks it
**Then** it expands to reveal individual alert rows within the group (no page navigation)

**Given** an individual alert row within an expanded RCE group
**When** the user clicks it
**Then** the application navigates to the full-page Incident Detail view

**Given** a fast-path incident exists in the list
**When** it is rendered
**Then** a PatternFly `Label` (info, compact) with "Fast-Path" text is displayed on the row per UX-DR4

**Given** the Incidents toolbar
**When** it renders
**Then** it includes a Firing/Resolved `ToggleGroup` (Firing selected by default) per UX-DR8
**And** selecting "Resolved" reveals a time-range dropdown (1h, 6h, 24h, 7d)

**Given** the Incidents toolbar
**When** it renders
**Then** it includes a severity `Select` (checkbox variant) for multi-select filtering (critical, warning, info — all selected by default) per UX-DR9

**Given** the Firing/Resolved toggle or severity filter is changed
**When** the filter state updates
**Then** the selection persists in URL query parameters per UX-DR22
**And** navigating back from the detail view restores the filter state

**Given** no alerts are currently firing
**When** the Incidents view loads in Firing mode
**Then** a PatternFly `EmptyState` is displayed with check-circle success icon and text "No active alerts." — no call-to-action per UX-DR16

**Given** the Incidents view is loading data
**When** the API call is in flight
**Then** PatternFly `Skeleton` rows (6–8) matching the DataList layout shape are displayed per UX-DR17

**Given** the API returns an error
**When** the Incidents view handles it
**Then** a PatternFly `EmptyState` with danger icon displays "Unable to reach the API." with a Retry button per UX-DR20

### Story 5.3: Incident Detail View & Pipeline Visualization

As an SRE,
I want to see the full diagnostic pipeline for an incident with expandable stage details,
So that I can understand exactly what the system did, what it found, and what it recommends.

**Acceptance Criteria:**

**Given** the user navigates to an incident detail
**When** the page loads
**Then** a PatternFly `Breadcrumb` displays "Incidents > {Alert Name}" per UX-DR13
**And** clicking "Incidents" returns to the list view preserving the previous filter state (Firing/Resolved, severity, time range)

**Given** the incident detail page
**When** the pipeline visualization renders
**Then** it uses a PatternFly `ProgressStepper` (horizontal, `isCenterAligned`) with six stages: Triage, Diagnosis, Skeptic, Remediation, Execution, Outcome per UX-DR10
**And** each stage shows icon + label + state using semantic variants per UX-DR1: completed (check-circle, success), active (in-progress, info), awaiting (pending, warning), failed (exclamation-circle, danger), skipped (minus-circle, disabled)

**Given** the pipeline visualization
**When** a stage is clicked
**Then** a content panel expands below it showing the stage-specific content per UX-DR11 (accordion — only one panel open at a time)
**And** the currently active stage auto-expands on page load

**Given** the Triage stage content panel
**When** expanded
**Then** it displays: alert payload summary, correlation reasoning (which alerts grouped and why), priority score using `DescriptionList`

**Given** the Diagnosis stage content panel
**When** expanded
**Then** it displays: root-cause code (as PatternFly `Label`), causal chain (ordered list), affected resources, evidence artifacts (collapsible section), agent conversation summary (prose), and confidence score as a PatternFly `Label` (compact) with three tiers per UX-DR2 — high (success), medium (warning), low (danger)

**Given** the Skeptic stage content panel
**When** expanded
**Then** it displays: challenge summary, response summary, and stability verdict (pass/fail with reasoning)

**Given** the Remediation stage content panel
**When** expanded
**Then** it displays: plan steps (ordered list), blast radius (`Label`: workload/namespace/node/cluster), rollback plan (collapsible), dry-run confidence badge per UX-DR2, and preconditions list

**Given** the Execution stage content panel
**When** expanded
**Then** it displays: execution log (timestamped steps), MCP Server calls made, duration, and current status (running/completed/failed)

**Given** the Outcome stage content panel
**When** expanded
**Then** it displays: resolution status (alert resolved: yes/no), time to resolution, post-remediation verification results, and case record link

**Given** a fast-path incident
**When** the detail view renders
**Then** Diagnosis, Skeptic, and Remediation stages show `skipped` state (greyed, minus-circle icon) per UX-DR20
**And** a "Fast-Path" `Label` (info) with similarity score is displayed in the page header

**Given** a diagnosis that failed and was re-challenged
**When** the Diagnosis stage content panel is expanded
**Then** both the original and re-challenged diagnosis attempts are shown (versioned) per UX-DR20

**Given** a failed remediation
**When** the detail view renders
**Then** the Execution stage shows `failed` and the Outcome stage shows alert-not-resolved
**And** the rollback action is available per UX-DR20

**Given** an LLM-unavailable diagnosis
**When** the detail view renders
**Then** the Diagnosis stage shows `failed` with message "Diagnosis unavailable — LLM unreachable"
**And** if a fast-path match exists, a fast-path badge appears with an option to proceed per UX-DR20

### Story 5.4: Approval Workflow & Real-Time Updates

As an on-call SRE,
I want to approve or reject remediations directly in the UI with real-time pipeline progress,
So that I can act on recommendations immediately without refreshing the page or polling for updates.

**Acceptance Criteria:**

**Given** an incident is in `awaiting_approval` state
**When** the detail view loads
**Then** the Remediation stage auto-expands with Approve (PatternFly `Button`, primary) and Reject (PatternFly `Button`, danger) buttons as the first element in the panel per UX-DR12
**And** these are single-click actions with no confirmation modal for standard blast radius

**Given** the user clicks Approve
**When** the API call succeeds
**Then** the pipeline visualization updates in real time: Remediation transitions to `completed`, Execution transitions to `active`
**And** the navigation approval badge count decrements

**Given** the user clicks Reject
**When** the API call succeeds
**Then** the incident transitions to `failed` state and the pipeline reflects it

**Given** incidents are awaiting approval
**When** the sidebar navigation renders
**Then** the "Incidents" nav item displays a PatternFly `NotificationBadge` with the count of items in `awaiting` state per UX-DR3
**And** the badge is hidden when the count is 0

**Given** the user is viewing an incident detail page
**When** any pipeline stage transitions
**Then** the update arrives via SSE subscription per UX-DR21
**And** the pipeline visualization updates without page refresh

**Given** a pipeline stage is in `active` state
**When** the detail view is displayed
**Then** it auto-refreshes every 5 seconds while any stage is active per UX-DR20

**Given** the SSE connection drops
**When** reconnection fails
**Then** the frontend falls back to polling the REST API for updates per UX-DR21

### Story 5.5: Statistics Dashboard

As an ops team lead,
I want to see operational metrics and trends at a glance,
So that I can report on the tool's effectiveness and identify areas for improvement.

**Acceptance Criteria:**

**Given** the user navigates to the Statistics view
**When** the page loads with data
**Then** five PatternFly `Card` (compact) tiles render across the top row per UX-DR14: total incidents handled, auto-resolved percentage, success/failure ratio, mean time to resolution (MTTR), and fast-path hit rate
**And** each card shows the current value and a trend indicator (up/down/flat compared to the previous period)

**Given** the Statistics view with data
**When** the charts render
**Then** PatternFly Charts display: alerts over time, diagnoses over time, and resolutions over time as line charts; MTTR as a separate area chart per UX-DR15

**Given** the Statistics view
**When** the user selects a time range
**Then** a time-range selector offers day, week, and month options per UX-DR15
**And** all cards and charts update to reflect the selected range

**Given** the Statistics view data
**When** it is displayed
**Then** the data is read-only — no approval or configuration actions are available from this view

**Given** the Statistics view on a fresh deployment with no data
**When** the page loads
**Then** cards show "—" for values and charts display "No data for this time range." per UX-DR20

**Given** the Statistics view is loading
**When** the API calls are in flight
**Then** cards display PatternFly `Skeleton` and charts show the PatternFly chart skeleton pattern per UX-DR17

**Given** the backend REST API
**When** the statistics endpoints are called
**Then** they return aggregated data for the summary cards and time-series chart data filterable by the requested time range
**And** responses follow the standard `{data, meta}` envelope

### Story 5.6: Keyboard Shortcuts & Accessibility

As an SRE,
I want full keyboard navigation and screen reader support,
So that I can operate the tool efficiently and it meets WCAG 2.2 AA compliance.

**Acceptance Criteria:**

**Given** the Incidents list view
**When** the user presses `j` or `k`
**Then** focus moves down or up through incident list rows per UX-DR18

**Given** a focused incident row
**When** the user presses `Enter`
**Then** the application navigates to the incident detail view per UX-DR18

**Given** the incident detail view
**When** the user presses `Backspace` or `Esc`
**Then** the application returns to the Incidents list per UX-DR18

**Given** the incident detail view
**When** the user presses `1` through `6`
**Then** the corresponding pipeline stage is selected and its content panel expands per UX-DR18

**Given** the incident detail view with Remediation stage in `awaiting` state and expanded
**When** the user presses `a`
**Then** the approve action is triggered per UX-DR18

**Given** pipeline stage states in the ProgressStepper
**When** a screen reader encounters them
**Then** each stage communicates its state via `aria-label` (e.g., "Diagnosis: completed", "Remediation: awaiting approval") — not color alone per UX-DR19

**Given** a DataList RCE group
**When** a screen reader encounters the expansion control
**Then** the expansion state is announced (e.g., "Root-Cause Event: etcd fsync latency, 3 correlated alerts, collapsed. Activate to expand.") per UX-DR19

**Given** the Approve and Reject buttons
**When** a screen reader encounters them
**Then** they include `aria-describedby` linking to the remediation plan summary so the user gets context before acting per UX-DR19

**Given** the ProgressStepper stages
**When** keyboard navigation is used
**Then** left/right arrow keys move between stages per the PatternFly ProgressStepper accessibility pattern per UX-DR19

**Given** the user navigates from the Incidents list to a detail view
**When** the detail page loads
**Then** focus moves to the breadcrumb per UX-DR19
**And** when returning to the list, focus is restored to the previously selected row

**Given** the Statistics charts
**When** a screen reader encounters them
**Then** each chart includes an `aria-label` with a text summary of the data (e.g., "Line chart: 23 alerts over the last 7 days, peak on Tuesday") per UX-DR19

**Given** an alert storm produces many RCE groups
**When** the Incidents list renders
**Then** all groups are collapsed by default with highest-severity groups sorted to the top per UX-DR20
**And** the full list renders without pagination (scroll) per the EXPERIENCE.md specification

---

## Epic 6: LLM Configuration & Optimization

Teams configure per-agent LLM endpoints and models with layered override (Helm seed → runtime API → restart merge). Complexity-based model routing directs simple alerts to cheaper/faster models and complex multi-hop failures to frontier models. A semantic cache with cluster-context fingerprint invalidation reduces LLM cost and latency. The system handles LLM unavailability gracefully with exponential backoff and fast-path fallback. Policy matrix is configurable via Helm values or runtime API with audit-logged changes.

### Story 6.1: Per-Agent LLM Configuration & Layered Override

As an SRE team,
I want to configure different LLM endpoints and models for each agent role,
So that I can optimize cost, latency, and quality per task type without being locked to a single provider.

**Acceptance Criteria:**

**Given** the LLM configuration system
**When** agent roles are configured
**Then** each role (orchestrator, specialists, skeptics, remediation planner) can be pointed to a different LLM endpoint with independent model name, temperature, and thinking/reasoning mode settings

**Given** the LLM configuration
**When** it specifies an endpoint
**Then** it includes: URL, credentials (from Kubernetes Secret reference), model name, temperature, and whether to use thinking/reasoning mode
**And** no dependency on OpenShift AI exists — any compatible LLM endpoint works

**Given** Helm values define initial LLM configuration
**When** the backend starts for the first time
**Then** the Helm values seed the agent LLM configuration in the database

**Given** an SRE modifies LLM configuration via the runtime API
**When** the change is persisted
**Then** it is stored in the application database and takes precedence over Helm values immediately
**And** the change is audit-logged with actor identity and timestamp

**Given** the backend pod restarts
**When** configuration loads
**Then** Helm defaults load first, then DB-stored overrides are applied on top per AD-7
**And** DB always wins for any field it overrides

**Given** the runtime configuration API
**When** an SRE queries it
**Then** it returns the effective configuration per agent role (merged view of Helm + DB overrides)

### Story 6.2: LLM Resilience & Graceful Degradation

As an SRE,
I want the system to handle LLM unavailability without losing incidents,
So that alert processing continues even when the AI backend is temporarily unreachable.

**Acceptance Criteria:**

**Given** an LLM endpoint returns a transient error (timeout, 5xx)
**When** the agent makes an inference call
**Then** the client retries with configurable exponential backoff per AD-7

**Given** all retry attempts are exhausted for an LLM call
**When** a fast-path match exists for the current alert
**Then** the system proceeds with the fast-path remediation (proven plan from the Learning Store) without LLM involvement

**Given** all retry attempts are exhausted and no fast-path match exists
**When** the pipeline cannot proceed
**Then** the incident is queued with a "diagnosis unavailable — LLM unreachable" status visible in the UI and API
**And** the pipeline does not fail permanently — it can be retried when the LLM recovers

**Given** the retry configuration
**When** it is inspected
**Then** backoff parameters (initial delay, multiplier, max retries, max delay) are configurable per agent role via Helm values or runtime API

**Given** an LLM call succeeds or fails
**When** the outcome is recorded
**Then** the LLM call latency and error rate are available as Prometheus metrics per NFR-4

### Story 6.3: Complexity-Based Model Routing

As an SRE team,
I want simple alerts routed to cheaper models and complex failures to frontier models,
So that we optimize LLM costs without sacrificing diagnostic quality on hard problems.

**Acceptance Criteria:**

**Given** a Root-Cause Event enters the diagnosis pipeline
**When** the model router evaluates complexity
**Then** it estimates task complexity based on: alert type, number of correlated alerts in the RCE, and whether a partial fast-path match exists

**Given** a simple, well-known alert pattern (e.g., single alert, common type, partial fast-path match)
**When** the router selects a model
**Then** it routes to the cheaper, faster model configured for low-complexity tasks

**Given** a complex multi-hop failure pattern (e.g., multiple correlated alerts across subsystems, no fast-path match)
**When** the router selects a model
**Then** it routes to the frontier model configured for high-complexity tasks

**Given** the model routing rules
**When** they are configured
**Then** complexity heuristics and model assignments are configurable via Helm values or runtime API per AD-7

**Given** a diagnosis completes
**When** the incident record is inspected
**Then** the audit trail records which model handled the diagnosis (model name, endpoint)

### Story 6.4: Semantic Cache & Policy Matrix Configuration

As an SRE team,
I want LLM responses cached for similar queries and the policy matrix configurable at runtime,
So that we reduce redundant LLM calls and tune auto-remediation thresholds without redeploying.

**Acceptance Criteria:**

**Given** an agent is about to send a prompt to the LLM
**When** the semantic cache middleware in `knowledge/` intercepts the call per AD-22
**Then** it checks pgvector for prior responses to sufficiently similar prompts in a similar cluster context

**Given** a cache hit above the similarity threshold with a matching cluster-context fingerprint
**When** the cached response is found
**Then** it is returned directly, bypassing the LLM call entirely

**Given** a cache entry exists but the cluster-context fingerprint has changed (OCP version upgrade or topology change)
**When** the cache is queried
**Then** the stale entry is not returned — the query proceeds to the LLM per AD-17

**Given** a new LLM response is received
**When** it is stored in the cache
**Then** it is persisted in pgvector (via `db/`) with the prompt embedding and the current cluster-context fingerprint (OCP version + topology hash)

**Given** the semantic cache
**When** its performance is monitored
**Then** the cache hit rate is exposed as a Prometheus metric per FR-31

**Given** the auto-remediation policy matrix
**When** an SRE configures it via Helm values
**Then** the three-dimensional matrix (severity × blast radius × confidence) is fully customizable
**And** the default configuration requires human approval for all remediations (most conservative)

**Given** the policy matrix
**When** an SRE modifies it via the runtime API
**Then** the change is persisted to the database, takes effect immediately, and is audit-logged with actor identity per AD-7

**Given** the policy matrix runtime API
**When** queried
**Then** it returns the effective matrix (merged Helm defaults + DB overrides)

---

## Epic 7: Eval Harness & Trust Building

Teams validate diagnostic accuracy on simulated alert scenarios processed through the full diagnosis pipeline without executing remediation. Results are compared against human-validated answer keys, scoring diagnosis accuracy, remediation appropriateness, and time-to-response per domain. Auto-remediation enablement per domain is gated on eval harness results — passing produces a recommendation report that an SRE uses to explicitly relax the Policy Matrix.

### Story 7.1: Simulated Alert Injection

As an SRE team,
I want to inject simulated alerts into the system for evaluation without risking real cluster changes,
So that I can test the system's diagnostic capabilities safely before relying on it in production.

**Acceptance Criteria:**

**Given** the eval harness API
**When** simulated alert payloads are submitted
**Then** they are accepted and processed through the full diagnosis pipeline (triage, correlation, orchestrator, skeptic)

**Given** a simulated alert is processed
**When** the pipeline reaches remediation
**Then** a remediation plan is generated but NOT executed — execution is blocked for eval-mode incidents

**Given** eval harness results (diagnoses and remediation plans)
**When** they are stored
**Then** they are persisted in a separate eval results store, not mixed with production Case Records

**Given** a simulated alert payload
**When** it is submitted to the eval harness
**Then** it is distinguishable from real AlertManager webhooks via an eval-mode flag
**And** eval-mode incidents do not appear in the production Incidents list or affect the navigation approval badge

**Given** the eval harness
**When** multiple simulated scenarios are submitted
**Then** they can be submitted as a batch and processed sequentially

### Story 7.2: Accuracy Measurement & Domain Scoring

As an SRE team,
I want the system's diagnostic accuracy measured against known-correct answers,
So that I have objective evidence of its competence before extending trust.

**Acceptance Criteria:**

**Given** each simulated scenario includes a human-validated answer key
**When** the answer key is defined
**Then** it contains: a known-correct root-cause code (from the controlled taxonomy) and an expected remediation approach

**Given** the eval harness has processed a simulated scenario
**When** the result is scored
**Then** the system measures: diagnosis accuracy (correct root-cause identification — root-cause code match), remediation appropriateness (plan alignment with expected approach), and time-to-response (latency from alert injection to diagnosis completion)

**Given** eval harness results across multiple scenarios
**When** they are aggregated
**Then** scores are aggregated per domain (compute, storage, network) and overall
**And** individual scenario results are also available for drill-down

**Given** eval harness scoring results
**When** they are queried via the API
**Then** they return per-domain accuracy percentages, aggregated remediation appropriateness, and mean time-to-response

### Story 7.3: Auto-Remediation Trust Gate

As an SRE team lead,
I want auto-remediation gated on proven eval harness performance per domain,
So that I can progressively extend trust based on measured accuracy, not blind faith.

**Acceptance Criteria:**

**Given** a domain (e.g., storage) has been evaluated by the eval harness
**When** its accuracy score meets or exceeds the configurable accuracy threshold
**Then** the eval harness produces a recommendation report stating the domain passed and recommending policy relaxation

**Given** the recommendation report
**When** an SRE reviews it
**Then** it includes: domain name, number of scenarios tested, accuracy score, threshold required, pass/fail verdict, and a summary of any failed scenarios

**Given** the recommendation report indicates a domain passed
**When** an SRE wants to enable auto-remediation for that domain
**Then** they explicitly relax the Policy Matrix for the matching severity/blast-radius/confidence combinations via the runtime API (Story 6.4)
**And** the eval harness does NOT automatically change the Policy Matrix — human action is required

**Given** the accuracy threshold
**When** it is configured
**Then** it is configurable per-domain, not globally, via Helm values or runtime API

**Given** the eval harness configuration
**When** the threshold and current pass rate are queried
**Then** they are visible via the API (and optionally in a future configuration UI)
