---
title: "Addendum: OpenShift AI Ops"
created: 2026-08-02
updated: 2026-08-02
---

# Addendum: OpenShift AI Ops

Detailed technical specifications supporting the OpenShift AI Ops product brief. Reference material for downstream PRD, architecture spec, and solution design.

## Agent Pipeline Detail

The full pipeline, with each stage's responsibilities:

1. **Webhook Intake** — AlertManager firing/resolved webhooks. Priority queue ordered by urgency x recency. Dedup via status tracking ("already triaging this alert").
2. **TTL Cleanup** — AlertManager sends `resolved` webhooks for instant dequeue. TTL-based expiry as safety net (if no renewal within configurable window, verify via AM API and remove).
3. **Vector DB Fast-Path** — If a past case matches above a configurable similarity threshold with a successful outcome, skip LLM diagnosis entirely and replay proven remediation.
4. **Self-Selecting Specialists** — Each specialist has label-matching rules. If alert labels match their domain, they claim it (binary claim, no confidence score on the claim). Multiple specialists can claim the same alert.
5. **Orchestrator Roles** — (a) Dispatch/synthesis for multi-specialist alerts, (b) Generalist of last resort for unclaimed alerts, (c) Gap detection — flags "no specialist covers this" in the UI.
6. **Structured Diagnosis Object** — Schema: `{root_cause_component, failure_mode, causal_chain: [...], affected_resources: [...]}`. Root-cause code from controlled taxonomy (e.g., `node/memory-pressure`, `network/dns-failure`, `storage/pvc-stuck-pending`).
7. **Diagnosis Comparison** — Same-vs-different determined by root-cause hash (deterministic field diff). Embedding distance as fallback for novel failures not yet in taxonomy.
8. **Skeptic Protocol** — One challenge round. If root-cause hash unchanged after challenge → pass. If fundamentally changed → re-challenge the new diagnosis. No infinite loops.
9. **RBAC Airlock** — Diagnosis output is an immutable artifact handed to remediation planner. Remediation agent cannot re-diagnose or re-interpret — takes root-cause code and causal chain as given.
10. **Remediation Plan Schema** — `{steps: [...], blast_radius: workload|namespace|node|cluster, rollback_plan: [...], estimated_risk, preconditions}`.
11. **Dry-Run** — `oc apply --dry-run=server`, admission webhook validation, RBAC checks, quota checks. Always runs before human review.
12. **Policy Matrix** — Three dimensions: severity (enum from AlertManager) x blast_radius (workload|namespace|node|cluster) x diagnosis confidence (0-1). User-configurable thresholds.
13. **Execution Constraints** — Global lock (one remediation at a time). Configurable cooldown between remediations. After cooldown, queued alerts may have auto-resolved (cascade fix).
14. **Rollback Policy** — Included in plan when feasible. Never automatic — human-triggered only. Triggered rollback = failure signal stored in vector DB.
15. **Learning Record Schema** — Alert signature, root-cause code + structured diagnosis, remediation plan, outcome (success|failure), cluster context (version, topology). Temporal decay: `effective_confidence = base_confidence * decay_factor(age) * version_relevance(OCP version then vs now)`.

## Knowledge Sources Detail

| Source | Purpose | Integration |
|--------|---------|-------------|
| [openshift/runbooks](https://github.com/openshift/runbooks/tree/master/alerts) | Operational playbooks indexed by alert type | RAG retrieval during diagnosis |
| [Red Hat Offline Knowledge Portal](https://access.redhat.com/products/red-hat-offline-knowledge-portal/) | Platform-level guidance, KBase articles, CVEs | Search during diagnosis |
| [openshift/agentic-skills](https://github.com/openshift/agentic-skills/tree/main) | Domain-specific command sequences (cluster-update, find-token) | Loaded as specialist tools |
| [pramodmax/openshift-ai-skills](https://github.com/pramodmax/openshift-ai-skills) | RHOAI platform, inference optimization, governance expertise | Knowledge augmentation |
| Vector DB (pgvector) | Accumulated case records with temporal decay | Primary knowledge for known patterns |

## OpenShift MCP Server Integration

The official [OpenShift MCP Server](https://github.com/openshift/openshift-mcp-server) (Go-native, direct K8s API, no kubectl dependency) is deployed as two in-cluster instances:

- **Read-only instance:** Bound to `cluster-reader` ServiceAccount. Used by all agents during diagnosis. `--read-only` flag as defense-in-depth alongside RBAC.
- **Read-write instance:** Bound to `cluster-admin` ServiceAccount. Used exclusively by the remediation executor. Only accessible after policy gate approval.

Both instances deployed via the MCP lifecycle operator, providing health checks, pod security (restricted PSS), and service discovery.

## Eval Harness Concept

To build trust safely before production auto-remediation:

- Simulate real alerts by injecting webhook payloads matching known scenarios
- Record the tool's diagnosis and proposed remediation without executing
- Compare against known-correct responses (human-validated answer key)
- Measure: diagnosis accuracy, remediation appropriateness, time-to-response
- Gate: a domain must pass X% accuracy on simulated scenarios before auto-remediation is enabled for that domain

## Design Philosophy

- **"Don't depend on the patient you're trying to heal"** — drove the no-CRD, self-contained architecture
- **"The alert is why we're here, so its absence is victory"** — simple success signal
- **"The LLM is the fallback, not the hot path"** — vector DB fast-path by default
- **"Serialize and pause"** — one remediation at a time with cooldown, no complex locking
- **"Rollback is a failure signal"** — human-triggered only, stored as negative case

## Rejected Alternatives

- **CRD/Operator model:** Rejected because depending on Kubernetes API machinery to heal Kubernetes is circular — if the API server is degraded, CRD watches break.
- **Predictive alerting from raw metrics:** Rejected for MVP — 5k+ metric types make combinatorial prediction intractable. Instead: learn post-hoc and propose PrometheusRules.
- **Qdrant as vector DB:** Replaced by pgvector — one fewer component since PostgreSQL is already required for structured data.
- **Claim confidence on specialists:** Dropped — binary claim/no-claim via label matching is sufficient; diagnosis confidence is the real signal.
- **Automatic rollback:** Rejected — "worse" is too hard to measure objectively beyond alert resolution; human judgment needed.
