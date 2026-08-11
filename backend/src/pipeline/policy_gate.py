"""Three-dimensional policy gate evaluator (Story 3.3).

Pure deterministic logic — no LLM involvement.
Evaluates severity × blast_radius × confidence against configured
thresholds, checks evidence completeness (AD-15), and decides
auto-execution vs. human approval.
"""

from __future__ import annotations

from ..config.logging import Component, get_logger
from ..config.policy_settings import PolicyMatrixSettings, get_policy_matrix_settings
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.policy_gate import DryRunResult, PolicyDecision, PolicyDimension
from ..models.remediation import BlastRadius, RemediationPlan

logger = get_logger(Component.PIPELINE)

BLAST_RADIUS_ORDER: dict[str, int] = {
    BlastRadius.WORKLOAD.value: 0,
    BlastRadius.NAMESPACE.value: 1,
    BlastRadius.NODE.value: 2,
    BlastRadius.CLUSTER.value: 3,
}


async def evaluate_policy_gate(
    plan: RemediationPlan,
    artifact: ImmutableDiagnosisArtifact,
    dry_run: DryRunResult,
    settings: PolicyMatrixSettings | None = None,
    alert_severity: str | None = None,
) -> PolicyDecision:
    """Evaluate the policy gate for auto-execution eligibility.

    Checks:
    1. Evidence gaps must be empty (AD-15 hard block)
    2. Each causal chain element must have supporting evidence
    3. Dry-run must have passed
    4. Three dimensions: severity × blast_radius × confidence
    All must pass for auto-execution.
    """
    config = settings or get_policy_matrix_settings()

    evidence_gaps_empty = len(artifact.evidence_gaps) == 0
    evidence_complete = _check_causal_chain_evidence(artifact)

    severity_dim = _evaluate_severity(alert_severity, config)
    blast_radius_dim = _evaluate_blast_radius(plan, config)
    confidence_dim = _evaluate_confidence(artifact, config)

    dimensions = [severity_dim, blast_radius_dim, confidence_dim]
    all_dimensions_pass = all(d.passed for d in dimensions)

    auto_approved = (
        evidence_gaps_empty
        and evidence_complete
        and dry_run.dry_run_passed
        and all_dimensions_pass
    )

    reasoning = _build_reasoning(
        auto_approved, dimensions, evidence_gaps_empty,
        evidence_complete, dry_run.dry_run_passed,
    )

    return PolicyDecision(
        incident_id=plan.incident_id,
        plan_id=plan.id,
        dimensions=dimensions,
        evidence_complete=evidence_complete,
        evidence_gaps_empty=evidence_gaps_empty,
        auto_execution_approved=auto_approved,
        reasoning=reasoning,
    )


def _check_causal_chain_evidence(artifact: ImmutableDiagnosisArtifact) -> bool:
    """Check each causal chain element has at least one supporting evidence artifact.

    Per FR-13: evidence artifacts required per causal chain element.
    Iterates per-artifact to avoid set-deduplication or zip-truncation
    dropping valid pairings.
    """
    if not artifact.causal_chain:
        return False

    for chain_element in artifact.causal_chain:
        element_lower = chain_element.lower()
        has_support = any(
            element_lower in e.result.lower() or element_lower in e.query.lower()
            for e in artifact.evidence
        )
        if not has_support:
            return False

    return True


def _evaluate_severity(
    alert_severity: str | None,
    config: PolicyMatrixSettings,
) -> PolicyDimension:
    """Evaluate severity dimension against auto-approve threshold.

    Uses the AlertManager severity from the incident record (AC #3),
    not inferred from diagnosis taxonomy.
    """
    severity_str = (alert_severity or "unknown").lower()
    threshold_str = ", ".join(config.severity_auto_approve) or "(none)"
    passed = severity_str in [s.lower() for s in config.severity_auto_approve]

    return PolicyDimension(
        name="severity",
        value=severity_str,
        threshold=threshold_str,
        passed=passed,
    )


def _evaluate_blast_radius(
    plan: RemediationPlan,
    config: PolicyMatrixSettings,
) -> PolicyDimension:
    """Evaluate blast radius dimension against auto-approve threshold."""
    radius = plan.blast_radius.value
    threshold_str = ", ".join(config.blast_radius_auto_approve) or "(none)"
    passed = radius in [b.lower() for b in config.blast_radius_auto_approve]

    return PolicyDimension(
        name="blast_radius",
        value=radius,
        threshold=threshold_str,
        passed=passed,
    )


def _evaluate_confidence(
    artifact: ImmutableDiagnosisArtifact,
    config: PolicyMatrixSettings,
) -> PolicyDimension:
    """Evaluate confidence dimension against minimum threshold."""
    confidence = artifact.confidence
    passed = confidence >= config.confidence_minimum

    return PolicyDimension(
        name="confidence",
        value=confidence,
        threshold=config.confidence_minimum,
        passed=passed,
    )


def _build_reasoning(
    auto_approved: bool,
    dimensions: list[PolicyDimension],
    evidence_gaps_empty: bool,
    evidence_complete: bool,
    dry_run_passed: bool,
) -> str:
    """Build a human-readable reasoning string for the decision."""
    parts: list[str] = []

    if auto_approved:
        parts.append("Auto-execution approved: all policy dimensions pass.")
    else:
        parts.append("Auto-execution denied.")

    if not evidence_gaps_empty:
        parts.append("Evidence gaps present (AD-15 hard block).")

    if not evidence_complete:
        parts.append("Causal chain evidence incomplete.")

    if not dry_run_passed:
        parts.append("Dry-run pre-flight failed.")

    for dim in dimensions:
        status = "PASS" if dim.passed else "FAIL"
        parts.append(f"{dim.name}: {dim.value} vs threshold {dim.threshold} [{status}]")

    return " ".join(parts)
