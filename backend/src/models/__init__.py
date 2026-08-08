"""Shared typed models — THE contract (AD-4).

This module is a leaf dependency. It imports nothing from the rest of the project.
All other modules import from here.
"""

from .alert import Alert, AlertStatus
from .api import (
    ERROR_INTERNAL,
    ERROR_NOT_FOUND,
    ERROR_UNAUTHORIZED,
    ERROR_VALIDATION,
    ApiError,
    ApiMeta,
    ApiResponse,
)
from .events import BusEvent, EventBus, EventNames, SSEEventData
from .incident import Incident, Severity
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
    "ApiError",
    "ApiMeta",
    "ApiResponse",
    "BusEvent",
    "CorrelationEvidence",
    "CorrelationLayer",
    "ERROR_INTERNAL",
    "ERROR_NOT_FOUND",
    "ERROR_UNAUTHORIZED",
    "ERROR_VALIDATION",
    "EventBus",
    "EventNames",
    "Incident",
    "IncidentState",
    "InvalidTransitionError",
    "initial_state",
    "RootCauseEvent",
    "SSEEventData",
    "Severity",
    "TERMINAL_STATES",
    "VALID_TRANSITIONS",
    "WebhookAlertStatus",
    "transition",
]
