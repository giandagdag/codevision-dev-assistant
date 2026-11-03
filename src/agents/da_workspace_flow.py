"""The Workspace actions the screen calls (spec section 1). Thin, like da_approach_flow.

The browser does the file work between two server calls; the server only judges and keeps the
record. Each action reads with no lock held, and every save is ONE write transaction that holds
state, file rows, audit events and chat lines together (rule W2). The workspace has its own
revision number for the stale-window check.

AS400 picture: the program that holds the change form (the file plan) decides which members may
be touched; the workstation job does the actual CHGPFM and reports back; this module journals it.
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
    check_facts,
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
    read_latest_approach,
    save_approach_state,
)
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
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
    read_messages,
)
from db_table_functions.db_tbl_da_workspace import (
    WorkspaceError,
    ensure_workspace_tables,
    insert_scan,
    insert_workspace_file,
    read_baseline_times,
    read_known_files,
    read_latest_scan,
    read_workspace_revision,
    read_workspace_state,
    save_workspace_state,
)
from pydantic_classes.da_approach_models import MAX_CHANGES, ApproachVersion, PlannedFile
from pydantic_classes.da_models import (
    STATUS_APPROACH_PROPOSED,
    STATUS_ESCALATION,
    STATUS_READY_TO_BUILD,
    Actor,
    Request,
)
from pydantic_classes.da_request_record_models import Speaker
from pydantic_classes.da_rulebook_models import Policy
from pydantic_classes.da_workspace_models import (
    CheckResult,
    FileRow,
    FolderFacts,
    WorkspaceFile,
    WorkspaceMode,
    WorkspaceState,
    WorkspaceStep,
    WorkspaceView,
    WriteJob,
    WriteReport,
)

logger = get_logger(__name__)

# Button labels and keys. "Browser" buttons are run by JavaScript; "server" buttons by Python.
CHOOSE_KEY, CHOOSE_LABEL = "choose", "Choose workspace folder"
CHOOSE_OTHER_LABEL = "Choose another folder"
RESCAN_KEY, RESCAN_LABEL = "rescan", "Re-scan"
CHANGE_FOLDER_KEY, CHANGE_FOLDER_LABEL = "change_folder", "Change"
DOWNLOAD_KEY, DOWNLOAD_LABEL = "download", "Download ZIP"
UPLOAD_KEY, UPLOAD_LABEL = "upload", "Upload folder to check"
RETRY_PICKER_KEY, RETRY_PICKER_LABEL = "retry_picker", "Try the folder picker again"
CHANGE_APPROACH_KEY = "change_approach"
HELP_KEY = "help"
BUILD_LABEL = "Build (coming in Phase 6)"

ESCALATED_PREFIX = "Escalated in Workspace: "
DOWNLOAD_ADVICE = (
    "In download mode, upload your folder before every new download so I never overwrite "
    "your edits."
)
NO_FOLDER_TEXT = "No folder chosen."

README_NAME = "READ_ME_FIRST.txt"
SCAN_KINDS = ("unchanged", "changed", "missing")


@dataclass
class Judgement:
    """The answer to a set of facts: a blocked view (already saved), or a job to run."""

    job: WriteJob | None
    view: WorkspaceView


@dataclass
class DownloadPackage:
    """What the browser needs to build the ZIP: the files and the one-page note."""

    job: WriteJob
    readme: str
    view: WorkspaceView


@dataclass
class _Snap:
    request: Request
    approach: ApproachVersion
    approach_state_step: str
    approach_change_count: int
    state: WorkspaceState | None
    known: dict[str, WorkspaceFile]
    policy: Policy
    revision: int

    @property
    def step(self) -> WorkspaceStep:
        return self.state.step if self.state else "start"

    @property
    def planned(self) -> list[PlannedFile]:
        return self.approach.plan.files

    @property
    def planned_paths(self) -> list[str]:
        return [normalise_path(item.path) for item in self.planned]


class _Tx:
    """One action's work inside its write transaction."""

    def __init__(self, conn: sqlite3.Connection, request: Request, now: datetime):
        self.conn = conn
        self.request = request
        self.now = now

    def say(self, speaker: Speaker, text: str) -> None:
        add_message(self.conn, self.request.request_id, speaker, text, self.now)

    def audit(self, actor: Actor, event_type: str, details: dict | None = None) -> None:
        insert_audit_event(
            self.conn, self.request.request_id, actor, event_type, details, self.now
        )

    def move_to(self, status: str) -> None:
        old = self.request.status
        self.request = update_request(
            self.conn, self.request.request_id, now=self.now, status=status
        )
        self.audit("system", "status_changed", {"from": old, "to": status})


