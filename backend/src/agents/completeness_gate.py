"""Completeness gate — verifies diagnosis addresses all RCE alerts (AC #6).

This is a deterministic check (no LLM). It verifies that all alert
fingerprints from the Root-Cause Event are addressed in the diagnosis
evidence or explicit reasoning. If incomplete, the diagnosis is sent back
to the orchestrator for retry (max 2 retries).
"""

from __future__ import annotations

from ..config.logging import Component, get_logger
from ..models.diagnosis import DiagnosisObject
from ..models.knowledge import CompletenessResult

logger = get_logger(Component.AGENT)


def evaluate_completeness(
    diagnosis: DiagnosisObject,
    rce_alerts: list[dict],
    evidence_ledger: list[dict] | None = None,
) -> CompletenessResult:
    """Evaluate whether the diagnosis addresses all alerts in the RCE.

    Checks that each alert's fingerprint appears in the diagnosis text
    (fingerprint is the primary identifier). Alertname is only a fallback
    when the alert has no fingerprint. Also verifies that no gathered
    evidence was left unexamined (AC #6).

    Args:
        diagnosis: The structured diagnosis to evaluate.
        rce_alerts: List of alert dicts from the Root-Cause Event.
        evidence_ledger: Optional list of evidence items gathered by tools.

    Returns:
        CompletenessResult indicating pass/fail with details.
    """
    if not rce_alerts:
        return CompletenessResult(
            complete=True,
            unaddressed_alerts=[],
            reasoning="No alerts to verify — diagnosis is trivially complete",
        )

    diagnosis_text = _build_diagnosis_text(diagnosis)
    diagnosis_text_lower = diagnosis_text.lower()

    addressed_count = 0
    unaddressed: list[str] = []

    for alert in rce_alerts:
        fingerprint = alert.get("fingerprint", "")
        labels = alert.get("labels", alert)
        alertname = labels.get("alertname", "")

        if not fingerprint and not alertname:
            addressed_count += 1
            continue

        if fingerprint and fingerprint.lower() in diagnosis_text_lower:
            addressed_count += 1
            continue

        if not fingerprint and alertname and alertname.lower() in diagnosis_text_lower:
            addressed_count += 1
            continue

        unaddressed.append(fingerprint or alertname)

    total = len(rce_alerts)

    unexamined_evidence = _check_evidence_examined(diagnosis, evidence_ledger or [])

    if not unaddressed and not unexamined_evidence:
        return CompletenessResult(
            complete=True,
            unaddressed_alerts=[],
            reasoning=f"All {total} alerts addressed in diagnosis; all evidence examined",
        )

    reasons: list[str] = []
    if unaddressed:
        reasons.append(
            f"Addressed {addressed_count}/{total} alerts. Missing: {unaddressed}"
        )
    if unexamined_evidence:
        reasons.append(
            f"{len(unexamined_evidence)} evidence item(s) not examined in diagnosis"
        )

    return CompletenessResult(
        complete=False,
        unaddressed_alerts=unaddressed + unexamined_evidence,
        reasoning="; ".join(reasons),
    )


def _check_evidence_examined(
    diagnosis: DiagnosisObject,
    evidence_ledger: list[dict],
) -> list[str]:
    """Return list of evidence items from the ledger not referenced in the diagnosis.

    Each evidence item gathered by tools should have its key findings
    (from the result summary, not just query terms) referenced somewhere
    in the diagnosis text (evidence, causal chain, or summary).

    Runbook searches with no hits are excluded — they have nothing
    to examine and should not count as positive evidence.
    """
    if not evidence_ledger:
        return []

    diagnosis_text_lower = _build_diagnosis_text(diagnosis).lower()
    unexamined: list[str] = []

    for item in evidence_ledger:
        if item.get("no_hit"):
            continue

        query = item.get("query", "")
        result_summary = item.get("result_summary", "")

        if not query and not result_summary:
            continue

        searchable = f"{query} {result_summary}".lower()
        terms = [t for t in searchable.split() if len(t) > 3]
        if not terms:
            continue

        matched = sum(1 for t in terms if t in diagnosis_text_lower)
        threshold = max(1, len(terms) // 3)
        if matched < threshold:
            label = query[:80] if query else result_summary[:80]
            unexamined.append(f"unexamined evidence: {label}")

    return unexamined


def _build_diagnosis_text(diagnosis: DiagnosisObject) -> str:
    """Build a searchable text from all diagnosis fields."""
    parts = [
        diagnosis.root_cause_component,
        diagnosis.failure_mode,
        diagnosis.root_cause_code,
        diagnosis.agent_summary,
        " ".join(diagnosis.causal_chain),
        " ".join(diagnosis.affected_resources),
    ]

    for evidence in diagnosis.evidence:
        parts.append(evidence.query)
        parts.append(evidence.result)

    for gap in diagnosis.evidence_gaps:
        parts.append(gap.query)
        parts.append(gap.reason)

    return " ".join(parts)
