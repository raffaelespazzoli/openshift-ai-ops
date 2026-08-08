---
title: OpenShift AI Ops
status: final
created: 2026-08-02
updated: 2026-08-02
---

# PRD: OpenShift AI Ops

## 0. Document Purpose

This PRD defines the requirements for OpenShift AI Ops, an alert-driven AI operations tool for OpenShift clusters. It is written for downstream architecture, UX, and epic/story generation. The document builds on a completed brainstorm session and product brief (see `_bmad-output/brainstorming/brainstorm-openshift-ai-ops-tool-2026-08-02/` and `_bmad-output/planning-artifacts/briefs/brief-openshift-ai-ops-2026-08-02/`). Features are grouped with globally numbered functional requirements (FR-N). Assumptions are tagged inline as `[ASSUMPTION]` and indexed in §14.

## 1. Vision

OpenShift clusters generate thousands of metrics, hundreds of alerting rules, and during cascading failures can produce dozens of simultaneous alerts. Today, SRE teams respond manually — interpreting symptoms across Grafana dashboards, running `oc` commands, cross-referencing runbooks, and applying fixes under pressure. Diagnosis is slow (15–60 minutes per incident for experienced engineers, longer for juniors), error-prone, and doesn't scale. Institutional knowledge lives in people's heads and walks out when they leave.

OpenShift AI Ops replaces that workflow with an AI-driven pipeline that receives AlertManager webhooks, orchestrates multi-agent diagnosis with adversarial validation, proposes policy-gated remediation, and stores outcomes in a vector-enabled learning store. The system gets faster, cheaper, and more decisive with every incident — known patterns eventually bypass the LLM entirely, replaying proven fixes at machine speed.

This is not a generic monitoring overlay. It is built on deep OpenShift knowledge — platform-specific runbooks, Red Hat knowledge base articles, and purpose-built operational skills — so it understands what `etcdHighFsyncDurations` means out of the box, with depth that generic AI ops vendors cannot match. It doesn't depend on the cluster it's healing: no CRDs, no operator dependencies, self-contained persistence and UI. If the cluster's API machinery is degraded, the tool still functions.

Teams start in full human-in-the-loop mode and progressively open auto-remediation as confidence builds. By year one, it's a co-pilot — suggesting and explaining while humans approve. By year two, it handles the routine autonomously while humans focus on novel failures and architecture. By year three, it's proposing alerting improvements from discovered patterns, identifying systemic weaknesses, and feeding insights back to platform engineering. The cluster doesn't just heal — it evolves.

## 2. Target User

### 2.1 Jobs To Be Done

- **Respond to cluster alerts faster and more accurately** — on-call SREs need to go from alert to resolution without manually correlating symptoms across multiple tools and runbooks.
- **Preserve and reuse institutional knowledge** — ops teams need past diagnosis and resolution knowledge to survive team turnover and remain accessible for future incidents.
- **Reduce alert fatigue during cascading failures** — SREs drowning in correlated alert storms need alerts grouped into root-cause events so they handle one problem, not forty symptoms.
- **Build trust in automation incrementally** — ops teams need to observe the tool's judgment under controlled conditions before granting it autonomous remediation authority.
- **Report operational health** — ops team leads and management need to see how many issues were resolved, how fast, and whether the tool is improving over time.

### 2.2 Non-Users (v1)

- **Application developers and app owners** — the tool operates at the cluster infrastructure layer, not at the application workload layer.
- **Cluster users who don't have ops responsibilities** — the tool's UI and approval workflows are designed for people responsible for cluster health.
- **Multi-cluster fleet managers** — v1 is single-cluster; federated learning and cross-cluster aggregation are out of scope.

### 2.3 Key User Journeys

- **UJ-1. Karim, on-call SRE, gets paged at 2am for a storage alert.** He opens the OpenShift AI Ops web UI on his laptop, sees the alert already triaged and diagnosed — the tool identified a PVC stuck in Pending state caused by a StorageClass misconfiguration after a recent cluster upgrade. A remediation plan is waiting for his approval: patch the StorageClass, verify PVC binds, confirm the alert resolves. He reviews the diagnosis reasoning, checks the dry-run result, approves. The fix executes, the alert resolves within 3 minutes, and the case is stored for future fast-path replay. He goes back to bed.

- **UJ-2. Priya, platform team lead, installs OpenShift AI Ops on a new production cluster.** She runs `helm install` with a values file pointing to the team's LLM endpoint and configuring the policy matrix to require human approval for everything above workload-scoped blast radius. She configures the AlertManager webhook route. The tool picks up its first alert within hours. Over the next two weeks she monitors its diagnosis accuracy and begins relaxing the policy matrix for low-severity, low-blast-radius remediations.

- **UJ-3. Marco, ops team lead, reviews the weekly operations summary.** He opens the summary dashboard and sees that OpenShift AI Ops handled 23 incidents this week — 18 auto-remediated (low-severity pod restarts, resource scaling), 5 required human approval. Mean time to resolution dropped from 34 minutes to 4 minutes for handled categories. He exports the summary for the monthly ops review with management.

## 3. Glossary

- **Agentic Skill** — An executable, domain-specific command sequence (e.g., cluster-update checks, token discovery, node diagnostics) loaded as a callable tool for agents. Distinct from passive knowledge sources (runbooks, RHOKP): skills perform operations, knowledge sources provide reference material. Diagnosis-side skills are read-only; write-capable skills are remediation-only.
- **Alert** — A notification from AlertManager indicating a firing or resolved condition, delivered as an HTTP webhook payload. The fundamental input to the system.
- **Alert Storm** — Multiple related alerts firing simultaneously during a cascading failure. The triage stage correlates these into a single Root-Cause Event.
- **Blast Radius** — The scope of impact of a remediation action: `workload`, `namespace`, `node`, or `cluster`. One of three dimensions in the Policy Gate.
- **Evidence Artifact** — A concrete, machine-verifiable piece of evidence supporting a diagnosis: a specific log line, metric value, resource state, or MCP Server query result. Required for auto-execution via the Policy Gate.

