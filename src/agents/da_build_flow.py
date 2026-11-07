"""The Build actions the screen calls (spec section 1), and the shared save helper.

Thin, like da_workspace_flow: read with no lock, do the slow work outside any transaction, then
ONE write transaction holds state, rows, audit events and chat lines together (rule B3). The
build has its own revision for the stale-window check. The loop itself, which runs on a
background thread, is in da_build_loop.py.

AS400 picture: SBMJOB. These actions submit, hold, end or ask for help with the job; the loop is
the job itself, writing its log to the database as it goes.
"""

import ast
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agents.da_approach_checks import normalise_path
from agents.da_approach_flow import CAP_MESSAGE, CHANGE_APPROACH_OPTION, HELP_BUTTON, TEXT_PROMPTS
from agents.da_build_checks import case_ids_from_method, find_test_methods
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
    read_test_plans,
    save_approach_state,
)
from db_table_functions.db_tbl_da_audit import (
    ensure_audit_table,
    insert_audit_event,
    list_audit_events,
)
from db_table_functions.db_tbl_da_build import (
    BuildError,
    close_build_run,
    ensure_build_tables,
    insert_build_run,
    next_build_number,
    read_build_revision,
    read_build_run,
    read_build_state,
    read_frozen_files,
    read_latest_code,
    read_progress,
    read_rounds,
    save_build_state,
)
from db_table_functions.db_tbl_da_requests import (
    get_rulebook_for_request,
    read_request,
    update_request,
)
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
from pydantic_classes.da_build_models import (
    BuildFileRow,
    BuildRun,
    BuildState,
    BuildView,
    TestRow,
)
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
STOP_KEY, STOP_LABEL = "stop_build", "Cancel build"
TRY_AGAIN_KEY, TRY_AGAIN_LABEL = "try_again", "Resume build"
CANCEL_MESSAGE = (
    "The build was cancelled. Nothing was written to your folder. "
    "The record of this build stays in the Audit tab."
)
REBUILD_KEY, REBUILD_LABEL = "rebuild", "Re-scan and build again"
CHANGE_APPROACH_KEY = "change_approach"
HELP_KEY = "help"

ESCALATED_PREFIX = "Escalated in Build: "
RUNNING_STEPS = ("b_running", "b_round_failed", "b_tester_review")
# Steps from which Get help is offered (B6).
HELP_STEPS = ("b_interrupted", "b_unable", "b_done", "b_written", "b_write_stopped")
UNABLE_MESSAGE = "I could not write tests from your plan."
DONT_EDIT_MESSAGE = "Please don't edit the planned files until I finish."
STARTED_MESSAGE = "Building. This takes a few minutes. You can leave this page."
PRESCAN_MESSAGE = "Checking your folder before I start."
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
    settings,
    request_id: str,
    base_revision: int,
    now: datetime | None = None,
    facts: FolderFacts | None = None,
) -> BuildState:
    """Build (B1, B4). The request must be READY_TO_BUILD with workspace step `ws_ready`.
    Starts a new build number with a fresh budget. The loop is run by the caller (the runner).

    `facts` is the pre-build re-scan from the browser (B1): a planned file the developer changed
    is saved as a `scanned` row, and his text becomes the starting text for the build (D-K)."""
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
        if facts is not None:
            changed = _save_prescan(tx, approach_state.accepted_approach_version, facts)
            tx.say("assistant", PRESCAN_MESSAGE)
            tx.audit("system", "build_prescan", {"changed": changed})
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
        tx.say("assistant", CANCEL_MESSAGE)
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
        tx.say("assistant", "Resuming the build from where I stopped.")
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
        tx.say("developer", HELP_BUTTON)
        escalate(tx, f"{ESCALATED_PREFIX}{step}", {"step": step})
    return get_state(settings, request_id)


