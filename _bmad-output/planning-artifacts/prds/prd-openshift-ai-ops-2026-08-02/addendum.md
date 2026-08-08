---
title: "Addendum: OpenShift AI Ops PRD"
created: 2026-08-02
updated: 2026-08-02
---

# Addendum: OpenShift AI Ops PRD

Technical depth and implementation-level detail from the brainstorm and product brief that belong in downstream architecture, solution design, or UX specifications. Referenced by the PRD but not duplicated there.

## Tech Stack Decisions (for Architecture Spec)

| Component | Technology | Rationale |
|---|---|---|
| Agent framework | LangGraph | Stateful graphs, native HITL interrupt/resume, checkpoint persistence to PostgreSQL, full audit trail |
| Database | PostgreSQL + pgvector | Single store for structured data, vector embeddings, and LangGraph checkpoints — eliminates a separate vector DB component |
| Cluster access | OpenShift MCP Server (official, Go-native) | Direct K8s API, no kubectl dependency, RBAC-respecting, supports `--read-only` mode, bearer token auth |
| Deployment | Helm chart | Avoids CRD dependency on the cluster being healed; self-contained; single `helm install` |
| UI (standalone) | React web application | Works independently of console availability |
| UI (integrated) | OpenShift Console dynamic plugin | Native experience for console users (post-MVP) |
| LLM integration | Configurable HTTP endpoints | Per-agent model selection, supports thinking mode, vendor-agnostic |

## Rejected Alternatives

- **CRD/Operator model:** Depending on Kubernetes API machinery to heal Kubernetes is circular — if the API server is degraded, CRD watches break. Helm chart avoids this.
- **Predictive alerting from raw metrics:** 5k+ metric types make combinatorial prediction intractable for MVP. Instead: learn post-hoc and propose PrometheusRules (future COULD).
- **Qdrant as vector DB:** Replaced by pgvector — one fewer component since PostgreSQL is already required for structured data and LangGraph checkpoints.
- **Claim confidence on specialists:** Dropped — binary claim/no-claim via label matching is sufficient; diagnosis confidence is the meaningful signal.
- **Automatic rollback:** "Worse" is too hard to measure objectively beyond alert resolution; human judgment needed. Triggered rollback stored as negative case.

## Knowledge Sources Detail (for Architecture Spec)

