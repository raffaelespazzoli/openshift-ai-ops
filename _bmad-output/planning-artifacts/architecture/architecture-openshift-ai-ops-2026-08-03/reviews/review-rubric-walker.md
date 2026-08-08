# Architecture Spine Review — Rubric Walker

| Field | Value |
| --- | --- |
| Spine | `ARCHITECTURE-SPINE.md` (OpenShift AI Ops, feature altitude) |
| Spec | `SPEC.md` (SPEC-openshift-ai-ops) |
| Reviewer | rubric-walker |
| Date | 2026-08-06 |
| Overall verdict | **CONCERN** — one critical finding (RHOKP topology contradicts spec), two high findings; otherwise strong |

---

## Criterion 1 — Divergence-point coverage for epics

**Verdict: CONCERN (high)**

The spine identifies 23 ADs that cover the major divergence surfaces: pipeline paradigm boundaries, RBAC split, database schema ownership, shared-types contract, correlation algorithm, LLM configuration pattern, tech stack, pod topology, API versioning, auth, knowledge retrieval, source-tree layout, MCP timeout handling, freshness gate, cache invalidation, remediation locking, incident state machine, case-record schema ownership, SSE event envelope, semantic cache location, and priority-queue concurrency. This is thorough.

**Gap:** The RHOKP integration topology is a real divergence point that is not fixed. The spec's Resolved Questions section explicitly decided: *"Deploy RHOKP (Solr container, 600k+ docs) + okp-mcp (MCP server) as sidecar deployments in the Helm chart."* Yet AD-13 still says *"RHOKP bundled/cached (API unconfirmed)"* and routes everything through pgvector RAG. The Deferred table also says *"RHOKP API integration — blocked on open question #1 from PRD"* even though the spec marks this resolved. Two epics — one building the Helm chart topology and one building the knowledge retrieval layer — would diverge on whether RHOKP is a Solr container + okp-mcp sidecar or an embedded pgvector index.

No other significant divergence points are missing at this altitude.

---

## Criterion 2 — AD rules: enforceable and effective

**Verdict: PASS (with one medium concern)**

All 23 ADs have explicit, prescriptive rules. Most are directly enforceable through code structure (AD-14 source layout), infrastructure (AD-2 separate SAs, AD-9 separate pods), or typed contracts (AD-4 shared types, AD-21 SSE envelope). Highlights:

- **AD-5** (five-layer correlator) is unusually specific for a spine-level decision, but this is appropriate — the layers are ordered, deterministic, and prevent LLM cost on correlation, which is the stated divergence.
- **AD-19** (incident state machine) is well-defined with explicit state transitions and transition ownership ("only the pipeline engine may advance state").
- **AD-23** (priority queue concurrency) prescribes the exact PostgreSQL locking pattern, preventing a common divergence where two epics independently invent queue semantics.

**Concern (medium):** AD-2 defaults the remediation ServiceAccount to `cluster-admin`. The PRD §7.1 explicitly flagged this as *"the single highest-friction point for SRE team adoption"* and said *"architecture must resolve this before implementation."* AD-2's resolution is to default to `cluster-admin` and make it "Helm-configurable," but the rule doesn't define what a tighter-scoped default would look like or what permission set the remediation planner's output constrains. The dry-run pre-flight (FR-12) is positioned as a safety net, but a permissive default paired with a "catch it later" strategy weakens the AD's preventive value. The rule is enforceable but may not adequately prevent the divergence the PRD anticipated: teams adopting the tool with an unnecessarily broad SA.

---

## Criterion 3 — Deferred items: divergence risk

**Verdict: CONCERN (critical)**

Most deferred items are low-risk and correctly scoped:

- Error handling per stage, Prometheus metric names, cache eviction policy, skills loading, migration tooling, console plugin details, specialist self-selection, LLM fallback, resource sizing — all internal to a single module or post-MVP. No cross-epic divergence risk.