def escalate(tx: BuildTx, open_item: str, details: dict) -> None:
    """Hand the request to a senior (ESCALATION_REQUIRED) with a named open item. Used by Get help
    and by Dispute (Phase 7). Call it inside an action's transaction."""
    approach_state = read_approach_state(tx.conn, tx.request.request_id)
    if approach_state is None:
        raise BuildError("There is no approach to escalate.")
    approach_revision = approach_state.revision
    approach_state.step = "escalated"
    approach_state.open_item = open_item
    if _run_is_open(tx):
        tx.close_run("", "", "Escalated.", tx.state.current_round)
    tx.audit("developer", "escalated", details | {"open_item": open_item})
    tx.move_to(STATUS_ESCALATION)
    tx.say(
        "assistant",
        "A senior developer will pick this up. (The escalations inbox comes in Phase 10.)",
    )
    save_approach_state(tx.conn, approach_state, approach_revision, tx.now)
    tx.set(step="escalated")


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
        written_paths = [i.path for i in report.written]
        if report.stopped is None and written_paths != [f.path for f in job.files]:
            # A report that says "no stop" must have written EVERY file of the job.
            raise BuildError("The browser's report does not list every file. Nothing was saved.")
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


def _save_prescan(tx: BuildTx, approach_version: int, facts: FolderFacts) -> int:
    """Take the developer's current text of every changed planned file as a `scanned` row."""
    approach = _approach_by_number(tx.conn, tx.request.request_id, approach_version)
    planned = [normalise_path(item.path) for item in approach.plan.files]
    try:
        verify_facts(facts, planned)
    except FactsProblem as error:
        raise BuildError(str(error)) from error
    known = {}
    for path in planned:
        versions = read_file_versions(tx.conn, tx.request.request_id, path)
        if versions:
            known[path] = versions[-1].fingerprint
    texts = {normalise_path(f.path): f.text for f in facts.files}
    changed = [
        item.path
        for item in rescan_results(facts, planned, known).items
        if item.outcome == "changed"
    ]
    for path in changed:
        if texts.get(path) is not None:
            _insert_scanned(tx, path, texts[path], approach_version)
    return len(changed)


def _approach_by_number(conn: sqlite3.Connection, request_id: str, number: int):
    return {v.approach_version: v for v in read_approach_versions(conn, request_id)}[number]


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


# --- what the screen shows ---


def get_build_view(settings, request_id: str) -> BuildView:
    """Everything the Build tab, the Tests tab and the chat buttons need, read on one connection
    (no lock held)."""
    policy = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    # Read BEFORE the read transaction below: a second connection opened while it is open can
    # deadlock with a build that is saving at the same moment (plan item P18).
    stopped = [
        e.details.get("path", "")
        for e in list_audit_events(settings.db_path, request_id)
        if e.event_type == "workspace_write_stopped"
    ]
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_workspace_tables(conn)
        conn.execute("BEGIN")
        request = _require_request(conn, request_id)
        saved = read_build_state(conn, request_id)
        state = saved or BuildState(request_id=request_id)
        revision = read_build_revision(conn, request_id)
        workspace = read_workspace_state(conn, request_id)
        approach_state = read_approach_state(conn, request_id)
        if state.build_number == 0:
            return _view(request.status, state, revision, policy, workspace, approach_state)
        number = state.build_number
        approach = _approach_of(conn, request_id, state)
        plans = {p.plan_version: p for p in read_test_plans(conn, request_id)}
        cases = plans[approach_state.accepted_plan_version].cases if approach_state else []
        frozen = read_frozen_files(conn, request_id, state.approach_version)
        code = read_latest_code(conn, request_id, number)
        known = {
            normalise_path(i.path): read_file_versions(conn, request_id, normalise_path(i.path))
            for i in approach.plan.files
        }
        return _view(
            request.status,
            state,
            revision,
            policy,
            workspace,
            approach_state,
            run=read_build_run(conn, request_id, number),
            progress=read_progress(conn, request_id, number),
            rounds=read_rounds(conn, request_id, number),
            cases=cases,
            frozen=frozen,
            approach=approach,
            code=code,
            known=known,
            stopped_path=stopped[-1] if stopped else "",
        )


