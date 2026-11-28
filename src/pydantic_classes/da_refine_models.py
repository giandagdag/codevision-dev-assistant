"""Data shapes for Refine (Phase 8): the lane suggestion, the changes-only reply of revision mode,
the record diff, conflicts, and the rows that are saved.

Plain code builds and checks all of these (da_refine_checks.py). AS400 picture: an amendment to a
signed change request (the revision reply and the diff), and two programmers on one source member
(a conflict).
"""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN
from pydantic_classes.da_request_record_models import (
    CRITERION_ID_PATTERN,
    CriterionKind,
    RequestRecord,
)
from pydantic_classes.da_rule_conflict_models import Gap, RuleConflict
from pydantic_classes.da_tester_models import Finding

LaneName = Literal["requirement", "approach", "bug"]
LANES: tuple[str, ...] = ("requirement", "approach", "bug")
# The bug lane while its fix build runs; the build loop closes the Refine when that build ends.
STEP_BUG_FIXING = "bug_fixing"
# Fix it on a Should fix: the same kind of fix build, with the finding as the only input.
STEP_FINDING_FIXING = "finding_fixing"
# Why a Refine started (spec section 13).
RefineSource = Literal["feedback", "finding", "failed_check", "added_test"]
ConflictChoice = Literal["mine", "ai"]
# Whether a "last tested" set came from a build, a rebuild, a check run or a restore.
LastTestedKind = Literal["build", "rebuild", "check", "restore"]

REASON_LIMIT = 300


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- the lane suggestion (spec section 4) ---


class LaneSuggestion(_Shape):
    lane: LaneName
    reason: str = Field(max_length=REASON_LIMIT)
    # For a bug: the criterion it breaks, or None when no criterion covers it.
    criterion_id: str | None = Field(default=None, pattern=CRITERION_ID_PATTERN)


# --- revision mode: the AI names changes only (spec section 5, D-C) ---


class CriterionOp(_Shape):
    """One change to one criterion. `add` has no id (the app numbers it); `change` and `remove`
    name an existing id."""

    op: Literal["add", "change", "remove"]
    id: str | None = Field(default=None, pattern=CRITERION_ID_PATTERN)
    kind: CriterionKind | None = None
    given: str | None = None
    when: str | None = None
    then: str | None = None


class RevisionReply(_Shape):
    criteria_ops: list[CriterionOp] = Field(default_factory=list, max_length=24)
    # Only the record fields that change (the app checks the names).
    field_updates: dict[str, str | list[str]] = Field(default_factory=dict)


# --- the diff of two record versions (Summary tab) ---


class FieldChange(BaseModel):
    field: str
    old: Any
    new: Any


class CriterionChange(BaseModel):
    id: str
    change: Literal["added", "changed", "removed"]
    # {"kind", "given", "when", "then"} or None (an added one has no old text, a removed no new).
    old: dict[str, str] | None = None
    new: dict[str, str] | None = None


class RecordDiff(BaseModel):
    from_version: int
    to_version: int
    fields: list[FieldChange] = Field(default_factory=list)
    criteria: list[CriterionChange] = Field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.fields and not self.criteria


# --- conflicts (spec section 8) ---


class Conflict(BaseModel):
    """A place where the Generator's change touches or sits next to his lines."""

    path: str
    conflict_id: str  # C-1, C-2... per file
    # Line numbers (1-based, inclusive) in HIS text that the AI's change replaces.
    his_start: int = Field(ge=1)
    his_end: int = Field(ge=0)
    his_lines: list[str] = Field(default_factory=list)
    ai_lines: list[str] = Field(default_factory=list)
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)
    choice: ConflictChoice | None = None


class ConflictPick(BaseModel):
    path: str
    conflict_id: str
    choice: ConflictChoice


# --- saved rows (spec section 13) ---


class PendingRepro(_Shape):
    """A repro test that fails on today's code, waiting for his "Yes, this is the bug"."""

    case_id: str
    criterion_id: str = Field(pattern=CRITERION_ID_PATTERN)
    given: str
    expect: str
    method: str
    failure: str = ""


class RefineState(_Shape):
    """One row per request (da_refine_state). Its own revision, for the stale check (F1)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    refine_number: int = Field(default=0, ge=0)
    step: str = "start"
    refine_count: int = Field(default=0, ge=0)
    # The build whose files are "last tested" (spec section 3), for Phase 10's fingerprint check.
    last_tested_build: int = Field(default=0, ge=0)
    last_tested_kind: LastTestedKind | Literal[""] = ""
    # Rebuilds in a row that ended NOT_PASSING (F4). Acts in Phase 10.
    not_passing_in_a_row: int = Field(default=0, ge=0)
    revision: int = Field(default=1, ge=1)
    # The Refine in progress (saved when the lane suggestion is shown, kept until it closes).
    pending_feedback: str = ""
    pending_source: RefineSource = "feedback"
    suggested_lane: LaneName | Literal[""] = ""
    suggested_reason: str = ""
    suggested_criterion: str = ""
    chosen_lane: LaneName | Literal[""] = ""
    from_status: str = ""
    # Requirement lane: the proposed next record version, shown with its diff until he decides.
    pending_record: RequestRecord | None = None
    lane_unusable: bool = False
    # Bug lane: the repro test waiting for his click, and the tries used so far (not rounds).
    repro: PendingRepro | None = None
    repro_tries: int = Field(default=0, ge=0)
    repro_passed_today: int = Field(default=0, ge=0)
    # Fix it: the Should fix finding being fixed (its text goes to the Generator in round 1).
    fix_finding: Finding | None = None
    # Restore: 0 nothing open, -1 the list of earlier builds is open, N the build chosen (its
    # warning is in the chat; Restore build N or Cancel waits). Cleared by Cancel or by the restore.
    restore_pick: int = 0
    # Fix G9 F5: what the rule check found in `pending_record` (old rows read as nothing found).
    check_conflicts: list[RuleConflict] = Field(default_factory=list)
    check_gaps: list[Gap] = Field(default_factory=list)
    check_failed: bool = False


class RefineRow(_Shape):
    """One Refine (da_refines). Updated only to close it."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    refine_number: int = Field(ge=1)
    source: RefineSource = "feedback"
    feedback: str = ""
    suggested_lane: LaneName | Literal[""] = ""
    reason: str = ""
    chosen_lane: LaneName | Literal[""] = ""
    from_status: str = ""
    record_version_before: int = Field(default=0, ge=0)
    record_version_after: int = Field(default=0, ge=0)
    approach_version_before: int = Field(default=0, ge=0)
    approach_version_after: int = Field(default=0, ge=0)
    build_number: int = Field(default=0, ge=0)
    # How many repro tests passed on today's code (WF-2: lets the Tester bake-off compare models).
    repro_passed_today: int = Field(default=0, ge=0)
    result: str = ""
    created_at: AwareDatetime | None = None
    closed_at: AwareDatetime | None = None


class TestSet(_Shape):
    """One version of the frozen test set (da_test_sets, append-only)."""

    __test__ = False

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    test_set_version: int = Field(ge=1)
    approach_version: int = Field(ge=1)
    added_case_ids: list[str] = Field(default_factory=list)
    text: str
    fingerprint: str
    # Phase 9: which test methods are the safety net, and which of those are expected to change.
    net_methods: list[str] = Field(default_factory=list)
    expected_to_change_methods: list[str] = Field(default_factory=list)
    created_at: AwareDatetime | None = None
