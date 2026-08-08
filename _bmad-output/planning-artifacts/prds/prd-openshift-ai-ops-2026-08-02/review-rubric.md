# PRD Quality Review — OpenShift AI Ops

## Overall verdict

This is a well-built PRD that earns its length. The pipeline architecture (intake → diagnosis → validation → remediation → learning) is coherent, the safety model is genuinely thought through, and the scope honesty is above average — rejected alternatives are named, post-MVP items are tagged, and the assumptions index roundtrips cleanly. What holds the PRD back from "strong" across the board is softness in the diagnosis pipeline's testable consequences: the hardest engineering problems (alert correlation logic, multi-specialist conflict resolution, "appropriateness" scoring in the eval harness) are described in outcome language but not in verifiable language. An architect reading §4.2 will know what the system should *feel like* but will need to invent the acceptance criteria for how it gets there.

## Decision-readiness — adequate

Decisions are stated as decisions, not buried: no-CRD architecture, pgvector over Qdrant, serialized remediation, default-deny policy, specialist deferral to post-MVP. The addendum's Rejected Alternatives section does genuine work — each rejection names what was given up and why. Open Questions (§13) are authentically open; none answer themselves in the next sentence.

Where this slips from strong: the PRD smooths over at least two real tensions without surfacing them as decisions. First, the vision (§1) declares "by year two, it handles the routine autonomously" while the MVP defaults to all-human-approval — the gap between those two positions is a product strategy question, not a deployment detail, and it isn't framed as one. Second, Open Question 4 (multi-tenancy) could fundamentally change the RBAC model and the UI's authorization surface, but it's parked as an open question rather than scoped as a decision with consequences either way. A decision-maker reading this would approve the pipeline but want a sharper stance on the trust-escalation timeline and multi-tenancy before committing architecture resources.

### Findings
- **medium** Vision-to-MVP trust gap not surfaced as a decision (§1, §6, §12) — The three-year progression (co-pilot → autonomous → proposing improvements) is stated as a roadmap fact, but no intermediate validation gates or decision criteria connect it to the MVP's default-deny posture. A PM needs to decide: what evidence triggers the transition from year-one to year-two behavior? *Fix:* Add a `[NOTE FOR PM]` at the vision's year-two claim, framing the transition criteria as a product decision requiring definition, or add a success metric that gates it.
- **medium** Multi-tenancy parked without consequence analysis (§13 OQ-4) — Namespace-scoped views vs. cluster-admin-only is not a detail — it changes the RBAC model, the UI authorization surface, and the policy matrix granularity. *Fix:* Either scope it out as an explicit non-goal for v1 (with a sentence on why) or promote it to a decision with two options and their downstream consequences.

## Substance over theater — strong

The content is earned. Three user journeys with named protagonists (Karim, Priya, Marco) each drive distinct system behaviors — UJ-1 drives the pipeline, UJ-2 drives deployment and trust escalation, UJ-3 drives the summary dashboard. No persona exists without a job. The competitive landscape in the addendum names specific products, identifies a concrete whitespace (no existing tool reasons natively about OpenShift-specific abstractions), and doesn't claim differentiation that the features can't deliver. NFRs carry product-specific thresholds (500ms webhook ack, 1s intake latency, 100-alert storm ceiling, pgvector indexing strategy), not boilerplate. The vision is specific to the OpenShift operational domain and couldn't be swapped into a generic AI ops PRD without rewriting.

### Findings
- **low** SM-3 fleet adoption target is aspirational, not product-validating (§10) — "100% of OpenShift clusters in the fleet within 12 months" measures organizational rollout, not whether the product thesis is correct. A tool that's deployed everywhere but ignored by SREs would score perfectly on SM-3. *Fix:* Reframe as a secondary metric or add a qualifier (e.g., "deployed and actively processing alerts on 100% of clusters").

## Strategic coherence — strong

