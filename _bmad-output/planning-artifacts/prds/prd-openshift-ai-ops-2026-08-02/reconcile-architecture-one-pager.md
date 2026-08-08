# Reconciliation: Architecture One-Pager → PRD + Addendum

**Input:** `architecture-one-pager.md` (brainstorm output)
**PRD:** `prd.md` (2026-08-02)
**Addendum:** `addendum.md` (2026-08-02)
**Date:** 2026-08-02

---

## Summary

The PRD faithfully captures the majority of the architecture one-pager's structure, components, and data flow. However, five gaps were identified where qualitative intent, architectural decisions, or explicit scope items from the one-pager were silently dropped — neither addressed in the PRD's requirements nor deferred in §6.2 nor captured in the addendum.

---

## Gap 1: Confidence Boosting from Repeated Successes

**Source:** Architecture one-pager §9 Scope Boundaries — COULD: "confidence boosting from past successes"

**What it means:** When the same alert pattern is successfully remediated multiple times, the system should increase its confidence for that pattern over time. This is the inverse of temporal decay — a positive feedback loop that rewards proven remediations.

**What the PRD has:** FR-19 defines temporal decay (confidence decreases with age and version drift). The fast-path (FR-20) replays past successes. But neither FR nor the addendum defines a mechanism for confidence to *increase* through repetition.

**Why it matters:** Without confidence boosting, the Policy Gate thresholds remain static — a pattern that succeeds 50 times still requires the same approval level as one that succeeded once. This undermines the "trust escalation" narrative (§12) by forcing manual policy matrix relaxation rather than evidence-driven automation.

**Recommendation:** Add as a future-scope item in §6.2, or define an FR for confidence accumulation that feeds into the Policy Gate.

---

## Gap 2: Learning Store Scale Expectations (Thousands-to-Millions)

**Source:** Architecture one-pager §3 Tech Stack — Embeddings row: "Sufficient for thousands-to-millions of case records"

**What it means:** The architecture made an explicit sizing decision: pgvector was chosen *because* it handles the expected scale of case record accumulation over the tool's lifetime across fleet deployment.

**What the PRD has:** No scale target, sizing guidance, or capacity requirement for the Learning Store. §7.3 Performance defines alert storm handling (100 alerts) and intake latency (1s) but nothing about storage growth or query performance at scale.

**Why it matters:** Downstream architecture needs to know whether to design for hundreds of records (single cluster, months) or millions (fleet-wide, years). Index strategy, embedding dimensions, and query patterns differ significantly. The one-pager made this decision; the PRD doesn't carry it forward.

**Recommendation:** Add a capacity NFR in §7.3 or a note in the addendum's Tech Stack section stating the expected case record scale and its implications for pgvector index design.

---

## Gap 3: Specialist Dispatch Mechanism as MVP Infrastructure

**Source:** Architecture one-pager §9 Scope Boundaries — MVP (MUST): "orchestrator → specialist dispatch" listed as part of the core pipeline

**What it means:** The architecture one-pager distinguishes between the *dispatch mechanism* (routing infrastructure, label-matching framework, multi-agent synthesis protocol) and the *specialist agents themselves* (compute, storage, network — listed as SHOULD). The intent: build the extensibility framework in MVP so specialists are a deployment-time addition, not a code change.

**What the PRD has:** FR-7 (Domain Specialist Agents) is marked `[POST-MVP — SHOULD]`. §6.2 defers specialists entirely: "Orchestrator handles all domains as generalist initially." No FR defines the dispatch/routing infrastructure separately from the specialist agents that use it.

**Why it matters:** If the dispatch mechanism isn't built in MVP, adding specialists post-MVP requires re-architecting the orchestrator's internals rather than just deploying new agents that register label-matching rules. The one-pager's intent is a plugin architecture from day one — even if the only "plugin" at launch is the generalist orchestrator itself.

