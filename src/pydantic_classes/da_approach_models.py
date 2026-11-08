"""Data shapes for Approach (Phase 4): the plan, the test plan, the working state and the view.

The limits here (spec section 3 and 5) work like DDS field lengths: a value that is too long is
refused, never cut short. The AI never fills the fields the app computes (warnings, zones, IDs).
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_discovery_models import DiscoveryResult
from pydantic_classes.da_models import REQUEST_ID_PATTERN, Request
from pydantic_classes.da_request_record_models import (
    CRITERION_ID_PATTERN,
    ChatMessage,
    RequestRecord,
)

SUMMARY_LIMIT = 300
PATH_LIMIT = 200
TEXT_LIMIT = 200
OPTION_LIMIT = 100
LIBRARY_LIMIT = 50
FILE_COUNT_LIMIT = 12
NEEDS_PEOPLE_LIMIT = 5
REUSE_COUNT_LIMIT = 3
REUSE_DECISION_LIMIT = 10
DESIGN_CHOICE_LIMIT = 3
LIBRARY_COUNT_LIMIT = 12

TEST_COUNT_LIMIT = 30
TEST_TEXT_LIMIT = 300
MAX_TESTER_CASES_PER_CRITERION = 3
MAX_DEVELOPER_CASES = 5

# Typed-text limits (spec section 1).
CUSTOM_ANSWER_LIMIT = 300
CHANGE_LIMIT = 1000
LIMIT_REASON_MIN = 10
LIMIT_REASON_LIMIT = 300
CASE_TEXT_LIMIT = 500
MAX_CHANGES = 3

FileAction = Literal["create", "modify"]
ReuseChoice = Literal["reuse", "extend", "ignore"]
ApproachSource = Literal["proposal", "settled", "change", "revision", "refine"]
CaseSource = Literal["tester", "developer"]
PlanChangeSource = Literal["tester_plan", "developer_case", "revision", "refine"]

# Where the Approach conversation is. "start" is not stored: it means no state row yet.
ApproachStep = Literal[
    "start",
    "choices",
    "review",
    "change",
    "limit_reason",
    "tests_pending",
    "tests",
    "case_text",
    "case_check",
    "done",
    "escalated",
]


class _Shape(BaseModel):
    # extra="forbid": an unknown field name is an error, not silently dropped.
    model_config = ConfigDict(extra="forbid")


# --- the Generator's reply ---


class PlannedFile(_Shape):
    path: str = Field(min_length=1, max_length=PATH_LIMIT)
    action: FileAction
    purpose: str = Field(min_length=1, max_length=TEXT_LIMIT)
    # Discover hit numbers this file reuses.
    reuses: list[int] = Field(default_factory=list, max_length=REUSE_COUNT_LIMIT)


class NeedsPerson(_Shape):
    path: str = Field(min_length=1, max_length=PATH_LIMIT)
    reason: str = Field(min_length=1, max_length=TEXT_LIMIT)


class ReuseDecision(_Shape):
    hit_id: int
    decision: ReuseChoice
    reason: str = Field(min_length=1, max_length=TEXT_LIMIT)


class DesignChoice(_Shape):
    question: str = Field(min_length=1, max_length=TEXT_LIMIT)
    # What changes depending on the answer.
    impact: str = Field(min_length=1, max_length=TEXT_LIMIT)
    # No recommended option: the developer decides (the same principle as rule R3 in Understand).
    options: list[Annotated[str, Field(min_length=1, max_length=OPTION_LIMIT)]] = Field(
        min_length=2, max_length=3
    )


class ApproachReply(_Shape):
    """The Generator's one JSON reply (first call, settle call and change)."""

    summary: str = Field(min_length=1, max_length=SUMMARY_LIMIT)
    files: list[PlannedFile] = Field(default_factory=list, max_length=FILE_COUNT_LIMIT)
    needs_people: list[NeedsPerson] = Field(default_factory=list, max_length=NEEDS_PEOPLE_LIMIT)
    reuse_decisions: list[ReuseDecision] = Field(
        default_factory=list, max_length=REUSE_DECISION_LIMIT
    )
    # The policy limit (3 in the starter rulebook) is checked by da_approach_checks.
    design_choices: list[DesignChoice] = Field(default_factory=list, max_length=DESIGN_CHOICE_LIMIT)
    libraries: list[Annotated[str, Field(min_length=1, max_length=LIBRARY_LIMIT)]] = Field(
        default_factory=list, max_length=LIBRARY_COUNT_LIMIT
    )
    # Phase 8 approach lane: true when the asked change would need an acceptance criterion changed.
    # The app then refuses the reply and points to the requirement lane.
    changes_criteria: bool = False


