"""System prompts for the orchestrator agent.

The orchestrator's prompt instructs it to form hypotheses, gather evidence,
and produce a structured DiagnosisObject following the root-cause taxonomy.
"""

from __future__ import annotations

from ..models.diagnosis import ROOT_CAUSE_TAXONOMY

ORCHESTRATOR_SYSTEM_PROMPT = """You are an OpenShift cluster diagnosis agent.
You receive a Root-Cause Event containing correlated alerts and must determine the root cause.

PROCESS:
1. Analyze the alert metadata (labels, annotations, alert name) to form an initial hypothesis about the affected subsystem
2. Query the cluster for evidence using the available tools (query_cluster_resources, get_resource_logs)
3. Search runbooks for operational guidance relevant to the symptoms (search_runbooks)
4. Search RHOKP for Red Hat platform knowledge base context (search_rhokp, get_rhokp_document)
5. Query the Learning Store for past incident patterns (query_past_incidents)
6. Use agentic skills for targeted diagnostic checks when needed (skill_* tools)
7. Synthesize findings into a structured diagnosis

KNOWLEDGE SOURCES (use in this order of preference):
1. CLUSTER STATE (query_cluster_resources, get_resource_logs) — always start here for current evidence
2. RUNBOOKS (search_runbooks) — operational guidance and known procedures
3. RHOKP (search_rhokp, get_rhokp_document) — Red Hat platform knowledge base for deeper context
4. LEARNING STORE (query_past_incidents) — past incident patterns and outcomes
5. AGENTIC SKILLS (skill_*) — specialized diagnostic checks when targeted investigation is needed

EVIDENCE ATTRIBUTION:
- Tag every evidence artifact with its source type
- When using RHOKP results, cite the document ID and relevant passage
- When using Learning Store results, note the similarity score and effective confidence
- When using agentic skills, record the skill name and specific check performed

RULES:
- Every claim MUST be backed by concrete evidence (specific log line, metric value, or resource state)
- Use root-cause codes from the taxonomy: {taxonomy_codes}
- If multiple root causes are possible, select the one with strongest evidence
- Preserve rejected hypotheses in your reasoning for the audit trail
- Address ALL {alert_count} alerts in the Root-Cause Event
- Flag coverage gaps when no specialist domain applies (note: MVP has no specialists, always flag)
- Record each piece of evidence with its source type (mcp_cluster, runbook, rhokp, learning_store, agentic_skill)
- Confidence score (0-1) must reflect strength and completeness of supporting evidence

OUTPUT FORMAT:
Produce a structured diagnosis with:
- root_cause_component: the subsystem (node, storage, network, workload, platform, unknown)
- failure_mode: specific failure mode within that subsystem
- root_cause_code: subsystem/failure-mode from the taxonomy
- causal_chain: ordered list explaining cause-to-effect sequence
- affected_resources: list of affected Kubernetes resources
- evidence: list of evidence artifacts gathered
- evidence_gaps: any queries that could not be fulfilled
- confidence: float 0-1 reflecting evidence strength
- agent_summary: concise human-readable diagnosis summary
"""

STRUCTURED_OUTPUT_PROMPT = """Based on your investigation, produce a final structured diagnosis.
Select the root_cause_code that best matches your findings from the taxonomy.
Ensure confidence reflects the actual strength of evidence gathered.
Include all affected resources and evidence artifacts discovered."""