| Source | Purpose | Integration Pattern |
|---|---|---|
| [openshift/runbooks](https://github.com/openshift/runbooks/tree/master/alerts) | Operational playbooks indexed by alert type | RAG retrieval during diagnosis |
| [Red Hat Offline Knowledge Portal](https://access.redhat.com/products/red-hat-offline-knowledge-portal/) | Platform-level guidance, KBase articles, CVEs | Search during diagnosis |
| [openshift/agentic-skills](https://github.com/openshift/agentic-skills/tree/main) | Domain-specific command sequences (cluster-update, find-token) | Loaded as specialist tools |
| [pramodmax/openshift-ai-skills](https://github.com/pramodmax/openshift-ai-skills) | RHOAI platform, inference optimization, governance expertise | Knowledge augmentation |
| pgvector Learning Store | Accumulated case records with temporal decay | Primary knowledge for known patterns |

## Structured Schema Detail (for Architecture Spec)

**Diagnosis Object:**
```json
{
  "root_cause_component": "storage",
  "failure_mode": "pvc-stuck-pending",
  "root_cause_code": "storage/pvc-stuck-pending",
  "causal_chain": ["StorageClass misconfigured after upgrade", "Provisioner cannot bind PV", "PVC remains Pending"],
  "affected_resources": ["pvc/data-volume-0", "storageclass/gp3-csi"],
  "confidence": 0.87
}
```

**Remediation Plan:**
```json
{
  "steps": ["Patch StorageClass parameters", "Delete stuck PVC to trigger re-bind", "Verify new PVC binds within 60s"],
  "blast_radius": "workload",
  "rollback_plan": ["Restore original StorageClass parameters", "Recreate PVC with original spec"],
  "estimated_risk": "low",
  "preconditions": ["cluster-admin SA has patch permission on StorageClass", "No other PVCs bound to this StorageClass are in use"]
}
```

**Case Record:**
```json
{
  "alert_signature": "KubePersistentVolumeFillingUp",
  "root_cause_code": "storage/pvc-stuck-pending",
  "diagnosis": { "...full diagnosis object..." },
  "remediation_plan": { "...full plan..." },
  "outcome": "success",
  "cluster_context": { "ocp_version": "4.16.2", "topology": "3-master-6-worker" },
  "effective_confidence": 0.87,
  "created_at": "2026-08-02T14:30:00Z"
}
```

## Policy Matrix Example (for Architecture Spec)

Example post-trust-escalation configuration — **not the shipping default**. The PRD specifies that the shipping default requires human approval for all remediations (all-approval matrix). This example illustrates a configuration an SRE team might adopt after running the eval harness and observing production accuracy:

| | blast: workload | blast: namespace | blast: node | blast: cluster |
|---|---|---|---|---|
| sev: low + high conf | auto | auto | approval | approval |
| sev: high + high conf | auto | approval | approval | approval |
| sev: any + low conf | approval | approval | approval | approval |

## Temporal Decay Formula (for Architecture Spec)

```
effective_confidence = base_confidence × decay_factor(age) × version_relevance(OCP_version_then, OCP_version_now)
```

- `decay_factor(age)`: configurable decay curve (e.g., exponential with half-life of 90 days)
- `version_relevance`: reduces confidence when the OCP version has changed significantly (e.g., 4.14 → 4.16 carries less relevance than 4.16.1 → 4.16.2)

## MCP Server Deployment Detail (for Architecture Spec)

Two separate OpenShift MCP Server deployments:

- **Read-only instance:** Bound to `cluster-reader` ServiceAccount. `--read-only` flag as defense-in-depth alongside RBAC. Used by all diagnosis agents.
- **Read-write instance:** Bound to `cluster-admin` ServiceAccount. Used exclusively by the remediation executor. Only reachable after policy gate approval.

Both deployed within the Helm chart's namespace. The product brief specifies deployment via the MCP lifecycle operator, providing health checks, pod security (restricted Pod Security Standard), and service discovery. The MCP Server natively supports multi-cluster configurations — a future enabler for cross-cluster features, though out of scope for v1.

## Confidence Boost (Post-MVP COULD)

The inverse of temporal decay: when a Case Record's remediation succeeds repeatedly across multiple incidents, its effective confidence should increase — reinforcing proven fixes. MVP includes only temporal decay (downward pressure); confidence boost (upward reinforcement from repeated success) is deferred to post-MVP as a COULD. The architecture spec should define a Case Record schema that accommodates bidirectional confidence adjustment.

## Eval Harness Design (for Architecture Spec)

- Simulate real alerts by injecting webhook payloads matching known scenarios
- Record the tool's diagnosis and proposed remediation without executing
- Compare against known-correct responses (human-validated answer key)
- Measure: diagnosis accuracy, remediation appropriateness, time-to-response
- Gate: a domain must pass configurable accuracy threshold on simulated scenarios before auto-remediation is enabled for that domain

## Competitive Landscape (for Positioning)

**Commercial platforms:** Dynatrace Davis AI (causal AI, strong diagnosis, weak on active remediation, SaaS-only), PagerDuty AIOps (alert noise suppression and triage routing, not a diagnostic engine), Shoreline.io/Kubiya (autonomous remediation agents, generic Kubernetes, no OpenShift awareness), Plural (self-hosted fleet management with causal AI, newer entrant).

**Red Hat's own:** OpenShift Lightspeed (console GenAI assistant, conversational, no closed-loop remediation), Red Hat Insights (predictive analytics, rule-based not agentic), OpenShift AI Observability Summarizer (metric summarization for AI workloads, read-only), OpenShift MCP Server (infrastructure enabling agentic workflows, not a product).

**Open-source:** K8sGPT (CNCF Sandbox, CLI scanner, reactive ask-and-answer), Robusta + HolmesGPT (CNCF, closest OSS analog — intercepts AlertManager alerts, runs multi-step investigations), Scorching AIOps (multi-agent with LangGraph + Neo4j, early-stage), RocketplaneIO (self-hosted AI SRE with eBPF, air-gap capable), Tagent (autonomous Night Guardian mode, on-cluster).

**Whitespace OpenShift AI Ops fills:** No existing tool reasons natively about OpenShift-specific abstractions (ClusterVersion, MachineConfigPool, OLM/operator lifecycle, Routes, SCCs), operator health diagnosis (CSV failures, InstallPlan issues), RHEL CoreOS node issues (MachineConfig drift, ostree/bootc), upgrade path intelligence (channel/version graph, EUS-to-EUS), or platform-aware remediation (drain vs. cordon, MachineConfigPool rollback, operator vs. operand restart). The gap is a tool combining deep OpenShift domain knowledge with closed-loop, safety-gated diagnosis and remediation.

## Design Philosophy (Reference)

- **"Don't depend on the patient you're trying to heal"** — drove the no-CRD, self-contained architecture
- **"The alert is why we're here, so its absence is victory"** — simple success signal
- **"The LLM is the fallback, not the hot path"** — vector DB fast-path by default
- **"Serialize and pause"** — one remediation at a time with cooldown, no complex locking
- **"Rollback is a failure signal"** — human-triggered only, stored as negative case