The PRD has a clear thesis: replace manual SRE incident response with AI-driven, safety-gated, self-improving diagnosis and remediation. Every feature group serves the pipeline arc. The Learning Store (§4.5) and fast-path bypass (FR-20) are load-bearing — they're the mechanism for the "gets better over time" claim, not a nice-to-have bolted on. Success metrics validate the thesis: SM-1 (diagnosis accuracy) validates the intelligence claim, SM-2 (MTTR) validates the speed claim, SM-4 (trust progression) validates the safety-escalation model. Counter-metrics (SM-C1, SM-C2) genuinely counterbalance — SM-C1 catches the system getting more dangerous as it gets more autonomous, SM-C2 catches the system doing unnecessary work.

MVP scope is problem-solving (solve incident response end-to-end) and the scope logic follows: the pipeline is complete from intake to learning, with the specialist depth deferred to post-MVP. The `[NOTE FOR PM]` on specialist deferral (§6.2) correctly identifies it as the highest-value post-MVP item.

### Findings
- **low** Eval harness → trust progression link is implicit (§4.7, §10 SM-4) — SM-4 says "at least one SRE team trusts the tool for auto-remediation within 6 months." FR-26 gates auto-remediation on eval harness results. But the PRD never explicitly connects them: does passing the eval harness *automatically* unlock auto-remediation in the policy matrix, or does it produce a report that a human uses to justify relaxing the matrix? *Fix:* One sentence in FR-26 or SM-4 clarifying the handoff from eval harness pass → policy matrix change.

## Done-ness clarity — adequate

Most FRs carry specific, testable consequences. The best examples: FR-1 (HTTP 200 within 500ms, HTTP 400 on malformed), FR-8/FR-9 (root-cause hash unchanged = pass, changed = one re-challenge), FR-12 (dry-run=server, admission webhooks exercised, RBAC/quota checked), FR-15 (global lock, configurable cooldown, skip stale). Schema definitions for the Structured Diagnosis Object and Remediation Plan are provided in the addendum with concrete field-level examples. An engineer reading FR-10 through FR-17 would know exactly what "done" looks like.

Where this falls short is the diagnosis pipeline (§4.2), which is also the hardest part of the system. Three FRs rely on outcome language that an engineer cannot directly verify without inventing the criteria:

### Findings
- **high** Alert correlation logic is unspecified (§4.1 FR-2) — "Related alerts firing within a configurable time window are grouped into a single Root-Cause Event" leaves "related" undefined. Is it label overlap? Alert name prefix? Common target resource? Temporal proximity alone? An engineer implementing this needs a correlation strategy, not just the word "related." *Fix:* Name the correlation dimensions (label intersection, target resource overlap, temporal window) or flag as a `[NOTE FOR PM]` requiring specification before implementation.
- **high** Conflict resolution in the Orchestrator is hand-wavy (§4.2 FR-4) — "Resolves conflicting findings from multiple Specialists into a single coherent diagnosis" is an outcome, not a testable condition. What makes a synthesis "coherent"? Does the Orchestrator pick one, merge fields, or re-diagnose? *Fix:* Add at least one testable consequence: e.g., "When specialists produce conflicting root-cause codes, the Orchestrator produces a single diagnosis with a rationale for the selected root cause, and the rejected hypotheses are preserved in the audit trail."
- **medium** Eval harness "appropriateness" scoring is vague (§4.7 FR-25) — "Remediation appropriateness (plan alignment with expected approach)" has no defined scoring mechanism. Is it binary match/no-match on root-cause code? Step-level similarity? Human judgment? *Fix:* Define the comparison method — e.g., root-cause code exact match for diagnosis accuracy, step-category match for remediation appropriateness.
- **medium** "estimated_risk" has no defined scale (§4.4 FR-11) — The Remediation Plan schema includes `estimated_risk` but the PRD doesn't specify the value space (numeric? categorical? what range?). The addendum example shows `"low"` as a string, but the valid values aren't enumerated. *Fix:* Define the risk scale (e.g., `low | medium | high | critical`) or flag as requiring architecture specification.

## Scope honesty — strong

Non-Goals (§5) does genuine work — it names six things a reasonable reader might expect and explains why each is out. The specialist deferral (§6.2) is the right call for MVP with a `[NOTE FOR PM]` flag. Post-MVP items are tagged inline at their FRs (FR-7, FR-23, FR-29 fallback), not hidden in a footnote. The Assumptions Index (§14) roundtrips cleanly: all 11 inline `[ASSUMPTION]` tags appear in the index, and all index entries trace back to inline tags. Open Questions (§13) are genuinely unresolved and cover real unknowns (RHOKP integration mechanism, eval scenario authorship, LLM requirements, multi-tenancy, upgrade path).

