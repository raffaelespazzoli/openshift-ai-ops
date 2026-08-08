"""Shared typed models — THE contract (AD-4).

This module is a leaf dependency. It imports nothing from the rest of the project.
All other modules import from here.
"""

from .alert import Alert, AlertStatus
from .events import EventBus, EventHandler
from .incident import Incident, Severity
from .state_machine import (
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    IncidentState,
    InvalidTransitionError,
    transition,
)

__all__ = [
    "Alert",
    "AlertStatus",
    "EventBus",
    "EventHandler",
    "Incident",
    "IncidentState",
    "InvalidTransitionError",
    "Severity",
    "TERMINAL_STATES",
    "VALID_TRANSITIONS",
    "transition",
]
