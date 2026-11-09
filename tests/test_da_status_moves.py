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
    # Phase 6, Build (spec section 2).
    ("READY_TO_BUILD", "BUILDING"),
    ("BUILDING", "READY_TO_BUILD"),
    ("BUILDING", "NOT_PASSING"),
    ("BUILDING", "ESCALATION_REQUIRED"),
    ("READY_FOR_REVIEW", "ESCALATION_REQUIRED"),
    ("NOT_PASSING", "ESCALATION_REQUIRED"),
    ("READY_FOR_REVIEW", "BUILDING"),
    ("NOT_PASSING", "BUILDING"),
    # Phase 7, Independent Tester (spec section 3).
    ("BUILDING", "TESTER_REVIEW"),
    ("TESTER_REVIEW", "BUILDING"),
    ("TESTER_REVIEW", "READY_FOR_REVIEW"),
    ("TESTER_REVIEW", "NOT_PASSING"),
    ("TESTER_REVIEW", "READY_TO_BUILD"),
    ("TESTER_REVIEW", "ESCALATION_REQUIRED"),
    ("READY_FOR_REVIEW", "TESTER_REVIEW"),
    # Phase 8, Refine (spec section 10).
    ("READY_FOR_REVIEW", "REVISION_IN_PROGRESS"),
    ("NOT_PASSING", "REVISION_IN_PROGRESS"),
    ("BUILDING", "READY_FOR_REVIEW"),  # Stop build on a check run
    ("REVISION_IN_PROGRESS", "CLARIFICATION_IN_PROGRESS"),
    ("REVISION_IN_PROGRESS", "READY_FOR_CONFIRMATION"),
    ("REVISION_IN_PROGRESS", "APPROACH_PROPOSED"),
    ("REVISION_IN_PROGRESS", "BUILDING"),
    ("REVISION_IN_PROGRESS", "READY_FOR_REVIEW"),
    ("REVISION_IN_PROGRESS", "NOT_PASSING"),
    ("REVISION_IN_PROGRESS", "ESCALATION_REQUIRED"),
}

# Every real move: 17 x 17 statuses minus the 17 "same status" pairs.
REAL_MOVES = list(permutations(STATUSES, 2))


def test_there_are_272_real_moves():
    assert len(REAL_MOVES) == 272


def test_confirmed_for_discovery_moves_only_to_searching():
    assert ALLOWED_MOVES["CONFIRMED_FOR_DISCOVERY"] == ("SEARCHING",)


def test_final_statuses_have_no_moves_yet():
    assert ALLOWED_MOVES["ESCALATION_REQUIRED"] == ()


def test_moves_out_of_ready_to_build():
    assert set(ALLOWED_MOVES["READY_TO_BUILD"]) == {
        "APPROACH_PROPOSED",
        "BUILDING",
        "ESCALATION_REQUIRED",
    }


def test_build_moves():
    # Phase 7: every pass goes through the Tester. Phase 8: only Stop build on a check run goes
    # straight back to READY_FOR_REVIEW.
    assert set(ALLOWED_MOVES["BUILDING"]) == {
        "READY_TO_BUILD",
        "TESTER_REVIEW",
        "NOT_PASSING",
        "READY_FOR_REVIEW",
        "ESCALATION_REQUIRED",
    }
    # Only Get help and "Re-scan and build again" leave a finished build before Phase 8.
    # Phase 8 adds REVISION_IN_PROGRESS (a lane is chosen) to both finished statuses.
    assert set(ALLOWED_MOVES["NOT_PASSING"]) == {
        "BUILDING",
        "ESCALATION_REQUIRED",
        "REVISION_IN_PROGRESS",
    }
    # READY_FOR_REVIEW also has "Run the Tester review again" (Phase 7, D-D).
    assert set(ALLOWED_MOVES["READY_FOR_REVIEW"]) == {
        "BUILDING",
        "ESCALATION_REQUIRED",
        "TESTER_REVIEW",
        "REVISION_IN_PROGRESS",
    }


def test_8_revision_moves():
    assert set(ALLOWED_MOVES["REVISION_IN_PROGRESS"]) == {
        "CLARIFICATION_IN_PROGRESS",
        "READY_FOR_CONFIRMATION",
        "APPROACH_PROPOSED",
        "BUILDING",
        "READY_FOR_REVIEW",
        "NOT_PASSING",
        "ESCALATION_REQUIRED",
    }


def test_7_tester_review_moves():
    assert set(ALLOWED_MOVES["TESTER_REVIEW"]) == {
        "BUILDING",
        "READY_FOR_REVIEW",
        "NOT_PASSING",
        "READY_TO_BUILD",
        "ESCALATION_REQUIRED",
    }


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