The default-deny policy (§8.1) is the strongest scope-honesty signal: the PRD doesn't pretend the system will be autonomous out of the box, and it's honest that trust must be earned through the eval harness and operational observation.

## Downstream usability — strong

This PRD is structured for clean source-extraction by architecture, UX, and story generation workflows. The glossary (§3) defines 20+ domain terms with precision — Blast Radius, Policy Gate vs. Policy Matrix, RBAC Airlock, Immutable Diagnosis Artifact. FR IDs are contiguous (FR-1 through FR-31), UJ IDs are clean (UJ-1 through UJ-3), SM IDs are contiguous with counter-metrics separately namespaced (SM-C1, SM-C2). Feature descriptions cross-reference UJs ("Realizes UJ-1, UJ-2"). SMs cross-reference FRs. The addendum properly separates architecture-level detail (schemas, tech stack, deployment topology) from the PRD's requirements-level content.

Each section stands alone: an architect could pull §4.4 (Remediation Planning and Execution) out of context and understand the inputs, outputs, and constraints without reading §4.2.

### Findings
- **low** "Agentic skills" not in glossary (§3, §4.2 FR-6) — Used in FR-6 ("agentic skills — executable, domain-specific command sequences") and §6.1, but not defined in the glossary. The inline parenthetical in FR-6 is a definition, but glossary consumers won't find it. *Fix:* Add to §3.
- **low** Addendum introduces "MCP lifecycle operator" without PRD reference (addendum §MCP Server Deployment Detail) — The addendum says "the product brief specifies deployment via the MCP lifecycle operator, providing health checks, pod security..." but this component doesn't appear in the PRD, the integration table, or the glossary. Downstream architecture will wonder whether it's in scope. *Fix:* Either add it to §9 (Integration and Dependencies) or note it's a deployment detail for the architecture spec to resolve.

## Shape fit — strong

The rubric calls out: "Internal tool, single-operator role → capability spec shape; UJs may be overhead." This PRD threads the needle correctly. It's an internal tool, but it has three distinct operator roles (on-call SRE, platform lead deploying and tuning, ops lead reporting) with meaningfully different interaction patterns. Three UJs is appropriate — each drives system design. The PRD leans capability-spec where it should (the pipeline stages, the policy matrix, the eval harness) and uses UJs where they clarify operator experience (the 2am incident, the trust-escalation journey, the weekly review). SMs are operational (MTTR, diagnosis accuracy, fast-path rate), fitting the internal tool shape. The PRD is neither over-formalized nor under-formalized for its product type.

## Mechanical notes

- **Glossary drift:** "Policy Gate" and "Policy Matrix" are both defined in §3 with a clear distinction (gate = decision function, matrix = configuration), but §8.1 uses "Policy Matrix" where "Policy Gate" would be more precise ("The default Policy Matrix requires human approval" — it's the gate that requires approval; the matrix is the configuration that the gate reads). Minor, but could confuse downstream consumers. Similarly, §4.4 FR-13 uses both terms correctly, but §4.8 FR-30 title says "Policy Matrix Configuration" while the gate is the functional element — consistent but worth a glance.
- **ID continuity:** FR-1 through FR-31 contiguous, no gaps. UJ-1 through UJ-3 contiguous. SM-1 through SM-6 contiguous, SM-C1/SM-C2 properly namespaced. No duplicates or unresolved cross-references found.
- **Assumptions Index roundtrip:** 11 inline `[ASSUMPTION]` tags, 11 index entries. All resolve correctly. Clean.
- **UJ protagonist naming:** All three UJs have named protagonists (Karim, Priya, Marco) with role and context. Clean.
- **Required sections:** All present for an enterprise internal tool feeding downstream architecture, UX, and story generation. Document Purpose, Vision, Target User, Glossary, Features, Non-Goals, MVP Scope, NFRs, Constraints, Integrations, Success Metrics, Risks, Rollout, Open Questions, Assumptions Index.