- **Case Record** — A structured entry in the Learning Store capturing the full lifecycle of an incident: alert signature, root-cause code, structured diagnosis, remediation plan, outcome, and cluster context. Stored with vector embeddings for similarity search.
- **Diagnosis Confidence** — A numeric score (0–1) representing the system's confidence in a diagnosis. One of three dimensions in the Policy Gate.
- **Fast-Path** — A bypass of the full LLM diagnosis pipeline: when a new alert matches a past successful Case Record above a configurable similarity threshold, the proven remediation is replayed directly.
- **Immutable Diagnosis Artifact** — The finalized, read-only diagnosis object that crosses the RBAC boundary from diagnosis to remediation. The remediation planner takes it as given and cannot re-diagnose or re-interpret.
- **Learning Store** — The pgvector-backed knowledge base of past Case Records, queryable by embedding similarity. Older records carry reduced confidence via Temporal Decay.
- **MCP Server** — The official OpenShift MCP Server (Model Context Protocol), a Go-native interface to the Kubernetes API. Deployed as two instances: read-only (diagnosis) and read-write (remediation).
- **Orchestrator** — The central agent that forms initial hypotheses, dispatches to Specialists, synthesizes findings, and acts as generalist of last resort for unclaimed alerts.
- **Policy Gate** — The configurable decision matrix (severity × blast radius × diagnosis confidence) that determines whether a remediation auto-executes or requires human approval.
- **Policy Matrix** — The user-configurable thresholds for the Policy Gate. Defines which combinations of severity, blast radius, and confidence levels are trusted for auto-execution.
- **Priority Queue** — The ordered queue of alerts awaiting processing, ranked by urgency × recency.
- **RBAC Airlock** — The security boundary between diagnosis (read-only cluster access) and remediation (read-write cluster access), enforced by separate ServiceAccounts and MCP Server instances.
- **Remediation Plan** — A structured object: `{steps, blast_radius, rollback_plan, estimated_risk, preconditions}`. Produced by the remediation planner from an Immutable Diagnosis Artifact.
- **RHOKP** — Red Hat Offline Knowledge Portal. Platform-level guidance, KBase articles, and CVE information used as a knowledge source during diagnosis.
- **Model Routing** — Dynamic selection of which LLM model handles a request based on estimated task complexity. Simple alerts use cheaper, faster models; complex multi-hop failures use frontier models.
- **Root-Cause Code** — A structured identifier from a controlled taxonomy (e.g., `node/memory-pressure`, `network/dns-failure`, `storage/pvc-stuck-pending`). Part of the Structured Diagnosis Object.
- **Root-Cause Event** — The output of alert correlation: a single event representing the probable root cause behind one or more correlated alerts.
- **Semantic Cache** — A cache layer that stores and reuses LLM responses for semantically similar queries, reducing LLM cost and latency. Entries are invalidated when relevant cluster state changes.
- **Skeptic** — An adversarial agent that challenges a diagnosis or remediation plan in a single round of structured debate. Stability under challenge (root-cause hash unchanged) = acceptance.
- **Specialist** — A domain-specific diagnosis agent (compute, storage, network) that self-selects alerts via label-matching rules. Extensible by deployment.
- **Structured Diagnosis Object** — Schema-enforced output: `{root_cause_component, failure_mode, causal_chain: [...], affected_resources: [...]}`. Enables deterministic comparison via root-cause hash.
- **Temporal Decay** — A confidence reduction applied to older Case Records: `effective_confidence = base_confidence × decay_factor(age) × version_relevance(OCP_version_then vs now)`.

## 4. Features

### 4.1 Alert Intake and Triage

**Description:** The entry point for all cluster alerts. The system receives AlertManager webhooks, deduplicates storm traffic, correlates related alerts into Root-Cause Events, and maintains a Priority Queue for downstream processing. This stage is stateless and high-throughput — it must absorb alert storms without drowning the agent pipeline. Realizes UJ-1.

**Functional Requirements:**

#### FR-1: Webhook Receiver

The system can receive HTTP POST webhooks from AlertManager carrying `firing` and `resolved` alert payloads.

**Consequences (testable):**
- System accepts AlertManager v2 webhook payloads and acknowledges with HTTP 200 within 500ms. `[ASSUMPTION: 500ms SLA is appropriate]`
- `resolved` webhooks immediately dequeue matching alerts from the Priority Queue.
- Malformed payloads are rejected with HTTP 400 and logged.

#### FR-2: Alert Deduplication and Correlation

The system can deduplicate repeated firings of the same alert and correlate related alerts into single Root-Cause Events.

**Consequences (testable):**
- Duplicate alerts (same fingerprint, already in processing) are absorbed without creating new queue entries.
- Related alerts are correlated into a single Root-Cause Event based on: label intersection (shared target resource, namespace, or component labels), temporal proximity (firing within a configurable time window), and known cascade patterns from the Learning Store. `[ASSUMPTION: these three correlation dimensions are sufficient for MVP; additional dimensions may be needed based on operational experience]`
- The UI displays the correlation: which alerts were grouped, the correlation dimensions that matched, and why.

#### FR-3: Priority Queue

The system can order incoming Root-Cause Events by urgency × recency for processing.

**Consequences (testable):**
- Events are dequeued in priority order (highest urgency × most recent first).
- Events that receive no renewal within a configurable TTL are verified against the AlertManager API and removed if no longer active.
- Configurable parallelism cap limits how many events are processed concurrently.

### 4.2 Diagnosis Pipeline

