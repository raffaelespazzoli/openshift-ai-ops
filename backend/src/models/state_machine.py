"""Incident state machine with canonical transitions.

All incident state changes MUST go through the transition() function.
Direct writes to the state column are forbidden (AD-19).
"""

from __future__ import annotations

from enum import StrEnum


class IncidentState(StrEnum):
    RECEIVED = "received"
    CORRELATING = "correlating"
    QUEUED = "queued"
    DIAGNOSING = "diagnosing"
    DIAGNOSED = "diagnosed"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    OBSERVING = "observing"
    RESOLVED = "resolved"
    FAILED = "failed"
    CANCELLED = "cancelled"


VALID_TRANSITIONS: dict[IncidentState, list[IncidentState]] = {
    IncidentState.RECEIVED: [IncidentState.CORRELATING],
    IncidentState.CORRELATING: [IncidentState.QUEUED],
    IncidentState.QUEUED: [
        IncidentState.DIAGNOSING,
        IncidentState.DIAGNOSED,
        IncidentState.CANCELLED,
    ],
    IncidentState.DIAGNOSING: [IncidentState.DIAGNOSED, IncidentState.FAILED, IncidentState.QUEUED],
    IncidentState.DIAGNOSED: [
        IncidentState.PLANNING,
        IncidentState.AWAITING_APPROVAL,
        IncidentState.EXECUTING,
    ],
    IncidentState.PLANNING: [IncidentState.AWAITING_APPROVAL, IncidentState.FAILED],
    IncidentState.AWAITING_APPROVAL: [IncidentState.EXECUTING, IncidentState.FAILED],
    IncidentState.EXECUTING: [IncidentState.OBSERVING],
    IncidentState.OBSERVING: [IncidentState.RESOLVED, IncidentState.FAILED],
}

TERMINAL_STATES: frozenset[IncidentState] = frozenset(
    {IncidentState.RESOLVED, IncidentState.FAILED, IncidentState.CANCELLED}
)


def initial_state() -> IncidentState:
    """Return the canonical initial state for new incidents.

    All incident creation MUST call this function rather than
    referencing IncidentState.RECEIVED directly (AD-19).
    """
    return IncidentState.RECEIVED


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_state: IncidentState, target_state: IncidentState) -> None:
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(
            f"Invalid transition: {current_state.value} → {target_state.value}"
        )


def transition(current_state: IncidentState, target_state: IncidentState) -> IncidentState:
    """Transition an incident from current_state to target_state.

    Args:
        current_state: The current state of the incident.
        target_state: The desired next state.

    Returns:
        The new state (target_state) if the transition is valid.

    Raises:
        InvalidTransitionError: If the transition is not permitted.
    """
    if current_state in TERMINAL_STATES:
        raise InvalidTransitionError(current_state, target_state)

    allowed = VALID_TRANSITIONS.get(current_state, [])
    if target_state not in allowed:
        raise InvalidTransitionError(current_state, target_state)

    return target_state
