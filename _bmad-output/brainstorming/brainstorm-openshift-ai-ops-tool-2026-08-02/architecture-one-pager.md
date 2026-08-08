# OpenShift AI Ops — Technical Architecture One-Pager

## 1. System Overview

OpenShift AI Ops is an alert-driven, multi-agent diagnostic and remediation tool for OpenShift cluster practitioners. It receives alerts from AlertManager, orchestrates specialized AI agents to diagnose root causes, generates structured remediation plans subjected to adversarial review, and executes approved fixes — all while accumulating cluster-specific failure knowledge that makes future responses faster and cheaper. The system enforces a hard RBAC boundary: diagnosis is strictly read-only; remediation is the only path to write operations, gated by a configurable policy matrix and optional human approval.

## 2. Component Diagram

```
┌──────────────┐       ┌─────────────────────┐      ┌──────────────────┐
│ AlertManager  │──webhook──▶│  Webhook Receiver   │─────▶│  Priority Queue  │
│  (external)   │  firing/   │  dedup + correlate  │      │  urgency×recency │
└──────────────┘  resolved   └─────────────────────┘      └────────┬─────────┘
                                                                   │
                          ┌────────────────────────────────────────┘
                          ▼
               ┌─────────────────────────────────────────────────────────┐
               │              AGENT PIPELINE  (LangGraph)                │
               │                                                         │
               │  ┌──────────────┐    ┌─────────────────────────────┐   │
               │  │ Orchestrator │───▶│ Specialist Agents            │   │
               │  │  • dispatch  │◀───│  • compute  • storage       │   │
               │  │  • synthesize│    │  • network  • (extensible)  │   │
               │  │  • generalist│    └─────────────────────────────┘   │
               │  │    fallback  │                                       │
               │  └──────┬───────┘                                       │
               │         ▼                                               │
               │  ┌──────────────┐   challenge    ┌──────────────────┐  │
               │  │  Diagnosis   │──────────────▶│ Diagnosis Skeptic │  │
               │  │  (structured)│◀──────────────│  1-round debate   │  │
               │  └──────┬───────┘   response     └──────────────────┘  │
               │         ▼  immutable artifact                           │
               │  ┌──────────────┐   challenge    ┌──────────────────┐  │
               │  │ Remediation  │──────────────▶│  Remed. Skeptic   │  │
               │  │   Planner    │◀──────────────│  1-round debate   │  │
               │  └──────┬───────┘   response     └──────────────────┘  │
               │         ▼                                               │
               │  ┌──────────┐  ┌───────────┐  ┌──────────┐            │
               │  │ Dry-Run  │─▶│ Policy    │─▶│ Human    │            │
               │  │ (server) │  │ Gate      │  │ Approval │            │
               │  └──────────┘  │ sev×blast │  │ (if req) │            │
               │                │ ×confid.  │  └────┬─────┘            │
               │                └───────────┘       ▼                   │
               │                             ┌──────────┐               │
               │                             │ Executor │               │
               │                             └────┬─────┘               │
               │                                  ▼                     │
               │                             ┌──────────┐               │
               │                             │ Observer │               │
               │                             │ (alert   │               │
               │                             │ resolved?)│              │
               │                             └──────────┘               │
               └──────────────────────────────────────┬──────────────────┘
                          │                           │
            ┌─────────────┼───────────────────────────┼──────────────┐
            ▼             ▼                           ▼              ▼
  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  ┌──────────┐
  │  PostgreSQL  │  │   pgvector   │  │ OpenShift MCP Srv  │  │   LLM    │
  │  structured  │  │   embeddings │  │  ┌──────┐┌───────┐ │  │ endpoints│
  │  + LangGraph │  │   case       │  │  │read- ││read-  │ │  │ (config- │
  │  checkpoints │  │   records    │  │  │only  ││write  │ │  │  urable) │
  └──────────────┘  └──────────────┘  │  └──────┘└───────┘ │  └──────────┘
                                      └────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │       REST API        │
              ├───────────┬───────────┤
              │ Console   │ Standalone│
              │ Plugin    │ Web App   │
              └───────────┴───────────┘
```

## 3. Tech Stack

| Component | Technology | Rationale |
|---|---|---|
| Agent framework | LangGraph | Stateful graphs, native HITL interrupt/resume, checkpoint persistence, audit trail |
| Database | PostgreSQL + pgvector | Single store for structured data, vector embeddings, and LangGraph checkpoints |
| Cluster access | OpenShift MCP Server (official) | Go-native, no kubectl dep, RBAC-respecting, supports `--read-only` mode |
| Deployment | Helm chart | Avoids CRD dependency on the cluster being healed; self-contained |
| UI (integrated) | OpenShift Console plugin | Native experience for console users |
| UI (standalone) | Web application | Works independently of console availability |
| LLM integration | Configurable endpoints | Per-agent model selection, supports thinking mode, vendor-agnostic |
| Embeddings | pgvector | Sufficient for thousands-to-millions of case records |

## 4. Data Flow

