---
id: SPEC-openshift-ai-ops
companions:
  - glossary.md
  - ../../planning-artifacts/ux-designs/ux-openshift-ai-ops-2026-08-02/EXPERIENCE.md
  - ../../planning-artifacts/ux-designs/ux-openshift-ai-ops-2026-08-02/DESIGN.md
  - ../../planning-artifacts/architecture/architecture-openshift-ai-ops-2026-08-03/ARCHITECTURE-SPINE.md
sources:
  - ../../planning-artifacts/prds/prd-openshift-ai-ops-2026-08-02/prd.md
  - ../../planning-artifacts/prds/prd-openshift-ai-ops-2026-08-02/addendum.md
  - ../../planning-artifacts/briefs/brief-openshift-ai-ops-2026-08-02/brief.md
  - ../../planning-artifacts/briefs/brief-openshift-ai-ops-2026-08-02/addendum.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# OpenShift AI Ops

## Why

OpenShift clusters generate alert storms during cascading failures — dozens of simultaneous alerts that SREs must manually correlate across Grafana dashboards, `oc` commands, and runbooks under time pressure. Diagnosis takes 15–60 minutes per incident for experienced engineers, longer for juniors, and is error-prone. Institutional knowledge lives in people's heads and leaves when they do. The same failures repeat monthly with the same manual 30-minute diagnosis cycle. This is a **pain to solve** compounded by an **opportunity to capture**: frontier LLMs paired with curated OpenShift-specific knowledge (platform runbooks, Red Hat knowledge base, agentic skills) now enable closed-loop AI operations with depth that generic AI ops vendors cannot match — reasoning natively about ClusterVersion, MachineConfigPool, OLM lifecycle, Routes, SCCs, and RHEL CoreOS node issues. OpenShift AI Ops replaces the manual workflow with an AI-driven pipeline that receives AlertManager webhooks, orchestrates multi-agent diagnosis with adversarial validation, proposes policy-gated remediation, and stores outcomes in a learning store that makes the system faster, cheaper, and less LLM-dependent with every incident.

## Capabilities

- **CAP-1 — Alert intake and triage**
  - **intent:** The system can receive AlertManager webhooks, deduplicate repeated firings, correlate related alerts into Root-Cause Events, and order them in a priority queue for downstream processing.
  - **success:** A burst of 100 correlated alerts produces a small number of Root-Cause Events (not 100 independent diagnosis pipelines), queued by urgency × recency, with correlation reasoning visible in the UI.

- **CAP-2 — AI-driven root-cause diagnosis**
  - **intent:** The system can diagnose the root cause of a Root-Cause Event by querying the cluster (read-only), retrieving relevant operational knowledge from RHOKP (via okp-mcp), OpenShift runbooks, the Learning Store, and agentic skills, and producing a structured diagnosis with a root-cause code, causal chain, affected resources, evidence artifacts, and confidence score.
  - **success:** Given a known alert scenario (e.g., PVC stuck pending from StorageClass misconfiguration), the system produces a correct structured diagnosis with the right root-cause code from the controlled taxonomy, supported by concrete evidence from the cluster, without human guidance.

- **CAP-3 — Adversarial validation**
  - **intent:** Every diagnosis and every remediation plan can survive a mandatory round of structured challenge from a skeptic agent that probes for logical flaws, missing evidence, and alternative explanations before proceeding.
  - **success:** A diagnosis with a genuine flaw (e.g., wrong root-cause component, unexplained correlated alert) is rejected and re-evaluated; a sound diagnosis passes unchanged.

- **CAP-4 — Policy-gated remediation**
  - **intent:** The system can produce a structured remediation plan from the validated diagnosis, validate it via dry-run, evaluate it against a configurable policy matrix (severity × blast radius × confidence), present it for human approval when required, and execute it with serialized locking and cooldown — then observe whether the originating alert resolves.
  - **success:** An SRE reviewing a remediation sees the diagnosis, plan steps, blast radius, rollback procedure, dry-run results, and skeptic assessment — and can approve or reject with a single action. Auto-approved remediations execute only when all three policy dimensions pass threshold and evidence artifacts are present.

