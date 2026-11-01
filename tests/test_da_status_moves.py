from itertools import permutations

import pytest

from pydantic_classes.da_models import (
    ALLOWED_MOVES,
    STATUSES,
    StatusMoveError,
    check_status_move,
    display_status,
)

# The spec 3.1 table, written out again by hand so a change to ALLOWED_MOVES is caught.
SPEC_TABLE = {
    ("DRAFT", "CLARIFICATION_IN_PROGRESS"),
    ("CLARIFICATION_IN_PROGRESS", "DECISION_REQUIRED"),
    ("CLARIFICATION_IN_PROGRESS", "READY_FOR_CONFIRMATION"),
    ("DECISION_REQUIRED", "CLARIFICATION_IN_PROGRESS"),
    ("READY_FOR_CONFIRMATION", "CONFIRMED_FOR_DISCOVERY"),
    ("READY_FOR_CONFIRMATION", "CLARIFICATION_IN_PROGRESS"),
    ("READY_FOR_CONFIRMATION", "DECISION_REQUIRED"),
    # Phase 3, Discover (spec section 2).
    ("CONFIRMED_FOR_DISCOVERY", "SEARCHING"),
    ("SEARCHING", "SIMILAR_IMPLEMENTATION_FOUND"),
    ("SEARCHING", "NO_RELIABLE_MATCH"),
    ("SIMILAR_IMPLEMENTATION_FOUND", "DISCOVERY_CONFIRMED"),
    ("SIMILAR_IMPLEMENTATION_FOUND", "SEARCHING"),
    ("SIMILAR_IMPLEMENTATION_FOUND", "ESCALATION_REQUIRED"),
    ("NO_RELIABLE_MATCH", "DISCOVERY_CONFIRMED"),
    ("NO_RELIABLE_MATCH", "SEARCHING"),
    ("NO_RELIABLE_MATCH", "ESCALATION_REQUIRED"),
    # Phase 4, Approach (spec section 2).
    ("DISCOVERY_CONFIRMED", "APPROACH_PROPOSED"),
    ("APPROACH_PROPOSED", "READY_TO_BUILD"),
    ("APPROACH_PROPOSED", "ESCALATION_REQUIRED"),
    # Phase 5, Workspace (spec section 2).
    ("READY_TO_BUILD", "APPROACH_PROPOSED"),
    ("READY_TO_BUILD", "ESCALATION_REQUIRED"),
}

# Every real move: 12 x 12 statuses minus the 12 "same status" pairs.
REAL_MOVES = list(permutations(STATUSES, 2))


def test_there_are_132_real_moves():
    assert len(REAL_MOVES) == 132


def test_confirmed_for_discovery_moves_only_to_searching():
    assert ALLOWED_MOVES["CONFIRMED_FOR_DISCOVERY"] == ("SEARCHING",)


def test_final_statuses_have_no_moves_yet():
    assert ALLOWED_MOVES["ESCALATION_REQUIRED"] == ()


def test_workspace_moves_out_of_ready_to_build():
    assert ALLOWED_MOVES["READY_TO_BUILD"] == ("APPROACH_PROPOSED", "ESCALATION_REQUIRED")


def test_approach_moves():
    assert ALLOWED_MOVES["DISCOVERY_CONFIRMED"] == ("APPROACH_PROPOSED",)
    assert ALLOWED_MOVES["APPROACH_PROPOSED"] == ("READY_TO_BUILD", "ESCALATION_REQUIRED")


def test_allowed_moves_match_the_spec_table():
    coded = {(old, new) for old, targets in ALLOWED_MOVES.items() for new in targets}

    assert coded == SPEC_TABLE


@pytest.mark.parametrize(("old", "new"), REAL_MOVES)
def test_every_real_move_is_allowed_only_if_in_the_table(old, new):
    if (old, new) in SPEC_TABLE:
        check_status_move(old, new)
    else:
        with pytest.raises(StatusMoveError, match=f"cannot move from {old} to {new}"):
            check_status_move(old, new)


def test_status_is_shown_with_spaces():
    assert display_status("CONFIRMED_FOR_DISCOVERY") == "CONFIRMED FOR DISCOVERY"
