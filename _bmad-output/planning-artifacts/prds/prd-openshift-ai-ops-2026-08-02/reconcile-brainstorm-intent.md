# Reconciliation: brainstorm-intent.md → PRD + Addendum

**Input:** `brainstorm-intent.md` (68 lines — product identity, architectural decisions, agent pipeline, design principles, MoSCoW scope, knowledge sources, future roadmap)

**PRD:** `prd.md` (559 lines)
**Addendum:** `addendum.md` (75 lines)

---

## Gaps Found

### GAP 1: Vector DB Fast-Path Positioned as Core Philosophy, Deferred as Feature

**In brainstorm-intent:**
- Design Principle: "Vector DB fast-path as default — Past successes bypass LLM entirely. LLM is fallback for novel failures. System gets cheaper over time."
- Pipeline Step 3 describes it as "Default behavior."
- MoSCoW: listed as SHOULD (not MUST), creating an internal tension with the "default behavior" wording.

**In PRD:**
- FR-20 marks it POST-MVP SHOULD. §6.2 explicitly says "All alerts go through full LLM diagnosis initially."

**In Addendum:**
- Design Philosophy section preserves the quote: "The LLM is the fallback, not the hot path."

**Gap:** The brainstorm establishes a foundational design philosophy ("the LLM is the fallback") that the PRD contradicts at launch. The addendum preserves the *quote* but the PRD's MVP scope means the tool launches with the LLM as the hot path — the opposite of the stated principle. This isn't just a scope deferral; it's a philosophical inversion that affects how early users perceive the system's economics and architecture.

**Recommendation:** Either (a) pull fast-path into MVP (even with a conservative similarity threshold), or (b) explicitly acknowledge in the PRD that the MVP inverts the design philosophy and explain why (e.g., insufficient training data at launch).

---

### GAP 2: "Confidence Boost from Repeated Success" Silently Dropped

**In brainstorm-intent:**
- MoSCoW COULD: "confidence boost from repeated success"

**In PRD:** Absent. FR-19 covers temporal *decay* (confidence decreases over time) but never mentions the complementary positive signal — confidence *increasing* when the same solution succeeds repeatedly.

**In Addendum:** Absent.

**Gap:** The brainstorm envisions a bidirectional confidence model: decay pulls old cases down, repeated success pushes proven cases up. The PRD only implements the downward pressure. Without the upward mechanism, the system can never promote a repeatedly-successful fix to maximum confidence — it only ever degrades. This affects the long-term economics of the fast-path and the trust progression narrative (SM-4).

**Recommendation:** Add to PRD §6.2 as a named post-MVP item, or fold into FR-19's temporal decay formula as a "success multiplier" term.

---

### GAP 3: Agentic-Skills Repositories Missing from FR-Level Coverage

**In brainstorm-intent:**
- Knowledge Sources: "Agentic-skills repositories — Domain-specific command sequences and diagnostic procedures" listed as a primary knowledge source alongside runbooks, RHOKP, and pgvector.

**In PRD:**
- FR-6 (Knowledge Retrieval) testable consequences name three sources: OpenShift runbooks, RHOKP, and Learning Store. Agentic-skills repositories are absent.

**In Addendum:**
- Knowledge Sources Detail table preserves the URLs (`openshift/agentic-skills`, `pramodmax/openshift-ai-skills`) and describes them as "Loaded as specialist tools" / "Knowledge augmentation."

**Gap:** The addendum preserves implementation-level detail, but without FR-level coverage the agentic-skills integration has no testable requirement, no validation criteria, and no traceability to success metrics. It exists in architecture reference only — which means it could be deprioritized or forgotten without triggering a requirement gap in downstream specs.

**Recommendation:** Add a fourth bullet to FR-6's testable consequences: "Agents load domain-specific command sequences from configured agentic-skills repositories as executable tool definitions."

---

### GAP 4: Orchestrator "Completeness Gate" Concept Dropped

**In brainstorm-intent:**
- Pipeline Step 4 (Diagnosis Orchestrator): "Holds session state, resolves conflicts, **enforces completeness gate**."

**In PRD:**
- FR-4 captures: produces/synthesizes diagnosis, handles unclaimed alerts, resolves conflicting findings. No mention of a completeness gate — the concept that the orchestrator must verify the diagnosis is sufficiently complete before passing it to the skeptic.

**In Addendum:** Absent.

**Gap:** The "completeness gate" is a distinct quality control mechanism — the orchestrator doesn't just synthesize, it actively blocks progression until the diagnosis meets completeness criteria (e.g., all affected resources identified, causal chain has no unexplained jumps). Without this, the skeptic inherits the completeness check implicitly, but the skeptic's mandate is adversarial challenge, not completeness verification. These are different cognitive tasks.

**Recommendation:** Add a testable consequence to FR-4: "The Orchestrator does not pass a diagnosis to the Skeptic until configurable completeness criteria are met (e.g., affected resources enumerated, causal chain terminates at a root cause in the taxonomy)."

---

### GAP 5: Dry-Run Framed as Mandatory Safety Step vs. Optional Enhancement

**In brainstorm-intent:**
- Pipeline Step 8: "**Always executes before human review.**" This positions dry-run as intrinsic to the safety model — the human sees validated information, not raw proposals.
- MoSCoW: listed as SHOULD (internally inconsistent with "always executes").

**In PRD:**
- FR-12 marked POST-MVP SHOULD. §6.2 explicitly defers it.

**In Addendum:** Absent from design philosophy or safety discussion.

**Gap:** The brainstorm's pipeline narrative communicates that dry-run is part of the *trust contract* with the human approver — they're reviewing a pre-validated plan, not an unvalidated proposal. The PRD treats it as an optimization. This matters for UX design: without dry-run, the approval UI shows a plan with unknown feasibility, which undermines the confidence the human is supposed to derive from the review. The PRD's §11 Risk table lists "Bad remediation damages cluster" but dry-run is only listed as a mitigation with "(post-MVP)" qualifier.

**Recommendation:** Either (a) acknowledge in the PRD that MVP's human approval is reviewing *unvalidated* plans and add a UI indicator ("dry-run not performed"), or (b) consider promoting dry-run to MVP given its role in the safety narrative.

---

## Summary of Coverage

| Brainstorm Section | Coverage |
|---|---|
| Product Identity | Adequate — one-liner intent preserved in §1 Vision |
| Core Problem | Fully captured in §1 |
| Architectural Decisions (6 items) | All 6 captured across PRD + addendum |
| Agent Pipeline (12 steps) | 11/12 captured; completeness gate dropped from Orchestrator |
| Design Principles (7 items) | 6/7 captured; fast-path-as-default contradicted by MVP scope |
| MoSCoW MUST (17) | All represented in MVP scope |
| MoSCoW SHOULD (7) | All represented as POST-MVP SHOULD |
| MoSCoW COULD (4) | 3/4 captured; "confidence boost from repeated success" dropped |
| MoSCoW WON'T (2) | Both captured in §5 Non-Goals |
| Knowledge Sources (4) | 3/4 have FR coverage; agentic-skills addendum-only |
| Future Roadmap | Fully captured in §5 and §6.2 |

**Overall:** The PRD is thorough. The gaps are qualitative (philosophical tension, missing positive feedback loop, incomplete FR traceability) rather than wholesale feature omissions.
