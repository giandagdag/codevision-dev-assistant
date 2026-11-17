"""Data shapes for Enhance (Phase 9): the candidates, the freshness result, the "what it does today"
draft, the safety net, the impact rows, and the step state.

Plain code builds and checks all of these (da_enhance_checks.py). AS400 picture: the where-used list
(impact), the production-library compare (freshness) and the regression test pack (safety net).
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN
from pydantic_classes.da_request_record_models import (
    CRITERION_ID_PATTERN,
    FreshnessOverride,
    RequestKind,
)

# The steps of an enhance request (spec section 12). The header pill shows the label.
EnhanceStep = Literal[
    "e_find",
    "e_pick",
    "e_stale",
    "e_fresh",
    "s_writing",
    "s_unable",
    "s_review",
    "s_accepted",
    "escalated",  # Get help was pressed (spec section 2, test 9-45)
]
STEP_LABELS: dict[str, str] = {
    "e_find": "FIND THE PROGRAM",
    "e_pick": "FIND THE PROGRAM",
    "e_stale": "FRESHNESS CHECK",
    "e_fresh": "PROGRAM CONFIRMED",
    "s_writing": "WRITING SAFETY NET",
    "s_unable": "SAFETY NET NOT READY",
    "s_review": "SAFETY NET READY",
    "s_accepted": "",  # empty = show the normal status pill
    "escalated": "",  # the status pill shows ESCALATION REQUIRED
}

HowFound = Literal["name", "meaning", "name+meaning"]
FreshnessState = Literal["equal", "differs", "not_on_main", "missing_in_folder", "unreachable"]
ImpactKind = Literal["direct", "possible", "imports_only"]

SAFETY_CASE_ID_PATTERN = r"^S-[1-9]\d*$"
TODAY_LIMIT = 600
SENTENCE_LIMIT = 300


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Find (spec section 4) ---


class Candidate(_Shape):
    path: str = Field(min_length=1)
    how_found: HowFound
    score: float = 0.0
    best_match: bool = False
    # "" = not in the catalog.
    capability: str = ""
    named_senior: str = ""


# --- Freshness (spec section 5) ---


class PathFreshness(_Shape):
    path: str
    state: FreshnessState
    # Fingerprints; "" when that side has no file.
    his_fingerprint: str = ""
    main_fingerprint: str = ""


class FreshnessResult(_Shape):
    paths: list[PathFreshness] = Field(default_factory=list)
    main_source: str = ""
    override: FreshnessOverride = ""

    @property
    def all_equal(self) -> bool:
        return bool(self.paths) and all(item.state == "equal" for item in self.paths)


# --- the AI replies (sections 6 and 8) ---


class TodayDraft(_Shape):
    """Reply of the "what does it do today" call. Plain code checks the length, that there is no
    code in `today`, and that the symbols exist in the split."""

    today: str = Field(max_length=TODAY_LIMIT)
    functions_in_scope_guess: list[str] = Field(default_factory=list)


class SafetyCase(_Shape):
    id: str = Field(pattern=SAFETY_CASE_ID_PATTERN)
    today_behaviour: str = Field(min_length=1, max_length=SENTENCE_LIMIT)
    function: str = Field(min_length=1)
    nc_ids: list[str] = Field(default_factory=list)
    # An AC-<n>, or None for "must still pass".
    expected_to_change: str | None = Field(default=None, pattern=CRITERION_ID_PATTERN)


class NotCovered(_Shape):
    # A function name or an NC-<n> ID.
    item: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=SENTENCE_LIMIT)


class SafetyNet(_Shape):
    cases: list[SafetyCase] = Field(default_factory=list)
    test_code: str = ""
    not_covered: list[NotCovered] = Field(default_factory=list)


# --- impact (section 7) ---


class ImpactRow(_Shape):
    caller_path: str
    caller_function: str
    line: int = Field(ge=1)
    function_in_scope: str
    kind: ImpactKind
    capability: str = ""
    zone: str = ""


class ImpactResult(_Shape):
    """What impact found. `available` False = the reference copy could not be read."""

    available: bool = True
    rows: list[ImpactRow] = Field(default_factory=list)
    # How many more callers were found beyond the cap ("and N more").
    more: int = Field(default=0, ge=0)


# --- stored state (section 14) ---


class TargetChoice(_Shape):
    """A confirmed program (spec section 4, step 9) with its capability and named senior."""

    path: str = Field(min_length=1)
    how_found: HowFound
    capability: str = ""
    named_senior: str = ""
    # False when the developer picked the capability himself (Unassigned queue, D-J).
    capability_confirmed: bool = True


class EnhanceState(_Shape):
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    kind: RequestKind = "enhance"
    step: EnhanceStep = "e_find"
    find_rounds_used: int = Field(default=0, ge=0)
    corrections_used: int = Field(default=0, ge=0)
    # Set by "Confirm" at e_pick; empty until then.
    targets: list[TargetChoice] = Field(default_factory=list)
    # "This is a fix" pre-fills "What should change?" with this text (D-M).
    change_prefill: str = ""
    # `Escalated in Enhance: <step>` after Get help, else empty (Phase 10 reads it).
    open_item: str = ""
    # Own revision: goes up by 1 with every save (stale-save protection, F1).
    revision: int = Field(default=1, ge=1)


class SafetyNetRow(_Shape):
    """One saved version of the safety net (da_safety_nets, append-only). Accepting appends a copy
    with `accepted` True; the latest accepted row per record version is in force."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    net_version: int = Field(ge=1)
    record_version: int = Field(ge=1)
    net: SafetyNet
    fingerprint: str = ""
    # LayerBResult as a plain dictionary (proof run results), empty before the proof.
    proof: dict = Field(default_factory=dict)
    accepted: bool = False
    created_at: AwareDatetime | None = None


class FreshnessCheckRow(_Shape):
    """One saved freshness check (da_freshness_checks, append-only)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    check_number: int = Field(ge=1)
    record_version: int = Field(ge=1)
    result: FreshnessResult
    created_at: AwareDatetime | None = None


UnassignedState = Literal["open", "confirmed", "changed", "rejected"]


class UnassignedFile(_Shape):
    """A file in no capability, with the capability the developer picked (spec section 11)."""

    unassigned_id: int = 0
    path: str = Field(min_length=1)
    picked_capability: str = Field(min_length=1)
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    state: UnassignedState = "open"
    resolved_by: str = ""
    resolved_at: AwareDatetime | None = None
    # Phase 11b: the capability Admin moved the file to (state "changed"); empty otherwise.
    resolved_capability: str = ""
    created_at: AwareDatetime | None = None


def step_label(step: str) -> str:
    """The header pill text for a Phase 9 step ("" = show the normal status)."""
    return STEP_LABELS.get(step, "")
