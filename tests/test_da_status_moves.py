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
    # Phase 9, Enhance: Get help at the Find steps and at the safety-net steps.
    ("DRAFT", "ESCALATION_REQUIRED"),
    ("DISCOVERY_CONFIRMED", "ESCALATION_REQUIRED"),
    # Phase 9 code review round 2: a request switched from card 1 keeps its Understand status.
    ("CLARIFICATION_IN_PROGRESS", "ESCALATION_REQUIRED"),
    ("DECISION_REQUIRED", "ESCALATION_REQUIRED"),
    ("READY_FOR_CONFIRMATION", "ESCALATION_REQUIRED"),
    # Phase 10: handoff, and a senior's Return (the code checks the STORED status; the table
    # lists every status a request can be escalated from).
    ("READY_FOR_REVIEW", "HANDED_OFF"),
}
# Return moves: ESCALATION_REQUIRED back to every status that has a move into it.
SPEC_TABLE |= {
    ("ESCALATION_REQUIRED", old) for old, new in list(SPEC_TABLE) if new == "ESCALATION_REQUIRED"
}

# Every real move: 18 x 18 statuses minus the 18 "same status" pairs.
REAL_MOVES = list(permutations(STATUSES, 2))


def test_there_are_306_real_moves():
    assert len(REAL_MOVES) == 306


def test_confirmed_for_discovery_moves_only_to_searching():
    assert ALLOWED_MOVES["CONFIRMED_FOR_DISCOVERY"] == ("SEARCHING",)


def test_handed_off_has_no_moves_out_and_only_the_developer_gets_in():
    assert ALLOWED_MOVES["HANDED_OFF"] == ()
    into = {old for old, targets in ALLOWED_MOVES.items() if "HANDED_OFF" in targets}
    assert into == {"READY_FOR_REVIEW"}


def test_escalation_moves_back_only_to_statuses_it_can_come_from_never_to_handed_off():
    back = set(ALLOWED_MOVES["ESCALATION_REQUIRED"])
    came_from = {old for old, targets in ALLOWED_MOVES.items() if "ESCALATION_REQUIRED" in targets}
    assert back == came_from
    assert "HANDED_OFF" not in back
    assert "DRAFT" in back
    assert "ESCALATION_REQUIRED" not in back


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
    # Phase 10 adds HANDED_OFF (the final check passed).
    assert set(ALLOWED_MOVES["READY_FOR_REVIEW"]) == {
        "BUILDING",
        "ESCALATION_REQUIRED",
        "TESTER_REVIEW",
        "REVISION_IN_PROGRESS",
        "HANDED_OFF",
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
    assert ALLOWED_MOVES["DISCOVERY_CONFIRMED"] == ("APPROACH_PROPOSED", "ESCALATION_REQUIRED")
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
