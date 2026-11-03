"""The Build actions the screen calls (spec section 1), and the shared save helper.

Thin, like da_workspace_flow: read with no lock, do the slow work outside any transaction, then
ONE write transaction holds state, rows, audit events and chat lines together (rule B3). The
build has its own revision for the stale-window check. The loop itself, which runs on a
background thread, is in da_build_loop.py.

AS400 picture: SBMJOB. These actions submit, hold, end or ask for help with the job; the loop is
the job itself, writing its log to the database as it goes.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agents.da_approach_checks import normalise_path
from agents.da_approach_flow import CAP_MESSAGE, CHANGE_APPROACH_OPTION, HELP_BUTTON, TEXT_PROMPTS
from da_logging import get_logger
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_approach import (
    read_approach_state,
    save_approach_state,
)
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_build import (
    BuildError,
    close_build_run,
    ensure_build_tables,
    insert_build_run,
    next_build_number,
    read_build_revision,
    read_build_run,
    read_build_state,
    save_build_state,
)
from db_table_functions.db_tbl_da_requests import read_request, update_request
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    add_message,
)
from db_table_functions.db_tbl_da_workspace import (
    ensure_workspace_tables,
    read_workspace_state,
    save_workspace_state,
)
from pydantic_classes.da_approach_models import MAX_CHANGES
from pydantic_classes.da_build_models import BuildRun, BuildState
from pydantic_classes.da_models import (
    STATUS_APPROACH_PROPOSED,
    STATUS_BUILDING,
    STATUS_ESCALATION,
    STATUS_NOT_PASSING,
    STATUS_READY_FOR_REVIEW,
    STATUS_READY_TO_BUILD,
    Actor,
    Request,
)
from pydantic_classes.da_request_record_models import Speaker

logger = get_logger(__name__)

# Button labels and keys. The Build button is run by JavaScript first (the pre-build re-scan).
BUILD_KEY, BUILD_LABEL = "build", "Build"
STOP_KEY, STOP_LABEL = "stop_build", "Stop build"
TRY_AGAIN_KEY, TRY_AGAIN_LABEL = "try_again", "Try again"
REBUILD_KEY, REBUILD_LABEL = "rescan_and_build", "Re-scan and build again"
CHANGE_APPROACH_KEY = "change_approach"
HELP_KEY = "help"

ESCALATED_PREFIX = "Escalated in Build: "
RUNNING_STEPS = ("b_running", "b_round_failed")
# Steps from which Get help is offered (B6).
HELP_STEPS = ("b_interrupted", "b_unable", "b_done", "b_written", "b_write_stopped")
UNABLE_MESSAGE = "I could not write tests from your plan."
DONT_EDIT_MESSAGE = "Please don't edit the planned files until I finish."
STARTED_MESSAGE = "Building. This takes a few minutes. You can leave this page."
SERVER_RESTART_MESSAGE = "The server restarted during your build."


@dataclass
class BuildTx:
    """One action's work inside its write transaction. `state` is saved when the block ends."""

    conn: sqlite3.Connection
    request: Request
    state: BuildState
    now: datetime
    dirty: bool = False

    def say(self, speaker: Speaker, text: str) -> None:
        add_message(self.conn, self.request.request_id, speaker, text, self.now)

    def audit(self, actor: Actor, event_type: str, details: dict | None = None) -> None:
        insert_audit_event(self.conn, self.request.request_id, actor, event_type, details, self.now)

    def move_to(self, status: str) -> None:
        old = self.request.status
        self.request = update_request(
            self.conn, self.request.request_id, now=self.now, status=status
        )
        self.audit("system", "status_changed", {"from": old, "to": status})

    def set(self, **changes) -> None:
        """Change the build state. It is saved, with the revision going up by one, at the end."""
        self.state = self.state.model_copy(update=changes)
        self.dirty = True

    def close_run(self, status: str, label: str, stop_reason: str, rounds_used: int) -> None:
        close_build_run(
            self.conn,
            self.request.request_id,
            self.state.build_number,
            ended_at=self.now,
            rounds_used=rounds_used,
            result_status=status,
            label=label,
            stop_reason=stop_reason,
        )


# --- the actions the screen calls ---


