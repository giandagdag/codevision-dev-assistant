"""Data shapes for Handoff (Phase 10): the small state, the final-check result, the saved handoff.

AS400 picture: the promotion request form. The state says how far the form got; the handoff row is
the signed form that is never changed afterwards. Nothing here calls an AI.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN

# Steps of spec section 2. `h_start` is the state before the developer pressed the button.
HandoffStep = Literal["h_start", "h_blocked_findings", "h_checking", "h_blocked_folder", "h_done"]
PathResult = Literal["equal", "changed", "missing"]

LOCKED_MESSAGE = (
    "This request is handed off and locked. Start a new request for further changes; "
    "it will be linked to this one."
)
ESCALATION_OPEN_MESSAGE = "A senior is looking at this request."


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathCheck(_Shape):
    """The final check for one planned file (spec H4). Fingerprints are the Phase 5 ones."""

    path: str
    seen: str = ""  # what the browser read ("" when the file is missing)
    expected: str = ""  # the last tested fingerprint
    result: PathResult


class Blocker(_Shape):
    """One reason Handoff is refused, in plain words, with the finding it names (if any)."""

    kind: Literal["label", "must_fix", "should_fix", "last_tested"]
    finding_id: str = ""
    text: str


class HandoffState(_Shape):
    """Handoff's own small state (da_handoff_state). Own revision, like the Refine state."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    step: HandoffStep = "h_start"
    revision: int = Field(default=0, ge=0)
    blockers: list[Blocker] = Field(default_factory=list)
    checks: list[PathCheck] = Field(default_factory=list)


class HandoffRow(_Shape):
    """The signed form (da_handoffs): one per request, append-only."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    record_version: int = Field(ge=1)
    approach_version: int = Field(ge=0)
    last_tested_build: int = Field(ge=0)
    last_tested_kind: str = ""
    summary_text: str
    handed_off_by: str
    created_at: AwareDatetime | None = None
