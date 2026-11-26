"""Data shapes for the Developer Assistant: a Request and its AuditEvents."""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# CVDA-YYYY-NNNN. Four or more digits, so number 10000 still fits in a busy year.
REQUEST_ID_PATTERN = r"^CVDA-\d{4}-\d{4,}$"

# Statuses are stored as upper-case codes (spec 3.1). NEW from Phase 0 became DRAFT (decision D-B).
STATUS_DRAFT = "DRAFT"
STATUS_CLARIFICATION = "CLARIFICATION_IN_PROGRESS"
STATUS_DECISION_REQUIRED = "DECISION_REQUIRED"
STATUS_READY = "READY_FOR_CONFIRMATION"
STATUS_CONFIRMED = "CONFIRMED_FOR_DISCOVERY"
# Phase 3 (Discover), spec section 2.
STATUS_SEARCHING = "SEARCHING"
STATUS_SIMILAR_FOUND = "SIMILAR_IMPLEMENTATION_FOUND"
STATUS_NO_MATCH = "NO_RELIABLE_MATCH"
STATUS_DISCOVERY_CONFIRMED = "DISCOVERY_CONFIRMED"
STATUS_ESCALATION = "ESCALATION_REQUIRED"
# Phase 4 (Approach), spec section 2.
STATUS_APPROACH_PROPOSED = "APPROACH_PROPOSED"
STATUS_READY_TO_BUILD = "READY_TO_BUILD"
# Phase 6 (Build + test loop), spec section 2. TESTING and TESTER_REVIEW are not used yet.
STATUS_BUILDING = "BUILDING"
STATUS_READY_FOR_REVIEW = "READY_FOR_REVIEW"
STATUS_NOT_PASSING = "NOT_PASSING"
# Phase 7 (Independent Tester), spec section 3. TESTING stays unused.
STATUS_TESTER_REVIEW = "TESTER_REVIEW"
# Phase 8 (Refine), spec section 10: from the lane click until the lane hands over (D-A option 1).
STATUS_REVISION = "REVISION_IN_PROGRESS"
# Phase 10 (Handoff), spec section 3: the request is checked in and locked. No moves out.
STATUS_HANDED_OFF = "HANDED_OFF"
# Fix G5 part 1: the safety check stopped the request. Read only until Admin releases it.
STATUS_STOPPED = "STOPPED"

STATUSES: tuple[str, ...] = (
    STATUS_DRAFT,
    STATUS_CLARIFICATION,
    STATUS_DECISION_REQUIRED,
    STATUS_READY,
    STATUS_CONFIRMED,
    STATUS_SEARCHING,
    STATUS_SIMILAR_FOUND,
    STATUS_NO_MATCH,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_ESCALATION,
    STATUS_APPROACH_PROPOSED,
    STATUS_READY_TO_BUILD,
    STATUS_BUILDING,
    STATUS_READY_FOR_REVIEW,
    STATUS_NOT_PASSING,
    STATUS_TESTER_REVIEW,
    STATUS_REVISION,
    STATUS_HANDED_OFF,
    STATUS_STOPPED,
)

