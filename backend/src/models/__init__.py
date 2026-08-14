"""Shared typed models — THE contract (AD-4).

This module is a leaf dependency. It imports nothing from the rest of the project.
All other modules import from here.
"""

from .alert import Alert, AlertStatus
from .api import (
    ERROR_CONFLICT,
    ERROR_INTERNAL,
    ERROR_NOT_FOUND,
    ERROR_UNAUTHORIZED,
    ERROR_VALIDATION,
    ApiError,
    ApiMeta,
    ApiResponse,
)
from .approval import (
    ApprovalContext,
    ApprovalRecord,
    PolicyAdjustmentRequest,
    RejectionRequest,
)
from .diagnosis import (
    ROOT_CAUSE_TAXONOMY,
    VALID_SUBSYSTEMS,
    DiagnosisObject,
    EvidenceArtifact,
    EvidenceGap,
    EvidenceSource,
    ImmutableDiagnosisArtifact,
)
from .events import BusEvent, EventBus, EventNames, SSEEventData
from .skeptic import SkepticChallenge, SkepticRebuttal, SkepticResponse, SkepticVerdict
from .incident import Incident, Severity
from .remediation import (
    BlastRadius,
    Precondition,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from .remediation_skeptic import RemediationSkepticChallenge, RemediationSkepticVerdict
from .policy_gate import (
    DryRunResult,
    DryRunStepResult,
    PolicyDecision,
    PolicyDimension,
    PolicyMatrix,
)
from .case_record import CaseRecord, CaseRecordSummary
from .execution import (
    ExecutionLog,
    ExecutionStepLog,
    OutcomeConfidence,
    OutcomeResult,
    RollbackRecord,
)
from .knowledge import CompletenessResult, RunbookChunk
from .root_cause_event import CorrelationEvidence, CorrelationLayer, RootCauseEvent
from .state_machine import (
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    IncidentState,
    InvalidTransitionError,
    initial_state,
    transition,
)
from .webhook import AlertManagerAlert, AlertManagerWebhook, WebhookAlertStatus

__all__ = [
    "Alert",
    "AlertManagerAlert",
    "AlertManagerWebhook",
    "AlertStatus",
    "ApprovalContext",
    "ApprovalRecord",
    "ApiError",
    "BlastRadius",
    "ApiMeta",
    "ApiResponse",
    "BusEvent",
    "CaseRecord",
    "CaseRecordSummary",
    "CompletenessResult",
    "CorrelationEvidence",
    "CorrelationLayer",
    "DryRunResult",
    "DryRunStepResult",
    "DiagnosisObject",
    "ERROR_CONFLICT",
    "ERROR_INTERNAL",
    "ERROR_NOT_FOUND",
    "ERROR_UNAUTHORIZED",
    "ERROR_VALIDATION",
    "EventBus",
    "EventNames",
    "EvidenceArtifact",
    "EvidenceGap",
    "EvidenceSource",
    "ExecutionLog",
    "ExecutionStepLog",
    "ImmutableDiagnosisArtifact",
    "Incident",
    "IncidentState",
    "InvalidTransitionError",
    "OutcomeConfidence",
    "OutcomeResult",
    "PolicyDecision",
    "PolicyDimension",
    "PolicyMatrix",
    "PolicyAdjustmentRequest",
    "Precondition",
    "RemediationPlan",
    "RejectionRequest",
    "RemediationSkepticChallenge",
    "RemediationSkepticVerdict",
    "RemediationStep",
    "RiskLevel",
    "RollbackRecord",
    "ROOT_CAUSE_TAXONOMY",
    "RootCauseEvent",
    "RunbookChunk",
    "SSEEventData",
    "Severity",
    "SkepticChallenge",
    "SkepticRebuttal",
    "SkepticResponse",
    "SkepticVerdict",
    "TERMINAL_STATES",
    "VALID_SUBSYSTEMS",
    "VALID_TRANSITIONS",
    "WebhookAlertStatus",
    "initial_state",
    "transition",
]
