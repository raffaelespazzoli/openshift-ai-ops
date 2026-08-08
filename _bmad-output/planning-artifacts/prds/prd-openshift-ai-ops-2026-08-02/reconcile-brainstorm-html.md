# Reconciliation: brainstorm.html → PRD + Addendum

**Input:** `brainstorm.html` (OpenShift AI Ops — Mission Briefing)
**PRD:** `prd.md` (2026-08-02 draft)
**Addendum:** `addendum.md` (2026-08-02)

---

## Gap 1: Lateral Escalation Between Specialists

**Source (Ecosystem Thinking → Domain Specialists):**
> "Support lateral escalation: specialist refers to another specialist"

**What the PRD says:** FR-7 covers specialists self-selecting alerts via label matching and multiple specialists claiming the same alert, with the Orchestrator synthesizing findings. FR-4 describes the Orchestrator resolving conflicting findings.

**Gap:** The brainstorm describes a distinct interaction pattern — one specialist recognizing mid-diagnosis that another domain is involved and directly referring the case laterally, rather than relying solely on the Orchestrator to coordinate. The PRD's model is hub-and-spoke (specialists → orchestrator → synthesis), while the brainstorm also included peer-to-peer specialist referral. This changes how cross-domain failures are diagnosed: a storage specialist discovering that a network partition is the actual root cause would escalate laterally to the network specialist, rather than returning a partial finding for the orchestrator to re-dispatch. Neither the PRD nor the addendum acknowledges or explicitly rejects this pattern.

**Severity:** Medium — affects architecture of the specialist communication model and could improve diagnosis quality for cross-domain cascading failures.

---

## Gap 2: Food Web Layering — Knowledge Isolation per Agent Role

**Source (Ecosystem Thinking → Food Web Layering):**
> "Each organism accesses only its layer's knowledge — stays lean"
> - Specialists → cluster state + domain skills
> - Orchestrator → specialist outputs + runbooks + vector DB + RHOKP
> - Triage → raw alert stream + grouping rules

**What the PRD says:** FR-6 (Knowledge Retrieval) describes agents retrieving from runbooks, RHOKP, and the Learning Store — but does not establish which agents access which sources. The framing is "agents retrieve" generically.

**Gap:** The brainstorm proposed a strict knowledge-isolation principle: each pipeline stage accesses only its layer's knowledge to stay lean and reduce noise. Triage never queries the vector DB. Specialists never query RHOKP directly. This is an architectural guardrail that prevents context window pollution and enforces separation of concerns. The PRD treats knowledge retrieval as a shared capability available to all agents, losing the intentional layering. The addendum does not capture it.

**Severity:** Medium-High — this is a named architectural principle ("Food Web Layering") that affects agent prompt design, context window budgeting, and the security surface of each agent's knowledge access.

---

## Gap 3: Orchestrator as "Completeness Quality Gate"

**Source (Ecosystem Thinking → Orchestrator as Hypothesis Builder):**
> "Unique roles: dispatch logic, conflict resolution, completeness quality gate"

**What the PRD says:** FR-4 describes the Orchestrator forming hypotheses, dispatching to specialists, synthesizing findings, and resolving conflicts. It does not mention a completeness quality gate.

**Gap:** The brainstorm assigned the orchestrator an explicit "completeness quality gate" role — verifying that the assembled diagnosis is complete before passing it downstream (e.g., all affected subsystems investigated, no unresolved causal gaps). The PRD captures synthesis and conflict resolution but drops completeness verification as a distinct responsibility. Without this gate, an incomplete diagnosis (e.g., one that identifies the symptom but misses a contributing cause) could pass through to the skeptic and remediation stages.

**Severity:** Medium — a completeness check before adversarial validation could prevent partial diagnoses from wasting a skeptic round and producing incomplete remediation plans.

---

## Gap 4: "Confidence Boost" — MoSCoW Could-Have Silently Dropped

**Source (MoSCoW Prioritization → Could Have):**
> "PrometheusRule proposals, knowledge graph, confidence boost, version decay"

**What the PRD says:** PrometheusRule proposals (§5, §6.2), knowledge graph (§6.2), and version decay/temporal decay (FR-19) are all addressed — either as non-goals, future items, or implemented features. "Confidence boost" has no corresponding entry anywhere in the PRD or addendum.

**Gap:** The brainstorm identified "confidence boost" as a Could-Have feature. While temporal decay (reducing confidence over time) is well-specified in FR-19, the inverse — boosting a Case Record's effective confidence when the same fix succeeds repeatedly — is not mentioned. This would create a reinforcement learning signal: a fix that works three times in a row should carry higher confidence than one that worked once six months ago. The PRD has the decay half of the confidence lifecycle but silently dropped the growth half.

**Severity:** Medium — this mechanism would accelerate fast-path eligibility and provide a natural counterbalance to temporal decay. Its absence means confidence only degrades, never strengthens through repeated success.

---

## Gap 5: MCP Server Multi-Cluster Capability as Future Enabler

**Source (Emerging Tech Collision → OpenShift MCP Server):**
> "Supports --read-only mode, multi-cluster, RBAC-respecting, bearer token auth"

**What the PRD says:** §5 (Non-Goals) and §6.2 (Out of Scope) defer multi-cluster management. §9 (Integration) and §7.1 (Security) describe the MCP Server deployment in single-cluster terms. The addendum's MCP Server section describes dual-instance deployment but does not mention multi-cluster.

**Gap:** The brainstorm noted that the OpenShift MCP Server natively supports multi-cluster connectivity. While multi-cluster management is correctly deferred, the PRD does not acknowledge that the chosen cluster access layer already supports multi-cluster as a built-in capability. This matters because it validates the architectural choice: when multi-cluster moves from "Won't Have" to a future phase, no infrastructure replacement is needed. The PRD's non-goal framing implies multi-cluster is architecturally distant, when in fact the technology stack already enables it.

**Severity:** Low-Medium — no functional impact on MVP, but acknowledging the built-in capability in the addendum or architecture spec would de-risk future roadmap planning and strengthen the technology choice rationale.

---

## Summary

| # | Gap | Brainstorm Section | Severity |
|---|-----|--------------------|----------|
| 1 | Lateral escalation between specialists (peer-to-peer referral) | Ecosystem Thinking → Domain Specialists | Medium |
| 2 | Food Web Layering — strict knowledge isolation per agent role | Ecosystem Thinking → Food Web Layering | Medium-High |
| 3 | Orchestrator "completeness quality gate" responsibility | Ecosystem Thinking → Orchestrator | Medium |
| 4 | "Confidence boost" Could-Have feature silently dropped | MoSCoW Prioritization | Medium |
| 5 | MCP Server multi-cluster capability not acknowledged as future enabler | Emerging Tech Collision → OpenShift MCP Server | Low-Medium |

**Verdict:** The PRD faithfully captures the vast majority of the brainstorm's content — pipeline stages, tech stack decisions, swarm logic, adversarial protocol, identity philosophy, and MoSCoW prioritization. The gaps above are not contradictions but silent omissions: ideas and architectural principles that were present in the brainstorm but neither carried forward nor explicitly rejected. Gaps 2 and 4 are the most actionable — Food Web Layering is a named architectural principle that should inform the architecture spec, and Confidence Boost is a feature that disappeared without a trace.