# The only moves allowed: the spec 3.1 table, plus the Discover moves of Phase 3 (spec section 2).
ALLOWED_MOVES: dict[str, tuple[str, ...]] = {
    # Phase 9: Get help while finding the program (steps e_*) leaves from DRAFT.
    STATUS_DRAFT: (STATUS_CLARIFICATION, STATUS_ESCALATION),
    # Phase 9: a request switched from card 1 keeps its Understand status, so Get help at the
    # Enhance steps (e_pick, e_stale, e_fresh) must leave from these three too.
    STATUS_CLARIFICATION: (STATUS_DECISION_REQUIRED, STATUS_READY, STATUS_ESCALATION),
    STATUS_DECISION_REQUIRED: (STATUS_CLARIFICATION, STATUS_ESCALATION),
    STATUS_READY: (
        STATUS_CONFIRMED, STATUS_CLARIFICATION, STATUS_DECISION_REQUIRED, STATUS_ESCALATION,
    ),
    # Phase 10 trigger 2a: a record confirmed with a scope conflict goes to a senior right away.
    STATUS_CONFIRMED: (STATUS_SEARCHING, STATUS_ESCALATION),
    STATUS_SEARCHING: (STATUS_SIMILAR_FOUND, STATUS_NO_MATCH),
    STATUS_SIMILAR_FOUND: (STATUS_DISCOVERY_CONFIRMED, STATUS_SEARCHING, STATUS_ESCALATION),
    STATUS_NO_MATCH: (STATUS_DISCOVERY_CONFIRMED, STATUS_SEARCHING, STATUS_ESCALATION),
    # Phase 9: Get help during the safety net (steps s_*) leaves from DISCOVERY_CONFIRMED.
    # Fix G7 D1: "Search again" when the index came after Discovery and no plan exists yet.
    STATUS_DISCOVERY_CONFIRMED: (STATUS_APPROACH_PROPOSED, STATUS_SEARCHING, STATUS_ESCALATION),
    STATUS_APPROACH_PROPOSED: (STATUS_READY_TO_BUILD, STATUS_ESCALATION),
    # Phase 5 (Workspace): "Change the approach" and "Get help" from a blocked workspace check.
    # Phase 6 (Build): Build starts a build. The escalation inbox comes in Phase 10.
    STATUS_READY_TO_BUILD: (STATUS_APPROACH_PROPOSED, STATUS_BUILDING, STATUS_ESCALATION),
    # Stop build and "unable to write tests" go back to READY_TO_BUILD; a used-up budget ends in
    # NOT_PASSING. Phase 7: a pass goes to TESTER_REVIEW first (BUILDING to READY_FOR_REVIEW is
    # gone: every pass is reviewed by the independent Tester).
    # Phase 8: Stop build on a check run goes back to READY_FOR_REVIEW (NOT_PASSING is above).
    STATUS_BUILDING: (
        STATUS_READY_TO_BUILD,
        STATUS_TESTER_REVIEW,
        STATUS_NOT_PASSING,
        STATUS_READY_FOR_REVIEW,
        STATUS_ESCALATION,
    ),
    # Phase 7 (spec section 3): Must fix with budget left goes back to BUILDING; a clean or
    # unassessable review ends in READY_FOR_REVIEW; Stop build and Get help as in Phase 6.
    STATUS_TESTER_REVIEW: (
        STATUS_BUILDING,
        STATUS_READY_FOR_REVIEW,
        STATUS_NOT_PASSING,
        STATUS_READY_TO_BUILD,
        STATUS_ESCALATION,
    ),
    # Get help, "Re-scan and build again" after the edit guard stopped the write (B9), and
    # "Run the Tester review again" when the label is Unable to assess (Phase 7, D-D).
    # Phase 8: choosing a lane moves to REVISION_IN_PROGRESS.
    STATUS_READY_FOR_REVIEW: (
        STATUS_BUILDING,
        STATUS_ESCALATION,
        STATUS_TESTER_REVIEW,
        STATUS_REVISION,
        STATUS_HANDED_OFF,  # Phase 10: the developer's Ready for handoff, after the final check
    ),
    STATUS_NOT_PASSING: (STATUS_BUILDING, STATUS_ESCALATION, STATUS_REVISION),
    # Phase 8 (spec section 10). Requirement lane: Understand in revision mode (clarifying
    # questions, then the checkpoint READY_FOR_CONFIRMATION), or straight to the approach.
    # Approach lane: APPROACH_PROPOSED. Bug lane and Fix it: BUILDING. Cancel: back to where
    # Refine started (READY_FOR_REVIEW or NOT_PASSING). Get help: ESCALATION_REQUIRED.
    STATUS_REVISION: (
        STATUS_CLARIFICATION,
        STATUS_READY,
        STATUS_APPROACH_PROPOSED,
        STATUS_BUILDING,
        STATUS_READY_FOR_REVIEW,
        STATUS_NOT_PASSING,
        STATUS_ESCALATION,
    ),
    STATUS_ESCALATION: (),
    STATUS_HANDED_OFF: (),  # Phase 10: locked for good (spec section 4)
}
# Phase 10 (spec section 3): a senior's Return sends the request back to where it came from. The
# table lists every status a request can be escalated from; the escalation code checks that the
# move is to the one STORED on the escalation row. Never to HANDED_OFF: only the developer hands
# off.
ALLOWED_MOVES[STATUS_ESCALATION] = tuple(
    status for status, targets in ALLOWED_MOVES.items() if STATUS_ESCALATION in targets
)
# Fix G5 P4: any Understand status can be stopped; only Admin Release moves back (the code checks
# the move is to the status stored on the stop event). Never to a later status.
UNDERSTAND_STATUSES = (STATUS_DRAFT, STATUS_CLARIFICATION, STATUS_DECISION_REQUIRED, STATUS_READY)
for _status in UNDERSTAND_STATUSES:
    ALLOWED_MOVES[_status] = (*ALLOWED_MOVES[_status], STATUS_STOPPED)
ALLOWED_MOVES[STATUS_STOPPED] = UNDERSTAND_STATUSES

Actor = Literal["developer", "system", "llm", "senior"]


class Request(BaseModel):
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    title: str = Field(min_length=1)
    developer_id: str = Field(min_length=1)
    status: str = STATUS_DRAFT
    version: int = Field(default=1, ge=1)
    # AwareDatetime refuses times without a time zone, so every stored time is clearly UTC.
    created_at: AwareDatetime
    updated_at: AwareDatetime
    # The rulebook version number this request is pinned to. Set when the request is created
    # and never changed. Empty only for a request built outside create_request.
    rulebook_version: int | None = Field(default=None, ge=1)
    # Phase 10: the request this one follows after a handoff (only a link, nothing is copied).
    follows_request_id: str | None = Field(default=None, pattern=REQUEST_ID_PATTERN)


class StatusMoveError(Exception):
    """A status move that is not in the spec 3.1 table was refused."""


def check_status_move(old_status: str, new_status: str) -> None:
    """Refuse any move that is not in ALLOWED_MOVES. Staying on the same status is not a move,
    so callers only call this when the status actually changes."""
    if new_status not in ALLOWED_MOVES.get(old_status, ()):
        raise StatusMoveError(
            f"A request cannot move from {old_status} to {new_status}. "
            "This step is not allowed at this point."
        )


def display_status(status: str) -> str:
    """How a status is shown on screen: CONFIRMED_FOR_DISCOVERY becomes CONFIRMED FOR DISCOVERY."""
    return status.replace("_", " ")


class AuditEvent(BaseModel):
    # frozen=True: once built, an event cannot be changed in memory either (rule R1).
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    timestamp: AwareDatetime
    actor: Actor
    event_type: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
