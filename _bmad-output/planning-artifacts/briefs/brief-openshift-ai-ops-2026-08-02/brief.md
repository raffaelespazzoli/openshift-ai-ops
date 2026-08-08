---
title: "Product Brief: OpenShift AI Ops"
status: draft
created: 2026-08-02
updated: 2026-08-02
---

# Product Brief: OpenShift AI Ops

## Executive Summary

OpenShift AI Ops is a self-contained AI operations tool purpose-built for OpenShift clusters. It listens to AlertManager, diagnoses root causes through multi-agent collaboration with adversarial validation, proposes remediations with configurable auto-execution, and learns from every incident it handles.

The tool is designed for the practitioners who actually run clusters — SREs and ops engineers who today respond to alerts by manually cross-referencing dashboards, runbooks, and tribal knowledge under time pressure. OpenShift AI Ops replaces that workflow with an AI-driven pipeline that gets faster, cheaper, and more accurate the longer it runs.

Frontier LLMs paired with curated OpenShift knowledge (runbooks, Red Hat knowledge base, agentic skills) now outperform the traditional monitor-alert-diagnose-fix cycle. AI ops initiatives are proliferating across large IT organizations at every level. This project focuses that capability specifically on OpenShift — leveraging deep platform knowledge that generic AI ops vendors cannot match.

## The Problem

**Alert fatigue is real.** An OpenShift cluster generates thousands of metrics, hundreds of alerting rules, and during cascading failures can produce dozens of simultaneous alerts. SREs context-switch between Grafana, `oc` commands, runbooks, and Slack threads — often at 2am.

**Diagnosis is slow and error-prone.** Connecting symptoms to root causes requires cross-domain reasoning (is it storage? network? compute? a combination?) that takes experienced engineers 15-60 minutes per incident. Junior engineers take longer and sometimes misdiagnose.

**Institutional knowledge walks out the door.** When senior SREs leave, their pattern recognition and war stories leave with them. There's no systematic way to capture "last time we saw this combination of alerts, the root cause was X and the fix was Y."

**The same failures repeat.** Without a learning loop, the same alert fires next month and the same human goes through the same 30-minute diagnosis exercise. The cost of the status quo compounds over time.

## Who This Serves

**Primary: SREs and Ops Engineers.** The on-call engineer who gets paged at 2am. Today they SSH in, run `oc get events`, stare at dashboards, and search Slack for "has anyone seen this before?" Tomorrow they see: "Alert: etcdHighFsyncDurations. Diagnosis: disk I/O contention on master-2 from excessive logging. Confidence: 0.87. Proposed fix: reduce audit log verbosity + restart etcd pod. Dry-run: passed. [Approve] [Reject] [Investigate more]."

**Secondary: Platform Teams.** Teams managing OpenShift for multiple developer tenants. They benefit from the learning loop — patterns discovered on one incident automatically inform the next — and from the UI's visibility into incident history and resolution patterns.

## The Solution

A Helm-deployed tool that drops into any OpenShift cluster and provides an intelligent operations co-pilot:

**Alert intake and triage.** Receives AlertManager webhooks, deduplicates storm alerts, and maintains a priority queue (urgency x recency). Alerts that have been seen before and successfully remediated are fast-tracked via vector similarity — no LLM call needed.

**Multi-agent diagnosis.** Domain-specialized agents (compute, storage, network — extensible) self-select alerts matching their expertise, run read-only diagnostic commands against the cluster, and return structured diagnoses with confidence scores. An orchestrator synthesizes partial findings into a unified root-cause assessment.

**Adversarial validation.** A skeptic agent challenges every diagnosis and every remediation plan in a single round of structured debate. If the diagnosis changes fundamentally under challenge, it's rejected and re-evaluated. This prevents the system from acting on flawed reasoning.

**Policy-gated remediation.** A configurable matrix (alert severity x blast radius x diagnosis confidence) determines which remediations execute automatically and which require human approval. The human sees the diagnosis, the plan, the skeptic's assessment, and a dry-run result before deciding.

**Learning from outcomes.** Every resolved incident — success or failure — is stored as a case record with embeddings. Older solutions decay in confidence. Failed remediations are stored as negative signals. The system gets more decisive and less LLM-dependent with every incident.

## What Makes This Different

**Deep OpenShift knowledge, not generic monitoring.** Built on platform-specific runbooks, Red Hat knowledge base, and purpose-built operational skills — it knows what `etcdHighFsyncDurations` means out of the box, with depth that generic AI ops vendors can't match.

**Doesn't depend on the patient it's healing.** No CRDs, no operator dependencies — self-contained persistence, API, and UI. If the cluster's API machinery is degraded, the tool still functions.

