---
title: "Adversarial Review: OpenShift AI Ops PRD"
verdict: CONCERNS
created: 2026-08-02
reviewed: prd.md, addendum.md, brief addendum
---

# Adversarial Review: OpenShift AI Ops PRD

**Verdict: CONCERNS** — The PRD is structurally solid and demonstrates genuine domain expertise. However, it contains a foundational self-containment claim that doesn't survive contact with reality, a security model that no skeptical SRE team lead would approve as stated, several requirements that sound testable but collapse under inspection, and an MVP scope that is dangerously large for a first release. The document can proceed to architecture, but these issues must be resolved — not deferred — or they will cascade into implementation surprises and adoption friction.

---

## Finding 1: The "Self-Contained" Architecture Is a Lie

**Severity: CRITICAL**
**Sections: §1 Vision, §8.2 Self-Containment, §7.2 Reliability, Addendum: Design Philosophy**

The design philosophy "Don't depend on the patient you're trying to heal" is the PRD's most compelling idea and its most dishonest claim. The system deploys PostgreSQL as a pod *inside the cluster it's supposed to heal*. If the control plane is degraded:

- The PostgreSQL pod may be evicted and unable to reschedule (scheduler unavailable).
- Its PVC may become inaccessible (storage subsystem degraded — one of the tool's own diagnosis categories).
- Networking between the tool's pods may be disrupted (CNI degraded).
- The MCP Server pods themselves may be unable to start or connect to the API server.

§8.2 says "The system's own data store remains available even if the cluster's control plane is impaired." This is false for any in-cluster PostgreSQL. The Priority Queue, LangGraph checkpoints, Learning Store, and audit trail all depend on PostgreSQL. If PostgreSQL is down, the tool is down — at exactly the moment it's supposed to be most useful.

The no-CRD decision is defensible. The claim that the tool "still functions" during cluster degradation is not. The PRD needs to either:

1. **Acknowledge the limitation honestly** — the tool works when *some* cluster subsystems are degraded, not when the control plane is fully impaired. Specify which failure modes it survives and which it doesn't.
2. **Specify an external PostgreSQL option** — allow the Helm chart to point to an off-cluster database, which actually delivers on the "don't depend on the patient" promise.
3. **Define degradation tiers** — what capabilities remain at each tier of cluster impairment? The current "degrades gracefully" language (§7.2) is exactly the kind of vague promise that wastes engineering time later.

---

## Finding 2: cluster-admin on an AI System Is a Non-Starter

**Severity: CRITICAL**
**Sections: §7.1 Security, §4.4 FR-15, Addendum: MCP Server Integration**

The read-write MCP Server is bound to a `cluster-admin` ServiceAccount. Every skeptical SRE team lead in the target audience will ask the same question: *"You want me to give an AI system — one whose behavior is non-deterministic by design — cluster-admin on my production cluster?"*

The PRD provides no answer. The Policy Gate is a software control that limits *when* the tool acts, but the hard RBAC boundary gives it *permission to do anything*. If there's a bug in the policy gate, a prompt injection via a malicious alert label, or an LLM hallucination that produces a valid but destructive `kubectl` command, the ServiceAccount has the permissions to execute it.

The PRD should:

1. **Define a least-privilege remediation ServiceAccount** with scoped permissions (e.g., patch deployments/statefulsets, cordon/drain nodes, delete pods, patch StorageClasses) instead of cluster-admin. The scope can be documented and audited.
2. **Acknowledge cluster-admin as a deployment option** for teams that want maximum flexibility, but make it opt-in, not default.
3. **Address prompt injection / adversarial input** as a risk. Alert labels come from Prometheus rules that could be authored by anyone with namespace access. A crafted label value could influence LLM reasoning. This is not in the risk table (§11).

---

## Finding 3: Alert Resolution as Sole Success Signal Is Fragile

**Severity: HIGH**
**Sections: §4.4 FR-16, §4.5 FR-18, Addendum: Design Philosophy**

The design philosophy says "the alert is why we're here, so its absence is victory." FR-16 operationalizes this as: alert resolved webhook arrives = success, timeout = failure. This binary signal will poison the Learning Store with both false positives and false negatives:

**False positives (success recorded, but fix didn't work):**
- Alert resolves due to its `for` duration resetting (metric dips below threshold briefly, re-fires later).
- Alert resolves because someone else fixed it manually while the tool's remediation was in the queue or cooldown.
- Alert resolves due to an unrelated cascading fix from a different remediation.

**False negatives (failure recorded, but fix worked):**
- Remediation fixes root cause, but alert evaluation interval hasn't fired yet within the timeout.
- Remediation requires a cluster component restart that temporarily disrupts the Prometheus scrape.
- Alert rule's `for` duration means it takes N minutes to resolve even after the condition clears.

**Impact:** Every false signal trains the fast-path wrong. False positives teach the system to replay ineffective fixes. False negatives discard good fixes and reduce fast-path coverage.

**Fix:**
1. Add a post-remediation verification step that actively checks the diagnosed condition (not just waits for the alert webhook). The Structured Diagnosis Object already contains `affected_resources` — verify their state directly.
2. Document the false-signal risks in the Case Record schema — add a `confidence_in_outcome` field, not just a binary success/failure.
3. Define what happens when the alert re-fires within N minutes of a "successful" remediation.

---

## Finding 4: The MVP Scope Is 18 Months of Work Labeled as v1

**Severity: HIGH**
**Sections: §6.1 In Scope, §10 Success Metrics SM-3**

Count the components in §6.1: webhook receiver, priority queue with dedup/correlation, LangGraph agent pipeline, orchestrator with completeness gate, structured diagnosis with taxonomy, adversarial skeptic (diagnosis + remediation), remediation planner, dry-run validation, policy gate, serialized executor, outcome observer, Learning Store with temporal decay, vector DB fast-path, REST API (versioned), standalone web UI (incidents + diagnosis + remediation + approval + summary dashboard), PostgreSQL + pgvector, two MCP Server instances, eval harness with scenario injection + accuracy measurement + trust gating, full audit trail. Plus "curated knowledge sources" integration (runbooks, RHOKP, agentic skills).

That is not an MVP. That is a full product. An MVP would be:

- Webhook intake → single-agent diagnosis → human-approval-only remediation → basic web UI → case record storage.

The word "minimal" in MVP has been redefined to mean "everything except domain specialists and the console plugin." SM-3 then demands 100% fleet adoption within 12 months of this overloaded scope. This sets the project up for one of two outcomes: ship late, or ship half-baked.

**Fix:**
1. Define a true MVP-0 that delivers value with a fraction of the scope. The eval harness alone (FR-24/25/26) is a separate epic that could ship after the core pipeline.
2. Phase the in-scope items into MVP-0, MVP-1, and v1.1 with clear ship gates.
3. Replace SM-3 with a meaningful adoption metric: "N pilot teams running in HITL mode within 3 months."

---

## Finding 5: Serialized Remediation Creates an Unbounded Queue Under Load

**Severity: HIGH**
**Sections: §4.4 FR-15, §8.1 Operational Safety, §10 SM-2**

FR-15 mandates a global lock: one remediation at a time, with configurable cooldown between executions. §10 SM-2 measures MTTR as a success metric.

During a real incident — the exact scenario the tool is built for — multiple Root-Cause Events will queue up. If each remediation takes 2-5 minutes to execute + observe + cooldown, and there are 10 events in the queue, the last event waits 20-50 minutes before its remediation even starts. This directly undermines SM-2 (MTTR reduction).

Worse: FR-15 says "queued remediations that are no longer needed (alert auto-resolved during cooldown) are detected and skipped." But what about remediations that *become* no longer needed because an earlier remediation in the queue fixed the root cause of a cascading failure? The dequeue logic relies on `resolved` webhooks, but those may arrive with delay or not at all if the earlier fix hasn't propagated yet. The queue could execute stale remediations against a cluster whose state has changed.

**Fix:**
1. Define queue drain behavior explicitly: re-validate the diagnosis and alert status before execution, not just during cooldown.
2. Acknowledge the MTTR tradeoff in the PRD — serialization is a safety/correctness tradeoff against speed. SM-2 targets should account for it.
3. Consider a "namespace-scoped parallelism" option for remediations with `workload` or `namespace` blast radius — two workload-scoped remediations in different namespaces don't conflict.

---

## Finding 6: Addendum Policy Matrix Contradicts PRD Default-Deny

**Severity: MEDIUM**
**Sections: §8.1 Operational Safety, Addendum: Policy Matrix Example**

§8.1 states unambiguously: *"The default Policy Matrix requires human approval for all remediations."* §12 repeats: *"Out of the box, all remediations require human approval."*

The Addendum includes an "illustrative default" policy matrix showing `auto` for four cells:
- sev: low + high conf + blast: workload → auto
- sev: low + high conf + blast: namespace → auto
- sev: high + high conf + blast: workload → auto

These are contradictory. Downstream architecture will implement one or the other and create a support burden. If the addendum's matrix is the "recommended starting point after eval harness passes," say so. If the PRD's default-deny is the shipping default, the addendum should not label an auto-permissive matrix as "default."

**Fix:** Label the addendum matrix as "example post-trust-escalation configuration" and reiterate that the shipping default is all-approval.

---

## Finding 7: RHOKP Is Marked "Required" but May Not Exist as Integrable

**Severity: MEDIUM**
**Sections: §9 Integration and Dependencies, §13 Open Questions #1**

The integration table marks RHOKP as `Required — platform knowledge`. Open Question #1 asks: *"Does RHOKP expose a search API accessible from within the cluster, or does it require a bundled/cached knowledge set?"*

You cannot mark a dependency as "Required" when you haven't confirmed the integration mechanism exists. If RHOKP turns out to require a cached/bundled knowledge set, that changes the architecture (build-time vs. runtime integration, refresh cadence, storage requirements). If it has no programmatic API at all, the feature is blocked.

**Fix:**
1. Downgrade RHOKP to `Required — pending integration validation` or `Conditional`.
2. Add a fallback: if RHOKP integration is infeasible for MVP, what's the degraded capability? The system should still diagnose without RHOKP, just with less context.

---

## Finding 8: UI Authentication During Cluster Degradation Is Unaddressed

**Severity: MEDIUM**
**Sections: §4.9 FR-31, §4.6 FR-21, §7.1 Security**

FR-31 assumes API authentication via OpenShift OAuth/service account tokens (§14 Assumptions Index). FR-21 claims the standalone web app "works independently of OpenShift Console availability."

But OpenShift OAuth is a cluster service. If the cluster's OAuth pods are degraded (which happens during real incidents), the SRE cannot authenticate to the standalone web app — and therefore cannot approve remediations. The tool's most critical workflow (human approval under pressure) fails at the moment it matters most.

**Fix:**
1. Define a fallback authentication mechanism for the standalone app: local admin credentials, client certificates, or an external IdP option.
2. Or acknowledge that "works independently of Console availability" is not the same as "works during full cluster degradation" — and scope the claim accordingly.

---

## Finding 9: Eval Harness Has No Scenario Library — Trust Gate Is Vapor

**Severity: MEDIUM**
**Sections: §4.7 FR-24/25/26, §12 Rollout and Adoption, §13 Open Questions #2**

The trust escalation path (§12) depends entirely on the eval harness: teams observe eval results → gain confidence → relax policy matrix. FR-26 gates auto-remediation on eval accuracy thresholds.

Open Question #2 asks: *"Who creates and maintains the simulated alert scenarios and known-correct answer keys?"* If the answer is "nobody yet," the trust gate is a paper requirement. The eval harness framework ships, but without scenarios it's an empty test runner.

**Fix:**
1. Make the scenario library a first-class deliverable, not an open question. Define at minimum 5-10 scenarios per domain (compute, storage, network) as part of MVP scope.
2. Assign ownership: is this a product team deliverable, an SRE team contribution, or a community effort?
3. Define the schema for a scenario (input alert payload + expected diagnosis + expected remediation approach) so teams can author their own.

---

## Finding 10: Agentic Skills on the Diagnosis Side May Violate the RBAC Airlock

**Severity: MEDIUM**
**Sections: §4.2 FR-6, §7.1 Security, Addendum: Knowledge Sources**

FR-6 says agents can "invoke agentic skills — executable, domain-specific command sequences — as callable tools during diagnosis." The addendum lists examples: `cluster-update`, `find-token`, `node diagnostics`.

Diagnosis agents use the read-only MCP Server instance. But "executable command sequences" implies active operations. Can a `node diagnostics` skill run commands that modify state? If so, the RBAC airlock is violated — diagnosis has write access through the skill backdoor. If not, the PRD needs to state explicitly that all diagnosis-side skills are read-only, and the skill loading mechanism must enforce this.

**Fix:**
1. State that diagnosis-side agentic skills are restricted to read-only operations and explain how this is enforced (not just by convention, but by the ServiceAccount binding).
2. Define a skill classification: read-only skills (diagnosis) vs. read-write skills (remediation only).

---

## Finding 11: No Cost Controls on LLM Usage

**Severity: LOW**
**Sections: §4.2, §4.3, §4.4, §4.8 FR-28**

The pipeline makes multiple LLM calls per incident: orchestrator hypothesis, specialist diagnosis (post-MVP), skeptic challenge (diagnosis), remediation planning, skeptic challenge (remediation). Multiply by the parallelism cap on concurrent pipelines during a storm of 100 alerts.

No mention of: token budgets per incident, cost caps per time period, rate limiting on LLM calls, or monitoring of LLM spend. For an enterprise internal tool, the first question from finance will be "what does this cost to run?" The PRD has no answer.

**Fix:** Add an NFR for LLM cost observability: expose per-incident token usage and cost estimates in the API/UI. Consider a configurable per-incident token budget.

---

## Finding 12: Mid-Remediation Crash Recovery Is Undefined

**Severity: LOW**
**Sections: §4.4 FR-15, §7.2 Reliability**

§7.2 says LangGraph checkpoints enable resumption from the last checkpoint on pod restart. But what happens during a multi-step remediation (FR-11 `steps: [...]`) when the tool crashes after step 2 of 5?

- Does it re-execute steps 1 and 2 (potentially non-idempotent)?
- Does it skip to step 3 (how does it know step 2 completed)?
- Does it abort and mark as failed?

The PRD doesn't say. For a tool that modifies production clusters, this is not an edge case — it's a core reliability requirement.

**Fix:** Define step-level checkpointing: each remediation step is individually recorded as complete/incomplete, and recovery skips completed steps. Require that remediation steps be idempotent where possible, and flag non-idempotent steps in the plan schema.

---

## Minor Issues (Not Individually Scored)

| Issue | Section | Note |
|-------|---------|------|
| "degrades gracefully" used without definition | §7.2 | Classic vague NFR. What does "partial data" mean? Define specific degradation behaviors. |
| No mention of multi-tenancy in MVP | §13 OQ#4 | If this is an enterprise tool for shared clusters, namespace-scoped views are likely a hard requirement, not an open question. |
| SM-6 "Alert Coverage" has no target | §10 | Every other primary metric has a target. Coverage is unmeasured. |
| No data retention policy | §4.5 | Learning Store scales to "millions" of records — who cleans up? What's the retention policy? |
| `estimated_risk` in remediation plan is free-text | Addendum schema | "low" is not a testable value. Define an enum or scoring rubric. |
| No mention of RBAC for the REST API beyond "enforces auth" | §4.9 FR-31 | Who can approve vs. view-only? Role definitions are missing. |
| Upgrade path is an open question | §13 OQ#5 | For a tool with stateful persistence and vector embeddings, schema migration strategy should be in-scope for MVP, not deferred. |

---

## Summary Assessment

The PRD demonstrates strong domain expertise and genuine security consciousness (RBAC airlock, adversarial skeptic, default-deny policy). The structured diagnosis and learning store concepts are well-thought-out. However:

- **Two critical findings** (self-containment claim, cluster-admin permissions) will block adoption by the target audience.
- **Three high-severity findings** (MVP scope, success signal fragility, serialized queue bottleneck) will cause implementation pain and metric gaming.
- **Five medium-severity findings** will create confusion or fail during real incidents.

The PRD should be revised to address Findings 1-5 before proceeding to architecture. Findings 6-12 can be resolved during architecture spec or story generation, but should be tracked as known gaps.
