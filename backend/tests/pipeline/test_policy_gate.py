"""Unit tests for the policy gate evaluator (Story 3.3).

Tests: all dimensions pass → auto-approve; any fail → deny;
evidence_gaps → deny; missing causal chain evidence → deny;
default-deny config; dry-run failed → deny.
"""

import uuid
from datetime import datetime, timezone

import pytest

from src.config.policy_settings import PolicyMatrixSettings
from src.models.diagnosis import (
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)
from src.models.policy_gate import DryRunResult, DryRunStepResult
from src.models.remediation import (
    BlastRadius,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from src.pipeline.policy_gate import evaluate_policy_gate


def _make_artifact(
    incident_id=None,
    confidence=0.85,
    evidence_gaps=(),
    causal_chain=("Pod CrashLoopBackOff",),
    evidence=None,
) -> ImmutableDiagnosisArtifact:
    iid = incident_id or uuid.uuid4()
    if evidence is None:
        evidence = (
            EvidenceArtifact(
                source=EvidenceSource.MCP_CLUSTER,
                query="get_resources",
                result="Pod CrashLoopBackOff",
                timestamp=datetime.now(timezone.utc),
            ),
        )
    return ImmutableDiagnosisArtifact(
        id=uuid.uuid4(),
        incident_id=iid,
        root_cause_component="workload",
        failure_mode="crash-loop-backoff",
        root_cause_code="workload/crash-loop-backoff",
        causal_chain=causal_chain,
        affected_resources=("pod/test-pod",),
        evidence=evidence,
        evidence_gaps=evidence_gaps,
        confidence=confidence,
        agent_summary="OOM crash loop",
        skeptic_verdict={
            "passed": True, "rounds_completed": 1,
            "original_hash": "a" * 64, "final_hash": "a" * 64,
            "challenge_history": [{"round": 1}],
            "verdict_reasoning": "ok",
        },
        sealed_at=datetime.now(timezone.utc),
    )


def _make_plan(
    incident_id=None,
    blast_radius=BlastRadius.WORKLOAD,
) -> RemediationPlan:
    iid = incident_id or uuid.uuid4()
    return RemediationPlan(
        incident_id=iid,
        diagnosis_id=uuid.uuid4(),
        steps=[
            RemediationStep(
                order=1,
                description="Fix",
                command="oc apply -f fix.yaml",
                resource="pod/test",
                action="apply",
                expected_outcome="Fixed",
            ),
        ],
        blast_radius=blast_radius,
        estimated_risk=RiskLevel.LOW,
        plan_summary="Fix it",
    )


def _make_dry_run(
    incident_id=None,
    plan_id=None,
    overall_passed=True,
) -> DryRunResult:
    return DryRunResult(
        incident_id=incident_id or uuid.uuid4(),
        plan_id=plan_id or uuid.uuid4(),
        step_results=[
            DryRunStepResult(
                step_order=1, command="cmd", success=True, message="ok"
            ),
        ],
        rbac_check_passed=True,
        quota_check_passed=True,
        admission_check_passed=True,
        overall_passed=overall_passed,
    )


def _permissive_settings() -> PolicyMatrixSettings:
    """Settings that allow auto-approve for common scenarios."""
    return PolicyMatrixSettings(
        severity_auto_approve=["info", "warning", "critical"],
        blast_radius_auto_approve=["workload", "namespace", "node", "cluster"],
        confidence_minimum=0.5,
    )


class TestPolicyGateAllPass:
    @pytest.mark.unit
    async def test_all_passing_auto_approved(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid)
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run,
            settings=_permissive_settings(),
            alert_severity="warning",
        )

        assert decision.auto_execution_approved is True
        assert decision.evidence_gaps_empty is True
        assert decision.evidence_complete is True
        assert len(decision.dimensions) == 3
        assert all(d.passed for d in decision.dimensions)


class TestPolicyGateEvidenceGaps:
    @pytest.mark.unit
    async def test_evidence_gaps_blocks_auto_approve(self):
        """AD-15: non-empty evidence_gaps always blocks auto-execution."""
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(
            incident_id=iid,
            evidence_gaps=(
                EvidenceGap(
                    query="check node memory",
                    reason="MCP timeout",
                    timeout_seconds=30.0,
                ),
            ),
        )
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run,
            settings=_permissive_settings(),
            alert_severity="warning",
        )

        assert decision.auto_execution_approved is False
        assert decision.evidence_gaps_empty is False
        assert "evidence gaps" in decision.reasoning.lower()


