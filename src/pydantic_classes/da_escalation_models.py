"""Data shapes for the Escalations inbox (Phase 10 spec sections 7 to 10, 15).

AS400 picture: a message on the help-desk queue. One open message per request; it is only ever
updated to add a reason, add guidance, take over or close.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN

TriggerName = Literal["cap_hit_twice", "out_of_scope", "dispute", "tester_unable_twice", "get_help"]
Outcome = Literal["open", "returned", "abandoned"]

UNASSIGNED = "Unassigned"


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Guidance(_Shape):
    """One piece of senior guidance. `used_in` is empty until a prompt builder has sent it."""

    text: str = Field(min_length=1, max_length=2000)
    sent_by: str = ""
    sent_at: AwareDatetime | None = None
    used_in: str = ""


class EscalationRow(_Shape):
    """One escalation of one request. `revision` is its own number for the stale check."""

    escalation_id: int = Field(default=0, ge=0)  # 0 until saved
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    triggers: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    open_item: str = ""
    from_status: str
    capability: str = ""
    other_capabilities: list[str] = Field(default_factory=list)
    senior_label: str = UNASSIGNED
    backup_label: str = ""
    taken_over_by: str = ""
    guidance: list[Guidance] = Field(default_factory=list)
    outcome: Outcome = "open"
    close_note: str = ""
    closed_by: str = ""
    # The count that fired (triggers 1 and 4); 0 for the others. Rule X2.
    fired_count: int = Field(default=0, ge=0)
    opened_at: AwareDatetime | None = None
    closed_at: AwareDatetime | None = None
    revision: int = Field(default=1, ge=1)


class Route(_Shape):
    """Who a new escalation goes to (spec section 8)."""

    capability: str = ""
    other_capabilities: list[str] = Field(default_factory=list)
    senior_label: str = UNASSIGNED
    backup_label: str = ""


class TriggerDecision(_Shape):
    """What one trigger function says: fire with this reason, stay quiet, or it is switched off."""

    trigger: str
    fire: bool = False
    reason: str = ""
    count: int = Field(default=0, ge=0)
    switched_off: bool = False
