"""Skeptic validation loop with hash-based termination and artifact sealing.

Implements the adversarial challenge/response loop between the Skeptic
agent and the Orchestrator. The loop runs as plain Python inside a single
graph node — the graph sees a single 'skeptic_validation' node.

Key constraints:
- Max 2 rounds (AD: "NEVER allow more than one re-challenge")
- Round 1: hash unchanged → pass. Hash changed → go to round 2.
- Round 2: pass regardless of hash change.
- SkepticVerdict.passed is always True after the loop completes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..config.logging import Component, get_logger
from ..models.diagnosis import DiagnosisObject, ImmutableDiagnosisArtifact
from ..models.skeptic import SkepticVerdict

logger = get_logger(Component.PIPELINE)

MAX_SKEPTIC_ROUNDS = 2


async def run_skeptic_validation(
    diagnosis: DiagnosisObject,
    state: dict,
) -> tuple[DiagnosisObject, SkepticVerdict]:
    """Run the skeptic challenge/response loop with hash-based termination.

    Args:
        diagnosis: The DiagnosisObject to validate.
        state: The DiagnosisState dict for context.

    Returns:
        Tuple of (possibly revised DiagnosisObject, SkepticVerdict).
    """
    from ..agents.orchestrator import run_orchestrator_rebuttal
    from ..agents.skeptic import run_skeptic

    incident_id = state.get("incident_id", "unknown")
    original_hash = diagnosis.root_cause_hash()
    current_diagnosis = diagnosis
    challenge_history: list[dict] = []

    logger.info(
        "Skeptic validation starting",
        extra={"incident_id": incident_id, "original_hash": original_hash[:16]},
    )

    for round_num in range(1, MAX_SKEPTIC_ROUNDS + 1):
        challenge = await run_skeptic(current_diagnosis, state)

        response = await run_orchestrator_rebuttal(
            current_diagnosis, challenge, state, round_number=round_num,
        )

        challenge_history.append({
            "round": round_num,
            "challenge": challenge.model_dump(mode="json"),
            "response": response.model_dump(mode="json"),
        })

        if response.revised_diagnosis is not None:
            current_diagnosis = response.revised_diagnosis

        current_hash = current_diagnosis.root_cause_hash()

        logger.info(
            "Skeptic round completed",
            extra={
                "incident_id": incident_id,
                "round": round_num,
                "hash_changed": current_hash != original_hash,
            },
        )

        if current_hash == original_hash:
            break

        if round_num == 1:
            original_hash = current_hash
            continue

    verdict = SkepticVerdict(
        passed=True,
        rounds_completed=len(challenge_history),
        original_hash=diagnosis.root_cause_hash(),
        final_hash=current_diagnosis.root_cause_hash(),
        challenge_history=challenge_history,
        verdict_reasoning=(
            f"Diagnosis validated after {len(challenge_history)} skeptic "
            f"round(s). Original hash: {diagnosis.root_cause_hash()[:16]}..., "
            f"final hash: {current_diagnosis.root_cause_hash()[:16]}..."
        ),
    )

    logger.info(
        "Skeptic validation complete",
        extra={
            "incident_id": incident_id,
            "rounds": verdict.rounds_completed,
            "hash_changed": verdict.original_hash != verdict.final_hash,
        },
    )

    return current_diagnosis, verdict


def seal_diagnosis(
    diagnosis: DiagnosisObject,
    verdict: SkepticVerdict,
) -> ImmutableDiagnosisArtifact:
    """Freeze the diagnosis into an immutable artifact for RBAC Airlock handoff.

    Creates a frozen ImmutableDiagnosisArtifact from the diagnosis with
    the skeptic verdict attached. Once sealed, no fields can be modified.

    Args:
        diagnosis: The validated DiagnosisObject.
        verdict: The SkepticVerdict from the validation loop.

    Returns:
        An immutable, frozen artifact ready for persistence and handoff.
    """
    return ImmutableDiagnosisArtifact(
        id=diagnosis.id,
        incident_id=diagnosis.incident_id,
        root_cause_component=diagnosis.root_cause_component,
        failure_mode=diagnosis.failure_mode,
        root_cause_code=diagnosis.root_cause_code,
        causal_chain=tuple(diagnosis.causal_chain),
        affected_resources=tuple(diagnosis.affected_resources),
        evidence=tuple(diagnosis.evidence),
        evidence_gaps=tuple(diagnosis.evidence_gaps),
        confidence=diagnosis.confidence,
        agent_summary=diagnosis.agent_summary,
        coverage_gaps=tuple(diagnosis.coverage_gaps),
        alternative_hypotheses=tuple(diagnosis.alternative_hypotheses),
        created_at=diagnosis.created_at,
        skeptic_verdict=verdict.model_dump(mode="json"),
        sealed_at=datetime.now(timezone.utc),
    )