**Critical issue:** *"RHOKP API integration"* is listed as deferred, blocked on *"open question #1 from PRD."* But the spec has already resolved this question. The deferred entry is stale. More importantly, this isn't safely deferrable even if it were genuinely unresolved — the answer changes the deployment topology (AD-9 pod count), the knowledge retrieval architecture (AD-13 RAG vs MCP-mediated Solr), and the Helm chart structure. Two epics would produce incompatible artifacts.

**Medium concern:** *"Internal TLS posture"* is deferred with the rationale "in-namespace traffic; OpenShift service mesh or NetworkPolicy scope." However, if one epic (e.g., backend↔MCP communication) assumes plaintext and another (e.g., frontend↔backend) assumes TLS, the Helm chart templates diverge. The risk is low for an MVP but should be acknowledged as a deliberate "plaintext within namespace" decision rather than left unaddressed.

---

## Criterion 4 — Named tech: verified current

**Verdict: PASS**

All major stack entries were verified against current releases as of 2026-08-06:

| Name | Spine version | Verified latest | Status |
| --- | --- | --- | --- |
| Python | ≥3.10 | 3.13+ available | Current (floor version is fine) |
| LangGraph | 1.2.x | 1.2.10 (2026-07-28) | Current |
| FastAPI | 0.141.x | 0.141.1 (2026-07-29) | Current |
| PostgreSQL | 18.x | 18.4 (supported through 2030) | Current |
| pgvector | 0.8.x | 0.8.6 (2026-07-29) | Current |
| kubernetes-mcp-server | 0.0.66+ | 0.0.66 (2026-08-04) | Current |
| React | 19.x | 19.x (PatternFly 6 supports 17/18/19) | Current |
| TypeScript | 7.x | 7.0.2 (2026-07-22) | Current |
| @patternfly/react-core | 6.6.x | 6.6.0 (2026-07-01) | Current |
| Helm | 4.x | 4.2.3 (2026-07-09) | Current |
| prometheus-client | 0.21.x | Not independently verified | Assumed current (stable, slow-moving) |
| nginx | 1.27.x | Not independently verified | Assumed current (LTS line) |

**Note (low):** prometheus-client and nginx were not independently verified but are mature, slow-cadence projects unlikely to have undergone a breaking major release. The kubernetes-mcp-server pinning note ("pre-1.0, pin to tested release") is a sensible precaution for a 0.x dependency.

---

## Criterion 5 — Spec coverage

**Verdict: CONCERN (critical, same root cause as Criterion 1)**

The spine binds FR-1 through FR-33 and NFR §7.1–§7.4 in its frontmatter. The Capability → Architecture Map traces every FR and NFR to at least one AD and a source-tree location. Coverage is comprehensive for 32 of 33 FRs and all four NFR sections.

**Critical gap — RHOKP integration diverges from spec resolution:**

The spec's Resolved Questions section states:

> Deploy RHOKP (Solr container, 600k+ docs) + okp-mcp (MCP server) as sidecar deployments in the Helm chart. Agents query knowledge via MCP streamable-http.

AD-13 instead says:

> RHOKP bundled/cached (API unconfirmed). Both indexed into separate pgvector-enabled tables… Retrieval: query with alert context, top-k chunks, inject into agent prompts.

These are incompatible architectures:

- **Spec:** RHOKP lives in a Solr container; agents query it via okp-mcp over MCP streamable-http. At least two additional pods (Solr + okp-mcp) in the topology.
- **Spine:** RHOKP content is pre-processed into pgvector embeddings at build time. No Solr, no okp-mcp. Five-pod topology (AD-9) has no room for them.

This affects CAP-2 (knowledge retrieval path), CAP-8 (deployment topology — 5 pods vs 7+), and FR-6 (knowledge source access pattern). The spine must either adopt the spec's resolution or document why it overrides it.

All other capabilities (CAP-1 through CAP-11, excluding the RHOKP aspect of CAP-2/CAP-8) are fully covered.

---

## Criterion 6 — Parent spine inheritance

