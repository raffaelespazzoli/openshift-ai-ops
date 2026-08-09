"""Structured Diagnosis Object and related models (AD-4, AD-15).

Defines the typed artifacts produced by the diagnosis pipeline stage.
DiagnosisObject is the immutable handoff artifact that crosses the
RBAC Airlock boundary to the remediation stage.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class EvidenceSource(StrEnum):
    MCP_CLUSTER = "mcp_cluster"
    RUNBOOK = "runbook"
    RHOKP = "rhokp"
    LEARNING_STORE = "learning_store"
    AGENTIC_SKILL = "agentic_skill"


class EvidenceArtifact(BaseModel):
    """A single piece of evidence gathered during diagnosis."""

    model_config = {"frozen": True}

    source: EvidenceSource
    query: str
    result: str
    timestamp: datetime


class EvidenceGap(BaseModel):
    """Records a query that could not be fulfilled (AD-15 partial evidence)."""

    model_config = {"frozen": True}

    query: str
    reason: str
    timeout_seconds: float | None = None


# Root-cause taxonomy — slash-delimited codes: {subsystem}/{failure-mode}
ROOT_CAUSE_TAXONOMY: frozenset[str] = frozenset({
    "node/memory-pressure",
    "node/disk-pressure",
    "node/not-ready",
    "node/pid-pressure",
    "storage/pvc-stuck-pending",
    "storage/volume-mount-failed",
    "storage/capacity-exceeded",
    "network/dns-failure",
    "network/service-unreachable",
    "network/ingress-misconfigured",
    "workload/crash-loop-backoff",
    "workload/oom-killed",
    "workload/image-pull-failed",
    "platform/etcd-latency",
    "platform/api-server-slow",
    "platform/scheduler-unschedulable",
    "unknown/unclassified",
})

VALID_SUBSYSTEMS: frozenset[str] = frozenset({
    code.split("/")[0] for code in ROOT_CAUSE_TAXONOMY
})


def _validate_root_cause_code(code: str) -> str:
    """Validate that a root-cause code is a member of the controlled taxonomy."""
    if "/" not in code:
        raise ValueError(
            f"Root-cause code must be slash-delimited (subsystem/failure-mode), got: {code!r}"
        )
    if code not in ROOT_CAUSE_TAXONOMY:
        raise ValueError(
            f"Root-cause code {code!r} is not in the controlled taxonomy. "
            f"Valid codes: {sorted(ROOT_CAUSE_TAXONOMY)}"
        )
    return code


class DiagnosisObject(BaseModel):
    """Structured diagnosis artifact produced by the diagnosis pipeline stage."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    root_cause_component: str
    failure_mode: str
    root_cause_code: str
    causal_chain: list[str]
    affected_resources: list[str]
    evidence: list[EvidenceArtifact]
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    agent_summary: str = ""
    coverage_gaps: list[str] = Field(default_factory=list)
    alternative_hypotheses: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _validate_root_cause_fields(self) -> DiagnosisObject:
        _validate_root_cause_code(self.root_cause_code)
        expected_code = f"{self.root_cause_component}/{self.failure_mode}"
        if self.root_cause_code != expected_code:
            raise ValueError(
                f"root_cause_code ({self.root_cause_code!r}) must equal "
                f"root_cause_component/failure_mode ({expected_code!r})"
            )
        return self

    def root_cause_hash(self) -> str:
        """Deterministic hash for comparing two diagnoses (AC #6)."""
        canonical = (
            f"{self.root_cause_component}|"
            f"{self.failure_mode}|"
            f"{'|'.join(sorted(self.causal_chain))}"
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


class ImmutableDiagnosisArtifact(BaseModel):
    """Frozen snapshot of a DiagnosisObject for RBAC Airlock handoff.

    Once created, no fields can be modified. This is the artifact
    that crosses the diagnosis → remediation boundary.
    """

    model_config = {"frozen": True}

    id: uuid.UUID
    incident_id: uuid.UUID
    root_cause_component: str
    failure_mode: str
    root_cause_code: str
    causal_chain: tuple[str, ...]
    affected_resources: tuple[str, ...]
    evidence: tuple[EvidenceArtifact, ...]
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    agent_summary: str = ""
    coverage_gaps: tuple[str, ...] = ()
    alternative_hypotheses: tuple[dict, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def root_cause_hash(self) -> str:
        """Deterministic hash matching DiagnosisObject.root_cause_hash()."""
        canonical = (
            f"{self.root_cause_component}|"
            f"{self.failure_mode}|"
            f"{'|'.join(sorted(self.causal_chain))}"
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def from_diagnosis(cls, diag: DiagnosisObject) -> ImmutableDiagnosisArtifact:
        """Freeze a mutable DiagnosisObject into an immutable artifact."""
        return cls(
            id=diag.id,
            incident_id=diag.incident_id,
            root_cause_component=diag.root_cause_component,
            failure_mode=diag.failure_mode,
            root_cause_code=diag.root_cause_code,
            causal_chain=tuple(diag.causal_chain),
            affected_resources=tuple(diag.affected_resources),
            evidence=tuple(diag.evidence),
            evidence_gaps=tuple(diag.evidence_gaps),
            confidence=diag.confidence,
            agent_summary=diag.agent_summary,
            coverage_gaps=tuple(diag.coverage_gaps),
            alternative_hypotheses=tuple(diag.alternative_hypotheses),
            created_at=diag.created_at,
        )