**Recommendation:** Either (a) add an FR for the agent routing/dispatch framework as MVP scope (distinct from FR-7's specialist agents), or (b) explicitly note in §6.2 that the extensibility mechanism is deferred alongside the specialists, accepting the future rework.

---

## Gap 4: REST API as Explicit Interface Contract

**Source:** Architecture one-pager §2 Component Diagram (REST API as named component), §7 Key Interfaces (REST API row: "Incidents, diagnoses, remediations, config, audit")

**What it means:** The architecture treats the REST API as a first-class component with defined scope: it serves incidents, diagnoses, remediations, configuration, and audit data to both UI surfaces.

**What the PRD has:** The REST API appears in FR-27's component list ("REST API service") and §9's integration table ("HTTP/JSON — Incidents, diagnoses, remediations, config, audit"). But no FR defines the API itself — its resource model, authentication, pagination, or contract guarantees. The UI FRs (FR-21–23) describe what the UIs show, not what the API provides.

**Why it matters:** Both UIs (standalone web app and console plugin) are documented as consuming this API. Without an explicit interface specification, downstream architecture must infer the API contract from scattered UI requirements. Authentication model (ServiceAccount token? OIDC? Basic auth?) is unspecified.

**Recommendation:** Add an FR for the REST API defining: resource model scope (incidents, diagnoses, plans, config, audit), authentication/authorization model, and pagination/filtering contract. Alternatively, flag it as an architecture-spec deliverable in the addendum.

---

## Gap 5: LLM Resilience as Architectural Degradation Pattern

**Source:** Architecture one-pager §8 Resilience — "LLM unavailable" row: "Retry with configurable backoff → fallback to secondary LLM endpoint → pgvector fast-path: replay past successful remediation if case similarity exceeds threshold"

**What it means:** The architecture defines a three-tier graceful degradation cascade as a *system property*, not a feature. The system is designed so that at every tier of failure, it still provides value: full LLM → backup LLM → replay proven fix → queue with status. This is an architectural resilience pattern.

**What the PRD has:** FR-29 (LLM Resilience) is marked `[POST-MVP — SHOULD]` and treated as a single feature. The PRD's MVP has no LLM failure handling beyond the implicit "it doesn't work." The architectural intent — that the system's data flow is *designed from the start* to degrade gracefully through multiple fallback tiers — is lost when the entire cascade is deferred as one feature.

**Why it matters:** If the architecture isn't designed for graceful degradation from day one, retrofitting the cascade post-MVP requires reworking the pipeline's control flow. The one-pager's §8 pairs with the addendum's design philosophy ("The LLM is the fallback, not the hot path") to establish that the system ARCHITECTURE assumes LLM failure is normal — even if the fallback endpoints aren't configured at launch.

**Recommendation:** Separate the architectural concern (pipeline designed for fallback injection points) from the feature concern (configuring secondary LLM endpoints). The MVP pipeline should have the degradation hooks even if only the "queue with status" fallback is implemented initially.

---

## Items Confirmed as Covered

The following architecture one-pager content was verified as present in the PRD or addendum:

- Full data flow pipeline (§4 Data Flow → PRD §4.1–4.5)
- Security model with two MCP Server instances and RBAC airlock (§5 → PRD §7.1, addendum MCP detail)
- Policy matrix with three dimensions (§5 → PRD FR-13, addendum Policy Matrix)
- Deployment model with no CRDs (§6 → PRD §8.2, FR-27)
- All key interfaces and protocols (§7 → PRD §9)
- Resilience patterns for cluster degradation, pod restarts, alert storms, remediation conflicts (§8 → PRD §7.2, §7.3, FR-15)
- Scope boundary items: PrometheusRule proposals, knowledge graph, cross-cluster federation (§9 → PRD §5, §6.2)
- Design philosophy statements (addendum §Design Philosophy)
- Rejected alternatives (addendum §Rejected Alternatives)
- Competitive landscape (addendum §Competitive Landscape)

---

## Verdict

**5 gaps found.** Three are architectural intent that needs to be captured somewhere (Gaps 3, 4, 5). Two are explicit scope items or decisions that were dropped without deferral notice (Gaps 1, 2). None represent fundamental contradictions — the PRD is directionally aligned with the architecture — but the gaps could cause downstream misalignment if not addressed before architecture spec or epic generation.
