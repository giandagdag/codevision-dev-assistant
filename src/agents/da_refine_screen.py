"""What the Refine part of the screen offers at `b_written` (Phase 8 step 13a, tests 8-1/2/12).

Decisions only, no components (rule R12): the layout turns a RefineBox into buttons and a text box.

AS400 picture: the command-key line at the bottom of a 5250 screen. Which keys are lit depends on
the state of the job, and this file decides which ones.
"""

from dataclasses import dataclass, field

from agents.da_refine_checks import (
    cap_message,
    criterion_marks,
    diff_records,
    refine_cap_reached,
)
from agents.da_refine_flow import (
    CHECK_KEY,
    CHECK_LABEL,
    EDIT_STATUSES,
    RESCAN_KEY,
    RESTORE_KEY,
    RESTORE_LABEL,
    get_edit_view,
    rescan_label,
)
from agents.da_refine_lanes import get_refine_state
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_versions
from db_table_functions.db_tbl_da_refine import read_all_records
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from pydantic_classes.da_approach_models import ApproachVersion
from pydantic_classes.da_refine_models import RecordDiff
from pydantic_classes.da_request_record_models import RequestRecord

REFINE_PLACEHOLDER = "Tell me what to change or fix, then press Send."
EDIT_HINT = "Edit anything, then click Re-scan."


@dataclass
class RefineBox:
    """`offered` False means no Refine controls at all (8-2). When the cap is reached the text box
    is closed and says why, but Re-scan and Check my edits still work (8-12)."""

    offered: bool = False
    text_open: bool = False
    placeholder: str = ""
    # (key, label): Re-scan runs in the browser, the others on the server.
    browser_buttons: list[tuple[str, str]] = field(default_factory=list)
    buttons: list[tuple[str, str]] = field(default_factory=list)
    hint: str = ""


def make_refine_box(
    status: str,
    step: str,
    refine_count: int,
    cap: int,
    mode: str = "picker",
    has_edits: bool = False,
) -> RefineBox:
    """Pure rule: Refine is offered only at `b_written` with READY_FOR_REVIEW or NOT_PASSING."""
    if step != "b_written" or status not in EDIT_STATUSES:
        return RefineBox()
    capped = refine_cap_reached(refine_count, cap)
    buttons = [(CHECK_KEY, CHECK_LABEL)] if has_edits else []
    buttons.append((RESTORE_KEY, RESTORE_LABEL))
    return RefineBox(
        offered=True,
        text_open=not capped,
        placeholder=cap_message(refine_count) if capped else REFINE_PLACEHOLDER,
        browser_buttons=[(RESCAN_KEY, rescan_label(mode))],
        buttons=buttons,
        hint=EDIT_HINT,
    )


def get_refine_box(settings, request_id: str, status: str, step: str, mode: str) -> RefineBox:
    """Reads the Refine count, the cap and whether re-scanned edits wait, then decides."""
    if step != "b_written" or status not in EDIT_STATUSES:
        return RefineBox()
    state = get_refine_state(settings, request_id)
    count = state.refine_count if state else 0
    cap = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    edits = get_edit_view(settings, request_id)
    return make_refine_box(
        status, step, count, cap.refine_max_per_request, mode, has_edits=bool(edits.changed)
    )


# --- version history for the Summary and Approach tabs (step 13b) ---


@dataclass
class VersionHistory:
    """Record diffs and the approach versions. Empty when nothing was refined."""

    diffs: list[RecordDiff] = field(default_factory=list)
    marks: dict[str, list[str]] = field(default_factory=dict)
    # (approach version, source, record version)
    approaches: list[tuple[int, str, int]] = field(default_factory=list)


def make_history(records: list[RequestRecord], approaches: list[ApproachVersion]) -> VersionHistory:
    """Pure rule: one diff for each step from a record version to the next."""
    diffs = [diff_records(old, new) for old, new in zip(records, records[1:], strict=False)]
    listed = [(a.approach_version, a.source, a.record_version) for a in approaches]
    return VersionHistory(
        diffs=diffs,
        marks=criterion_marks(diffs),
        approaches=listed,
    )


def get_history(settings, request_id: str) -> VersionHistory:
    with open_db(settings.db_path) as conn:
        return make_history(
            read_all_records(conn, request_id), read_approach_versions(conn, request_id)
        )