class ApproachDecision(_Shape):
    """A design choice the developer answered."""

    question: str
    choice: str
    custom: bool
    decided_at: AwareDatetime


class ApproachVersion(_Shape):
    """One saved version of the approach (a row in da_approach_versions). Append-only."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    approach_version: int = Field(ge=1)
    source: ApproachSource
    record_version: int = Field(ge=1)
    rulebook_version: int = Field(ge=1)
    discovery_round: int = Field(ge=1)
    plan: ApproachReply
    decisions: list[ApproachDecision] = Field(default_factory=list)
    # Computed by the app, never by the AI.
    warnings: list[str] = Field(default_factory=list)
    zones_touched: list[str] = Field(default_factory=list)
    model: str = ""
    created_at: AwareDatetime | None = None


# --- the Tester's replies and the saved test plan ---


class TestCaseReply(_Shape):
    __test__ = False  # not a pytest class, whatever the name looks like

    criterion_id: str = Field(pattern=CRITERION_ID_PATTERN)
    given: str = Field(min_length=1, max_length=TEST_TEXT_LIMIT)
    expect: str = Field(min_length=1, max_length=TEST_TEXT_LIMIT)


class TestPlanReply(_Shape):
    __test__ = False

    cases: list[TestCaseReply] = Field(min_length=1, max_length=TEST_COUNT_LIMIT)


class TestCaseDraftReply(_Shape):
    """The Tester's answer to "Add a test case": one case, or null with a reason."""

    __test__ = False

    case: TestCaseReply | None = None
    note: str = Field(default="", max_length=TEST_TEXT_LIMIT)


class TestCase(_Shape):
    __test__ = False

    test_id: str = Field(pattern=r"^T-[1-9]\d*$")
    criterion_id: str = Field(pattern=CRITERION_ID_PATTERN)
    given: str
    expect: str
    source: CaseSource
    # Phase 8: written by the Tester for a new or changed criterion in the requirement lane.
    new: bool = False


class TestPlanVersion(_Shape):
    __test__ = False

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    plan_version: int = Field(ge=1)
    # The approach version this plan was written for.
    approach_version: int = Field(ge=1)
    cases: list[TestCase]
    source_of_change: PlanChangeSource
    model: str = ""
    created_at: AwareDatetime | None = None


# --- the working state and the view ---


class ApproachState(_Shape):
    """The working state of one request in Approach (a row in da_approach_state)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    step: ApproachStep = "review"
    # Design choices not answered yet, first in the list first.
    pending_choices: list[DesignChoice] = Field(default_factory=list)
    decisions: list[ApproachDecision] = Field(default_factory=list)
    accepted_approach_version: int = Field(default=0, ge=0)
    accepted_plan_version: int = Field(default=0, ge=0)
    change_count: int = Field(default=0, ge=0)
    # "Help requested: <question>" or "Escalated in Approach: <step>", else empty.
    open_item: str = ""
    limit_reason: str = ""
    draft_case: TestCaseReply | None = None
    # True when "Change the approach" was pressed on the tests step (G4: not counted in G9).
    change_from_tests: bool = False
    revision: int = Field(default=1, ge=1)


class GateCheck(_Shape):
    name: str
    passed: bool
    detail: str = ""


class ApproachView(BaseModel):
    """Everything the screen needs to show Approach for one request."""

    request: Request
    record: RequestRecord
    messages: list[ChatMessage]
    status_label: str
    step: ApproachStep
    # The latest round Discover saved (for the reuse table), or None.
    discovery: DiscoveryResult | None
    approach: ApproachVersion | None
    plan: TestPlanVersion | None
    gate: list[GateCheck]
    # (key, label) pairs in screen order; the key says which action a button stands for.
    buttons: list[tuple[str, str]]
    # What the text box is for at this step, or "" when it is closed.
    text_prompt: str
    # The label of the Send button: at the review and tests steps it is the action itself.
    send_label: str = "Send"
    note: str
    open_item: str
    draft_case: TestCaseReply | None
    change_count: int
    developer_case_count: int
    tests_folder: str
    # The soft limit of code files from the pinned rulebook (decision D-C).
    file_limit: int
    failed_first_call: bool
    revision: int
    demo_mode: bool
