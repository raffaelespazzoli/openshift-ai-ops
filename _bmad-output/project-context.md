---
project_name: openshift-ai-ops
user_name: Raffa
date: '2026-08-06'
sections_completed: ['technology_stack', 'language_specific_rules', 'framework_specific_rules', 'testing_rules', 'code_quality_style', 'development_workflow', 'critical_dont_miss']
status: complete
rule_count: 100
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

| Component | Technology | Version | Notes |
|-----------|-----------|---------|-------|
| Backend language | Python | ≥3.13 | LangGraph requirement |
| Agent framework | LangGraph | 1.2.x | Checkpoint persistence to PostgreSQL |
| API framework | FastAPI | 0.141.x | REST + SSE + webhook receiver |
| Database | PostgreSQL | 18.x | Structured data + LangGraph checkpoints |
| Vector extensions | pgvector | 0.8.x | Case records, knowledge, semantic cache |
| Cluster access | kubernetes-mcp-server | 0.0.66+ | Pre-1.0; pin to tested release |
| Knowledge platform | Solr (RHOKP) | 9.x | 600k+ docs, PVC-backed |
| Knowledge MCP | okp-mcp | latest | Bridges agent queries to Solr |
| Frontend framework | React | 19.x | Required by PatternFly 6 |
| Frontend language | TypeScript | 7.x | Go-native rewrite, 10x faster builds |
| UI components | @patternfly/react-core | 6.6.x | No custom components in v1 |
| Deployment | Helm | 4.x | Single chart, single namespace |
| Metrics | prometheus-client | 0.25.x | In-process /metrics endpoint |
| Static serving | nginx | 1.30.x | Frontend container |

### Version Constraints

- kubernetes-mcp-server is pre-1.0 — breaking changes possible. Pin exact version in Helm chart and test before upgrading.
- MCP transport MUST be Streamable HTTP (not stdio) — MCP servers are separate pods, not sidecars.
- PatternFly 6.6.x is the minimum for full React 19 compatibility.
- No dependency on OpenShift AI — any LLM endpoint with tool-use + structured output works.

## Critical Implementation Rules

### Language-Specific Rules

#### Python (Backend)

- **Snake_case everywhere** — modules, functions, variables, database columns. No exceptions.
- **Pydantic models for all typed artifacts** — every stage-boundary object (RootCauseEvent, DiagnosisObject, RemediationPlan, CaseRecord) is a Pydantic model in `backend/src/models/`.
- **Async-first** — FastAPI endpoints and LangGraph nodes use `async def`. Database access via asyncpg. The in-process event bus is asyncio-based (AD-24).
- **Structured errors** — pipeline stage failures produce a typed `StageError` (with `stage`, `error_code`, `detail`, `recoverable` flag). API errors return `{error: string, code: string, detail: object}`.
- **No direct SQL in business logic** — all database access goes through the data layer (`backend/src/db/`). Pipeline stages and agents never write raw SQL inline.
- **Import discipline** — `models/` is a leaf (depends on nothing). `agents/` never imports from `api/` or `pipeline/`. Stages invoke agents, not the reverse.

#### TypeScript (Frontend)

- **camelCase for all variables, functions, props** — aligns with JSON API responses.
- **Kebab-case filenames** — all `.tsx`, `.ts`, `.css` files use kebab-case (e.g., `incident-detail.tsx`, not `IncidentDetail.tsx`).
- **No custom components** — use PatternFly React components exclusively. No wrapping PF components in project-specific abstractions in v1.
- **PatternFly design tokens only** — never use raw hex/rgb colors. Reference `--pf-t--global--*` CSS custom properties. Dark mode is handled entirely by PF's theme toggle.
- **API envelope assumption** — all REST responses follow `{data: T, meta: {timestamp, request_id}}`. Frontend types must match this envelope.

#### Shared (Both Languages)

- **ISO 8601 dates with timezone** — `2026-08-05T09:30:00Z` everywhere (API, database, logs). No locale-dependent formats.
- **UUIDs for entity IDs** — incidents, case records, remediation plans. Alert fingerprints from AlertManager are hex strings (not UUIDs).
- **Root-cause codes use slash-delimited taxonomy** — `{subsystem}/{failure-mode}` (e.g., `node/memory-pressure`, `storage/pvc-stuck-pending`).

### Framework-Specific Rules

#### FastAPI (Backend API)

- **Single Python process** — REST API, webhook receiver, SSE streams, and LangGraph pipeline all run in one process (AD-9). No microservice decomposition of the backend.
- **SSE for real-time updates** — use FastAPI's `EventSourceResponse` for live pipeline stage transitions and incident state changes. Frontend subscribes on detail views, falls back to polling on connection drop.
- **URL-path versioning** — all REST routes under `/api/v1/`. No header-based negotiation.
- **API response envelope** — every response wraps in `{data: T, meta: {timestamp, request_id}}`. No bare JSON arrays or objects.
- **OpenShift OAuth** — all endpoints require a valid bearer token validated against the OpenShift OAuth server. Approver identity extracted from token.

