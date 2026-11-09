"""Data shapes for Enhance (Phase 9): the candidates, the freshness result, the "what it does today"
draft, the safety net, the impact rows, and the step state.

Plain code builds and checks all of these (da_enhance_checks.py). AS400 picture: the where-used list
(impact), the production-library compare (freshness) and the regression test pack (safety net).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


# --- stored state (section 14) ---


class EnhanceState(_Shape):
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    kind: RequestKind = "enhance"
    step: EnhanceStep = "e_find"
    find_rounds_used: int = Field(default=0, ge=0)
    corrections_used: int = Field(default=0, ge=0)
    # Own revision: goes up by 1 with every save (stale-save protection, F1).
    revision: int = Field(default=1, ge=1)


def step_label(step: str) -> str:
    """The header pill text for a Phase 9 step ("" = show the normal status)."""
    return STEP_LABELS.get(step, "")