def start_build(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> BuildState:
    """Build (B1, B4). The request must be READY_TO_BUILD with workspace step `ws_ready`.
    Starts a new build number with a fresh budget. The loop is run by the caller (the runner)."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id) or BuildState(request_id=request_id)
        _require_can_start(conn, request, state)
        approach_state = read_approach_state(conn, request_id)
        if approach_state is None or not approach_state.accepted_approach_version:
            raise BuildError("There is no accepted approach to build.")
        number = next_build_number(conn, request_id)
        tx = BuildTx(conn, request, state, now)
        tx.set(
            build_number=number,
            step="b_running",
            approach_version=approach_state.accepted_approach_version,
            current_round=0,
            write_state="not_written",
            message="",
        )
        insert_build_run(
            conn,
            BuildRun(
                request_id=request_id,
                build_number=number,
                approach_version=approach_state.accepted_approach_version,
                started_at=now,
            ),
        )
        tx.say("developer", BUILD_LABEL)
        tx.move_to(STATUS_BUILDING)
        tx.audit("developer", "build_started", {"build": number})
        tx.say("assistant", STARTED_MESSAGE)
        tx.say("assistant", DONT_EDIT_MESSAGE)  # B8: once per build
        return _save(tx, base_revision)


def stop_build(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> BuildState:
    """Stop build (B5). No label, nothing written, back to READY_TO_BUILD. Audited."""
    now = now or datetime.now(UTC)
    with _turn(settings.db_path, request_id, base_revision, now) as tx:
        _require_step(tx.state, *RUNNING_STEPS, "b_interrupted")
        tx.close_run("", "", "Stopped by the developer.", tx.state.current_round)
        tx.say("developer", STOP_LABEL)
        tx.audit("developer", "build_stopped", {"build": tx.state.build_number})
        tx.move_to(STATUS_READY_TO_BUILD)
        tx.set(step="start", message="")
        tx.say("assistant", "The build was stopped. Nothing was written to your folder.")
    return get_state(settings, request_id)


def try_again(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> BuildState:
    """Try again. From b_interrupted it resumes the same build at the same step (no round is
    used). From b_unable it starts a new build, since no round was used and the run is closed."""
    now = now or datetime.now(UTC)
    state = get_state(settings, request_id)
    if state.step == "b_unable":
        return start_build(settings, request_id, base_revision, now)
    with _turn(settings.db_path, request_id, base_revision, now) as tx:
        _require_step(tx.state, "b_interrupted")
        tx.say("developer", TRY_AGAIN_LABEL)
        tx.audit("developer", "build_resumed", {"build": tx.state.build_number})
        tx.say("assistant", "Trying again from where I stopped.")
        tx.set(step="b_running", message="")
    return get_state(settings, request_id)


def request_help(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> BuildState:
    """Get help (B6): ESCALATION_REQUIRED, open item `Escalated in Build: <step>`."""
    now = now or datetime.now(UTC)
    with _turn(settings.db_path, request_id, base_revision, now) as tx:
        _require_step(tx.state, *HELP_STEPS)
        step = tx.state.step
        open_item = f"{ESCALATED_PREFIX}{step}"
        approach_state = read_approach_state(tx.conn, tx.request.request_id)
        if approach_state is None:
            raise BuildError("There is no approach to escalate.")
        approach_revision = approach_state.revision
        approach_state.step = "escalated"
        approach_state.open_item = open_item
        if _run_is_open(tx):
            tx.close_run("", "", "Escalated.", tx.state.current_round)
        tx.say("developer", HELP_BUTTON)
        tx.audit("developer", "escalated", {"step": step, "open_item": open_item})
        tx.move_to(STATUS_ESCALATION)
        tx.say(
            "assistant",
            "A senior developer will pick this up. (The escalations inbox comes in Phase 10.)",
        )
        save_approach_state(tx.conn, approach_state, approach_revision, now)
        tx.set(step="escalated")
    return get_state(settings, request_id)


def change_approach(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> BuildState:
    """Change the approach (B7), only from b_unable. Counts toward the 3 changes (G9)."""
    now = now or datetime.now(UTC)
    with _turn(settings.db_path, request_id, base_revision, now) as tx:
        _require_step(tx.state, "b_unable")
        approach_state = read_approach_state(tx.conn, tx.request.request_id)
        if approach_state is None or approach_state.step != "done":
            raise BuildError("The approach is not at its final step, so it cannot be reopened.")
        if approach_state.change_count >= MAX_CHANGES:
            raise BuildError(CAP_MESSAGE)
        approach_revision = approach_state.revision
        approach_state.step = "change"
        approach_state.change_count += 1
        approach_state.change_from_tests = True
        tx.say("developer", CHANGE_APPROACH_OPTION)
        tx.move_to(STATUS_APPROACH_PROPOSED)
        tx.audit(
            "developer",
            "approach_reopened",
            {"from": "b_unable", "change_count": approach_state.change_count},
        )
        tx.say("assistant", TEXT_PROMPTS["change"] + ".")
        save_approach_state(tx.conn, approach_state, approach_revision, now)
        # The old workspace check no longer matches a changed plan, so it starts over (as in
        # Phase 5), and the next approach version gets a fresh build.
        workspace = read_workspace_state(tx.conn, tx.request.request_id)
        if workspace is not None:
            fresh = workspace.model_copy(update={"step": "start", "last_check": None})
            save_workspace_state(tx.conn, fresh, workspace.revision, now)
        tx.set(step="start", message="")
    return get_state(settings, request_id)


# --- reading ---


def get_state(settings, request_id: str) -> BuildState:
    """The saved build state, or a fresh one (step `start`) when the request has no build yet."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        state = read_build_state(conn, request_id)
    return state or BuildState(request_id=request_id)


def get_revision(settings, request_id: str) -> int:
    """The build revision a window must send back with its next action. 0 = no build row yet."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        return read_build_revision(conn, request_id)


# --- helpers shared with the loop ---


@contextmanager
def _write(db_path: Path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Set up tables before taking the lock: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_audit_table(conn)
        ensure_workspace_tables(conn)
        ensure_build_tables(conn)
        begin_write(conn)
        yield conn


@contextmanager
def _turn(db_path: Path, request_id: str, base_revision: int, now: datetime) -> Iterator[BuildTx]:
    """Open one action's transaction, check the revision, and save the state at the end."""
    with _write(db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        if state is None:
            raise BuildError("There is no build for this request yet.")
        tx = BuildTx(conn, request, state, now)
        yield tx
        _save(tx, base_revision)


def _save(tx: BuildTx, base_revision: int) -> BuildState:
    saved = save_build_state(tx.conn, tx.state, base_revision, tx.now)
    tx.state = saved
    return saved


def _check_revision(conn: sqlite3.Connection, request_id: str, base_revision: int) -> None:
    if read_build_revision(conn, request_id) != base_revision:
        raise StaleRevisionError(STALE_MESSAGE)


def _require_request(conn: sqlite3.Connection, request_id: str) -> Request:
    request = read_request(conn, request_id)
    if request is None:
        raise BuildError(f"Request {request_id} does not exist.")
    return request


def _run_is_open(tx: BuildTx) -> bool:
    run = read_build_run(tx.conn, tx.request.request_id, tx.state.build_number)
    return run is not None and run.ended_at is None


def _require_can_start(conn: sqlite3.Connection, request: Request, state: BuildState) -> None:
    if request.status != STATUS_READY_TO_BUILD:
        raise BuildError(_wrong_status_message(request.status))
    workspace = read_workspace_state(conn, request.request_id)
    if workspace is None or workspace.step != "ws_ready":
        raise BuildError("Choose and check your workspace folder first. Build needs it.")
    if state.step not in ("start", "b_unable"):
        raise BuildError(_wrong_step_message(state.step))


def _require_step(state: BuildState, *steps: str) -> None:
    if state.step not in steps:
        raise BuildError(_wrong_step_message(state.step))


def _wrong_status_message(status: str) -> str:
    if status in (STATUS_BUILDING,):
        return "A build is already running for this request."
    if status in (STATUS_READY_FOR_REVIEW, STATUS_NOT_PASSING):
        return "This request has already been built. Changing it again is a later phase (Refine)."
    return "Build can only start when the request is READY TO BUILD."


def _wrong_step_message(step: str) -> str:
    messages = {
        "start": "Press Build first.",
        "b_running": "The build is running. You can stop it or wait.",
        "b_round_failed": "The build is running. You can stop it or wait.",
        "b_interrupted": "The build paused. Try again, stop it, or get help.",
        "b_unable": "I could not write tests. Try again, change the approach, or get help.",
        "b_done": "The build is finished and is being written to your folder.",
        "b_written": "The build is finished and written to your folder.",
        "b_write_stopped": "The write stopped because you changed a file. Re-scan and build again.",
        "escalated": "This request was handed to a senior developer.",
    }
    return messages.get(step, "That is not possible at this step.")


def planned_paths_of(approach) -> list[str]:
    return [normalise_path(item.path) for item in approach.plan.files]