def _view(
    status,
    state,
    revision,
    policy,
    workspace,
    approach_state,
    *,
    run=None,
    progress=(),
    rounds=(),
    cases=(),
    frozen=None,
    approach=None,
    code=None,
    known=None,
    stopped_path="",
) -> BuildView:
    frozen = frozen or {}
    test_code = frozen["test"].text if "test" in frozen else ""
    results = _latest_results(rounds)
    tests = _test_rows(cases, test_code, results)
    rows = _build_rows(approach, code or {}, known or {}, state)
    capped = bool(approach_state and approach_state.change_count >= MAX_CHANGES)
    server, browser = _build_buttons(state, capped)
    last = rounds[-1] if rounds else None
    kind, text = _banner(
        state, status, run, last, len(cases), policy.build_max_rounds, stopped_path
    )
    taken = int((run.ended_at - run.started_at).total_seconds()) if run and run.ended_at else 0
    passing = ""
    if last and last.layer_b:
        passing = f"{last.layer_b.passed} of {len(last.layer_b.tests)}"
    return BuildView(
        state=state,
        revision=revision,
        request_status=status,
        banner_kind=kind,
        banner_text=text,
        run=run,
        progress=list(progress),
        rounds=list(rounds),
        max_rounds=policy.build_max_rounds,
        time_limit=policy.build_test_timeout_seconds,
        tests=tests,
        # Layer A stopped every round, so no frozen test has a result (Phase 6 fixes, F9b).
        tests_not_run=bool(rounds)
        and not any(record.layer_b is not None for record in rounds)
        and any(row.result == "" for row in tests),
        test_code=test_code,
        rows=rows,
        label=run.label if run else "",
        buttons=server,
        browser_buttons=browser,
        polling=state.step in RUNNING_STEPS,
        auto_write=state.step == "b_done" and state.write_state == "not_written",
        folder_name=workspace.folder_name if workspace else "",
        mode=workspace.mode if workspace else "picker",
        seconds_taken=taken,
        tests_passing=passing,
    )


def _latest_results(rounds) -> dict[str, str]:
    """test id -> its newest result, from the newest round that ran the tests."""
    for record in reversed(list(rounds)):
        if record.layer_b is not None:
            found = {}
            for item in record.layer_b.tests:
                ids = case_ids_from_method(item.name)
                if ids:
                    found[ids[0]] = item.result
            return found
    return {}


def _test_rows(cases, test_code: str, results: dict[str, str]) -> list[TestRow]:
    docs = {}
    if test_code:
        try:
            for name, method in find_test_methods(ast.parse(test_code)).items():
                ids = case_ids_from_method(name)
                if ids:
                    docs[ids[0]] = (ast.get_docstring(method) or "").split("\n")[0]
        except SyntaxError:
            pass
    return [
        TestRow(
            test_id=case.test_id,
            criterion_id=case.criterion_id,
            yours=case.source == "developer",
            description=docs.get(case.test_id) or case.expect,
            result=results.get(case.test_id, ""),
        )
        for case in cases
    ]


def _build_rows(approach, code, known, state) -> list[BuildFileRow]:
    if approach is None:
        return []
    rows = []
    for item in approach.plan.files:
        path = normalise_path(item.path)
        built = code.get(path)
        last = known.get(path) or []
        written = bool(
            built
            and last
            and last[-1].kind == "written"
            and last[-1].fingerprint == built.fingerprint
        )
        rows.append(
            BuildFileRow(
                path=path,
                action="New" if item.action == "create" else "Change",
                status="Written" if written else ("Not written yet" if built else "Waiting"),
            )
        )
    return rows