**Verdict: PASS (not applicable)**

The spine is at `altitude: feature` with `companions: []`. Only one `ARCHITECTURE-SPINE.md` exists in the output tree. There is no parent spine to inherit from or potentially contradict.

---

## Criterion 7 — Silent dimensions

**Verdict: CONCERN (high)**

The spine covers the pipeline, data, deployment, API, auth, observability, and source-tree dimensions well. However, three operational/environmental dimensions are either silent or underspecified:

### 7a. Upgrade strategy — SILENT (high)

There is no AD, deferred entry, or open question addressing how the system upgrades. Key unanswered questions:

- Does `helm upgrade` perform a rolling update or require downtime?
- What happens to in-flight pipelines during upgrade? LangGraph checkpoints are mentioned for pod-restart resilience (NFR §7.2 coverage), but checkpoint-format compatibility across LangGraph versions is not addressed.
- Application-schema migrations (AD-3 separates the two schema domains, AD-20 assigns ownership) — but when and how do migrations run during upgrade? Pre-hook? Init container?
- Database migration tooling is deferred, which is fine for the tool choice, but the *strategy* for running migrations at upgrade time is a topology-level concern that could cause two epics to diverge (one assuming init container, another assuming Helm pre-upgrade hook).

### 7b. AD-9 topology inconsistency — PostgreSQL Deployment vs StatefulSet (medium)

AD-9's rule says *"five Deployments in a single namespace"* and lists PostgreSQL as item 3. However, the Deployment Topology diagram correctly shows PostgreSQL as `StatefulSet: 1 replica`. This is a factual inconsistency — PostgreSQL with a PVC should be a StatefulSet (stable network identity, ordered pod management). The rule text should say "four Deployments + one StatefulSet."

### 7c. Multi-environment strategy — SILENT but acceptable (low)

The spine doesn't address dev/staging/prod environment differentiation, image registry strategy, or CI/CD pipeline structure. At feature altitude for an MVP, this is arguably below the spine's concern. Noting for completeness.

---

## Findings Summary

| # | Tier | Criterion | Finding |
| --- | --- | --- | --- |
| F-1 | **Critical** | 1, 3, 5 | **RHOKP topology contradicts spec.** AD-13 bundles RHOKP into pgvector RAG; Deferred table says RHOKP is "blocked on open question"; spec's Resolved Questions says deploy as Solr + okp-mcp sidecar pods. AD-9 (five-pod topology) is also wrong if the spec resolution is adopted. The spine must reconcile with the spec or document a deliberate override with rationale. |
| F-2 | **High** | 7 | **Upgrade strategy is completely silent.** No AD, deferral, or open question covers Helm upgrade behavior, in-flight pipeline handling, or migration execution strategy. This is a topology-level concern that can cause epic-level divergence. |
| F-3 | **High** | 1 | **AD-9 (five-pod topology) undercounts pods.** Even setting aside RHOKP, the spine should explicitly state that PostgreSQL is a StatefulSet, not a Deployment. If the spec's RHOKP resolution is adopted, the topology grows to at least seven pods (+ Solr, + okp-mcp). |
| F-4 | **Medium** | 2 | **AD-2 defaults to `cluster-admin` without defining a tighter baseline.** The PRD flagged this as the highest-friction adoption point. The AD resolves it with a permissive default + configurability escape hatch, but doesn't define what a recommended least-privilege scope looks like. |
| F-5 | **Medium** | 3 | **Internal TLS posture is deferred without a divergence assessment.** If the decision is "plaintext within namespace for MVP," it should be stated as an explicit AD or convention, not left ambiguous. |
| F-6 | **Medium** | 7 | **AD-9 text says "five Deployments" but PostgreSQL is a StatefulSet in the diagram.** Minor factual inconsistency that should be corrected to avoid confusing Helm chart implementers. |
| F-7 | **Low** | 4 | **prometheus-client and nginx versions not independently verified.** Both are slow-moving, stable projects; risk is minimal. |