**Description:** The core intelligence of the system. An Orchestrator agent receives Root-Cause Events, forms initial subsystem hypotheses from alert metadata and runbook context, and either handles simple cases solo or dispatches to domain Specialists. All agents query the cluster via the read-only MCP Server instance and draw on curated knowledge sources (runbooks, RHOKP, Learning Store). Output is a Structured Diagnosis Object with confidence scoring. Realizes UJ-1.

**Functional Requirements:**

#### FR-4: Orchestrator Agent

The Orchestrator can form an initial hypothesis from alert metadata and contextual knowledge, dispatch to Specialists when cross-domain reasoning is needed, synthesize partial findings, and handle unclaimed alerts as generalist of last resort.

**Consequences (testable):**
- For each Root-Cause Event, the Orchestrator produces or synthesizes a Structured Diagnosis Object.
- When no Specialist claims an alert, the Orchestrator handles it directly and flags a coverage gap in the UI ("no specialist covers this alert type").
- When Specialists produce conflicting root-cause codes, the Orchestrator produces a single diagnosis with a rationale for the selected root cause; rejected hypotheses are preserved in the audit trail.
- The Orchestrator enforces a completeness gate before handoff to the Skeptic — verifying that the diagnosis addresses all correlated alerts in the Root-Cause Event and that no evidence was left unexamined.

#### FR-5: Structured Diagnosis Output

The system can produce schema-enforced diagnosis objects with a root-cause code from a controlled taxonomy.

**Consequences (testable):**
- Every diagnosis conforms to the schema: `{root_cause_component, failure_mode, causal_chain: [...], affected_resources: [...], evidence: [...]}`.
- Root-cause codes come from a controlled taxonomy (e.g., `node/memory-pressure`, `network/dns-failure`).
- Each diagnosis includes an `evidence` array of concrete artifacts — the specific log lines, metric values, resource states, and MCP Server query results that support the root-cause conclusion. Evidence is machine-verifiable, not free-text rationale.
- Two diagnoses can be compared deterministically via root-cause hash (field diff), with embedding distance as fallback for novel failures not yet in the taxonomy.

#### FR-6: Knowledge Retrieval and Operational Tools

The system can retrieve relevant operational knowledge from curated sources and execute domain-specific operational tools during diagnosis.

**Consequences (testable):**
- Agents retrieve matching runbooks from the OpenShift runbooks repository indexed by alert type (passive knowledge).
- Agents query RHOKP for platform-level guidance, KBase articles, and CVE information relevant to the diagnosed failure mode (passive knowledge).
- Agents query the Learning Store for past Case Records matching the current alert signature (passive knowledge).
- Agents can invoke agentic skills — executable, domain-specific command sequences (e.g., cluster-update checks, token discovery, node diagnostics) — as callable tools during diagnosis, not just as reference material.

#### FR-7: Domain Specialist Agents

Specialist agents can self-select alerts matching their domain expertise via label-matching rules and produce domain-specific diagnoses. `[POST-MVP — SHOULD]`

**Consequences (testable):**
- Each Specialist has configurable label-matching rules defining which alerts it claims.
- Multiple Specialists can claim the same alert; all findings flow to the Orchestrator for synthesis.
- New Specialists can be deployed without reconfiguring existing agents — they auto-claim matching alerts.
- Specialists access domain-specific runbooks, agentic skills, and the Learning Store.

### 4.3 Adversarial Validation

**Description:** Every diagnosis and every remediation plan must survive a single round of structured challenge from a Skeptic agent before proceeding. This is a mandatory pipeline stage — not an optional review. The Skeptic probes for logical flaws, missing evidence, alternative explanations, and overlooked risks. If the diagnosis changes fundamentally under challenge, it is rejected and re-evaluated. Note: the diagnosis pipeline processes multiple events concurrently (bounded by the parallelism cap in FR-3); only remediation execution is serialized (FR-15). The Skeptic does not create a throughput bottleneck — it runs as part of each concurrent diagnosis pipeline instance. Realizes UJ-1.

**Functional Requirements:**

#### FR-8: Diagnosis Skeptic

A Skeptic agent can challenge a Structured Diagnosis Object in one round of structured debate.

**Consequences (testable):**
- The Skeptic receives the diagnosis and produces a structured challenge (alternative hypotheses, evidence gaps, logical weaknesses).
- If the root-cause hash is unchanged after the challenge response, the diagnosis passes.
- If the root-cause hash changes fundamentally, the new diagnosis is re-challenged (one additional round only — no infinite loops).
- The challenge and response are persisted as part of the audit trail.

#### FR-9: Remediation Skeptic

A Skeptic agent can challenge a Remediation Plan in one round of structured debate.

**Consequences (testable):**
- The Skeptic evaluates the plan's steps, blast radius assessment, rollback feasibility, precondition completeness, and estimated risk.
- Same stability protocol as FR-8: unchanged plan passes, fundamentally changed plan is re-challenged once.
- The challenge and response are persisted as part of the audit trail.

### 4.4 Remediation Planning and Execution

**Description:** Once a diagnosis survives adversarial challenge, it becomes an Immutable Diagnosis Artifact and crosses the RBAC Airlock to the remediation side. A remediation planner produces a structured plan. The plan passes through dry-run validation, a configurable Policy Gate, and optional human approval before serialized execution. The system observes whether the original alert resolves as its success criterion. Realizes UJ-1, UJ-2.

**Functional Requirements:**

#### FR-10: Immutable Diagnosis Handoff

The system can produce an immutable diagnosis artifact that crosses the RBAC boundary to remediation.

**Consequences (testable):**
- The remediation planner receives the diagnosis as a read-only input and cannot re-diagnose or re-interpret.
- The root-cause code and causal chain are taken as given.
- The immutable artifact is persisted for audit.

#### FR-11: Structured Remediation Plan

The remediation planner can produce a structured plan from the Immutable Diagnosis Artifact.

