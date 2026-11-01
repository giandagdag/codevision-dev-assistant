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
)

# The only moves allowed: the spec 3.1 table, plus the Discover moves of Phase 3 (spec section 2).
ALLOWED_MOVES: dict[str, tuple[str, ...]] = {
    STATUS_DRAFT: (STATUS_CLARIFICATION,),
    STATUS_CLARIFICATION: (STATUS_DECISION_REQUIRED, STATUS_READY),
    STATUS_DECISION_REQUIRED: (STATUS_CLARIFICATION,),
    STATUS_READY: (STATUS_CONFIRMED, STATUS_CLARIFICATION, STATUS_DECISION_REQUIRED),
    STATUS_CONFIRMED: (STATUS_SEARCHING,),
    STATUS_SEARCHING: (STATUS_SIMILAR_FOUND, STATUS_NO_MATCH),
    STATUS_SIMILAR_FOUND: (STATUS_DISCOVERY_CONFIRMED, STATUS_SEARCHING, STATUS_ESCALATION),
    STATUS_NO_MATCH: (STATUS_DISCOVERY_CONFIRMED, STATUS_SEARCHING, STATUS_ESCALATION),
    STATUS_DISCOVERY_CONFIRMED: (STATUS_APPROACH_PROPOSED,),
    STATUS_APPROACH_PROPOSED: (STATUS_READY_TO_BUILD, STATUS_ESCALATION),
    # Phase 6 adds the moves out of READY_TO_BUILD; the escalation inbox comes in Phase 10.
    STATUS_READY_TO_BUILD: (),
    STATUS_ESCALATION: (),
}

Actor = Literal["developer", "system", "llm"]


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