# --- the actions the screen calls ---


def judge_facts(
    settings,
    request_id: str,
    facts: FolderFacts,
    base_revision: int,
    now: datetime | None = None,
) -> Judgement:
    """Hop 2: the browser sent its facts. Blocked: save that (one write). Passed: give the job."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "start", "ws_blocked", "ws_ready", "ws_fallback")
    result, job = _evaluate(snap, facts, request_id)
    if result.passed:
        return Judgement(job, get_workspace_view(settings, request_id))
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        _save_blocked(tx, snap, facts, result, "picker", base_revision)
    return Judgement(None, get_workspace_view(settings, request_id))


def save_check(
    settings,
    request_id: str,
    facts: FolderFacts,
    report: WriteReport,
    base_revision: int,
    now: datetime | None = None,
) -> WorkspaceView:
    """Hop 4: the browser ran the job. ONE write: baselines, written rows, state, audit, chat.

    The server does not keep the job. It rebuilds it from the saved plan and the same facts and
    accepts only what is in it (rule W3).
    """
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "start", "ws_blocked", "ws_ready", "ws_fallback")
    result, job = _evaluate(snap, facts, request_id)
    if not result.passed:
        raise WorkspaceError(
            "The folder changed while it was being checked. Please choose it again."
        )
    _verify(lambda: verify_report(job, report))
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        _save_written(tx, snap, report, "picker")
        if report.stopped is not None:
            tx.audit(
                "system", "workspace_write_stopped",
                {"path": report.stopped.path, "reason": report.stopped.reason},
            )
            tx.say("assistant", stop_message(job, report))
            # The revision still goes up, so a replay of this save is refused as stale (W2).
            # (A first-ever stop saves a state that is still at step `start`.)
            stopped_state = snap.state or WorkspaceState(request_id=request_id)
            save_workspace_state(tx.conn, stopped_state, base_revision, now)
        else:
            _save_ready(tx, snap, facts, result, "picker", base_revision)
    # Read the view only after the write has been committed.
    return get_workspace_view(settings, request_id)


def rescan(
    settings,
    request_id: str,
    facts: FolderFacts,
    base_revision: int,
    now: datetime | None = None,
) -> WorkspaceView:
    """Re-scan (spec section 6). Detects and lists. Never changes the step or the status (W8)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "ws_ready")
    known = {path: item.fingerprint for path, item in snap.known.items()}
    try:
        result = rescan_results(facts, snap.planned_paths, known)
    except FactsProblem as error:
        raise WorkspaceError(str(error)) from error
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        insert_scan(conn, request_id, result, now)
        _save_scanned(tx, snap, facts, result, snap.state.mode)
        tx.audit(
            "developer", "workspace_rescanned",
            {kind: result.count(kind) for kind in SCAN_KINDS},
        )
        tx.say("developer", RESCAN_LABEL)
        tx.say("assistant", _scan_text(result))
        save_workspace_state(conn, snap.state, base_revision, now)
    return get_workspace_view(settings, request_id)


def picker_cancelled(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> WorkspaceView:
    """The developer closed the picker. Back at start with a chat line; nothing else is saved."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "start", "ws_blocked", "ws_ready", "ws_fallback")
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        tx.say("assistant", NO_FOLDER_TEXT)
    return get_workspace_view(settings, request_id)


def different_folder(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> WorkspaceView:
    """The picked folder has the linked folder's NAME but is another folder (P26). One chat
    line; nothing is linked and the revision does not move. The name comes from the saved
    link, not from the browser (rule W3)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "start", "ws_blocked", "ws_ready", "ws_fallback")
    name = snap.state.folder_name if snap.state else ""
    if not name:
        raise WorkspaceError(
            "No folder is linked to this request yet, so there is nothing to compare."
        )
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        tx.say("assistant", different_folder_text(name))
    return get_workspace_view(settings, request_id)


def different_folder_text(name: str) -> str:
    return f"This is a different folder that is also called {name}. Use Change to link it."


