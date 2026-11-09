"""What each Refine button does (Phase 8 step 16a). No Dash here: the callbacks stay thin (R12).

Two functions:
- `get_refine_bar`: for the situation the request is in, the note line, the buttons and whether the
  text box is open. The page draws it; a click comes back as a key.
- `perform_refine`: one key to one engine call (or a short chain, like the Phase 6 "starts by
  itself" steps). Returns an `Outcome`: the job the caller must start (`"build"` means call
  `build_runner.submit_build`) and a message for a chained step that failed.

AS400 picture: the command-key line (which keys are lit) and the function-key program (what each
key calls). The checks themselves stay in the engine functions built in steps 5 to 12.
"""

from collections.abc import Callable
from dataclasses import dataclass

from agents import da_build_flow as build_flow
from agents import da_refine_approach as approach
from agents import da_refine_bug as bug
from agents import da_refine_edit as edit
from agents import da_refine_fixit as fixit
from agents import da_refine_flow as rflow
from agents import da_refine_help as help_
from agents import da_refine_lanes as lanes
from agents import da_refine_owntest as owntest
from agents import da_refine_picks as picks
from agents import da_refine_revision as revision
from agents.da_refine_hooks import STEP_REQ_APPROACH, STEP_REQ_FINDINGS
from agents.da_refine_screen import RefineBox, get_refine_box
from configs.da_config import ConfigError
from db_table_functions.da_db import DatabaseBusyError, open_db
from db_table_functions.db_tbl_da_build import (
    ensure_build_tables,
    read_build_run,
    read_build_state,
)
from db_table_functions.db_tbl_da_refine import RefineError, read_refine_state
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_rulebook import RulebookError
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
)
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables, read_workspace_state
from pydantic_classes.da_models import STATUS_NOT_PASSING, STATUS_REVISION

# Problems the developer can read. Anything else is a real bug and is allowed to stop loudly.
SHOWN_CHAIN_ERRORS = (UnderstandError, RulebookError, DatabaseBusyError, ConfigError)
BUILD_JOB = "build"
BROWSER_KEYS = (rflow.RESCAN_KEY, "restore_go")  # these run in the browser, never here
SEND_KEY = "send"

# Labels of the buttons that are not defined next to their engine function.
LABELS = {
    "cancel": lanes.CANCEL_LABEL,
    "revise": "Try again",
    "discover": "Try again",
    "rev_approach": "Try again",
    "approach_change": "Try again",
    "findings_ok": "Findings look right",
    "bug_fix": "Start the fix",
    "help": "Get help",
    "apply": picks.APPLY_LABEL,
}
LANE_KEYS = {
    "lane_requirement": "requirement",
    "lane_approach": "approach",
    "lane_bug": "bug",
}
PICK_LINE = lanes.PICK_LINE

# step -> (note, buttons, text placeholder or "", Send label). The lane steps of spec sections 4-8.
CHECKPOINT_PROMPT = "Type a correction, or press Confirm v2."
BUG_PROMPT = "Describe the bug in your own words, then press Send."
LANE_STEPS: dict[str, tuple[str, list[tuple[str, str]], str, str]] = {
    lanes.STEP_REQ_REVISE: (
        "I could not work out the change yet.",
        [("revise", LABELS["revise"]), ("cancel", lanes.CANCEL_LABEL)],
        "",
        "Send",
    ),
    lanes.STEP_REQ_CHECKPOINT: (
        "Check the change above.",
        [("confirm_v2", lanes.CONFIRM_V2_LABEL), ("cancel", lanes.CANCEL_REVISION_LABEL)],
        CHECKPOINT_PROMPT,
        lanes.CORRECT_LABEL,
    ),
    lanes.STEP_REQ_DISCOVER: ("Discover on the new version.", [("discover", "Try again")], "", ""),
    STEP_REQ_FINDINGS: ("Check the findings.", [("findings_ok", "Findings look right")], "", ""),
    STEP_REQ_APPROACH: (
        "Planning the changed request.", [("rev_approach", "Try again")], "", ""
    ),
    lanes.STEP_APPROACH: (
        "Changing the approach.",
        [("approach_change", "Try again"), ("cancel", lanes.CANCEL_LABEL)],
        "",
        "",
    ),
    lanes.STEP_APPROACH_REFUSED: (
        "That change touches a criterion.",
        [("switch", approach.SWITCH_LABEL), ("cancel", lanes.CANCEL_LABEL)],
        "",
        "",
    ),
    lanes.STEP_BUG: ("Describe the bug.", [("cancel", lanes.CANCEL_LABEL)], BUG_PROMPT, "Send"),
    lanes.STEP_BUG_CONFIRM: (
        "Is this the bug?",
        [
            ("repro_yes", bug.YES_LABEL),
            ("repro_no", bug.NO_LABEL),
            ("cancel", lanes.CANCEL_LABEL),
        ],
        "",
        "",
    ),
    lanes.STEP_BUG_HELP: (
        "I could not get a test that fails.",
        [("repro_no", bug.NO_LABEL), ("cancel", lanes.CANCEL_LABEL)],
        "",
        "",
    ),
    lanes.STEP_BUG_REBUILD: ("The test is saved.", [("bug_fix", LABELS["bug_fix"])], "", ""),
    owntest.STEP_OWN_CONFIRM: (
        "Your new test passes today.",
        [("own_add", owntest.ADD_LABEL), ("own_drop", owntest.DROP_LABEL)],
        "",
        "",
    ),
    owntest.STEP_OWN_FAILS: (
        owntest.FAILS_LINE,
        [("own_bug", owntest.YES_FIX_LABEL), ("own_drop", owntest.DROP_LABEL)],
        "",
        "",
    ),
}
# Steps where Get help is added (the request is REVISION_IN_PROGRESS, spec section 10).
HELP_STATUSES = (STATUS_REVISION,)


