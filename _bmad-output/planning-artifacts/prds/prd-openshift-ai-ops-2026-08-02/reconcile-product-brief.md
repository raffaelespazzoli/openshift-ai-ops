---
title: "Reconciliation: Product Brief → PRD"
type: gap-analysis
created: 2026-08-02
inputs:
  - brief-openshift-ai-ops-2026-08-02/brief.md
  - brief-openshift-ai-ops-2026-08-02/addendum.md
output:
  - prd-openshift-ai-ops-2026-08-02/prd.md
  - prd-openshift-ai-ops-2026-08-02/addendum.md
---

# Reconciliation: Product Brief → PRD

## Summary

The PRD is a faithful and thorough translation of the product brief. It adds meaningful structure (numbered FRs, glossary, counter-metrics, open questions) that strengthen the spec. However, five items from the brief and its addendum were silently dropped or diluted — ranging from a specific deployment mechanism to qualitative vision language that informed the product's positioning.

---

## Gap 1: MCP Lifecycle Operator and Pod Security Standards (Dropped)

**Source:** Brief Addendum §OpenShift MCP Server Integration

> "Both instances deployed via the MCP lifecycle operator, providing health checks, pod security (restricted PSS), and service discovery."

**What the PRD says:** PRD Addendum §MCP Server Deployment Detail states: "Both deployed as sidecar or standalone pods within the Helm chart's namespace."

**What was lost:**
- The explicit use of the "MCP lifecycle operator" as the deployment vehicle for MCP Server instances.
- Health checks provided by that operator.
- Pod security via the **restricted Pod Security Standard (PSS)** profile.
- Service discovery mechanism.

**Impact:** This affects the architecture spec downstream. The PRD implies the Helm chart manages MCP pods directly, while the brief intended operator-managed lifecycle with specific security posture guarantees. A restricted PSS profile is a meaningful security constraint that should appear in §7.1 Security or §8.2 Self-Containment.

**Recommendation:** Add to PRD §7.1 or as a new NFR: MCP Server pods must run under the `restricted` PSS profile. Clarify whether the MCP lifecycle operator is a dependency (contradicts no-operator philosophy?) or whether the Helm chart replicates its capabilities.

---

## Gap 2: Year Three Vision and "Operational Memory" Framing (Dropped)

**Source:** Brief §Vision

> "If this works, OpenShift AI Ops becomes the **operational memory** of every cluster it runs on."

> "By year three, it's proposing alerting improvements, identifying systemic weaknesses, and feeding insights back to platform engineering. The cluster doesn't just heal — it evolves."

**What the PRD says:** PRD §1 Vision stops at year two: "By year two, it handles the routine autonomously while humans focus on novel failures and architecture." No year-three horizon. No "operational memory" concept.

**What was lost:**
- The year-three milestone of proactively proposing alerting improvements and identifying systemic weaknesses (feedback loop from operations back to platform engineering).
- The "operational memory" positioning — a qualitative framing that distinguishes the tool from transactional automation.
- The "cluster evolves" language connecting operational learning to platform improvement.

**Impact:** Low for implementation but medium for product positioning. The year-three vision connects to the "PrometheusRule proposals from learned patterns" future item in scope — but the PRD doesn't draw that line. Downstream marketing, roadmap discussions, and architecture decisions benefit from knowing where the product aspires to go beyond year two.

**Recommendation:** Add a brief year-three sentence to PRD §1 Vision referencing proactive improvement proposals. Consider noting that the future "PrometheusRule proposals" feature is the concrete realization of the year-three vision.

---

## Gap 3: Federated Learning Vision Detail (Diluted to One Line)

**Source:** Brief §Vision (final paragraph)

> "The longer-term possibility: federated learning across clusters, where anonymized case records create a collective intelligence. Your cluster encounters a novel failure — but another cluster in the fleet solved it last week, and the fix flows back automatically. An immune system that gets stronger with scale."

**What the PRD says:** §6.2 Out of Scope: "Cross-cluster federated learning — deferred indefinitely."

