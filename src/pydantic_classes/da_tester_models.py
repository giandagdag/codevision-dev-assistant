"""Data shapes for the Independent Tester (Phase 7): the AI's reply, a finding, the seven check
results, a saved review, and the developer's actions on findings.

Like a peer-review sheet: every comment names a member and a line, and plain code throws away
any comment that does not (da_tester_review.py). Nothing here calls an AI.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN

Severity = Literal["must_fix", "should_fix", "fyi"]
SEVERITIES: tuple[str, ...] = ("must_fix", "should_fix", "fyi")
SEVERITY_TEXT = {"must_fix": "Must fix", "should_fix": "Should fix", "fyi": "FYI"}
ReviewResult = Literal["done", "unable", "interrupted"]
CheckState = Literal["passed", "failed", "warning", "not_run"]
# Phase 10: a senior can overrule a finding (actor `senior:<id>`); the developer cannot.
ActionKind = Literal["accepted", "reopened", "disputed", "overruled"]
MadeByTester = Literal["plain", "tester"]

# The seven checks (spec section 5): number -> short name. 1, 2, 3 and 7 are plain code.
CHECK_NAMES = {
    1: "Every criterion has a test",
    2: "Every criterion's tests pass",
    3: "Files match the file plan",
    4: "Approach decisions followed",
    5: "Nothing extra built",
    6: "Judgement rules kept",
    7: "Flag-for-review zones",
}
AI_CHECKS = (4, 5, 6)

ACCEPT_MIN_CHARS = 10
ACCEPT_MAX_CHARS = 300
MESSAGE_LIMIT = 300
QUOTE_LIMIT = 200
MAX_REPLY_FINDINGS = 50


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- the AI's reply (spec section 4) ---


class ReplyFinding(_Shape):
    """One finding as the Tester wrote it. Limits on text are NOT set here: a too-long message
    drops that one finding (rule E5) instead of making the whole reply unusable."""

    check: Literal[4, 5, 6]
    severity: Severity
    file: str
    line: int
    quote: str
    cites: str
    message: str


class TesterReviewReply(_Shape):
    __test__ = False  # not a pytest class

    findings: list[ReplyFinding] = Field(default_factory=list, max_length=MAX_REPLY_FINDINGS)


# --- saved shapes ---


class Finding(_Shape):
    """One finding of one review (da_tester_findings, append-only)."""

    finding_id: str  # F-1
    check: int = Field(ge=1, le=7)
    severity: Severity
    file: str = ""
    line: int = 0
    quote: str = ""
    cites: str = ""
    message: str = ""
    made_by: MadeByTester = "tester"
    kept: bool = True
    reject_reason: str = ""
    # False for check 1: the Generator may not touch tests, so it cannot fix this.
    fixable: bool = True


class CheckResult(_Shape):
    number: int = Field(ge=1, le=7)
    name: str
    state: CheckState
    findings: int = 0
    note: str = ""


class ReviewRecord(_Shape):
    """One Layer C review (da_tester_reviews). Saved when the review closes."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    build_number: int = Field(ge=1)
    round: int = Field(ge=1)
    review_number: int = Field(ge=1)
    model: str = ""
    calls: int = Field(default=0, ge=0)
    prompt_chars: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    result: ReviewResult = "done"
    checks: list[CheckResult] = Field(default_factory=list)
    zone_warnings: list[str] = Field(default_factory=list)
    label: str = ""
    findings: list[Finding] = Field(default_factory=list)
    created_at: AwareDatetime | None = None


class FindingAction(_Shape):
    """What the developer did to a finding (append-only; the newest action is its state)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    build_number: int = Field(ge=1)
    review_number: int = Field(ge=1)
    finding_id: str
    action: ActionKind
    reason: str = ""
    actor: str = "developer"
    created_at: AwareDatetime | None = None


# --- what the Tests tab shows ---


class FindingRow(BaseModel):
    """A kept finding with its current state, for the table."""

    finding: Finding
    state: str = "open"  # open, accepted, disputed, overruled
    reason: str = ""
    actor: str = ""  # who made the newest action ("senior:<id>" for an overrule)


class TesterView(BaseModel):
    """Everything the Tests tab needs about the newest review (and the older ones)."""

    review: ReviewRecord | None = None
    label: str = ""
    rows: list[FindingRow] = Field(default_factory=list)
    dropped: list[Finding] = Field(default_factory=list)
    earlier: list[ReviewRecord] = Field(default_factory=list)
    summary: str = ""
    reason: str = ""  # G5 B3: why the label is Not passing, one line
    can_rerun: bool = False
    layer_c_ran: bool = False