#### LangGraph (Agent Pipeline)

- **Staged pipeline is THE paradigm** — the system is a directed graph of typed stages, not a collection of autonomous agents. Stages accept typed input and produce typed output. Fast-path and re-challenge are conditional edges, not a different paradigm.
- **Agents are INTERNAL to stages** — orchestrator, specialists, skeptics live inside stages. They never appear as pipeline-level nodes or cross stage boundaries.
- **LangGraph checkpoints to PostgreSQL** — all pipeline state persists. Workflows resume from last checkpoint on pod restart.
- **LangGraph owns its tables** — `langgraph_*` tables are a black box. Never query them from application code. Application schema is separate (AD-3).
- **State machine transitions only** — incident state advances via the canonical state machine function in `models/`. No direct status column writes anywhere.

#### React + PatternFly (Frontend)

- **PatternFly wholesale** — inherit all PF tokens, components, and patterns. The tool must look like it belongs inside the OpenShift Console.
- **Console shell layout** — horizontal masthead (top) + vertical navigation (left sidebar). Matches the Console for future plugin migration.
- **Status colors are semantic only** — `danger` = critical/failed, `warning` = medium/awaiting action, `success` = resolved/completed, `info` = active/informational. Never decorative.
- **ProgressStepper for pipeline visualization** — each step uses semantic `variant` from the DESIGN.md component tokens. Horizontal, `isCenterAligned` on detail views.
- **DataList for incident lists** — expandable rows for alert grouping under Root-Cause Events.
- **Dark mode as default** — SREs work at 2am. Support both themes via PF toggle, but default to dark.
- **No animations or pulsing** — clinical calm. No urgency theatrics. The data speaks.

### Testing Rules

#### Backend (Python)

- **pytest as the test runner** — standard for Python/FastAPI/LangGraph ecosystem.
- **Tests mirror source layout** — `backend/tests/` mirrors `backend/src/` (e.g., `tests/api/`, `tests/pipeline/`, `tests/agents/`, `tests/db/`).
- **Unit tests for stage contracts** — every pipeline stage gets unit tests that verify: correct typed output given typed input, state machine transition correctness, and error propagation via `StageError`.
- **Mock MCP Server calls** — never hit a real cluster in unit tests. Mock the MCP client interface at the boundary.
- **Mock LLM calls** — never call real LLM endpoints in unit tests. Mock at the LLM client boundary with deterministic responses.
- **Integration tests for database** — use a real PostgreSQL instance (testcontainers or equivalent) for tests involving pgvector queries, row-level locking, and migration verification.
- **Eval harness is NOT unit tests** — the eval harness (FR-24–26) is a separate simulation system for diagnostic accuracy. It is not part of the test suite; it runs as a distinct pipeline mode.

#### Frontend (TypeScript)

- **Test files colocated** — `*.test.tsx` lives next to the component file it tests.
- **React Testing Library** — test user behavior, not implementation details. Query by role, label, text — never by CSS class or test-id unless no accessible alternative exists.
- **Mock API responses** — use MSW (Mock Service Worker) or equivalent to intercept REST/SSE at the network level. Never mock `fetch` directly.
- **PatternFly component usage is NOT tested** — don't assert that a specific PF component is rendered. Assert visible text, accessible roles, and user interactions.

#### Integration Test Strategy

Five test layers, each with its own infrastructure and trigger:

| Layer | What | Infrastructure | When Built |
|-------|------|---------------|------------|
| Unit | Logic, contracts, pure functions | Mocked dependencies | Every story |
| DB integration | Migrations, queries, locks, pgvector | Testcontainers (PostgreSQL 18 + pgvector) | Fixtures in Story 1.0, each story adds tests |
| API integration | HTTP endpoints, SSE, auth, audit | FastAPI TestClient + testcontainers | Fixtures in Story 1.0, Story 1.4 adds tests |
| Pipeline integration | LangGraph orchestration, checkpoints, state flow | Mocked LLM + real PostgreSQL | Story 2.1 (first pipeline story) |
| MCP integration | Streamable HTTP, canned cluster responses | Mock MCP server | Story 2.1 (first MCP usage) |

- **Unit through MCP integration run in CI on every PR.** They are fast, deterministic, and containerized.
- **pytest markers** — `unit`, `db`, `api`, `pipeline` to select test layers. Default runs all.
- **Testcontainers fixture** — shared `conftest.py` fixture spins up PostgreSQL + pgvector, runs migrations, provides clean session per test.
- **Mock MCP server** — a lightweight Streamable HTTP server returning canned responses, built when Epic 2 introduces MCP usage.

