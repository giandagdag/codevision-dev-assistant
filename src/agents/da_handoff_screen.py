"""What the Handoff parts of the screen show (Phase 10, step 5). No rules here: the box is filled
from the Handoff flow's own view, and the layout only draws it (rule R12).

AS400 picture: the function-key line at the bottom of a 5250 screen. Which keys are lit depends on
where the promotion request stands.
"""

from dataclasses import dataclass, field

from agents.da_handoff_flow import NOT_PASSING_LINE, READY_LABEL, get_handoff_view
from pydantic_classes.da_models import (
    STATUS_HANDED_OFF,
    STATUS_NOT_PASSING,
    STATUS_READY_FOR_REVIEW,
)

READY_KEY, FOLLOW_UP_KEY = "ready", "follow_up"
CHECK_FOLDER_KEY = "handoff_check"  # browser button: reads the planned files for the final check
CHECK_FOLDER_LABEL = "Check my folder"
UPLOAD_CHECK_LABEL = "Upload folder to check in"
CHECK_FOLDER_HINT = "Last step: confirms your folder still matches the tested version."  # G9 S1
FOLLOW_UP_LABEL = "Start a follow-up request"
LOCKED_LINE = "This request is handed off and locked. You can still read every tab."
CHECKING_NOTE = "Press the button so I can compare your folder with the last test."
BLOCKED_FOLDER_NOTE = (
    "Your folder differs from the last test. Re-scan and check my edits, or Restore the tested "
    "version, then press Check my folder again."
)


@dataclass
class HandoffBox:
    """`offered` False means no Handoff controls at all (the request is not at that point)."""

    offered: bool = False
    locked: bool = False
    revision: int = 0
    step: str = ""
    buttons: list[tuple[str, str]] = field(default_factory=list)  # server-run (key, label)
    browser_buttons: list[tuple[str, str]] = field(default_factory=list)
    note: str = ""
    blockers: list[str] = field(default_factory=list)
    summary: str = ""
    # The tab to open: the Tests tab when findings block, the Audit tab once handed off.
    open_tab: str | None = None


def make_handoff_box(status: str, view, mode: str = "picker") -> HandoffBox:
    """Pure rule: which Handoff controls a request at this status and step gets."""
    if status == STATUS_HANDED_OFF:
        box = HandoffBox(offered=True, locked=True, step="h_done", open_tab="audit")
        box.revision = view.state.revision
        box.summary = view.handoff.summary_text if view.handoff else ""
        box.note = LOCKED_LINE
        box.buttons = [(FOLLOW_UP_KEY, FOLLOW_UP_LABEL)]
        return box
    if status == STATUS_NOT_PASSING:
        return HandoffBox(note=NOT_PASSING_LINE)
    if status != STATUS_READY_FOR_REVIEW:
        return HandoffBox()
    step = view.state.step
    box = HandoffBox(offered=True, revision=view.state.revision, step=step)
    if step in ("h_checking", "h_blocked_folder"):
        label = UPLOAD_CHECK_LABEL if mode == "download" else CHECK_FOLDER_LABEL
        box.browser_buttons = [(CHECK_FOLDER_KEY, label)]
        box.note = BLOCKED_FOLDER_NOTE if step == "h_blocked_folder" else CHECKING_NOTE
        box.blockers = [f"{item.path}: {item.result}" for item in view.state.checks
                        if item.result != "equal"]
        return box
    box.buttons = [(READY_KEY, READY_LABEL)]
    if step == "h_blocked_findings":
        box.blockers = [item.text for item in view.state.blockers]
        box.open_tab = "tests"
    return box


def get_handoff_box(settings, request_id: str, status: str, mode: str = "picker") -> HandoffBox:
    """Reads the Handoff view (no lock) and decides. Nothing is written."""
    if status not in (STATUS_READY_FOR_REVIEW, STATUS_HANDED_OFF, STATUS_NOT_PASSING):
        return HandoffBox()
    return make_handoff_box(status, get_handoff_view(settings, request_id), mode)
