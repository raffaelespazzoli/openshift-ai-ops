"""Unit tests for the incident state machine."""

import pytest

from src.models.state_machine import (
    VALID_TRANSITIONS,
    IncidentState,
    InvalidTransitionError,
    transition,
)


class TestValidTransitions:
    """Test that all valid transitions succeed."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "current,target",
        [
            (IncidentState.RECEIVED, IncidentState.CORRELATING),
            (IncidentState.CORRELATING, IncidentState.QUEUED),
            (IncidentState.QUEUED, IncidentState.DIAGNOSING),
            (IncidentState.QUEUED, IncidentState.DIAGNOSED),
            (IncidentState.QUEUED, IncidentState.CANCELLED),
            (IncidentState.DIAGNOSING, IncidentState.DIAGNOSED),
            (IncidentState.DIAGNOSING, IncidentState.FAILED),
            (IncidentState.DIAGNOSED, IncidentState.AWAITING_APPROVAL),
            (IncidentState.DIAGNOSED, IncidentState.EXECUTING),
            (IncidentState.AWAITING_APPROVAL, IncidentState.EXECUTING),
            (IncidentState.AWAITING_APPROVAL, IncidentState.FAILED),
            (IncidentState.EXECUTING, IncidentState.OBSERVING),
            (IncidentState.OBSERVING, IncidentState.RESOLVED),
            (IncidentState.OBSERVING, IncidentState.FAILED),
        ],
    )
    def test_valid_transition_succeeds(self, current: IncidentState, target: IncidentState):
        result = transition(current, target)
        assert result == target

    @pytest.mark.unit
    def test_all_valid_transitions_covered(self):
        """Ensure every transition in the adjacency list is testable."""
        for state, targets in VALID_TRANSITIONS.items():
            for target in targets:
                assert transition(state, target) == target


class TestInvalidTransitions:
    """Test that invalid transitions raise InvalidTransitionError."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "current,target",
        [
            (IncidentState.RECEIVED, IncidentState.EXECUTING),
            (IncidentState.RECEIVED, IncidentState.RESOLVED),
            (IncidentState.CORRELATING, IncidentState.DIAGNOSING),
            (IncidentState.QUEUED, IncidentState.OBSERVING),
            (IncidentState.EXECUTING, IncidentState.DIAGNOSED),
            (IncidentState.OBSERVING, IncidentState.QUEUED),
        ],
    )
    def test_invalid_transition_raises(self, current: IncidentState, target: IncidentState):
        with pytest.raises(InvalidTransitionError) as exc_info:
            transition(current, target)
        assert exc_info.value.current_state == current
        assert exc_info.value.target_state == target

    @pytest.mark.unit
    @pytest.mark.parametrize("terminal", [IncidentState.RESOLVED, IncidentState.FAILED, IncidentState.CANCELLED])
    def test_terminal_state_no_outgoing(self, terminal: IncidentState):
        """Terminal states cannot transition to anything."""
        with pytest.raises(InvalidTransitionError):
            transition(terminal, IncidentState.RECEIVED)
