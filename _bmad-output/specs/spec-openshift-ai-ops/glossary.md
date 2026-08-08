# Glossary — OpenShift AI Ops

Domain terminology used throughout the spec and its companions. Terms are defined at the system boundary — how this system uses them, not generic definitions.

| Term | Definition |
|------|-----------|
| **Agentic Skill** | An executable, domain-specific command sequence (e.g., cluster-update checks, token discovery, node diagnostics) loaded as a callable tool for agents. Distinct from passive knowledge sources: skills perform operations, knowledge sources provide reference material. Diagnosis-side skills are read-only; write-capable skills are remediation-only. |
| **Alert** | A notification from AlertManager indicating a firing or resolved condition, delivered as an HTTP webhook payload. The fundamental input to the system. |
| **Alert Storm** | Multiple related alerts firing simultaneously during a cascading failure. The triage stage correlates these into a single Root-Cause Event. |
| **Blast Radius** | The scope of impact of a remediation action: `workload`, `namespace`, `node`, or `cluster`. One of three dimensions in the Policy Gate. |
| **Case Record** | A structured entry in the Learning Store capturing the full lifecycle of an incident: alert signature, root-cause code, structured diagnosis, remediation plan, outcome, and cluster context. Stored with vector embeddings for similarity search. |
| **Diagnosis Confidence** | A numeric score (0–1) representing the system's confidence in a diagnosis. One of three dimensions in the Policy Gate. |
| **Evidence Artifact** | A concrete, machine-verifiable piece of evidence supporting a diagnosis: a specific log line, metric value, resource state, or MCP Server query result. Required for auto-execution via the Policy Gate. |
| **Fast-Path** | A bypass of the full LLM diagnosis pipeline: when a new alert matches a past successful Case Record above a configurable similarity threshold, the proven remediation is replayed directly. |
| **Immutable Diagnosis Artifact** | The finalized, read-only diagnosis object that crosses the RBAC boundary from diagnosis to remediation. The remediation planner takes it as given and cannot re-diagnose or re-interpret. |
| **Learning Store** | The pgvector-backed knowledge base of past Case Records, queryable by embedding similarity. Older records carry reduced confidence via Temporal Decay. |
| **MCP Server** | The official OpenShift MCP Server (Model Context Protocol), a Go-native interface to the Kubernetes API. Deployed as two instances: read-only (diagnosis) and read-write (remediation). |
| **Model Routing** | Dynamic selection of which LLM model handles a request based on estimated task complexity. Simple alerts use cheaper, faster models; complex multi-hop failures use frontier models. |
| **Orchestrator** | The central agent that forms initial hypotheses, dispatches to Specialists, synthesizes findings, and acts as generalist of last resort for unclaimed alerts. |
| **Policy Gate** | The configurable decision matrix (severity × blast radius × diagnosis confidence) that determines whether a remediation auto-executes or requires human approval. |
| **Policy Matrix** | The user-configurable thresholds for the Policy Gate. Defines which combinations of severity, blast radius, and confidence levels are trusted for auto-execution. |
| **Priority Queue** | The ordered queue of alerts awaiting processing, ranked by urgency × recency. Persisted to PostgreSQL (not in-memory). |
| **RBAC Airlock** | The security boundary between diagnosis (read-only cluster access) and remediation (read-write cluster access), enforced by separate ServiceAccounts and MCP Server instances. |
| **Remediation Plan** | A structured object: `{steps, blast_radius, rollback_plan, estimated_risk, preconditions}`. Produced by the remediation planner from an Immutable Diagnosis Artifact. |
| **okp-mcp** | MCP server for the Red Hat Offline Knowledge Portal (`rhel-lightspeed/okp-mcp`). Bridges LLM tool calls to the RHOKP Solr index via streamable-http transport. Exposes `search_portal` (multi-query search with reciprocal rank fusion) and `get_document` (full content retrieval with BM25-scored passage extraction) tools. |
| **RHOKP** | Red Hat Offline Knowledge Portal. A containerized Apache Solr 9.8 instance containing 600k+ documents — Red Hat documentation, KBase solutions, articles, CVEs, and errata. Deployed as a sidecar in the Helm chart alongside okp-mcp. Agents query it via MCP during diagnosis. Refreshed by updating the container image. |
| **Root-Cause Code** | A structured identifier from a controlled taxonomy (e.g., `node/memory-pressure`, `network/dns-failure`, `storage/pvc-stuck-pending`). Part of the Structured Diagnosis Object. |
| **Root-Cause Event** | The output of alert correlation: a single event representing the probable root cause behind one or more correlated alerts. |
| **Semantic Cache** | A cache layer that stores and reuses LLM responses for semantically similar queries, reducing LLM cost and latency. Entries are invalidated when relevant cluster state changes. |
| **Skeptic** | An adversarial agent that challenges a diagnosis or remediation plan in a single round of structured debate. Stability under challenge (root-cause hash unchanged) = acceptance. |
| **Specialist** | A domain-specific diagnosis agent (compute, storage, network) that self-selects alerts via label-matching rules. Post-MVP; the orchestrator handles all domains as generalist in MVP. |
| **Structured Diagnosis Object** | Schema-enforced output: `{root_cause_component, failure_mode, causal_chain, affected_resources, evidence}`. Enables deterministic comparison via root-cause hash. |
| **Temporal Decay** | A confidence reduction applied to older Case Records: `effective_confidence = base_confidence × decay_factor(age) × version_relevance(OCP_version_then vs now)`. |