- **CAP-5 — Outcome-driven learning**
  - **intent:** The system can store every resolved incident as a Case Record with vector embeddings, apply temporal decay to reduce confidence of old or version-mismatched records, and bypass the full LLM diagnosis pipeline when a high-similarity past success exists (fast-path).
  - **success:** After accumulating successful case records, a recurring alert pattern is resolved via fast-path (no LLM call) with the proven remediation replayed through the policy gate. The fast-path percentage trends upward over time.

- **CAP-6 — Operational web UI**
  - **intent:** SREs and ops team leads can manage incidents, review diagnoses, approve remediations, and view operational metrics through a standalone web application that works independently of OpenShift Console availability.
  - **success:** An on-call SRE opens the UI at 2am, sees an alert already diagnosed with a remediation awaiting approval, reviews the full pipeline context, approves, and sees resolution confirmed — all without leaving the tool. An ops lead views the summary dashboard showing incidents handled, auto-remediated percentage, MTTR, and fast-path hit rate over configurable time ranges.

- **CAP-7 — Eval harness for trust building**
  - **intent:** The system can accept simulated alert payloads, process them through the full diagnosis pipeline without executing remediation, measure accuracy against human-validated answer keys, and gate auto-remediation enablement per domain based on results.
  - **success:** A domain (e.g., storage) passes the configurable accuracy threshold on simulated scenarios, producing a recommendation report that an SRE uses to explicitly relax the policy matrix for that domain.

- **CAP-8 — Self-contained deployment and LLM configuration**
  - **intent:** An SRE team can deploy the complete system with a single `helm install` into a dedicated namespace, configure per-agent LLM endpoints and models, and benefit from complexity-based model routing and semantic caching — with no CRDs, no OLM dependency, and no requirement for OpenShift AI.
  - **success:** `helm install` with a minimal values file (LLM endpoint + credentials) produces a functional system. Different agent roles use different models (cheaper for simple alerts, frontier for complex). Semantic cache reduces LLM cost on repeated similar queries.

- **CAP-9 — Versioned REST API**
  - **intent:** All UI surfaces consume a single versioned REST API for incident lifecycle, diagnosis artifacts, remediation plans, approval actions, configuration, and audit data.
  - **success:** The standalone web app and future console plugin both function correctly against the same API contract. All state-changing operations are audit-logged with actor identity.

- **CAP-10 — Domain specialist agents** *(post-MVP)*
  - **intent:** Domain-specific agents (compute, storage, network) can self-select alerts matching their expertise via configurable label-matching rules and produce domain-specific diagnoses that the orchestrator synthesizes.
  - **success:** A new specialist agent is deployed without reconfiguring existing agents and auto-claims matching alerts. Multiple specialists can claim the same alert; the orchestrator synthesizes their findings.

- **CAP-11 — OpenShift Console plugin** *(post-MVP)*
  - **intent:** Key views (incident list, diagnosis detail, approval workflow) can be surfaced as a Console dynamic plugin within the native OpenShift Console experience.
  - **success:** The Console plugin uses the same REST API as the standalone app and provides equivalent functionality for incident management.

## Constraints

