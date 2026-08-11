"""Unit tests for the remediation skeptic validation loop (Story 3.2).

Tests hash-unchanged passes in 1 round, hash-changed triggers re-challenge,
max 2 rounds enforced.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models.diagnosis import (
    EvidenceArtifact,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)
from src.models.remediation import (
    BlastRadius,
    Precondition,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from src.models.remediation_skeptic import (
    RemediationSkepticChallenge,
    RemediationSkepticVerdict,
)
from src.pipeline.remediation_skeptic_validation import (
    MAX_REMEDIATION_SKEPTIC_ROUNDS,
    run_remediation_skeptic_validation,
)


def _make_artifact(incident_id=None) -> ImmutableDiagnosisArtifact:
    iid = incident_id or uuid.uuid4()
    return ImmutableDiagnosisArtifact(
        id=uuid.uuid4(),
        incident_id=iid,
        root_cause_component="workload",
        failure_mode="crash-loop-backoff",
        root_cause_code="workload/crash-loop-backoff",
        causal_chain=("Pod CrashLoopBackOff", "OOM killed"),
        affected_resources=("pod/test-pod",),
        evidence=(
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources",
                result="{}",
                timestamp=datetime.now(timezone.utc),
            ),
        ),
        confidence=0.85,
        agent_summary="OOM crash loop",
        skeptic_verdict={
            "passed": True,
            "rounds_completed": 1,
            "original_hash": "a" * 64,
            "final_hash": "a" * 64,
            "challenge_history": [{"round": 1}],
            "verdict_reasoning": "ok",
        },
        sealed_at=datetime.now(timezone.utc),
    )


def _make_plan(incident_id=None, **overrides) -> RemediationPlan:
    defaults = dict(
        incident_id=incident_id or uuid.uuid4(),
        diagnosis_id=uuid.uuid4(),
        steps=[
            RemediationStep(
                order=1,
                description="Increase memory limit",
                command="kubectl set resources",
                resource="deployment/test-app",
                action="patch",
                expected_outcome="Higher memory limit",
            ),
        ],
        blast_radius=BlastRadius.WORKLOAD,
        rollback_plan=[
            RemediationStep(
                order=1,
                description="Revert memory",
                resource="deployment/test-app",
                action="patch",
                expected_outcome="Original limit",
            ),
        ],
        estimated_risk=RiskLevel.LOW,
        preconditions=[
            Precondition(
                type="rbac",
                description="Patch deployments",
                requirement="patch on deployments",
            ),
        ],
        plan_summary="Increase memory limit",
    )
    defaults.update(overrides)
    return RemediationPlan(**defaults)


def _make_challenge() -> RemediationSkepticChallenge:
    return RemediationSkepticChallenge(
        step_correctness_issues=["Minor issue"],
        blast_radius_assessment="Accurate",
        rollback_feasibility_issues=[],
        precondition_gaps=[],
        risk_assessment_critique="Appropriate",
        overall_verdict="Plan is acceptable with minor notes",
    )


class TestMaxRounds:
    """MAX_REMEDIATION_SKEPTIC_ROUNDS is 2."""

    @pytest.mark.unit
    def test_max_rounds_is_two(self):
        assert MAX_REMEDIATION_SKEPTIC_ROUNDS == 2


class TestHashUnchanged:
    """When the plan hash is unchanged after round 1, validation passes in 1 round."""

    @pytest.mark.unit
    async def test_hash_unchanged_passes_in_one_round(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid)

        mock_skeptic = AsyncMock(return_value=_make_challenge())
        mock_rebuttal = AsyncMock(return_value=plan)

        with (
            patch(
                "src.agents.remediation_skeptic.run_remediation_skeptic",
                mock_skeptic,
            ),
            patch(
                "src.agents.planner.run_planner_rebuttal",
                mock_rebuttal,
            ),
        ):
            result_plan, verdict = await run_remediation_skeptic_validation(
                plan, artifact
            )

        assert verdict.passed is True
        assert verdict.rounds_completed == 1
        assert verdict.original_plan_hash == verdict.final_plan_hash
        assert len(verdict.challenge_history) == 1
        assert mock_skeptic.call_count == 1
        assert mock_rebuttal.call_count == 1


class TestHashChanged:
    """When the plan hash changes after round 1, a second round is triggered."""

    @pytest.mark.unit
    async def test_hash_changed_triggers_round_two(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid)

        revised_plan = _make_plan(
            incident_id=iid,
            steps=[
                RemediationStep(
                    order=1,
                    description="REVISED: Scale down then fix",
                    command="kubectl scale --replicas=0",
                    resource="deployment/test-app",
                    action="scale",
                    expected_outcome="Zero replicas",
                ),
            ],
        )

        call_count = {"n": 0}

        async def mock_rebuttal(p, c, a):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return revised_plan
            return revised_plan

        mock_skeptic = AsyncMock(return_value=_make_challenge())
        mock_rebuttal_fn = AsyncMock(side_effect=mock_rebuttal)

        with (
            patch(
                "src.agents.remediation_skeptic.run_remediation_skeptic",
                mock_skeptic,
            ),
            patch(
                "src.agents.planner.run_planner_rebuttal",
                mock_rebuttal_fn,
            ),
        ):
            result_plan, verdict = await run_remediation_skeptic_validation(
                plan, artifact
            )

        assert verdict.passed is True
        assert verdict.rounds_completed == 2
        assert verdict.original_plan_hash != verdict.final_plan_hash
        assert len(verdict.challenge_history) == 2


class TestMaxRoundsEnforced:
    """Even if hash keeps changing, max 2 rounds are enforced."""

    @pytest.mark.unit
    async def test_never_exceeds_two_rounds(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid)

        revision_counter = {"n": 0}

        async def always_change(p, c, a):
            revision_counter["n"] += 1
            return _make_plan(
                incident_id=iid,
                steps=[
                    RemediationStep(
                        order=1,
                        description=f"Revision {revision_counter['n']}",
                        command=f"cmd-{revision_counter['n']}",
                        resource="deployment/test-app",
                        action="patch",
                        expected_outcome=f"Outcome {revision_counter['n']}",
                    ),
                ],
            )

        mock_skeptic = AsyncMock(return_value=_make_challenge())
        mock_rebuttal = AsyncMock(side_effect=always_change)

        with (
            patch(
                "src.agents.remediation_skeptic.run_remediation_skeptic",
                mock_skeptic,
            ),
            patch(
                "src.agents.planner.run_planner_rebuttal",
                mock_rebuttal,
            ),
        ):
            result_plan, verdict = await run_remediation_skeptic_validation(
                plan, artifact
            )

        assert verdict.passed is True
        assert verdict.rounds_completed <= 2
        assert mock_skeptic.call_count <= 2
        assert mock_rebuttal.call_count <= 2

    @pytest.mark.unit
    async def test_always_passes_after_loop(self):
        """Plan ALWAYS passes after the loop completes, regardless of hash changes."""
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid)

        counter = {"n": 0}

        async def different_each_time(p, c, a):
            counter["n"] += 1
            return _make_plan(
                incident_id=iid,
                steps=[
                    RemediationStep(
                        order=1,
                        description=f"Version {counter['n']}",
                        command=f"kubectl v{counter['n']}",
                        resource="deployment/test-app",
                        action="patch",
                        expected_outcome=f"Result {counter['n']}",
                    ),
                ],
            )

        with (
            patch(
                "src.agents.remediation_skeptic.run_remediation_skeptic",
                AsyncMock(return_value=_make_challenge()),
            ),
            patch(
                "src.agents.planner.run_planner_rebuttal",
                AsyncMock(side_effect=different_each_time),
            ),
        ):
            _, verdict = await run_remediation_skeptic_validation(plan, artifact)

        assert verdict.passed is True