**What was lost:**
- The mechanism: **anonymized** case records shared across clusters.
- The value proposition: collective intelligence where one cluster's solution helps another.
- The "immune system" metaphor that captures the scaling benefit.
- The distinction between "deferred" (we'll do it later) and "vision" (this is what it could become).

**Impact:** Low for v1 implementation but medium for strategic alignment. If this vision informs architectural choices now (e.g., case record schema designed for portability, anonymization hooks), those decisions need to be made during architecture spec even though the feature is deferred.

**Recommendation:** Move from the flat "deferred indefinitely" list to a brief Vision Horizon note (2-3 sentences) that preserves the mechanism and informs schema decisions. Flag for architecture spec: design case records with anonymization/portability in mind even though federation is deferred.

---

## Gap 4: "LLM as Fallback" Differentiator vs. MVP Scope Tension (Unresolved)

**Source:** Brief §What Makes This Different

> "Learns and improves without retraining. Known patterns bypass the LLM entirely — reducing cost, latency, and dependence on external services as the case library grows."

**Source:** Brief Addendum §Design Philosophy

> "The LLM is the fallback, not the hot path — vector DB fast-path by default"

**What the PRD says:** FR-20 (Vector DB Fast-Path) is explicitly `[POST-MVP — SHOULD]`. In MVP, every incident goes through the full LLM diagnosis pipeline.

**What was lost:** Not the feature itself (it's in post-MVP), but the acknowledgment of a **positioning tension**. The brief lists "LLM is fallback, not hot path" as a core differentiator — something that makes the product different from competitors. But in MVP, this differentiator cannot be demonstrated because fast-path is deferred. The PRD doesn't flag this as a known limitation of MVP positioning or suggest how to address it (e.g., early case-record accumulation for day-one fast-path activation post-MVP).

**Impact:** Medium for go-to-market and stakeholder expectations. If "LLM as fallback" is marketed as a differentiator but MVP can't demonstrate it, there's a credibility gap. If the Learning Store accumulates cases during MVP but can't use them until post-MVP fast-path ships, there's a missed opportunity to communicate "the system is learning, just not yet acting on it."

**Recommendation:** Add a note in PRD §6.2 under the fast-path deferral acknowledging this tension. Suggest that MVP's Learning Store (FR-18, FR-19) is explicitly positioned as "building the fast-path knowledge base" — the UI could show a "fast-path readiness" indicator even before the feature is enabled. This makes the learning visible to users during MVP.

---

## Gap 5: Agentic Skills as Executable Tools vs. Passive Knowledge (Flattened)

**Source:** Brief Addendum §Knowledge Sources Detail

> `openshift/agentic-skills` — "Domain-specific command sequences (cluster-update, find-token)" — Integration: **"Loaded as specialist tools"**

**What the PRD says:** FR-6 (Knowledge Retrieval) describes all knowledge sources uniformly:
- "Agents retrieve matching runbooks..."
- "Agents query RHOKP..."
- "Agents query the Learning Store..."

The PRD Addendum preserves the distinction in its Knowledge Sources table ("Loaded as specialist tools") but FR-6 does not differentiate between:
- **Passive knowledge** (runbooks, RHOKP articles) retrieved via RAG for reasoning context.
- **Active tools** (agentic-skills command sequences) loaded as callable functions agents can execute.

**What was lost:** The functional requirement that agents don't just *read about* command sequences — they can *execute* them as structured tool calls. This is an architectural distinction: RAG retrieval augments the LLM prompt, while tool-loading extends the agent's action space.

**Impact:** Medium for architecture spec. If the downstream architect reads FR-6 as "everything is RAG," the agentic-skills integration will be built wrong. The tool-loading pattern requires a different integration mechanism (function registration in LangGraph, schema generation, permission scoping).

**Recommendation:** Split FR-6 or add FR-6b distinguishing knowledge retrieval (RAG) from tool registration (agentic-skills loaded as callable agent tools). Specify that agents can invoke agentic-skill command sequences as structured tool calls via the MCP Server, not merely reference them as context.

---

## Items Verified as Covered

The following brief items were confirmed present in the PRD (not gaps):

- TTL cleanup mechanism → FR-3 consequence
- Gap detection / "no specialist covers this" UI flag → FR-4 consequence
- Skeptic protocol (one round, no infinite loops) → FR-8, FR-9
- RBAC Airlock as immutable boundary → FR-10
- Temporal decay formula and version relevance → FR-19
- Design philosophy statements → PRD Addendum §Design Philosophy
- Rejected alternatives → PRD Addendum §Rejected Alternatives
- Competitive landscape → PRD Addendum §Competitive Landscape
- Policy matrix example → PRD Addendum §Policy Matrix Example
- Per-agent LLM configuration including thinking mode → FR-28
- Eval harness trust gating per domain → FR-26
- Two MCP Server instances with --read-only flag → §7.1, PRD Addendum
- Diagnosis comparison via root-cause hash → FR-5
- Alert deduplication and priority queue → FR-2, FR-3
- All success criteria from brief → SM-1 through SM-6

---

## Severity Summary

| # | Gap | Severity | Affects |
|---|-----|----------|---------|
| 1 | MCP Lifecycle Operator + restricted PSS | Medium | Architecture spec, security posture |
| 2 | Year-three vision + "operational memory" | Low | Roadmap, positioning |
| 3 | Federated learning vision detail | Low | Architecture (schema portability), strategy |
| 4 | LLM-as-fallback positioning tension | Medium | Go-to-market, stakeholder expectations, MVP UX |
| 5 | Agentic skills as tools vs. knowledge | Medium | Architecture spec, agent implementation |