- **RBAC Airlock.** Diagnosis agents access the cluster via a read-only MCP Server instance (bound to `cluster-reader` ServiceAccount, `--read-only` flag). Remediation executes via a separate read-write instance (bound to `cluster-admin` ServiceAccount). No cross-access. The immutable diagnosis artifact is the only thing that crosses the boundary.
- **No CRDs, no OLM.** The system deploys as a self-contained Helm chart. It does not install Custom Resource Definitions or depend on the Operator Lifecycle Manager — avoiding circular dependency on the cluster's API extension machinery.
- **Serialized remediation.** A global lock ensures only one remediation executes at a time. A configurable cooldown separates consecutive executions. Before executing a queued remediation, the system re-validates that the originating alert is still firing.
- **Default-deny policy.** The shipping-default policy matrix requires human approval for all remediations. Auto-execution must be explicitly enabled per severity/blast-radius/confidence combination.
- **No automatic rollback.** Rollback is human-triggered only. The system never autonomously decides a remediation made things worse. Triggered rollback is stored as a failure signal in the Learning Store.
- **Mandatory adversarial validation.** Every diagnosis and every remediation plan must survive skeptic challenge. This is a pipeline stage, not an optional review.
- **Evidence required for auto-execution.** Auto-execution is blocked when the diagnosis lacks concrete evidence artifacts (log lines, metric values, resource states) or when evidence gaps exist from MCP timeouts — regardless of other policy matrix dimensions.
- **Cluster-degradation resilience.** The tool must function when the managed cluster is partially degraded. Self-contained PostgreSQL persistence, graceful handling of MCP Server timeouts (partial evidence, not failure), and no dependency on cluster API machinery for the tool's own operation.

## Non-goals

- **Application-layer diagnosis.** The tool diagnoses cluster infrastructure (nodes, storage, networking, platform services). Application-level bugs, performance issues, and business logic failures are out of scope.
- **Multi-cluster management.** V1 operates on a single cluster. Cross-cluster aggregation, federated learning, and fleet-wide views are deferred.
- **Predictive alerting from raw metrics.** The system responds to alerts, not raw metrics. Post-hoc PrometheusRule proposals are a future possibility.
- **Replacing the monitoring stack.** The tool is a downstream consumer of alerts. It does not replace Prometheus, AlertManager, Grafana, or existing monitoring infrastructure.
- **Custom CRD-based API.** The system deliberately avoids CRDs to maintain independence from cluster API machinery.

## Success signal

An SRE team deploys OpenShift AI Ops on a production cluster, runs the eval harness to validate diagnostic accuracy at 90%+, and within six months trusts the tool for auto-remediation on at least some alert categories (e.g., pod restarts, resource scaling). Mean time to resolution for handled incidents shows measurable reduction against the pre-tool baseline, and the fast-path percentage trends upward as the Learning Store accumulates successful case records.

## Assumptions

- 500ms webhook acknowledgment SLA is appropriate for AlertManager integration.
- Label intersection, temporal proximity, and Learning Store cascade patterns are sufficient correlation dimensions for MVP.
- Complexity can be estimated from alert metadata before full diagnosis begins, enabling model routing.
- API authentication uses OpenShift OAuth / service account tokens.
- Standard Kubernetes Secret management is sufficient for LLM credentials in v1.
- pgvector with appropriate indexing (IVFFlat or HNSW) meets the thousands-to-millions scale target for the Learning Store.

## Resolved Questions

All original open questions have been resolved. Decisions are recorded in `.memlog.md` and summarized here for traceability.

- **RHOKP integration mechanism.** Deploy RHOKP (Solr container, 600k+ docs) + okp-mcp (MCP server) as sidecar deployments in the Helm chart. Agents query knowledge via MCP streamable-http. Offline-capable, no external API dependency.
- **Eval harness scenario library.** Seeded from the `openshift/runbooks` repo — each runbook maps alert name to diagnosis steps and remediation actions, structured into scenario + expected-answer pairs. Augmented over time with hand-authored scenarios and production case records promoted after human validation.
- **LLM endpoint minimum requirements.** Required capabilities: tool use / function calling, structured output (JSON schema conformance), multi-step reasoning. Specific model selection per agent role is a deployment decision, not a spec constraint.
- **Multi-tenancy.** Cluster-scoped only. The tool serves the ops team responsible for cluster health, not individual tenant teams.
- **MTTR baseline.** The organization's pre-existing MTTR tracking provides the baseline. The tool tracks its own MTTR via the summary dashboard (CAP-6) for comparison. No specific target number — success is that MTTR trends lower after adoption.