def use_fallback(
    settings, request_id: str, reason: str, base_revision: int, now: datetime | None = None
) -> WorkspaceView:
    """The picker is not available or was refused: offer the ZIP and upload (spec section 7)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "start", "ws_blocked", "ws_fallback")
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        state = (snap.state or WorkspaceState(request_id=request_id)).model_copy(
            update={"step": "ws_fallback", "mode": "download"}
        )
        tx.audit("developer", "workspace_fallback_used", {"which": reason})
        tx.say(
            "assistant",
            "I cannot reach your folder from this page. You can download the files as a ZIP, "
            "then upload your folder so I can check it.",
        )
        save_workspace_state(conn, state, base_revision, now)
    return get_workspace_view(settings, request_id)


def prepare_download(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> DownloadPackage:
    """Download ZIP: record the files as `written` with mode download, hand back the job."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "ws_fallback", "ws_ready")
    if snap.state.mode != "download":
        raise WorkspaceError("Download mode is not in use for this request.")
    job = _empty_job(request_id, snap.state.folder_name or "your folder")
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        for item in job.files:
            _insert_file(tx, snap, item.path, item.text, "written", "download")
        tx.audit("developer", "workspace_fallback_used", {"which": "download"})
        if job.files:  # before a build there is nothing to hand over, so nothing to journal
            tx.audit(
                "system",
                "workspace_written",
                {"mode": "download", "files": {i.path: fingerprint(i.text) for i in job.files}},
            )
        already = any(DOWNLOAD_ADVICE in m.text for m in read_messages(conn, request_id))
        tx.say("developer", DOWNLOAD_LABEL)
        tx.say("assistant", "The ZIP is ready. " + ("" if already else DOWNLOAD_ADVICE))
        save_workspace_state(conn, snap.state, base_revision, now)
    return DownloadPackage(job, readme_text(job), get_workspace_view(settings, request_id))


def check_uploaded(
    settings,
    request_id: str,
    facts: FolderFacts,
    base_revision: int,
    now: datetime | None = None,
) -> WorkspaceView:
    """Upload folder to check: the same check as the picker, on what the page sent. Nothing is
    written to the laptop, so a pass only takes the baselines (spec section 7)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "ws_fallback", "ws_blocked")
    result, _job = _evaluate(snap, facts, request_id)
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        tx.audit("developer", "workspace_fallback_used", {"which": "upload"})
        if not result.passed:
            _save_blocked(tx, snap, facts, result, "download", base_revision)
        else:
            _save_ready(tx, snap, facts, result, "download", base_revision)
    return get_workspace_view(settings, request_id)


def change_approach(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> WorkspaceView:
    """Change the approach from a blocked check (W5). Counts toward the 3 changes (G9)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "ws_blocked")
    if snap.approach_change_count >= MAX_CHANGES:
        raise WorkspaceError(CAP_MESSAGE)
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        approach_state = read_approach_state(conn, request_id)
        if approach_state is None or approach_state.step != "done":
            raise WorkspaceError("The approach is not at its final step, so it cannot be reopened.")
        approach_revision = approach_state.revision
        approach_state.step = "change"
        # Row 5-19: the counter goes up now (G9). The flag tells the Approach change step that
        # this change is already counted, so it is not counted a second time when sent.
        approach_state.change_count += 1
        approach_state.change_from_tests = True
        tx.say("developer", CHANGE_APPROACH_OPTION)
        tx.move_to(STATUS_APPROACH_PROPOSED)
        tx.audit(
            "developer", "approach_reopened",
            {"from": "ws_blocked", "change_count": approach_state.change_count},
        )
        tx.say("assistant", TEXT_PROMPTS["change"] + ".")
        save_approach_state(conn, approach_state, approach_revision, now)
        # The old check no longer matches a changed plan, so the workspace starts over.
        fresh = snap.state.model_copy(update={"step": "start", "last_check": None})
        save_workspace_state(conn, fresh, base_revision, now)
    return get_workspace_view(settings, request_id)


