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
from agents.da_workspace_checks import (
    FactsProblem,
    build_write_job,
    fingerprint,
    line_ending_of,
    rescan_results,
    stop_message,
    verify_facts,
    verify_report,
)
from da_logging import get_logger
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_approach import (
    read_approach_state,
    read_approach_versions,
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
    read_latest_code,
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
    insert_workspace_file,
    read_file_versions,
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
from pydantic_classes.da_workspace_models import (
    FolderFacts,
    WorkspaceFile,
    WorkspaceMode,
    WriteJob,
    WriteReport,
    WrittenFile,
)

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


# --- writing the code files to the developer's folder (spec section 9) ---


def prepare_write(settings, request_id: str, base_revision: int) -> WriteJob:
    """Hop 1 of the write: the job for the browser. Code files only, in file-plan order; the test
    file is never in it (the job builder refuses tests/). Nothing is saved yet."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_workspace_tables(conn)
        conn.execute("BEGIN")
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        _require_step(state or BuildState(request_id=request_id), "b_done")
        return _job_for(conn, request_id, state)


def save_write(
    settings,
    request_id: str,
    report: WriteReport,
    base_revision: int,
    mode: WorkspaceMode = "picker",
    now: datetime | None = None,
) -> BuildState:
    """Hop 2 of the write: the browser ran the job. ONE transaction saves the `written` rows,
    the audit event, the chat line and the new step. The job is rebuilt here from the saved
    code and the server accepts only paths that are in it (rule W3)."""
    now = now or datetime.now(UTC)
    with _turn(settings.db_path, request_id, base_revision, now) as tx:
        _require_step(tx.state, "b_done")
        job = _job_for(tx.conn, request_id, tx.state)
        try:
            verify_report(job, report)
        except FactsProblem as error:
            raise BuildError(str(error)) from error
        approach_version = tx.state.approach_version
        for item in report.written:
            _insert_written(tx, item, mode, approach_version)
        if report.written:
            tx.audit(
                "system",
                "workspace_written",
                {"mode": mode, "files": {i.path: fingerprint(i.text) for i in report.written}},
            )
        if report.stopped is not None:
            tx.audit(
                "system",
                "workspace_write_stopped",
                {"path": report.stopped.path, "reason": report.stopped.reason},
            )
            tx.say("assistant", stop_message(job, report))
            tx.set(step="b_write_stopped", write_state="stopped")
        else:
            tx.say("assistant", _written_text(report, mode))
            tx.set(step="b_written", write_state="written")
    return get_state(settings, request_id)


def prepare_build_download(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> tuple[WriteJob, str]:
    """Download mode (spec section 9): the ZIP holds the build's code files only. The files are
    recorded as `written` with mode download, as Phase 5 did, and the readme is returned."""
    from agents.da_workspace_flow import readme_text

    job = prepare_write(settings, request_id, base_revision)
    report = WriteReport(
        written=[
            WrittenFile(path=f.path, text=f.text, fingerprint=fingerprint(f.text))
            for f in job.files
        ]
    )
    save_write(settings, request_id, report, base_revision, "download", now)
    return job, readme_text(job)


def rebuild_after_stop(
    settings,
    request_id: str,
    facts: FolderFacts,
    base_revision: int,
    now: datetime | None = None,
) -> BuildState:
    """Re-scan and build again (B9), only from b_write_stopped. The re-scan takes the developer's
    current text of every changed planned file as a `scanned` row; the new build starts from it
    with a fresh budget and the same frozen tests. Phase 6 never overwrites what he changed:
    choosing between his version and the AI's is Phase 8."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        _require_step(state or BuildState(request_id=request_id), "b_write_stopped")
        approach = _approach_of(conn, request_id, state)
        planned = [normalise_path(item.path) for item in approach.plan.files]
        try:
            verify_facts(facts, planned)
        except FactsProblem as error:
            raise BuildError(str(error)) from error
        known = {}
        for path in planned:
            versions = read_file_versions(conn, request_id, path)
            if versions:
                known[path] = versions[-1].fingerprint
        found = rescan_results(facts, planned, known)
        tx = BuildTx(conn, request, state, now)
        texts = {normalise_path(f.path): f.text for f in facts.files}
        changed = [item.path for item in found.items if item.outcome == "changed"]
        for path in changed:
            if texts.get(path) is not None:
                _insert_scanned(tx, path, texts[path], approach.approach_version)
        number = next_build_number(conn, request_id)
        insert_build_run(
            conn,
            BuildRun(
                request_id=request_id,
                build_number=number,
                approach_version=state.approach_version,
                started_at=now,
            ),
        )
        tx.say("developer", REBUILD_LABEL)
        tx.audit("system", "build_prescan", {"changed": len(changed)})
        tx.move_to(STATUS_BUILDING)
        tx.audit("developer", "build_started", {"build": number, "after_stop": True})
        tx.say("assistant", STARTED_MESSAGE)
        tx.say("assistant", DONT_EDIT_MESSAGE)
        tx.set(
            build_number=number,
            step="b_running",
            current_round=0,
            write_state="not_written",
            message="",
        )
        return _save(tx, base_revision)


def _job_for(conn: sqlite3.Connection, request_id: str, state: BuildState) -> WriteJob:
    approach = _approach_of(conn, request_id, state)
    workspace = read_workspace_state(conn, request_id)
    code = read_latest_code(conn, request_id, state.build_number)
    planned = [normalise_path(item.path) for item in approach.plan.files]
    known = {}
    for path in planned:
        versions = read_file_versions(conn, request_id, path)
        if versions:  # the newest known text: baseline, his re-scan, or an earlier write
            known[path] = (versions[-1].fingerprint, versions[-1].line_ending)
    items = [(path, code[path].text) for path in planned if path in code]
    folder = workspace.folder_name if workspace and workspace.folder_name else "your folder"
    try:
        return build_write_job(request_id, folder, items, known)
    except FactsProblem as error:
        raise BuildError(str(error)) from error


def _approach_of(conn: sqlite3.Connection, request_id: str, state: BuildState):
    versions = {v.approach_version: v for v in read_approach_versions(conn, request_id)}
    return versions[state.approach_version]


def _insert_written(tx: BuildTx, item: WrittenFile, mode: WorkspaceMode, approach_version: int):
    insert_workspace_file(
        tx.conn,
        WorkspaceFile(
            request_id=tx.request.request_id,
            path=item.path,
            file_version=1,
            kind="written",
            text=item.text,
            fingerprint=fingerprint(item.text),
            line_ending=line_ending_of(item.text),
            mode=mode,
            approach_version=approach_version,
        ),
        tx.now,
    )


def _insert_scanned(tx: BuildTx, path: str, text: str, approach_version: int) -> None:
    insert_workspace_file(
        tx.conn,
        WorkspaceFile(
            request_id=tx.request.request_id,
            path=path,
            file_version=1,
            kind="scanned",
            text=text,
            fingerprint=fingerprint(text),
            line_ending=line_ending_of(text),
            mode="picker",
            approach_version=approach_version,
        ),
        tx.now,
    )


def _written_text(report: WriteReport, mode: WorkspaceMode) -> str:
    count = len(report.written)
    where = "to your folder" if mode == "picker" else "into the ZIP"
    names = ", ".join(item.path for item in report.written)
    return (
        f"Wrote {count} code file{'s' if count != 1 else ''} {where}: {names}. "
        "Try it yourself: start CodeVision on your laptop and test the change by hand."
    )


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