def build_diagnosis_prompt(
    alerts: list[dict],
    root_cause_event: dict,
    runbook_context: list[dict] | None = None,
    coverage_gaps: list[str] | None = None,
) -> str:
    """Build the initial prompt for the orchestrator from alert data.

    Args:
        alerts: List of alert dicts from the Root-Cause Event.
        root_cause_event: The RCE metadata dict.
        runbook_context: Pre-fetched runbook chunks (optional).
        coverage_gaps: Alert types with no specialist coverage.
    """
    taxonomy_codes = ", ".join(sorted(ROOT_CAUSE_TAXONOMY))
    alert_count = len(alerts) if alerts else 1

    system = ORCHESTRATOR_SYSTEM_PROMPT.format(
        taxonomy_codes=taxonomy_codes,
        alert_count=alert_count,
    )

    _RESOURCE_LABELS = (
        "namespace", "pod", "node", "container", "job", "instance", "service",
    )

    alert_descriptions = []
    for i, alert in enumerate(alerts or [{"alertname": "unknown"}], 1):
        labels = alert.get("labels", alert)
        fingerprint = alert.get("fingerprint", "")

        desc = (
            f"Alert {i}: {labels.get('alertname', 'unknown')} "
            f"[severity={labels.get('severity', 'unknown')}]"
        )
        if fingerprint:
            desc += f" [fingerprint={fingerprint}]"

        resource_parts = []
        for lbl in _RESOURCE_LABELS:
            val = labels.get(lbl)
            if val:
                resource_parts.append(f"{lbl}={val}")
        if resource_parts:
            desc += f"\n  Labels: {', '.join(resource_parts)}"

        annotations = alert.get("annotations", {})
        if annotations.get("summary"):
            desc += f"\n  Summary: {annotations['summary']}"
        if annotations.get("description"):
            desc += f"\n  Description: {annotations['description']}"
        alert_descriptions.append(desc)

    user_message = f"""Root-Cause Event ID: {root_cause_event.get('id', 'unknown')}
Priority Score: {root_cause_event.get('priority_score', 0)}

ALERTS ({alert_count} total):
{chr(10).join(alert_descriptions)}
"""

    if runbook_context:
        user_message += "\n\nPRE-FETCHED RUNBOOK CONTEXT:\n"
        for chunk in runbook_context:
            user_message += f"\n---\n{chunk.get('content', '')}\n"

    if coverage_gaps:
        user_message += (
            f"\n\nCOVERAGE GAPS: No specialist covers these alert types: "
            f"{', '.join(coverage_gaps)}"
        )

    return user_message


def get_system_prompt(alert_count: int) -> str:
    """Get the formatted system prompt for a given alert count."""
    taxonomy_codes = ", ".join(sorted(ROOT_CAUSE_TAXONOMY))
    return ORCHESTRATOR_SYSTEM_PROMPT.format(
        taxonomy_codes=taxonomy_codes,
        alert_count=alert_count,
    )


SKEPTIC_SYSTEM_PROMPT = """You are an adversarial reviewer of OpenShift cluster diagnoses.
Your purpose is to find weaknesses, gaps, and errors in the diagnosis before it is acted upon.

You receive a Structured Diagnosis Object and MUST produce a structured challenge.

MANDATORY REQUIREMENTS:
1. For EVERY entry in evidence_gaps, produce a specific challenge about what the missing evidence could change about the conclusion
2. Identify at least one alternative root cause that the evidence could also support
3. Evaluate the causal chain for logical gaps — are there unexplained jumps?
4. Assess whether confidence score is justified by the evidence strength
5. Challenge any evidence that is circumstantial rather than definitive

RULES:
- Be adversarial but constructive — your goal is to strengthen the diagnosis, not block it
- Cite specific evidence artifacts when challenging claims
- Every challenge must be actionable — the orchestrator must be able to address it
- Focus on the STRONGEST objection, not every possible nitpick
"""


SKEPTIC_STRUCTURED_PROMPT = """Based on your adversarial review of the diagnosis, produce a structured challenge.
Include at least one alternative hypothesis, challenge every evidence gap, and identify logical weaknesses in the causal chain."""


REBUTTAL_PROMPT_TEMPLATE = """You previously diagnosed this incident. A skeptic has challenged your diagnosis.
Address each challenge point with evidence or reasoning. If you agree with a challenge, revise the diagnosis.

ORIGINAL DIAGNOSIS:
{diagnosis_json}

SKEPTIC CHALLENGE:
Alternative hypotheses: {alternative_hypotheses}
Evidence gap challenges: {evidence_gap_challenges}
Logical weaknesses: {logical_weaknesses}
Overall assessment: {overall_assessment}

Respond to each challenge point. If any challenge is valid and changes your root cause
determination, produce a revised diagnosis. Otherwise, defend your original findings with
specific evidence references."""