1. **Alert arrival** — AlertManager fires webhook (`firing`/`resolved` status) to Webhook Receiver.
2. **Dedup & correlate** — Receiver deduplicates storm alerts via status tracking, correlates related alerts into single root-cause events.
3. **Enqueue** — Event enters Priority Queue ranked by urgency × recency.
4. **Fast-path check** — Queue consumer queries pgvector for past case match above similarity threshold with successful outcome. If match: skip to step 9 with replayed remediation.
5. **Dispatch** — Orchestrator forms subsystem hypothesis from alert metadata + runbook context, dispatches to specialist agents (or handles simple cases solo).
6. **Diagnosis** — Specialists query cluster via read-only MCP Server, access runbooks/RHOKP/pgvector, return structured diagnosis with confidence level. Orchestrator synthesizes.
7. **Adversarial review** — Diagnosis Skeptic challenges; if diagnosis holds (deterministic field-diff + embedding fallback) → accepted. If fundamentally changed → re-challenged.
8. **Remediation planning** — Immutable diagnosis artifact passes to Remediation Planner → structured plan (steps, blast_radius, rollback, risk) → Remediation Skeptic challenge.
9. **Dry-run** — `oc apply --dry-run=server`, admission webhook validation, RBAC/quota checks. Results shown alongside plan.
10. **Policy gate** — Severity × blast_radius × confidence evaluated against user-configured matrix. Pass → auto-execute or queue for human approval.
11. **Execution** — Executor applies fix via read-write MCP Server instance. Global lock: one remediation at a time, configurable cooldown between executions.
12. **Observation** — Observer monitors for alert resolution (success criterion). Configurable timeout.
13. **Learning store update** — Case record (alert signature, root-cause code, structured diagnosis, remediation plan, outcome, cluster context) persisted to pgvector. Failures stored as negative cases. Temporal decay applied to confidence.

## 5. Security Model

**ServiceAccounts:**
- `cluster-reader` — read-only cluster access, bound to diagnosis-side MCP Server instance
- `cluster-admin` — write access, bound exclusively to remediation-side MCP Server instance

**MCP Server boundary enforcement:**
- Two separate OpenShift MCP Server deployments; read-only instance launched with `--read-only` flag
- Diagnosis agents can never reach the read-write instance; remediation agent can never re-diagnose

**Remediation policy matrix:**

| | blast: workload | blast: namespace | blast: node | blast: cluster |
|---|---|---|---|---|
| sev: low + high conf | auto | auto | approval | approval |
| sev: high + high conf | auto | approval | approval | approval |
| sev: any + low conf | approval | approval | approval | approval |

*User-configurable; above is illustrative. All three dimensions must pass threshold for auto-execution.*

**Additional controls:**
- Rollback is never automatic — human-triggered only
- Remediation serialized (global lock) with cooldown between executions
- Diagnosis output is immutable artifact crossing the RBAC boundary
- Full audit trail via LangGraph checkpoints + PostgreSQL event log

## 6. Deployment Model

- **Package:** Helm chart, single `helm install` into a dedicated namespace
- **No CRDs** — avoids dependency on cluster API machinery that may be degraded
- **Deployed components:**
  - Webhook Receiver + Priority Queue service
  - Agent Pipeline service (LangGraph runtime)
  - PostgreSQL (structured data + pgvector + LangGraph checkpoints)
  - OpenShift MCP Server × 2 (read-only + read-write)
  - REST API service
  - Console Plugin (optional, registered with OpenShift)
  - Standalone Web App
- **External dependencies:** LLM endpoint(s) — not deployed, user-configured

## 7. Key Interfaces

| Interface | Direction | Protocol | Purpose |
|---|---|---|---|
| AlertManager webhook | IN | HTTP POST | Receives `firing`/`resolved` alert payloads |
| REST API | OUT → UIs | HTTP/JSON | Incidents, diagnoses, remediations, config, audit |
| LLM endpoints | OUT | HTTP (configurable per agent) | Model inference, supports per-agent model/params |
| OpenShift MCP Server (read-only) | OUT → cluster | MCP over stdio/SSE | Cluster state queries during diagnosis |
| OpenShift MCP Server (read-write) | OUT → cluster | MCP over stdio/SSE | Remediation execution only |

## 8. Resilience

| Failure mode | Handling |
|---|---|
| **LLM unavailable** | Retry with configurable backoff → fallback to secondary LLM endpoint → pgvector fast-path: replay past successful remediation if case similarity exceeds threshold |
| **Cluster degradation** | Diagnosis agents degrade gracefully (partial data). MCP Server respects timeouts. No CRD dependency — tool's own data store remains available even if cluster API is impaired |
| **Pod restarts** | LangGraph checkpoints persisted to PostgreSQL; agent workflows resume from last checkpoint on restart |
| **Alert storms** | Deduplication at receiver, correlation into root-cause events, configurable parallelism cap, priority queue prevents agent drowning |
| **Remediation conflicts** | Global execution lock — one remediation at a time, configurable cooldown between executions for cluster state to settle |

## 9. Scope Boundaries

**MVP (MUST):** Core pipeline — webhook receiver → priority queue → orchestrator → specialist dispatch → diagnosis skeptic → remediation planner → remediation skeptic → policy gate → executor → observer → learning store. Standalone web UI. PostgreSQL + pgvector. Two MCP Server instances. Configurable LLM endpoints.

**SHOULD:** Compute/storage/network specialist agents, pgvector fast-path, dry-run pre-flight, OpenShift Console plugin, LLM retry + fallback chain.

**COULD:** PrometheusRule proposal generation, knowledge graph of causal patterns, confidence boosting from past successes, temporal decay on case records.

**WON'T (this version):** Cross-cluster federated learning, multi-cluster metrics aggregation.