**E2E tests (deferred to post-Epic 3):** Full pipeline with real MCP Servers and real LLM endpoints — nothing mocked. Validates end-to-end plumbing (pod communication, Streamable HTTP, LLM through LangGraph to DB to SSE to browser). Distinct from the eval harness (Epic 7) which scores diagnostic accuracy. Not CI — requires a dedicated test cluster and LLM endpoint. Periodic or manual trigger only.

#### Shared Principles

- **No snapshot tests** — they add noise and break on PF upgrades. Test behavior and contract outputs.
- **Structured JSON logging in tests** — tests should validate log output structure (component, level, incident_id correlation) for observability-critical paths.
- **State machine transitions are deterministic** — exhaustively test all valid transitions and verify that invalid transitions throw.
- **No flaky tests** — every integration test touching PostgreSQL or async must have explicit timeouts and deterministic setup/teardown. If a test can't pass 100 runs consecutively, it doesn't merge.

### Code Quality & Style Rules

#### File & Folder Structure

- **Monorepo layout is law** — follow AD-14 exactly:
  ```
  openshift-ai-ops/
    backend/src/{api,pipeline,agents,models,knowledge,db,config}/
    backend/tests/
    frontend/src/
    charts/openshift-ai-ops/{templates,values.yaml}/
    docs/
  ```
- **`models/` is the contract** — all stage-boundary artifacts defined here. Every other module imports from it. It imports from nothing.
- **`agents/` is encapsulated** — never imported by `api/` or `pipeline/` directly. Pipeline stages invoke agents through the graph definition, not direct import.

#### Naming Conventions

- **Python modules** — snake_case (`root_cause_event.py`, `diagnosis_skeptic.py`)
- **TypeScript files** — kebab-case (`incident-detail.tsx`, `pipeline-stepper.tsx`)
- **Helm templates** — kebab-case (`deployment-backend.yaml`, `service-frontend.yaml`)
- **Database tables/columns** — snake_case (`case_records`, `root_cause_code`, `created_at`)
- **API endpoints** — kebab-case paths (`/api/v1/incidents/{id}/remediation-plan`)
- **Environment variables** — UPPER_SNAKE_CASE (`LLM_ENDPOINT_URL`, `POSTGRES_HOST`)

#### Logging

- **Structured JSON to stdout** — every log entry: `{timestamp, level, component, request_id|incident_id, message}`.
- **Component values** — one of: `api`, `pipeline`, `agent`, `db`, `knowledge`.
- **Correlation** — always carry `request_id` (API calls) or `incident_id` (pipeline processing) for trace correlation.
- **No print statements** — use the structured logger exclusively.

#### Documentation

- **Code comments for non-obvious intent only** — no narration of what the code does. Comments explain WHY, not WHAT.
- **Docstrings on public functions** — Python: Google-style docstrings. TypeScript: JSDoc for exported functions.
- **Architecture decisions live in ARCHITECTURE-SPINE.md** — never duplicate AD rationale in code comments. Reference by AD number if needed.

### Development Workflow Rules

#### Repository & Branching

- **Monorepo** — backend, frontend, and Helm chart live in one repository. PRs may touch multiple directories.
- **Feature branches off main** — short-lived branches, merged via PR.
- **Conventional commits** — `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:` prefixes. Scope in parentheses maps to directory: `feat(pipeline):`, `fix(api):`, `feat(frontend):`, `chore(charts):`.

#### Deployment

- **Single `helm install`** — the entire system deploys from one chart into one namespace. No multi-chart orchestration.
- **No CRDs** — never introduce Custom Resource Definitions. The tool must not depend on cluster API extension machinery.
- **No OLM** — this is not an operator. It is a Helm-deployed application.
- **Seven deployments** — backend, frontend, postgresql, mcp-readonly, mcp-readwrite, solr, okp-mcp. Don't add more without an AD.
- **LLM credentials in Secrets** — never in Helm values directly, never in ConfigMaps, never in source code.

#### Configuration Layers

- **Helm values seed initial config** — base settings at install time.
- **Runtime API overrides persist to DB** — policy matrix and per-agent LLM config are mutable at runtime via API.
- **On restart: Helm defaults load first, then DB overrides apply** — DB always wins.
- **All config changes are audit-logged** — no silent mutation.

#### Development Environment

- **Backend** — Python virtual environment, `pip install -e .` for development. FastAPI dev server with hot reload.
- **Frontend** — npm/pnpm workspace. Vite or similar for dev server with HMR.
- **Database** — local PostgreSQL 18 + pgvector via container (podman/docker).
- **MCP Servers** — mock or local instances for development. Never connect dev to a production cluster.

### Critical Don't-Miss Rules

#### RBAC Airlock — The #1 Rule