**Adversarial validation is built in, not bolted on.** Every diagnosis and remediation plan must survive structured challenge before execution — a mandatory pipeline stage, not an optional review.

**Learns and improves without retraining.** Known patterns bypass the LLM entirely — reducing cost, latency, and dependence on external services as the case library grows.

**Trust is earned incrementally.** Operators start in full human-in-the-loop mode and progressively open auto-remediation as confidence builds. The eval harness validates behavior against simulated alerts before production trust is extended.

## Success Criteria

1. **Trust earned:** The SRE team trusts the tool for auto-remediation on at least some categories of alerts (e.g., pod restarts, resource scaling) within 6 months of deployment.
2. **Diagnosis accuracy:** 90% correct root-cause identification as validated against the eval harness and confirmed by human review of production incidents.
3. **Time to resolution:** Measurable reduction in mean-time-to-resolution for alerts the tool handles vs. the pre-tool baseline.
4. **Learning velocity:** The vector DB fast-path handles an increasing percentage of incidents over time (system gets faster without human effort). [ASSUMPTION: tracking this metric is feasible via the tool's own audit trail]

## Scope

**In — MVP (MUST):**
- Helm chart deployment (PostgreSQL + pgvector, API server, webhook receiver)
- AlertManager webhook integration with priority queue and dedup
- Single orchestrator/generalist agent (handles all domains initially)
- Structured diagnosis with root-cause taxonomy and confidence scoring
- Knowledge integration: OpenShift runbooks + RHOKP
- Adversarial skeptic for both diagnosis and remediation
- Remediation planner with structured plans (steps, blast radius, rollback)
- Policy gate: severity x blast_radius x confidence matrix
- Serialized execution with cooldown
- Observation: alert resolved = success
- Learning store: success/failure case records with temporal decay
- Per-agent LLM configuration (URL, credentials, model parameters)
- Standalone web UI (alerts, diagnosis, remediation, approval workflow)
- LangGraph with PostgreSQL checkpoints
- Two OpenShift MCP Server instances (read-only, read-write)
- Eval harness: simulated alert injection, response validation against known-correct answers, accuracy measurement — gates auto-remediation trust

**In — Post-MVP (SHOULD):**
- Domain specialist agents (compute, storage, network) with self-selection
- Vector DB fast-path (skip LLM for known cases)
- Dry-run pre-flight validation
- OpenShift Console dynamic plugin
- LLM retry + fallback endpoints

**Out — Future:**
- PrometheusRule proposals from learned patterns
- Knowledge graph of cluster-specific causal chains
- Cross-cluster federated learning
- Multi-cluster aggregation

## Technical Foundation

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Deployment | Helm chart | No CRDs, no OLM dependency, self-contained |
| Agent orchestration | LangGraph | Stateful graph, native HITL, checkpointing, audit trail |
| Persistence | PostgreSQL + pgvector | Single store for structured data + vector embeddings + LangGraph state |
| Cluster interaction | OpenShift MCP Server | Go-native, RBAC-respecting, read-only/read-write split |
| LLM | External (configurable) | No OpenShift AI requirement; any endpoint works |
| UI | React standalone + Console plugin | Works independently of cluster health |
| Security boundary | Two ServiceAccounts | cluster-reader (diagnosis), cluster-admin (remediation) |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Bad remediation damages cluster | High | Policy matrix gates risky actions; serialized execution with cooldown; dry-run pre-flight; adversarial skeptic; rollback plans (human-triggered only) |
| Over-trust in AI decisions | High | Eval harness with simulated alerts validates behavior before production trust; incremental policy opening; all actions auditable |
| LLM unavailability | Medium | Retry + fallback endpoint; vector DB fast-path for known cases works without LLM |
| Diagnosis hallucination | Medium | Structured output with taxonomy (not free-text); adversarial challenge; confidence scoring; past-case matching |
| Adoption resistance (SREs don't trust AI) | Medium | Start human-in-the-loop only; demonstrate value through diagnosis before offering auto-remediation; transparent reasoning in UI |

## Vision

If this works, OpenShift AI Ops becomes the operational memory of every cluster it runs on. In year one, it's a co-pilot — suggesting and explaining while humans approve. By year two, it handles the routine autonomously while humans focus on novel failures and architecture. By year three, it's proposing alerting improvements, identifying systemic weaknesses, and feeding insights back to platform engineering. The cluster doesn't just heal — it evolves.

The longer-term possibility: federated learning across clusters, where anonymized case records create a collective intelligence. Your cluster encounters a novel failure — but another cluster in the fleet solved it last week, and the fix flows back automatically. An immune system that gets stronger with scale.
