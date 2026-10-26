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
}

# Every real move: 5 x 5 statuses minus the 5 "same status" pairs.
REAL_MOVES = list(permutations(STATUSES, 2))


def test_there_are_20_real_moves():
    assert len(REAL_MOVES) == 20


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