**Consequences (testable):**
- Every plan conforms to the schema: `{steps: [...], blast_radius: workload|namespace|node|cluster, rollback_plan: [...], estimated_risk: low|medium|high|critical, preconditions}`.
- The plan includes a rollback procedure when feasible.
- Preconditions (RBAC, quota, resource availability) are enumerated.

#### FR-12: Dry-Run Pre-Flight

The system can validate a remediation plan via server-side dry-run before execution.

**Consequences (testable):**
- `oc apply --dry-run=server` validates resource manifests against the live API server.
- Admission webhook checks are exercised.
- RBAC and quota checks confirm the remediation ServiceAccount has sufficient permissions.
- Dry-run results are shown alongside the plan in the approval UI.

#### FR-13: Policy Gate

The system can evaluate a remediation plan against a configurable three-dimensional policy matrix to determine auto-execution or human approval.

**Consequences (testable):**
- The matrix evaluates: alert severity (from AlertManager) × blast radius (from Remediation Plan) × diagnosis confidence (from Structured Diagnosis).
- All three dimensions must pass threshold for auto-execution. Additionally, the diagnosis must include at least one concrete evidence artifact (FR-5) per element in the causal chain — auto-execution without supporting evidence is blocked regardless of the matrix.
- The policy matrix is user-configurable via Helm values or runtime configuration.
- When human approval is required, the plan is queued with full context (diagnosis, plan, skeptic assessments, dry-run results if available).

#### FR-14: Human Approval Workflow

An on-call SRE can review and approve or reject a remediation plan that requires human approval.

**Consequences (testable):**
- The approval UI presents: diagnosis summary, full remediation plan, skeptic challenge/response, dry-run results (if available), and blast radius assessment.
- SRE can approve (execute), reject (close with reason), or modify the policy gate thresholds for this category going forward.
- Approval/rejection is logged with the approver's identity and timestamp.
- For remediations with `node` or `cluster` blast radius, the system optionally enforces a minimum review time (configurable, e.g., 60 seconds) before the approve action is available — preventing rubber-stamping of high-risk actions under pressure. `[ASSUMPTION: minimum review time is a useful safety mechanism; can be disabled by teams who find it counterproductive]`

#### FR-15: Serialized Execution

The system can execute approved remediation plans one at a time with configurable cooldown.

**Consequences (testable):**
- A global lock ensures only one remediation executes at any time.
- A configurable cooldown period separates consecutive remediation executions to let cluster state settle.
- Before executing a queued remediation, the system re-validates that the originating alert is still firing and the diagnosis is still relevant to the current cluster state. Stale remediations (alert resolved during wait, or cluster state changed by a prior remediation) are skipped.
- Execution uses the read-write MCP Server instance exclusively.

**Notes:** Serialized remediation is a deliberate safety/correctness tradeoff against speed. Under high queue depth, the last event may wait significantly longer than the first. SM-2 (MTTR) targets should account for this inherent latency in multi-event scenarios.

#### FR-16: Outcome Observation

The system can observe whether the original alert resolves after remediation execution.

**Consequences (testable):**
- After execution, the system monitors for the corresponding `resolved` webhook from AlertManager within a configurable timeout.
- In addition to the alert webhook, the system performs a post-remediation verification by checking the state of the `affected_resources` from the Structured Diagnosis Object directly via the read-only MCP Server, reducing reliance on the alert evaluation cycle alone.
- Alert resolution = primary success signal. Direct resource verification = corroborating signal. Both are recorded.
- If the alert re-fires within a configurable window after a "successful" resolution, the Case Record is retroactively downgraded and the remediation is flagged for review.
- Outcome is recorded in the Case Record with an `outcome_confidence` field (not just binary success/failure), reflecting the strength of the corroborating evidence.

#### FR-17: Rollback

An SRE can trigger rollback of a completed remediation using the rollback plan. Rollback is never automatic.

**Consequences (testable):**
- The rollback plan from FR-11 is available in the UI after execution.
- Rollback is human-triggered only — the system never initiates rollback automatically.
- A triggered rollback is recorded as a failure signal in the Learning Store.

### 4.5 Learning Store

**Description:** Every resolved incident — success or failure — is captured as a Case Record with vector embeddings in pgvector. The Learning Store is the system's long-term memory: it powers the Fast-Path bypass for known patterns, provides historical context during diagnosis, and applies temporal decay so the system naturally favors recent, version-relevant fixes. Realizes UJ-1.

**Functional Requirements:**

#### FR-18: Case Record Persistence

The system can persist a structured Case Record for every completed incident.

**Consequences (testable):**
- Each record contains: alert signature, root-cause code, full Structured Diagnosis Object, Remediation Plan, outcome (success/failure), and cluster context (OCP version, topology snapshot).
- Records are stored with vector embeddings for similarity search.
- Failed remediations are stored as negative cases with the failure reason.

#### FR-19: Temporal Decay

The system can reduce the effective confidence of older Case Records.

**Consequences (testable):**
- `effective_confidence = base_confidence × decay_factor(age) × version_relevance(OCP_version_then vs now)`.
- Fixes proven on a different OCP major version carry reduced version relevance.
- Decay parameters are configurable.

#### FR-20: Vector DB Fast-Path

The system can bypass the full LLM diagnosis pipeline when a high-similarity past success exists.

**Consequences (testable):**
- Before dispatching to the agent pipeline, the system queries pgvector for Case Records matching the current alert signature above a configurable similarity threshold.
- Only records with successful outcomes are eligible for fast-path replay.
- Fast-path remediations still pass through the Policy Gate.
- The UI indicates when a fast-path was used vs. full diagnosis.

### 4.6 User Interface

**Description:** Two UI surfaces: a standalone web application (MVP) and an OpenShift Console dynamic plugin (post-MVP). Both consume the same REST API. The standalone app works independently of console availability — critical when the cluster is degraded. Management and ops team leads access a summary dashboard for operational reporting. Realizes UJ-1, UJ-2, UJ-3.

