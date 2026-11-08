"""What the Refine part of the screen offers at `b_written` (Phase 8 step 13a, tests 8-1/2/12).

Decisions only, no components (rule R12): the layout turns a RefineBox into buttons and a text box.

AS400 picture: the command-key line at the bottom of a 5250 screen. Which keys are lit depends on
the state of the job, and this file decides which ones.
"""

from dataclasses import dataclass, field

from agents.da_refine_checks import cap_message, refine_cap_reached
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
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request

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