class TestPolicyGateCausalChainEvidence:
    @pytest.mark.unit
    async def test_missing_causal_chain_evidence_blocks(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(
            incident_id=iid,
            causal_chain=("Totally unrelated cause",),
            evidence=(
                EvidenceArtifact(
                    source=EvidenceSource.MCP_CLUSTER,
                    query="get pods",
                    result="No matching evidence",
                    timestamp=datetime.now(timezone.utc),
                ),
            ),
        )
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run,
            settings=_permissive_settings(),
            alert_severity="warning",
        )

        assert decision.auto_execution_approved is False
        assert decision.evidence_complete is False

    @pytest.mark.unit
    async def test_empty_causal_chain_blocks(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(
            incident_id=iid,
            causal_chain=(),
        )
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run,
            settings=_permissive_settings(),
            alert_severity="warning",
        )

        assert decision.auto_execution_approved is False
        assert decision.evidence_complete is False


class TestPolicyGateDefaultDeny:
    @pytest.mark.unit
    async def test_default_deny_always_denies(self):
        """Default-deny config: impossible to auto-approve."""
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid, confidence=0.99)
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        default_settings = PolicyMatrixSettings()

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run, settings=default_settings
        )

        assert decision.auto_execution_approved is False
        failed_dims = [d for d in decision.dimensions if not d.passed]
        assert len(failed_dims) >= 1


class TestPolicyGateDryRunFailed:
    @pytest.mark.unit
    async def test_dry_run_failed_blocks(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid)
        dry_run = _make_dry_run(
            incident_id=iid, plan_id=plan.id, overall_passed=False
        )

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run,
            settings=_permissive_settings(),
            alert_severity="warning",
        )

        assert decision.auto_execution_approved is False
        assert "dry-run" in decision.reasoning.lower()


class TestPolicyGateSeverityDimension:
    @pytest.mark.unit
    async def test_severity_below_threshold_fails(self):
        """Alert severity 'critical' is not in auto-approve list ['info']."""
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid)
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        settings = PolicyMatrixSettings(
            severity_auto_approve=["info"],
            blast_radius_auto_approve=["workload"],
            confidence_minimum=0.5,
        )

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run, settings=settings,
            alert_severity="critical",
        )

        severity_dim = next(d for d in decision.dimensions if d.name == "severity")
        assert severity_dim.passed is False

    @pytest.mark.unit
    async def test_severity_none_uses_unknown(self):
        """When alert_severity is None, defaults to 'unknown'."""
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid)
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        settings = PolicyMatrixSettings(
            severity_auto_approve=["info"],
            blast_radius_auto_approve=["workload"],
            confidence_minimum=0.5,
        )

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run, settings=settings,
            alert_severity=None,
        )

        severity_dim = next(d for d in decision.dimensions if d.name == "severity")
        assert severity_dim.value == "unknown"
        assert severity_dim.passed is False


class TestPolicyGateBlastRadiusDimension:
    @pytest.mark.unit
    async def test_blast_radius_above_threshold_fails(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid, blast_radius=BlastRadius.CLUSTER)
        artifact = _make_artifact(incident_id=iid)
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        settings = PolicyMatrixSettings(
            severity_auto_approve=["info", "warning", "critical"],
            blast_radius_auto_approve=["workload"],
            confidence_minimum=0.5,
        )

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run, settings=settings,
            alert_severity="warning",
        )

        br_dim = next(d for d in decision.dimensions if d.name == "blast_radius")
        assert br_dim.passed is False
        assert decision.auto_execution_approved is False


class TestPolicyGateConfidenceDimension:
    @pytest.mark.unit
    async def test_confidence_below_threshold_fails(self):
        iid = uuid.uuid4()
        plan = _make_plan(incident_id=iid)
        artifact = _make_artifact(incident_id=iid, confidence=0.3)
        dry_run = _make_dry_run(incident_id=iid, plan_id=plan.id)

        settings = PolicyMatrixSettings(
            severity_auto_approve=["info", "warning", "critical"],
            blast_radius_auto_approve=["workload"],
            confidence_minimum=0.8,
        )

        decision = await evaluate_policy_gate(
            plan, artifact, dry_run, settings=settings,
            alert_severity="warning",
        )

        conf_dim = next(d for d in decision.dimensions if d.name == "confidence")
        assert conf_dim.passed is False
        assert decision.auto_execution_approved is False