**Functional Requirements:**

#### FR-21: Standalone Web Application

The system can provide a web-based UI for incident management, diagnosis review, and remediation approval.

**Consequences (testable):**
- Incident list view with filtering by status (active, awaiting approval, resolved, failed), severity, and time range.
- Incident detail view showing: correlated alerts, diagnosis with reasoning chain, skeptic challenge/response, remediation plan, dry-run results, and execution history.
- Approval/rejection workflow per FR-14.
- Works independently of OpenShift Console availability.

#### FR-22: Summary Dashboard

The system can present an operational summary view for management and team leads.

**Consequences (testable):**
- Displays: total incidents handled, auto-remediated vs. human-approved count, mean time to resolution, fast-path percentage, success/failure ratio.
- Filterable by time range (day, week, month). `[ASSUMPTION: these are the right time-range defaults]`
- Data is read-only — no approval or configuration actions from this view.

#### FR-23: OpenShift Console Plugin

The system can provide a Console dynamic plugin integrating key views into the native OpenShift Console experience. `[POST-MVP — SHOULD]`

**Consequences (testable):**
- Console plugin surfaces incident list, diagnosis detail, and approval workflow within the OpenShift Console.
- Plugin registers via the Console dynamic plugin API.
- All data sourced from the same REST API as the standalone app.

### 4.7 Eval Harness

**Description:** The eval harness builds trust before production auto-remediation. It validates diagnostic accuracy and remediation quality against simulated alert scenarios with known-correct answers, providing a measurable gate before extending auto-remediation trust to a domain. Realizes UJ-2.

**Functional Requirements:**

#### FR-24: Simulated Alert Injection

The system can accept simulated alert payloads for evaluation without triggering real remediation.

**Consequences (testable):**
- Simulated alerts are processed through the full diagnosis pipeline.
- Remediation plans are generated but not executed.
- Results are stored separately from production Case Records.

#### FR-25: Accuracy Measurement

The system can compare diagnosis and remediation outputs against a human-validated answer key.

**Consequences (testable):**
- Each simulated scenario includes a known-correct diagnosis (root-cause code) and expected remediation approach.
- The system scores: diagnosis accuracy (correct root-cause identification), remediation appropriateness (plan alignment with expected approach), and time-to-response.
- Results are aggregated per domain (compute, storage, network) and overall.

#### FR-26: Auto-Remediation Trust Gate

The system can gate auto-remediation enablement per domain based on eval harness results.

**Consequences (testable):**
- A domain must pass a configurable accuracy threshold on simulated scenarios before auto-remediation is enabled for that domain in the Policy Gate.
- Passing the eval harness produces a recommendation report; an SRE with appropriate permissions uses it to explicitly relax the Policy Matrix for that domain. The eval harness does not automatically change the Policy Matrix.
- The threshold and current pass rate are visible in the configuration UI.
- `[ASSUMPTION: the accuracy threshold is configured per-domain, not globally]`

### 4.8 Deployment and Configuration

**Description:** The system deploys as a single Helm chart into a dedicated namespace. No CRDs, no OLM dependency — self-contained by design, so it does not depend on cluster API machinery that may be degraded. Configuration covers LLM endpoints (per-agent), the Policy Matrix, knowledge source paths, and operational parameters. Realizes UJ-2.

**Functional Requirements:**

#### FR-27: Helm Chart Deployment

An SRE team can deploy the complete system with a single `helm install` command.

**Consequences (testable):**
- All components deploy into a single namespace: webhook receiver, agent pipeline (LangGraph runtime), PostgreSQL + pgvector, two MCP Server instances, REST API, standalone web app, and optional console plugin.
- No CRDs are installed. No OLM dependency.
- The system is functional after `helm install` with a minimal values file (LLM endpoint URL + credentials). `[ASSUMPTION: a minimal values file with LLM config is sufficient for first run]`

#### FR-28: Per-Agent LLM Configuration

An SRE team can configure different LLM endpoints, models, and parameters for each agent role.

**Consequences (testable):**
- Each agent role (orchestrator, specialists, skeptics, remediation planner) can be pointed to a different LLM endpoint with independent model selection and parameters.
- LLM endpoint configuration includes: URL, credentials, model name, temperature, and whether to use thinking/reasoning mode.
- No dependency on OpenShift AI — any compatible LLM endpoint works.

#### FR-29: LLM Resilience

The system can handle LLM unavailability gracefully.

**Consequences (testable):**
- Retry with configurable exponential backoff on transient failures.
- If all retries fail and a fast-path match exists, the system proceeds with the fast-path remediation.
- If no fast-path and no LLM: the incident is queued with a "diagnosis unavailable — LLM unreachable" status visible in the UI.
- Fallback to a secondary LLM endpoint if the primary is exhausted. `[POST-MVP — SHOULD]`

#### FR-30: Complexity-Based Model Routing

The system can dynamically route LLM requests to different models based on the estimated complexity of the diagnosis task.

**Consequences (testable):**
- Simple, well-known alert patterns (e.g., pod CrashLoopBackOff with a single clear cause) are routed to cheaper, faster models.
- Complex multi-hop failure patterns (e.g., cascading failures across subsystems) are routed to frontier models with stronger reasoning capabilities.
- Routing rules are configurable: complexity heuristics based on alert type, number of correlated alerts, and whether a partial fast-path match exists.
- The UI and audit trail record which model handled each diagnosis. `[ASSUMPTION: complexity can be estimated from alert metadata before full diagnosis begins]`

#### FR-31: Semantic Cache

The system can cache and reuse LLM responses for semantically similar queries to reduce cost and latency.

