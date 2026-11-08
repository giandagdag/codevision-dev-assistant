"""Data shapes for Refine (Phase 8): the lane suggestion, the changes-only reply of revision mode,
the record diff, conflicts, and the rows that are saved.

Plain code builds and checks all of these (da_refine_checks.py). AS400 picture: an amendment to a
signed change request (the revision reply and the diff), and two programmers on one source member
(a conflict).
"""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN
from pydantic_classes.da_request_record_models import CRITERION_ID_PATTERN, CriterionKind

LaneName = Literal["requirement", "approach", "bug"]
LANES: tuple[str, ...] = ("requirement", "approach", "bug")
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
    created_at: AwareDatetime | None = None
