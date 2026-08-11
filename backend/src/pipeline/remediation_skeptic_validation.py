"""Remediation skeptic validation loop with hash-based termination (Story 3.2).

Mirrors pipeline/skeptic_validation.py but for remediation plans.
Uses plan_hash() instead of root_cause_hash().

Key constraints:
- Max 2 rounds (AD: "NEVER allow more than one re-challenge")
- Round 1: hash unchanged → pass. Hash changed → go to round 2.
- Round 2: pass regardless of hash change.
- RemediationSkepticVerdict.passed is always True after the loop completes.
"""

from __future__ import annotations

from ..config.logging import Component, get_logger
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.remediation import RemediationPlan
from ..models.remediation_skeptic import (
    RemediationSkepticVerdict,
)

logger = get_logger(Component.PIPELINE)

MAX_REMEDIATION_SKEPTIC_ROUNDS = 2


async def run_remediation_skeptic_validation(
    plan: RemediationPlan,
    artifact: ImmutableDiagnosisArtifact,
) -> tuple[RemediationPlan, RemediationSkepticVerdict]:
    """Run the remediation skeptic challenge/response loop.

    Mirror of pipeline/skeptic_validation.py but for remediation plans.
    Uses plan_hash() instead of root_cause_hash().

    Args:
        plan: The RemediationPlan to validate.
        artifact: The sealed diagnosis artifact (read-only context).

    Returns:
        Tuple of (possibly revised RemediationPlan, RemediationSkepticVerdict).
    """
    from ..agents.planner import run_planner_rebuttal
    from ..agents.remediation_skeptic import run_remediation_skeptic

    incident_id = str(plan.incident_id)
    original_hash = plan.plan_hash()
    current_plan = plan
    challenge_history: list[dict] = []

    logger.info(
        "Remediation skeptic validation starting",
        extra={"incident_id": incident_id, "original_hash": original_hash[:16]},
    )

    for round_num in range(1, MAX_REMEDIATION_SKEPTIC_ROUNDS + 1):
        challenge = await run_remediation_skeptic(current_plan, artifact)
        revised_plan = await run_planner_rebuttal(
            current_plan, challenge, artifact
        )

        challenge_history.append({
            "round": round_num,
            "challenge": challenge.model_dump(mode="json"),
            "response": revised_plan.model_dump(mode="json"),
        })

        current_plan = revised_plan
        current_hash = current_plan.plan_hash()

        logger.info(
            "Remediation skeptic round completed",
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

    verdict = RemediationSkepticVerdict(
        passed=True,
        rounds_completed=len(challenge_history),
        original_plan_hash=plan.plan_hash(),
        final_plan_hash=current_plan.plan_hash(),
        challenge_history=challenge_history,
        verdict_reasoning=(
            f"Plan validated after {len(challenge_history)} skeptic "
            f"round(s). Original hash: {plan.plan_hash()[:16]}..., "
            f"final hash: {current_plan.plan_hash()[:16]}..."
        ),
    )

    logger.info(
        "Remediation skeptic validation complete",
        extra={
            "incident_id": incident_id,
            "rounds": verdict.rounds_completed,
            "hash_changed": verdict.original_plan_hash != verdict.final_plan_hash,
        },
    )

    return current_plan, verdict