**Consequences (testable):**
- Before sending a prompt to the LLM, the system checks a semantic cache for prior responses to sufficiently similar prompts in a similar cluster context.
- Cache hits bypass the LLM call entirely and return the cached response.
- Cache entries are invalidated when the cluster state relevant to the cached diagnosis changes (e.g., OCP version upgrade, topology change).
- Cache hit rate is exposed as a Prometheus metric. `[ASSUMPTION: embedding-based similarity with a configurable threshold is sufficient for cache matching]`

#### FR-32: Policy Matrix Configuration

An SRE team can configure the auto-remediation policy matrix via Helm values or runtime API.

**Consequences (testable):**
- The three-dimensional matrix (severity × blast radius × confidence) is fully configurable.
- Default configuration requires human approval for all remediations (most conservative).
- Changes to the policy matrix are logged in the audit trail.

### 4.9 REST API

**Description:** The REST API is the single contract between the backend pipeline and all UI surfaces (standalone web app, console plugin). It exposes incident lifecycle, diagnosis artifacts, remediation plans, approval workflows, configuration, and audit data. Both the standalone app and the console plugin consume this API exclusively — no direct database access from UI components. Realizes UJ-1, UJ-2, UJ-3.

**Functional Requirements:**

#### FR-33: REST API

The system can expose a versioned REST API serving all data and actions required by the UI surfaces.

**Consequences (testable):**
- API provides CRUD access to: incidents (list, detail, filter), diagnoses, remediation plans, approval actions, policy matrix configuration, eval harness results, and summary dashboard aggregations.
- API enforces authentication and authorization. `[ASSUMPTION: API authentication uses OpenShift OAuth/service account tokens]`
- API is versioned to support independent UI and backend evolution.
- All state-changing operations (approvals, policy changes) are audit-logged.

## 5. Non-Goals (Explicit)

- **Application-layer diagnosis.** The tool diagnoses cluster infrastructure problems (nodes, storage, networking, platform services). It does not diagnose application-level bugs, performance issues, or business logic failures.
- **Multi-cluster management.** V1 operates on a single cluster. Cross-cluster aggregation, federated learning, and fleet-wide views are deferred.
- **Predictive alerting from raw metrics.** The system responds to alerts, not raw metrics. Post-hoc PrometheusRule proposals (suggesting alerts for patterns the system learned) are a future COULD.
- **Replacing AlertManager or monitoring stack.** The tool is a downstream consumer of alerts. It does not replace Prometheus, AlertManager, Grafana, or any existing monitoring infrastructure.
- **Automatic rollback.** Rollback is always human-triggered. The system does not autonomously decide that a remediation made things worse and roll back.
- **Custom CRD-based API.** The system deliberately avoids CRDs to maintain independence from the cluster's API machinery.

## 6. MVP Scope

### 6.1 In Scope

- Helm chart deployment (PostgreSQL + pgvector, REST API, webhook receiver, agent pipeline, MCP Server instances, standalone web app)
- AlertManager webhook integration with priority queue, deduplication, and correlation
- Orchestrator/generalist agent with completeness gate (handles all domains initially)
- Structured diagnosis with root-cause taxonomy and confidence scoring
- Knowledge integration: OpenShift runbooks + RHOKP + agentic skills (as callable tools) + Learning Store
- Adversarial skeptic for both diagnosis and remediation (1-round protocol)
- Remediation planner with structured plans (steps, blast radius, rollback, risk, preconditions)
- Dry-run pre-flight validation (`--dry-run=server`, admission checks, RBAC/quota)
- Policy gate: severity × blast_radius × confidence matrix (default: all-human-approval)
- Serialized execution with global lock and configurable cooldown
- Outcome observation: alert resolved = success
- Human approval workflow in standalone web UI
- Learning store: success/failure Case Records with temporal decay
- Vector DB fast-path: bypass LLM for known successful patterns via pgvector similarity
- Per-agent LLM configuration (URL, credentials, model, parameters)
- Complexity-based model routing (cheaper models for simple alerts, frontier for complex)
- Semantic cache for LLM response reuse on similar queries
- Evidence artifacts required for auto-execution (concrete log lines, metric values, resource states supporting the diagnosis)
- LLM retry with configurable exponential backoff
- Versioned REST API serving all UI surfaces
- Standalone web UI (incidents, diagnosis, remediation, approval, summary dashboard)
- LangGraph runtime with PostgreSQL checkpoint persistence
- Two OpenShift MCP Server instances (read-only for diagnosis, read-write for remediation)
- Eval harness: simulated alert injection, response validation, accuracy measurement, domain-level auto-remediation trust gating
- Full audit trail via LangGraph checkpoints + PostgreSQL event log

### 6.2 Out of Scope for MVP

- **Domain specialist agents with self-selection** — deferred to post-MVP. Orchestrator handles all domains as generalist initially. `[NOTE FOR PM: this is the highest-value post-MVP item — unlocks domain depth]`
- **OpenShift Console dynamic plugin** — deferred to post-MVP. Standalone web app is the only UI surface at launch.
- **LLM fallback to secondary endpoint** — deferred to post-MVP. Basic retry-with-backoff is MVP; multi-endpoint failover is not.
- **Confidence boost from repeated success** — deferred to post-MVP. Temporal decay (downward) is MVP; upward reinforcement when a fix succeeds repeatedly is not.
- **Human correction feedback loop** — future. When an SRE overrides or edits a diagnosis, the correction feeds back into the Learning Store as a high-quality training signal, improving future diagnoses for similar alerts.
- **Prevention backlog generation** — future. Auto-remediated incidents optionally generate a follow-up item (e.g., "investigate why this StorageClass keeps misconfiguring after upgrades") because recovery is not resolution — recurring alerts signal upstream problems.
- **Alert hygiene recommendations** — future. The tool identifies noisy or non-actionable alerts (fire frequently, never lead to actionable diagnosis) and recommends tuning or deleting them.
- **AI outage drills** — future. Operational tooling and documentation for teams to simulate the tool being unavailable, ensuring SREs retain manual diagnostic skills and preventing automation complacency.
- **PrometheusRule proposal generation** — future.
- **Knowledge graph of cluster-specific causal chains** — future.
- **Cross-cluster federated learning** — deferred indefinitely.
- **Multi-cluster metrics aggregation** — deferred indefinitely.

