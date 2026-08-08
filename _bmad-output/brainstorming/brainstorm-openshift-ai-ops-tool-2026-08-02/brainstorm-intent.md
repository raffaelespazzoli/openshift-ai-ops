# Brainstorm Intent — OpenShift AI Ops

## Product Identity

**One-liner:** OpenShift AI Ops for practitioners — an alert-driven co-pilot that diagnoses, remediates, and learns from every cluster incident.

A Helm-deployed, self-contained AI operations tool that watches AlertManager webhooks, orchestrates multi-agent diagnosis with adversarial validation, executes policy-gated remediation, and stores outcomes in a vector-enabled knowledge base. It gets faster, cheaper, and more decisive with every incident it handles.

## Core Problem

OpenShift cluster operators respond to alerts manually — interpreting symptoms, running commands, cross-referencing runbooks, and applying fixes under pressure. This is slow, error-prone, and doesn't scale. Institutional knowledge lives in people's heads. The same failures repeat without systematic learning.

## Key Architectural Decisions

- **Deployment:** Helm chart, fully self-contained. No CRDs — avoids depending on the cluster API machinery you're healing.
- **Agent framework:** LangGraph — stateful graph execution, native human-in-the-loop (interrupt/resume), checkpoint persistence (survives pod restarts), full audit trail.
- **Persistence:** PostgreSQL + pgvector extension for both structured data (incidents, config, audit) and vector embeddings (case records, knowledge retrieval). Single component.
- **Cluster interaction:** Official OpenShift MCP Server (Go-native, direct K8s API, RBAC-respecting). Two instances: read-only (diagnosis) and read-write (remediation). Security boundary at infrastructure level.
- **LLM:** External, configurable URL + credentials per agent. Supports different models/parameters per agent role. Retry + fallback endpoint.
- **UI:** OpenShift Console extension plugin + standalone web app, both backed by the tool's own API layer.

## Agent Pipeline

1. **Webhook Intake** — AlertManager fires/resolved webhooks received; priority queue (urgency x recency); dedup via status tracking + TTL expiry.
2. **Triage Coral** — Stateless filter deduplicates alert storms, correlates related alerts into single root-cause events, prevents agent drowning during cascades.
3. **Vector DB Fast-Path** — If past case matches above similarity threshold with success outcome, skip full LLM diagnosis; replay proven remediation. Default behavior.
4. **Diagnosis Orchestrator** — Routes to domain specialists (compute, storage, network, extensible) or handles simple alerts solo. Holds session state, resolves conflicts, enforces completeness gate.
5. **Domain Specialists** — Self-selecting via label-matching (SWARM model). Access domain-specific runbooks, RHOKP, vector DB. Return structured diagnosis with confidence level. Unclaimed alerts fall to orchestrator as generalist.
6. **Adversarial Skeptic (Diagnosis)** — One challenge round. If diagnosis holds → pass. If fundamentally changed → re-challenge new diagnosis. Stability = acceptance.
7. **Remediation Planner** — Single agent receives immutable diagnosis artifact. Produces structured plan: steps, blast_radius, rollback_plan, estimated_risk, preconditions.
8. **Dry-Run Pre-Flight** — `--dry-run=server`, admission webhook validation, RBAC/quota checks. Always executes before human review.
9. **Adversarial Skeptic (Remediation)** — Same one-round challenge rule.
10. **Policy Gate** — Auto-execute or require human approval per configurable matrix: severity × blast_radius × diagnosis_confidence.
11. **Execution** — Serialized (global lock), configurable cooldown between remediations. Success = original alert resolves.
12. **Learning Store** — Case record written to pgvector: alert signature, root-cause code, structured diagnosis, remediation plan, outcome (success/failure), cluster context. Failures stored to avoid repetition.

## Key Design Principles

- **Don't depend on the patient you're healing** — No CRDs, no OLM, self-contained data store. If cluster API machinery is broken, the tool still functions.
- **Serialized remediation with cooldown** — One remediation at a time, pause between interventions to let cluster state settle. Prevents conflicting actions.
- **Structured diagnosis with root-cause taxonomy** — Schema-enforced objects (root_cause_component, failure_mode, causal_chain, affected_resources). Deterministic diff for same-vs-different comparison.
- **Vector DB fast-path as default** — Past successes bypass LLM entirely. LLM is fallback for novel failures. System gets cheaper over time.
- **One-round skeptic challenge with stability check** — No infinite debate loops. Diagnosis must survive one challenge unchanged to proceed.
- **Temporal decay on knowledge confidence** — Older solutions carry less confidence. System naturally favors recent fixes over stale ones.
- **Rollback is never automatic** — Human-triggered only. A triggered rollback is a clear failure signal stored as negative case.

## MoSCoW Scope

| Priority | Count | Examples |
|----------|-------|---------|
| **MUST** | 17 | Webhook intake, triage coral, diagnosis orchestrator, remediation planner, skeptic agents, policy gate, learning store, PostgreSQL+pgvector, Helm deployment, standalone UI, MCP Server integration |
| **SHOULD** | 7 | Domain specialists, vector DB fast-path, dry-run pre-flight, console plugin, LLM retry/fallback, SWARM self-selection, priority queue |
| **COULD** | 4 | PrometheusRule proposals, knowledge graph (causal map), confidence boost from repeated success, version-aware decay |
| **WON'T** | 2 | Cross-cluster federated learning, multi-cluster aggregation |

## Knowledge Sources

- **Runbooks repository** — Operational playbooks indexed for retrieval by alert type
- **RHOKP** (Red Hat OpenShift Knowledge Pack) — Platform-level guidance and failure patterns
- **Agentic-skills repositories** — Domain-specific command sequences and diagnostic procedures
- **Vector DB (pgvector)** — Accumulated case records of past incidents, diagnoses, and outcomes with temporal confidence weighting

## Future Roadmap

**COULDs:** Predictive alerting — post-hoc identification of metric trends that caused incidents, proposing new PrometheusRules to intercept next time. Knowledge graph mapping cluster-specific causal failure chains over time.

**WON'Ts (deferred):** Cross-cluster federated learning (requires metrics aggregation layer not in scope). Multi-cluster management aggregation.