def _build_buttons(state: BuildState, capped: bool):
    """(server buttons, browser buttons) for one build step (spec section 1 table)."""
    step = state.step
    if step in RUNNING_STEPS:
        return [(STOP_KEY, STOP_LABEL)], []
    if step == "b_interrupted":
        return [
            (TRY_AGAIN_KEY, TRY_AGAIN_LABEL),
            (STOP_KEY, STOP_LABEL),
            (HELP_KEY, HELP_BUTTON),
        ], []
    if step == "b_unable":
        change = [] if capped else [(CHANGE_APPROACH_KEY, CHANGE_APPROACH_OPTION)]
        return [(TRY_AGAIN_KEY, TRY_AGAIN_LABEL), *change, (HELP_KEY, HELP_BUTTON)], []
    if step in ("b_done", "b_written"):
        return [(HELP_KEY, HELP_BUTTON)], []
    if step == "b_write_stopped":
        return [(HELP_KEY, HELP_BUTTON)], [(REBUILD_KEY, REBUILD_LABEL)]
    return [], []


def _banner(state, status, run, last, cases: int, limit: int, stopped_path: str):
    step = state.step
    if step in RUNNING_STEPS:
        if last is not None and not (last.layer_a.ok and last.layer_b and last.layer_b.ok):
            return "red", _failed_banner(last, cases, limit)
        if step == "b_tester_review" and last is not None:
            return "blue", (
                f"Round {last.round} of {limit}: tests pass. "
                "The independent Tester is reviewing the code."
            )
        if step == "b_round_failed" and last is not None:  # the Tester's Must fix (Phase 7)
            return "red", (
                f"Round {last.round} of {limit}: the Tester found a Must fix. Only the file it "
                f"names is regenerated. Tests stay frozen. 1 shared budget of {limit} rounds."
            )
        number = last.round + 1 if last else 1
        return "blue", (
            f"Round {number} of {limit}. Running on the server. "
            "You can leave this page and come back."
        )
    if step == "b_interrupted":
        return "orange", f"The build paused: {state.message}"
    if step == "b_unable":
        return "orange", f"{UNABLE_MESSAGE} {state.message}".strip()
    if step == "b_write_stopped":
        return "orange", (
            f"You changed {stopped_path} while I was building. Nothing after it was written."
        )
    if step in ("b_done", "b_written"):
        label = run.label if run else ""
        colour = "red" if status == STATUS_NOT_PASSING else "green"
        if step == "b_done":
            colour = "blue"
            return colour, "Built, not written yet. Open this request with your workspace allowed."
        return colour, f"{label}. The code files are in your folder."
    return "", ""


def _failed_banner(last, cases: int, limit: int) -> str:
    report = last.failure_report
    files = ", ".join(path.rsplit("/", 1)[-1] for path in (report.files_to_fix if report else []))
    failed = last.layer_b.failed if last.layer_b else 0
    head = (
        f"Round {last.round} of {limit}: {failed} of {cases} tests failed."
        if last.layer_b
        else f"Round {last.round} of {limit}: the code did not pass the checks."
    )
    return (
        f"{head} Only {files} is regenerated. Tests stay frozen. 1 shared budget of {limit} rounds."
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
        "b_running": "The build is running. You can cancel it or wait.",
        "b_round_failed": "The build is running. You can cancel it or wait.",
        "b_tester_review": "The independent Tester is reviewing the code. You can cancel or wait.",
        "b_interrupted": "The build paused. Resume it, cancel it, or get help.",
        "b_unable": "I could not write tests. Resume the build, change the approach, or get help.",
        "b_done": "The build is finished and is being written to your folder.",
        "b_written": "The build is finished and written to your folder.",
        "b_write_stopped": "The write stopped because you changed a file. Re-scan and build again.",
        "escalated": "This request was handed to a senior developer.",
    }
    return messages.get(step, "That is not possible at this step.")


def planned_paths_of(approach) -> list[str]:
    return [normalise_path(item.path) for item in approach.plan.files]