- **NEVER give diagnosis code write access to the cluster.** Diagnosis uses `cluster-reader` SA + `--read-only` MCP Server. Remediation uses `cluster-admin` SA + separate MCP Server. These are different pods, different ServiceAccounts, different code paths.
- **The immutable diagnosis artifact is the ONLY thing that crosses the boundary.** Remediation cannot re-diagnose. Diagnosis cannot execute fixes.
- **Agentic skills on the diagnosis side are read-only.** Any skill that requires write access is classified remediation-only and unavailable during diagnosis.

#### Pipeline Paradigm Violations

- **NEVER build agents as autonomous microservices.** This is a staged pipeline with typed contracts. Agents are implementation details INSIDE stages.
- **NEVER skip the skeptic.** Adversarial validation is a mandatory pipeline stage. Not an optional flag. Not a review mode. It always runs.
- **NEVER allow more than one re-challenge.** If the skeptic changes the diagnosis/plan, it gets ONE re-challenge. Then it passes regardless. No infinite loops.
- **NEVER execute two remediations concurrently.** Global lock via PostgreSQL row-level lock (AD-18). One at a time, always. Cooldown between executions.

#### Data Model Violations

- **NEVER write incident status directly.** All state changes go through the canonical state machine transition function in `models/`. Direct column updates bypass validation.
- **NEVER query `langgraph_*` tables.** They are LangGraph internals. Application code uses the application schema only.
- **NEVER store vectors outside pgvector.** Case records, semantic cache, and runbook chunks all use pgvector. No separate vector database.
- **NEVER use in-memory queues.** Priority queue is PostgreSQL-backed (`SELECT FOR UPDATE SKIP LOCKED`). Must survive pod restart.

#### Security Anti-Patterns

- **NEVER auto-execute when `evidence_gaps` is non-empty.** MCP timeouts produce partial evidence. The Policy Gate blocks auto-execution regardless of other matrix dimensions.
- **NEVER auto-rollback.** Rollback is human-triggered only. The system never decides a remediation failed and rolls back on its own.
- **NEVER bypass the policy gate.** Even fast-path remediations (from Learning Store) pass through the policy gate. No shortcut to execution.
- **Default-deny is the shipping default.** All remediations require human approval unless explicitly configured otherwise.

#### Frontend Anti-Patterns

- **NEVER introduce custom hex colors.** All colors via PatternFly tokens. No `#rrggbb`, no `rgb()`, no CSS variables outside the PF namespace.
- **NEVER create custom wrapper components around PatternFly.** Use PF components directly as documented. No `<AppButton>` wrapping `<Button>`.
- **NEVER invent navigation patterns.** Use the Console shell layout (masthead + sidebar). The standalone app must migrate cleanly to a Console plugin.
- **NEVER use `danger` red for anything but genuine critical/failed states.** Semantic only.

#### Operational Gotchas

- **MCP timeout ≠ failure.** A timeout produces partial evidence with explicit `evidence_gaps`. Diagnosis continues with available data. It does NOT fail the pipeline.
- **Resolved webhook during in-flight pipeline does NOT cancel it.** The freshness gate at execution time catches stale remediations. Diagnostic work is preserved for the Learning Store.
- **Correlation over-groups by design.** The five-layer correlator (AD-5) prefers false positives. The orchestrator refines during diagnosis. Don't try to make correlation perfect.
- **Settling windows vary by severity.** Critical=60s, Warning=5min, Info=10min. Timer resets on each new alert joining the group.
- **Testcontainers requires Podman socket setup on Fedora/RHEL.** The `testcontainers` library defaults to the Docker socket (`/var/run/docker.sock`). On systems using Podman instead of Docker, you must: (1) start the Podman socket with `systemctl --user start podman.socket`, (2) set `DOCKER_HOST=unix:///run/user/$(id -u)/podman/podman.sock`, and (3) set `TESTCONTAINERS_RYUK_DISABLED=true` (Podman does not support Ryuk's privileged container). Without these, integration tests that depend on the `postgres_container` fixture will fail with `DockerException: Error while fetching server API version`. Unit tests (`pytest -m unit`) do not require a container runtime and always work.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code in this project
- Follow ALL rules exactly as documented — especially the "Critical Don't-Miss Rules" section
- When in doubt, prefer the more restrictive option
- Reference architecture decisions by AD number (see `ARCHITECTURE-SPINE.md`)
- The canonical incident state machine is: `received → correlating → queued → diagnosing → diagnosed → awaiting_approval → executing → observing → resolved | failed`

**For Humans:**

- Keep this file lean and focused on agent needs
- Update when technology stack changes or new architectural decisions are made
- Review quarterly for outdated rules
- Remove rules that become obvious over time as the codebase matures

Last Updated: 2026-08-06