## 7. Cross-Cutting NFRs

### 7.1 Security

- The RBAC Airlock is mandatory: diagnosis agents access the cluster via the read-only MCP Server instance (bound to `cluster-reader` ServiceAccount); remediation executes via the read-write instance. No cross-access.
- The read-only MCP Server instance is launched with the `--read-only` flag as defense-in-depth alongside RBAC.
- The remediation ServiceAccount must follow least-privilege principles: scoped to the specific operations the remediation planner can produce (e.g., patch deployments/statefulsets, cordon/drain nodes, delete pods, patch StorageClasses), not blanket `cluster-admin`. The exact permission set and whether `cluster-admin` is available as an opt-in override is an architecture decision. `[NOTE FOR PM: the SA permission model is the single highest-friction point for SRE team adoption — architecture must resolve this before implementation]`
- Diagnosis-side agentic skills (FR-6) are restricted to read-only operations, enforced by the `cluster-reader` ServiceAccount binding. Skills that require write access are classified as remediation-only and are not available during diagnosis.
- All remediation actions are audit-logged with: who approved (human or auto-policy), what was executed, when, and the outcome.
- LLM credentials are stored as Kubernetes Secrets, not in Helm values directly. `[ASSUMPTION: standard Secret management is sufficient; no external secret store integration in v1]`

### 7.2 Reliability

- LangGraph checkpoints are persisted to PostgreSQL. Agent workflows resume from the last checkpoint on pod restart.
- The Priority Queue survives pod restarts (persisted to PostgreSQL, not in-memory).
- The system degrades gracefully when the cluster is partially degraded: diagnosis agents work with partial data from the MCP Server (timeouts handled, not fatal).

### 7.3 Performance

- Alert intake (webhook receipt to queue insertion) completes within 1 second under normal load. `[ASSUMPTION: 1s is an appropriate target]`
- The system handles alert storms of up to 100 simultaneous alerts without dropping events. `[ASSUMPTION: 100 is a reasonable storm ceiling for a single cluster]`
- Configurable parallelism cap on concurrent diagnosis pipelines prevents resource exhaustion.
- The Learning Store scales to thousands-to-millions of Case Records without degrading similarity search performance. `[ASSUMPTION: pgvector with appropriate indexing (IVFFlat or HNSW) meets this at the expected scale]`

### 7.4 Observability

- The system exposes Prometheus metrics for: alert intake rate, queue depth, diagnosis latency, remediation execution count, fast-path hit rate, LLM call latency, and error rates.
- Structured logging (JSON) for all pipeline stages.
- LangGraph execution traces are queryable for debugging.

## 8. Constraints and Guardrails

### 8.1 Operational Safety

- **Serialized remediation.** One remediation at a time, globally. No concurrent cluster modifications.
- **Cooldown between remediations.** Configurable pause between consecutive executions lets cluster state settle and allows cascading fixes to resolve secondary alerts.
- **No automatic rollback.** Rollback is a human judgment call. Triggered rollback is stored as a failure signal.
- **Default-deny policy.** The default Policy Matrix requires human approval for all remediations. Auto-execution must be explicitly enabled per severity/blast-radius/confidence combination.

### 8.2 Self-Containment

- **No CRDs.** The system does not install Custom Resource Definitions. It does not depend on the cluster's API extension machinery.
- **No OLM dependency.** Deployed via Helm, not as an operator managed by OLM.
- **Self-contained persistence.** PostgreSQL runs within the Helm deployment. However, as an in-cluster component, PostgreSQL is subject to the same failure modes as other cluster workloads. The tool survives: individual node failures (PostgreSQL pod reschedules), API server latency/intermittent errors (MCP Server handles timeouts), and degradation of specific subsystems (storage, networking) that don't affect the tool's own namespace. The tool does **not** survive: full control plane unavailability (scheduler cannot reschedule pods), loss of the tool's own PVC (database inaccessible), or total cluster network partition. During these scenarios, the tool's last-known state is preserved via PostgreSQL WAL and LangGraph checkpoints for recovery once the cluster stabilizes.

## 9. Integration and Dependencies

| Integration Point | Direction | Protocol | Dependency Type |
|-------------------|-----------|----------|-----------------|
| AlertManager | IN | HTTP POST (webhook) | Required — primary input |
| OpenShift MCP Server (read-only) | OUT | MCP over stdio/SSE | Required — cluster state queries |
| OpenShift MCP Server (read-write) | OUT | MCP over stdio/SSE | Required — remediation execution |
| LLM endpoint(s) | OUT | HTTP (vendor-specific) | Required — agent inference |
| OpenShift runbooks repo | Build-time / startup | Git clone or bundled | Required — diagnostic knowledge |
| RHOKP | OUT | Search API or bundled | Required (pending integration validation) — platform knowledge. If no search API is available, fallback to bundled/cached knowledge set. `[ASSUMPTION: RHOKP has a search API accessible from within the cluster]` |
| OpenShift Console | OUT | Dynamic plugin API | Optional (post-MVP) |
| Prometheus | OUT | Metrics endpoint | Optional — system observability |

## 10. Success Metrics

**Primary**

- **SM-1: Diagnosis Accuracy** — Percentage of correct root-cause identifications as validated by the eval harness and confirmed by human review of production incidents. Target: 90%. Validates FR-4, FR-5, FR-6, FR-7.
- **SM-2: Mean Time to Resolution (MTTR)** — Average elapsed time from alert firing to alert resolution for incidents handled by the tool. Measured against pre-tool baseline. Validates FR-1 through FR-16.
- **SM-3: Fleet Adoption** — Percentage of OpenShift clusters in the fleet with OpenShift AI Ops deployed and actively processing alerts. Target: 100% within 12 months. Validates FR-27, FR-28, FR-30.
- **SM-4: Trust Progression** — At least one SRE team trusts the tool for auto-remediation on some alert categories within 6 months of deployment. Validates FR-13, FR-24, FR-25, FR-26.

