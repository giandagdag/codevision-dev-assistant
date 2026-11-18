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
ABANDONED_MESSAGE = (
    "A senior closed this request. It is locked. Start a new request for further changes."
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


class CriterionFact(_Shape):
    """One acceptance criterion with its test counts from the last tested run."""

    criterion_id: str
    tests: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)


class FileFact(_Shape):
    """One planned file in the PR summary."""

    path: str
    is_new: bool = False
    hand_edited: bool = False


class SummaryFacts(_Shape):
    """Everything the PR summary needs, as plain data (spec section 5). One field group per line
    of the summary. `gather_summary_facts` fills it from the tables; the builder only formats."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    record_version: int = Field(default=1, ge=1)
    summary: str = ""
    kind: Literal["new", "enhance", "fix"] = "new"
    capability: str = ""
    named_senior: str = ""
    capability_confirmed: bool = True
    follows_request_id: str | None = None
    criteria: list[CriterionFact] = Field(default_factory=list)
    yours: int = Field(default=0, ge=0)  # tests the developer wrote
    safety_net: int = Field(default=0, ge=0)  # Phase 9 safety-net tests
    tester_label: str = ""
    must_fixed: int = Field(default=0, ge=0)
    should_fixed: int = Field(default=0, ge=0)
    accepted: int = Field(default=0, ge=0)
    fyi: int = Field(default=0, ge=0)
    overruled: int = Field(default=0, ge=0)
    overruled_by: str = ""
    files: list[FileFact] = Field(default_factory=list)
    reuses: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    accepted_risks: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    impact_unchecked: bool = False
    senior_involvement: list[str] = Field(default_factory=list)
    build_number: int = Field(default=0, ge=0)
    checked_on: str = ""
    # Fix D1: the test report summary and file name; empty for a build with no saved report.
    report_summary: str = ""
    report_file: str = ""


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


class HandoffView(_Shape):
    """What the screen needs about Handoff, read with no lock."""

    state: HandoffState
    handoff: HandoffRow | None = None
    can_start: bool = False  # the Ready for handoff button (READY_FOR_REVIEW only)
    locked: bool = False