def request_help(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> WorkspaceView:
    """Get help from a blocked check (W6). The workspace step stays ws_blocked (not lost)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "ws_blocked")
    open_item = f"{ESCALATED_PREFIX}{snap.step}"
    with _write(settings.db_path) as conn:
        tx = _begin(conn, request_id, base_revision, now)
        approach_state = read_approach_state(conn, request_id)
        if approach_state is None:
            raise WorkspaceError("There is no approach to escalate.")
        approach_revision = approach_state.revision
        approach_state.step = "escalated"
        approach_state.open_item = open_item
        tx.say("developer", HELP_BUTTON)
        tx.audit("developer", "escalated", {"step": snap.step, "open_item": open_item})
        tx.move_to(STATUS_ESCALATION)
        tx.say(
            "assistant",
            "A senior developer will pick this up. (The escalations inbox comes in Phase 10.)",
        )
        save_approach_state(conn, approach_state, approach_revision, now)
        save_workspace_state(conn, snap.state, base_revision, now)
    return get_workspace_view(settings, request_id)


# --- what the screen shows ---


def get_workspace_view(settings, request_id: str) -> WorkspaceView:
    """Everything the screen needs for the workspace, read on one connection."""
    with open_db(settings.db_path) as conn:
        ensure_workspace_tables(conn)
        ensure_audit_table(conn)
        conn.execute("BEGIN")
        request = _require_request(conn, request_id)
        approach = read_latest_approach(conn, request_id)
        approach_state = read_approach_state(conn, request_id)
        state = read_workspace_state(conn, request_id)
        messages = read_messages(conn, request_id)
        scan = read_latest_scan(conn, request_id)
        known = read_known_files(conn, request_id)
        baselines = read_baseline_times(conn, request_id)
        revision = read_workspace_revision(conn, request_id)
    if approach is None:
        raise WorkspaceError("This request has no approach yet, so it has no workspace.")
    policy = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    step: WorkspaceStep = state.step if state else "start"
    mode: WorkspaceMode = state.mode if state else "picker"
    capped = approach_state is not None and approach_state.change_count >= MAX_CHANGES
    rows = _file_rows(approach, known, baselines, scan)
    server, browser, note = _buttons_for(step, mode, capped, bool(state and state.folder_name))
    return WorkspaceView(
        request=request,
        messages=messages,
        step=step,
        folder_name=state.folder_name if state else "",
        mode=mode,
        check=state.last_check if state else None,
        checked_at=state.checked_at if state else None,
        rows=rows,
        last_scan=scan,
        buttons=server,
        browser_buttons=browser,
        note=note,
        open_item=approach_state.open_item if approach_state else "",
        revision=revision,
        planned_paths=[normalise_path(item.path) for item in approach.plan.files],
        markers=policy.workspace_markers,
        max_file_kb=policy.workspace_max_file_kb,
        demo_mode=settings.llm_provider == "fake",
    )


def readme_text(job: WriteJob) -> str:
    """The one-page note inside the ZIP (spec section 7)."""
    lines = [
        "Developer Assistant: files to copy into your CodeVision folder",
        "",
        "1. Unzip this file into the folder that contains src (your CodeVision folder).",
        "2. Say yes if your computer asks to merge folders.",
        "3. Back in the Developer Assistant, press Upload folder to check.",
        "",
        "Files in this ZIP:",
        *[f"  {item.path}" for item in job.files],
    ]
    return "\r\n".join(lines) + "\r\n"


# --- the steps behind the actions ---


def _evaluate(snap: _Snap, facts: FolderFacts, request_id: str) -> tuple[CheckResult, WriteJob]:
    """Check the facts. Pure, nothing is saved. The job is empty: the check writes nothing
    (Phase 6, C1). It stays a job so the browser steps of Phase 5 keep their shape."""
    try:
        verify_facts(facts, snap.planned_paths)
        result = check_facts(
            facts, snap.planned, snap.policy, snap.state.folder_name if snap.state else ""
        )
    except FactsProblem as error:
        raise WorkspaceError(str(error)) from error
    return result, _empty_job(request_id, facts.folder_name)


def _empty_job(request_id: str, folder_name: str) -> WriteJob:
    return build_write_job(request_id, folder_name, [], {})


def _verify(check) -> None:
    try:
        check()
    except FactsProblem as error:
        raise WorkspaceError(str(error)) from error


def _save_blocked(
    tx: _Tx, snap: _Snap, facts: FolderFacts, result: CheckResult, mode: WorkspaceMode, base: int
) -> None:
    tx.audit("developer", "workspace_chosen", {"folder": facts.folder_name})
    tx.audit(
        "system",
        "workspace_check_failed",
        {"blockers": [{"code": b.code, "path": b.path} for b in result.blockers]},
    )
    for warning in result.warnings:
        tx.say("assistant", warning)
    tx.say("assistant", "I cannot use this folder yet:")
    for blocker in result.blockers:
        tx.say("assistant", f"{blocker.code}: {blocker.text}")
    state = _base_state(snap, tx.request.request_id).model_copy(
        update={
            "step": "ws_blocked",
            "mode": mode,
            "folder_name": facts.folder_name,
            "last_check": result,
            "checked_at": tx.now,
        }
    )
    save_workspace_state(tx.conn, state, base, tx.now)


def _save_written(tx: _Tx, snap: _Snap, report: WriteReport, mode: WorkspaceMode) -> None:
    for item in report.written:
        _insert_file(tx, snap, item.path, item.text, "written", mode)
    if report.written:
        tx.audit(
            "system",
            "workspace_written",
            {"mode": mode, "files": {i.path: fingerprint(i.text) for i in report.written}},
        )


def _save_ready(
    tx: _Tx, snap: _Snap, facts: FolderFacts, result: CheckResult, mode: WorkspaceMode, base: int
) -> None:
    baselines: dict[str, str] = {}
    texts = {normalise_path(f.path): f for f in facts.files}
    for planned in snap.planned:
        path = normalise_path(planned.path)
        fact = texts[path]
        if planned.action == "modify" and fact.text is not None:
            _insert_file(tx, snap, path, fact.text, "baseline", mode)
            baselines[path] = fingerprint(fact.text)
    tx.audit("developer", "workspace_chosen", {"folder": facts.folder_name})
    tx.audit("system", "workspace_check_passed", {"warnings": result.warnings})
    tx.audit("system", "workspace_baseline_taken", {"files": baselines})
    for warning in result.warnings:
        tx.say("assistant", warning)
    tx.say("assistant", f"Your folder {facts.folder_name} passed the check.")
    for line in result.info:
        tx.say("assistant", line)
    previous = snap.state
    linked = previous.linked_at if previous and previous.folder_name == facts.folder_name else None
    state = _base_state(snap, tx.request.request_id).model_copy(
        update={
            "step": "ws_ready",
            "mode": mode,
            "folder_name": facts.folder_name,
            "last_check": result,
            "linked_at": linked or tx.now,
            "checked_at": tx.now,
        }
    )
    save_workspace_state(tx.conn, state, base, tx.now)


def _save_scanned(tx: _Tx, snap: _Snap, facts: FolderFacts, result, mode: WorkspaceMode) -> None:
    """Keep the text of every planned file the developer changed (a `scanned` row)."""
    file_texts = {normalise_path(f.path): f.text for f in facts.files}
    for item in result.items:
        if item.outcome == "changed":
            text = file_texts.get(item.path)
            if text is not None:
                _insert_file(tx, snap, item.path, text, "scanned", mode)


def _insert_file(tx: _Tx, snap: _Snap, path: str, text: str, kind, mode: WorkspaceMode) -> None:
    insert_workspace_file(
        tx.conn,
        WorkspaceFile(
            request_id=tx.request.request_id,
            path=path,
            file_version=1,
            kind=kind,
            text=text,
            fingerprint=fingerprint(text),
            line_ending=line_ending_of(text),
            mode=mode,
            approach_version=snap.approach.approach_version,
        ),
        tx.now,
    )


def _scan_text(result) -> str:
    changed = result.count("changed")
    missing = result.count("missing")
    parts = []
    if changed:
        parts.append(f"{changed} file{'s' if changed != 1 else ''} changed by you")
    if missing:
        parts.append(f"{missing} file{'s' if missing != 1 else ''} missing")
    if not parts:
        return "No changes found since the last check."
    total = changed + missing
    pronoun = "It" if total == 1 else "They"
    return (
        ", ".join(parts).capitalize()
        + f". {pronoun} will be checked when the build runs (Phase 6 onwards)."
    )


def _file_rows(approach: ApproachVersion, known, baselines, scan) -> list[FileRow]:
    outcomes = {item.path: item.outcome for item in scan.items} if scan else {}
    rows = []
    for planned in approach.plan.files:
        path = normalise_path(planned.path)
        outcome = outcomes.get(path)
        if outcome == "changed":
            status = "Changed by you"
        elif outcome == "missing":
            status = "Missing"
        elif path in known and known[path].kind == "written":
            status = "Written"
        else:
            status = "Not written yet"
        rows.append(
            FileRow(
                path=path,
                action=planned.action,
                status=status,
                baseline_at=baselines.get(path) if planned.action == "modify" else None,
            )
        )
    return rows


def _buttons_for(step: str, mode: str, capped: bool, linked: bool = False):
    """(server buttons, browser buttons, note) for one step (spec section 1 table). Once a
    folder has been linked, Change is also offered at start, so a same-named different folder
    (P26) can be linked on purpose."""
    if step == "start":
        change = [(CHANGE_FOLDER_KEY, CHANGE_FOLDER_LABEL)] if linked else []
        return [], [(CHOOSE_KEY, CHOOSE_LABEL), *change], ""
    if step == "ws_blocked":
        server = [] if capped else [(CHANGE_APPROACH_KEY, CHANGE_APPROACH_OPTION)]
        server.append((HELP_KEY, HELP_BUTTON))
        pick_again = (CHOOSE_KEY, CHOOSE_OTHER_LABEL)
        browser = [(UPLOAD_KEY, UPLOAD_LABEL)] if mode == "download" else [pick_again]
        return server, browser, CAP_MESSAGE if capped else ""
    if step == "ws_ready":
        if mode == "download":
            upload = (UPLOAD_KEY, "Upload folder to re-scan")
            return [], [(DOWNLOAD_KEY, DOWNLOAD_LABEL), upload], ""
        return [], [(RESCAN_KEY, RESCAN_LABEL), (CHANGE_FOLDER_KEY, CHANGE_FOLDER_LABEL)], ""
    if step == "ws_fallback":
        return (
            [],
            [
                (DOWNLOAD_KEY, DOWNLOAD_LABEL),
                (UPLOAD_KEY, UPLOAD_LABEL),
                (RETRY_PICKER_KEY, RETRY_PICKER_LABEL),
            ],
            "",
        )
    return [], [], ""


# --- helpers ---


def _base_state(snap: _Snap, request_id: str) -> WorkspaceState:
    return snap.state or WorkspaceState(request_id=request_id)


def _snapshot(settings, request_id: str, base_revision: int) -> _Snap:
    """Read before any file work. Refused early if the window is out of date. Writes nothing."""
    with open_db(settings.db_path) as conn:
        ensure_workspace_tables(conn)
        ensure_audit_table(conn)
        conn.execute("BEGIN")
        request = _require_request(conn, request_id)
        if read_workspace_revision(conn, request_id) != base_revision:
            raise StaleRevisionError(STALE_MESSAGE)
        if request.status != STATUS_READY_TO_BUILD:
            raise WorkspaceError(
                "The workspace can only be used when the request is READY TO BUILD."
            )
        approach = read_latest_approach(conn, request_id)
        approach_state = read_approach_state(conn, request_id)
        if approach is None or approach_state is None:
            raise WorkspaceError("This request has no approach yet, so it has no workspace.")
        snap = _Snap(
            request=request,
            approach=approach,
            approach_state_step=approach_state.step,
            approach_change_count=approach_state.change_count,
            state=read_workspace_state(conn, request_id),
            known=read_known_files(conn, request_id),
            policy=get_rulebook_for_request(settings.db_path, request_id).rulebook.policy,
            revision=base_revision,
        )
    return snap


@contextmanager
def _write(db_path: Path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Set up tables before taking the lock: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_audit_table(conn)
        ensure_workspace_tables(conn)
        begin_write(conn)
        yield conn


def _begin(conn: sqlite3.Connection, request_id: str, base_revision: int, now: datetime) -> _Tx:
    """Inside the write lock: the revision must still be the one the window saw."""
    if read_workspace_revision(conn, request_id) != base_revision:
        raise StaleRevisionError(STALE_MESSAGE)
    return _Tx(conn, _require_request(conn, request_id), now)


def _require_request(conn: sqlite3.Connection, request_id: str) -> Request:
    request = read_request(conn, request_id)
    if request is None:
        raise WorkspaceError(f"Request {request_id} does not exist.")
    return request


def _require_step(snap: _Snap, *steps: str) -> None:
    if snap.step not in steps:
        raise WorkspaceError(_wrong_step_message(snap.step))


def _wrong_step_message(step: str) -> str:
    messages = {
        "start": f"Please press {CHOOSE_LABEL} first.",
        "ws_blocked": "The folder has a problem. Choose another folder, change the approach, "
        f"or {HELP_BUTTON}.",
        "ws_ready": "The workspace is ready. Use Re-scan or Change.",
        "ws_fallback": "Download mode is on. Download the ZIP or upload your folder.",
        "escalated": "This request was handed to a senior developer.",
    }
    return messages.get(step, "That is not possible at this step.")