**Secondary**

- **SM-5: Learning Velocity** — Percentage of incidents resolved via fast-path (no LLM call) trends upward over time. Validates FR-18, FR-19, FR-20.
- **SM-6: Alert Coverage** — Percentage of distinct alert types that the system can diagnose and propose remediation for. `[ASSUMPTION: tracking distinct alert type coverage is feasible via the root-cause taxonomy]`

**Counter-metrics (do not optimize)**

- **SM-C1: False Auto-Remediation Rate** — Percentage of auto-executed remediations that fail or require rollback. Must not increase as the policy matrix is relaxed. Counterbalances SM-2, SM-4.
- **SM-C2: Alert Resolution Without Action** — Percentage of alerts that resolve before the tool acts (false positives or self-healing). High values may indicate the tool is processing alerts that don't need intervention. Counterbalances SM-2.

## 11. Risk and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Bad remediation damages cluster | High | Policy matrix gates risky actions; serialized execution with cooldown; adversarial skeptic; rollback plans (human-triggered); dry-run pre-flight validation |
| Over-trust in AI decisions | High | Eval harness validates before production trust; incremental policy opening; all actions auditable; default-deny policy |
| LLM unavailability | Medium | Retry with exponential backoff; fast-path for known cases works without LLM; graceful degradation with clear status in UI; fallback endpoint (post-MVP) |
| Diagnosis hallucination | Medium | Structured output with taxonomy (not free-text); adversarial challenge; confidence scoring; past-case matching |
| Adoption resistance — SREs don't trust AI | Medium | Start human-in-the-loop only; demonstrate value through accurate diagnosis before offering auto-remediation; transparent reasoning in UI; eval harness proves competence |
| Cluster degradation impairs the tool | Medium | No CRD dependency; self-contained PostgreSQL; MCP Server timeouts handled gracefully; diagnosis degrades to partial data, not failure |
| Knowledge staleness | Low | Temporal decay reduces confidence on old Case Records; version relevance weighting; periodic runbook/RHOKP refresh |

## 12. Rollout and Adoption

- **Default-safe deployment.** Out of the box, all remediations require human approval. No team deploys this and gets surprised by autonomous changes.
- **Self-serve installation.** SRE teams deploy via `helm install` with a values file. Documentation covers: LLM endpoint setup, AlertManager webhook configuration, policy matrix tuning. No dedicated onboarding team required.
- **Trust escalation path.** Teams start in full HITL mode → run the eval harness → observe diagnosis accuracy on production alerts → progressively relax the policy matrix for low-risk categories → expand to higher-risk categories as confidence builds.
- **Fleet target.** 100% of OpenShift clusters in the fleet within 12 months. `[ASSUMPTION: "fleet" refers to all clusters managed by the organization deploying the tool, not a public marketplace]`

## 13. Open Questions

1. **RHOKP integration mechanism.** Does RHOKP expose a search API accessible from within the cluster, or does it require a bundled/cached knowledge set? This affects FR-6 and the Integration table.
2. **Eval harness scenario library.** Who creates and maintains the simulated alert scenarios and known-correct answer keys? Is there an existing corpus, or does this need to be built from scratch?
3. **LLM endpoint requirements.** What are the minimum model capabilities required (context window, tool use, structured output)? Does the tool work with smaller/cheaper models for some agent roles?
4. **Multi-tenancy.** If multiple teams share a cluster, does the tool need namespace-scoped views or permissions? Or is it always cluster-admin-scoped?
5. **Upgrade path.** How does the tool upgrade on clusters where it's already deployed and has accumulated Case Records? Helm upgrade with data migration?
6. **Runbook and RHOKP refresh cadence.** How often are knowledge sources updated? Is this a manual process or automated?
7. **MTTR baseline.** What is the current pre-tool MTTR for the target fleet? Needed to set a meaningful reduction target for SM-2.

## 14. Assumptions Index

- **§4.1 FR-1** — 500ms webhook acknowledgment SLA is appropriate for AlertManager integration.
- **§4.1 FR-2** — Label intersection, temporal proximity, and Learning Store cascade patterns are sufficient correlation dimensions for MVP.
- **§4.6 FR-22** — Day/week/month are the right default time-range filters for the summary dashboard.
- **§4.7 FR-26** — The eval harness accuracy threshold is configured per-domain, not globally.
- **§4.8 FR-27** — A minimal values file with LLM configuration is sufficient for first functional deployment.
- **§4.4 FR-14** — Minimum review time is a useful safety mechanism for high-blast-radius actions; can be disabled by teams who find it counterproductive.
- **§4.8 FR-30** — Complexity can be estimated from alert metadata before full diagnosis begins.
- **§4.8 FR-31** — Embedding-based similarity with a configurable threshold is sufficient for semantic cache matching.
- **§4.9 FR-33** — API authentication uses OpenShift OAuth/service account tokens.
- **§7.1** — Standard Kubernetes Secret management is sufficient for LLM credentials in v1; no external secret store integration needed.
- **§7.3** — 1-second intake latency and 100-alert storm ceiling are appropriate performance targets.
- **§7.3** — pgvector with appropriate indexing (IVFFlat or HNSW) meets the thousands-to-millions scale target for the Learning Store.
- **§9** — RHOKP has a search API accessible from within the cluster.
- **§10 SM-6** — Tracking distinct alert type coverage is feasible via the root-cause taxonomy.
- **§12** — "Fleet" refers to all clusters managed by the deploying organization, not a public marketplace.