@dataclass
class Outcome:
    job: str = ""  # "build": the caller starts the build runner
    message: str = ""  # a problem of a chained step; the first step is already saved


# --- 1. which buttons ---


def get_refine_bar(settings, request_id: str) -> RefineBox:
    """The Refine controls for the step the request is at. `offered` False means none."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_workspace_tables(conn)
        conn.execute("BEGIN")
        request = read_request(conn, request_id)
        build = read_build_state(conn, request_id)
        state = read_refine_state(conn, request_id)
        workspace = read_workspace_state(conn, request_id)
        run = read_build_run(conn, request_id, build.build_number) if build else None
    if request is None or build is None or build.build_number == 0:
        return RefineBox()
    rev = state.revision if state else 0
    step = state.step if state else lanes.STEP_START
    if build.step == picks.STEP:
        note = "Pick Keep mine or Take the AI's for each place, then press Apply my choices."
        return RefineBox(
            offered=True, lane=True, note=note, refine_revision=rev,
            buttons=[("apply", LABELS["apply"])],
        )
    if step == lanes.STEP_LANE_CHOICE:
        return _lane_choice_bar(state, rev)
    if step in LANE_STEPS:
        return _lane_bar(step, request.status, rev)
    mode = workspace.mode if workspace else "picker"
    box = get_refine_box(settings, request_id, request.status, build.step, mode)
    if not box.offered or step != lanes.STEP_START:
        return box
    box.refine_revision = rev
    restore, browser = _restore_buttons(settings, request_id, state, box)
    check = [item for item in box.buttons if item[0] == rflow.CHECK_KEY]
    # In this order: the R3 buttons, Check my edits, then the Restore ones.
    box.buttons = [*_edit_buttons(request.status, run), *check, *restore]
    box.browser_buttons = [*box.browser_buttons, *browser]
    return box


def _edit_buttons(status: str, run) -> list:
    """After a failed check run the three R3 buttons (spec section 3)."""
    if status == STATUS_NOT_PASSING and run is not None and run.kind == "check":
        return [
            (edit.FIX_EDIT_KEY, edit.FIX_EDIT_LABEL),
            (edit.EDIT_RIGHT_KEY, edit.EDIT_RIGHT_LABEL),
            ("fix_myself", rflow.FIX_MYSELF_LABEL),
        ]
    return []


def _restore_buttons(settings, request_id: str, state, box: RefineBox):
    """(server buttons, browser buttons). The three parts of the Restore flow: the plain button,
    the list of builds, or the warning with Restore build N (browser) and Cancel."""
    pick = state.restore_pick if state else 0
    versions = rflow.list_versions(settings, request_id)
    others = [v for v in versions if not v.is_last_tested]
    tested = next((v.build_number for v in versions if v.is_last_tested), 0)
    if pick == tested:
        pick = 0  # the restore is done: the choice is used up
    cancel = ("restore_cancel", lanes.CANCEL_LABEL)
    if pick == -1 and others:
        listed = [(f"restore_pick:{v.build_number}", f"Restore build {v.build_number}")
                  for v in reversed(others[-5:])]
        box.note = "Pick the build to go back to."
        return [*listed, cancel], []
    if pick > 0:
        box.note = f"Restore build {pick}: read the chat, then press the button."
        box.restore_build = pick
        return [cancel], [("restore_go", f"Restore build {pick}")]
    # Always offered (spec row 8-1); with no earlier build the click says so.
    return [(rflow.RESTORE_KEY, rflow.RESTORE_LABEL)], []


def _lane_choice_bar(state, rev: int) -> RefineBox:
    buttons = [(f"lane_{lane}", label) for lane, label in lanes.LANE_LABELS.items()]
    suggested = f"lane_{state.suggested_lane}" if state and state.suggested_lane else ""
    buttons.sort(key=lambda item: item[0] != suggested)  # the suggestion first, he still decides
    note = (state.suggested_reason + " " if state and state.suggested_reason else "") + PICK_LINE
    if state and state.lane_unusable:
        note = lanes.NO_SUGGESTION_LINE
    return RefineBox(
        offered=True, lane=True, note=note, refine_revision=rev,
        buttons=[*buttons, ("cancel", lanes.CANCEL_LABEL)],
    )


def _lane_bar(step: str, status: str, rev: int) -> RefineBox:
    note, buttons, prompt, send = LANE_STEPS[step]
    buttons = list(buttons)
    if status in HELP_STATUSES:
        buttons.append(("help", LABELS["help"]))
    return RefineBox(
        offered=True, lane=True, note=note, buttons=buttons, refine_revision=rev,
        text_open=bool(prompt), placeholder=prompt, send_label=send or "Send",
    )


# --- 2. what a key does ---


@dataclass
class _Call:
    key: str
    settings: object
    request_id: str
    refine_revision: int
    build_revision: int
    text: str
    arg: str

    def rr(self) -> int:
        """The Refine revision now. Used by the second step of a chain."""
        return lanes.get_refine_revision(self.settings, self.request_id)

    def br(self) -> int:
        return build_flow.get_revision(self.settings, self.request_id)


def perform_refine(
    settings,
    key: str,
    request_id: str,
    refine_revision: int,
    text: str = "",
    arg: str = "",
    build_revision: int = 0,
) -> Outcome:
    """Call the one engine function a key stands for. An old window is refused by the engine.
    `build_revision` is only used by the keys that work on the build (check, re-scan, restore)."""
    call = _Call(key, settings, request_id, refine_revision, build_revision, text or "", arg)
    if key.startswith("restore_pick:"):  # the build number rides in the button key
        call.key, call.arg = "restore_pick", key.partition(":")[2]
    handler = HANDLERS.get(call.key)
    if handler is None:
        raise RefineError("That button runs in your browser or does not exist.")
    # An old window is refused first, before the step is looked at (a second click would
    # otherwise get "not possible at this step" instead of the stale-window message, rule F2).
    if call.rr() != refine_revision:
        raise StaleRevisionError(STALE_MESSAGE)
    return handler(call)


def _chain(call: _Call, step: Callable[[], object]) -> Outcome:
    """The step that starts by itself after the click (like Discover after Proceed). A problem is
    shown as a message and the screen offers Try again; the first step stays saved."""
    try:
        step()
    except SHOWN_CHAIN_ERRORS as error:
        return Outcome(message=str(error))
    return Outcome(job=_job(call))


def _job(call: _Call) -> str:
    step = build_flow.get_state(call.settings, call.request_id).step
    return BUILD_JOB if step == "b_running" else ""


def _send(call: _Call) -> Outcome:
    state = lanes.get_refine_state(call.settings, call.request_id)
    step = state.step if state else lanes.STEP_START
    s, r, rr = call.settings, call.request_id, call.refine_revision
    if step == lanes.STEP_REQ_CHECKPOINT:
        lanes.revise(s, r, rr, correction=call.text)
    elif step == lanes.STEP_BUG:
        bug.start_repro(s, r, rr, description=call.text)
    elif step == lanes.STEP_START:
        lanes.suggest(s, r, call.text, rr)
    else:
        raise RefineError("That is not possible at this step of the Refine.")
    return Outcome()


def _lane(call: _Call) -> Outcome:
    s, r = call.settings, call.request_id
    lane = LANE_KEYS[call.key]
    lanes.choose_lane(s, r, lane, call.refine_revision)
    if lane == "requirement":
        return _chain(call, lambda: lanes.revise(s, r, call.rr()))
    if lane == "approach":
        return _chain(call, lambda: approach.start_approach_change(s, r, call.rr()))
    return _chain(call, lambda: bug.start_repro(s, r, call.rr()))


def _plain(function: Callable) -> Callable[[_Call], Outcome]:
    """A key that calls `function(settings, request_id, refine_revision)` and nothing else."""

    def run(call: _Call) -> Outcome:
        function(call.settings, call.request_id, call.refine_revision)
        return Outcome()

    return run


def _with_build_revision(function: Callable) -> Callable[[_Call], Outcome]:
    def run(call: _Call) -> Outcome:
        function(call.settings, call.request_id, call.build_revision)
        return Outcome(job=_job(call))

    return run


def _confirm_v2(call: _Call) -> Outcome:
    s, r = call.settings, call.request_id
    lanes.confirm_revision(s, r, call.refine_revision)
    return _chain(call, lambda: revision.run_discover(s, r, call.rr()))


def _findings_ok(call: _Call) -> Outcome:
    s, r = call.settings, call.request_id
    revision.confirm_findings(s, r, call.refine_revision)
    return _chain(call, lambda: revision.start_revision_approach(s, r, call.rr()))


def _switch(call: _Call) -> Outcome:
    s, r = call.settings, call.request_id
    approach.switch_to_requirement(s, r, call.refine_revision)
    return _chain(call, lambda: lanes.revise(s, r, call.rr()))


def _edit_right(call: _Call) -> Outcome:
    s, r = call.settings, call.request_id
    edit.edit_right(s, r, call.refine_revision)
    return _chain(call, lambda: lanes.revise(s, r, call.rr()))


def _repro_yes(call: _Call) -> Outcome:
    s, r = call.settings, call.request_id
    bug.confirm_repro(s, r, call.refine_revision)
    return _chain(call, lambda: bug.start_bug_fix(s, r, call.rr()))


def _own_add(call: _Call) -> Outcome:
    s, r = call.settings, call.request_id
    owntest.confirm_own_test(s, r, call.refine_revision)
    return _chain(call, lambda: rflow.start_check(s, r, call.br(), after_new_test=True))


def _own_bug(call: _Call) -> Outcome:
    s, r = call.settings, call.request_id
    owntest.treat_as_bug(s, r, call.refine_revision)
    return _chain(call, lambda: bug.start_bug_fix(s, r, call.rr()))


def _fix_edit(call: _Call) -> Outcome:
    edit.fix_edit(call.settings, call.request_id, call.refine_revision)
    return Outcome(job=_job(call))


def _bug_fix(call: _Call) -> Outcome:
    bug.start_bug_fix(call.settings, call.request_id, call.refine_revision)
    return Outcome(job=_job(call))


def _fix_it(call: _Call) -> Outcome:
    fixit.fix_it(call.settings, call.request_id, call.refine_revision, call.arg)
    return Outcome(job=_job(call))


def _add_case(call: _Call) -> Outcome:
    owntest.add_test_case(call.settings, call.request_id, call.refine_revision, call.arg, call.text)
    return Outcome()


def _restore_pick(call: _Call) -> Outcome:
    edit.pick_restore(call.settings, call.request_id, int(call.arg), call.refine_revision)
    return Outcome()


def perform_pick(
    settings, request_id: str, path: str, conflict_id: str, choice: str, build_revision: int
) -> None:
    """Keep mine or Take the AI's for one conflict (the build revision is the window's)."""
    picks.pick(settings, request_id, path, conflict_id, choice, build_revision)


HANDLERS: dict[str, Callable[[_Call], Outcome]] = {
    SEND_KEY: _send,
    "check_edits": _with_build_revision(lambda s, r, br: rflow.start_check(s, r, br)),
    "restore": _plain(edit.open_restore),
    "restore_pick": _restore_pick,
    "restore_cancel": _plain(edit.close_restore),
    "fix_edit": _fix_edit,
    "edit_right": _edit_right,
    "fix_myself": _with_build_revision(rflow.fix_myself),
    "cancel": _plain(lanes.cancel),
    "revise": _plain(lanes.revise),
    "confirm_v2": _confirm_v2,
    "discover": _plain(revision.run_discover),
    "findings_ok": _findings_ok,
    "rev_approach": _plain(revision.start_revision_approach),
    "approach_change": _plain(approach.start_approach_change),
    "switch": _switch,
    "repro_no": _plain(bug.reject_repro),
    "repro_yes": _repro_yes,
    "bug_fix": _bug_fix,
    "own_add": _own_add,
    "own_drop": _plain(owntest.drop_own_test),
    "own_bug": _own_bug,
    "help": _plain(help_.request_help),
    "apply": _with_build_revision(picks.apply_choices),
    "fixit": _fix_it,
    "add_case": _add_case,
    **{key: _lane for key in LANE_KEYS},
}
