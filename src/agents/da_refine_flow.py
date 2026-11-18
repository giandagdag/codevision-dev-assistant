"""The Refine actions the screen calls (Phase 8). Thin, like da_build_flow: read with no lock, slow
work outside any transaction, then ONE write transaction holds state, rows, audit events and chat
lines together (rule F1).

This file grows step by step. It starts with Re-scan after a build and Check my edits (spec
section 3). The lanes (sections 4 to 7), conflicts and Restore follow in the same file.

AS400 picture: CMPPFM against the last save. Re-scan finds which members the programmer changed
since the app wrote them; Check my edits runs the same acceptance run on his members as on the
app's own.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agents.da_build_flow import (
    BuildTx,
    _approach_of,
    _check_revision,
    _insert_written,
    _require_request,
    _require_step,
    _save,
    _save_prescan,
    _turn,
    _write,
    get_state,
    planned_paths_of,
)
from agents.da_check_words import CHECK_CHAT_LINE, NEW_TEST_CHECK_LINE
from agents.da_refine_merge import build_restore_set, side_by_side
from agents.da_workspace_checks import (
    FactsProblem,
    build_write_job,
    fingerprint,
    stop_message,
    verify_report,
)
from agents.da_workspace_flow import readme_text
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import (
    BuildError,
    ensure_build_tables,
    insert_build_run,
    next_build_number,
    read_build_run,
    read_build_runs,
    read_build_state,
    read_latest_code,
)
from db_table_functions.db_tbl_da_refine import read_tested, set_last_tested
from db_table_functions.db_tbl_da_workspace import (
    ensure_workspace_tables,
    read_file_versions,
    read_workspace_state,
)
from pydantic_classes.da_build_models import BuildRun, BuildState
from pydantic_classes.da_models import (
    STATUS_BUILDING,
    STATUS_NOT_PASSING,
    STATUS_READY_FOR_REVIEW,
)
from pydantic_classes.da_workspace_models import (
    FolderFacts,
    WorkspaceMode,
    WriteJob,
    WriteReport,
    WrittenFile,
)

RESTORE_KEY, RESTORE_LABEL = "restore", "Restore an earlier version"
NOTHING_TO_RESTORE_LINE = "Nothing to restore yet: there is only one tested version."


def undo_label(build_number: int) -> str:
    """F5: the last tested set, offered when a re-scan found edits that are not tested."""
    return f"Undo my edits (back to build {build_number})"


DOWNLOAD_RESCAN_LABEL = "Upload folder to re-scan"
UPLOAD_BEFORE_DOWNLOAD_LINE = (
    "Upload your folder before every new download, so I never overwrite your edits."
)
RESCAN_KEY, RESCAN_LABEL = "rescan", "Re-scan"
CHECK_KEY, CHECK_LABEL = "check_edits", "Check my edits"
NOT_TESTED_LINE = "Your edits are not tested yet. Press Check my edits."
ONLY_PLANNED_LINE = "Only the planned files are read. Edits in other files are not picked up."
NO_CHANGES_LINE = "I found no changes in the planned files."
FIX_MYSELF_LABEL = "I'll fix it myself"
FIX_MYSELF_LINE = "Edit the file in your folder, then press Re-scan."
EDIT_STATUSES =(STATUS_READY_FOR_REVIEW, STATUS_NOT_PASSING)


@dataclass
class FileDiff:
    """One edited file, side by side: left what the app last wrote, right his version."""

    path: str
    rows: list[tuple[str, str, bool]] = field(default_factory=list)


@dataclass
class EditView:
    """What the Build tab needs after a Re-scan."""

    changed: list[str] = field(default_factory=list)
    diffs: list[FileDiff] = field(default_factory=list)
    not_tested_line: str = ""
    only_planned_line: str = ONLY_PLANNED_LINE


# --- Re-scan (section 3) ---


def rescan(
    settings,
    request_id: str,
    facts: FolderFacts,
    base_revision: int,
    now: datetime | None = None,
) -> BuildState:
    """Re-scan at `b_written`: the browser has read every planned file. Each changed file is saved
    as a `scanned` row. The status and the label do not change (spec section 3)."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        _require_refinable(request.status, state)
        tx = BuildTx(conn, request, state, now)
        changed = _save_prescan(tx, state.approach_version, facts)
        tx.say("developer", RESCAN_LABEL)
        tx.audit("developer", "rescan", {"changed": changed})
        tx.say("assistant", _rescan_text(conn, request_id, state, changed))
        tx.set()  # the revision goes up, so an old window is refused
        _save(tx, base_revision)
    return get_state(settings, request_id)


def _rescan_text(conn: sqlite3.Connection, request_id: str, state: BuildState, changed: int) -> str:
    paths = changed_paths(conn, request_id, state)
    if not paths:
        return f"{NO_CHANGES_LINE} {ONLY_PLANNED_LINE}"
    names = ", ".join(paths)
    return f"I found your edits in {names}. {NOT_TESTED_LINE} {ONLY_PLANNED_LINE}"


def changed_paths(conn: sqlite3.Connection, request_id: str, state: BuildState) -> list[str]:
    """Planned files whose newest known text is not the text the last build or check run tested.
    That is "last tested" against what is in his folder as far as the app knows."""
    approach = _approach_of(conn, request_id, state)
    tested_build = read_tested(conn, request_id)["last_tested_build"] or state.build_number
    tested = read_latest_code(conn, request_id, tested_build)
    found = []
    for path in planned_paths_of(approach):
        versions = read_file_versions(conn, request_id, path)
        if not versions:
            continue
        newest, base = versions[-1], tested.get(path)
        if base is None:
            if newest.kind == "scanned":
                found.append(path)
        elif newest.fingerprint != base.fingerprint:
            found.append(path)
    return found


def has_untested_edits(settings, request_id: str) -> bool:
    """True when a re-scan found edits that no run has tested yet (F5: Undo my edits)."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_workspace_tables(conn)
        conn.execute("BEGIN")
        state = read_build_state(conn, request_id)
        if state is None or state.build_number == 0:
            return False
        return bool(changed_paths(conn, request_id, state))


def get_edit_view(settings, request_id: str) -> EditView:
    """The changed files side by side. Empty when nothing changed or the request has no build."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_workspace_tables(conn)
        conn.execute("BEGIN")
        state = read_build_state(conn, request_id)
        if state is None or state.build_number == 0:
            return EditView()
        diffs = []
        for path in changed_paths(conn, request_id, state):
            versions = read_file_versions(conn, request_id, path)
            written = [v for v in versions if v.kind == "written"]
            left = written[-1].text if written else ""
            diffs.append(FileDiff(path, side_by_side(left, versions[-1].text)))
    return EditView(
        changed=[d.path for d in diffs],
        diffs=diffs,
        not_tested_line=NOT_TESTED_LINE if diffs else "",
    )


# --- Check my edits (section 3, D-I) ---


def start_check(
    settings,
    request_id: str,
    base_revision: int,
    now: datetime | None = None,
    after_new_test: bool = False,
) -> BuildState:
    """Check my edits: a check run on his versions of the planned files. READY_FOR_REVIEW or
    NOT_PASSING goes to BUILDING with build kind `check` and a new build number. No Generator
    call, no fix rounds, no budget used. The loop is run by the caller (the runner).
    `after_new_test`: the run is for his new test case, so no edit is needed first."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        _require_refinable(request.status, state)
        if not after_new_test and not changed_paths(conn, request_id, state):
            raise BuildError("Nothing has changed since the last test. Edit a file, then Re-scan.")
        number = next_build_number(conn, request_id)
        tx = BuildTx(conn, request, state, now)
        insert_build_run(
            conn,
            BuildRun(
                request_id=request_id,
                build_number=number,
                approach_version=state.approach_version,
                started_at=now,
                kind="check",
            ),
        )
        tx.say("developer", CHECK_LABEL)
        tx.audit("developer", "check_run_started", {"build": number})
        came_from = request.status
        tx.move_to(STATUS_BUILDING)
        # F6: reads as testing, not building. B2 S6: his new test says what it is checking.
        tx.say("assistant", NEW_TEST_CHECK_LINE if after_new_test else CHECK_CHAT_LINE)
        tx.set(
            build_number=number,
            step="b_running",
            current_round=0,
            write_state="not_written",
            message="",
            return_status=came_from,
        )
        _save(tx, base_revision)
    return get_state(settings, request_id)


# --- I'll fix it myself (R3, test 8-7) ---


def fix_myself(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> BuildState:
    """After a failed check run: he fixes the file himself. Nothing changes except a chat line and
    an audit event; the status stays NOT_PASSING."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        _require_refinable(request.status, state)
        tx = BuildTx(conn, request, state, now)
        tx.say("developer", FIX_MYSELF_LABEL)
        tx.audit("developer", "fix_myself", {"build": state.build_number})
        tx.say("assistant", FIX_MYSELF_LINE)
        tx.set()
        _save(tx, base_revision)
    return get_state(settings, request_id)


# --- Versions and Restore (section 9, D-L) ---


@dataclass
class VersionRow:
    """One row of the Versions list: a finished build, rebuild or check run with saved code."""

    build_number: int
    kind: str
    ended_at: datetime
    label: str
    files: list[str]
    is_last_tested: bool = False


@dataclass
class RestorePreview:
    """What the chat shows before a Restore: the warning (if any) and the planned files that the
    set did not have (they stay as they are)."""

    build_number: int
    label: str
    files: list[str]
    warning: str = ""
    left_out: list[str] = field(default_factory=list)
    button_label: str = ""


def rescan_label(mode: str) -> str:
    """Download mode has no folder to read, so the developer uploads it (test 8-40)."""
    return DOWNLOAD_RESCAN_LABEL if mode == "download" else RESCAN_LABEL


def list_versions(settings, request_id: str) -> list[VersionRow]:
    """Every closed run that saved code, oldest first. Nothing is ever deleted (decision D-H)."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        tested = read_tested(conn, request_id)["last_tested_build"]
        rows = []
        for run in read_build_runs(conn, request_id):
            code = read_latest_code(conn, request_id, run.build_number)
            if run.ended_at is None or not code:
                continue
            rows.append(
                VersionRow(
                    run.build_number,
                    run.kind,
                    run.ended_at,
                    run.label,
                    list(code),
                    is_last_tested=run.build_number == tested,
                )
            )
    return rows


def restore_preview(settings, request_id: str, build_number: int) -> RestorePreview:
    """Read only. Names every file whose current text (his edit, after a re-scan) the restore
    would replace, and says the edit stays saved on the server."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_workspace_tables(conn)
        conn.execute("BEGIN")
        state = read_build_state(conn, request_id)
        run, items, left = _restore_items(conn, request_id, state, build_number)
        replaced = _replaced_edits(conn, request_id, items)
    warning = ""
    if replaced:
        warning = " ".join(
            f"Your current edits in `{path}` will be replaced. "
            "They stay saved on the server and can be restored."
            for path in replaced
        )
    return RestorePreview(
        build_number,
        run.label,
        [path for path, _ in items],
        warning,
        left,
        button_label=f"Restore build {build_number}",
    )


def prepare_restore(settings, request_id: str, build_number: int, base_revision: int) -> WriteJob:
    """Hop 1: the write job for the browser, the WHOLE set in plan order. The edit guard compares
    with the newest fingerprints the server knows, so a Re-scan comes first (spec section 9)."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_workspace_tables(conn)
        conn.execute("BEGIN")
        _check_revision(conn, request_id, base_revision)
        request = _require_request(conn, request_id)
        state = read_build_state(conn, request_id)
        _require_refinable(request.status, state)
        _, items, _ = _restore_items(conn, request_id, state, build_number)
        return _restore_job(conn, request_id, state, items)


def save_restore(
    settings,
    request_id: str,
    build_number: int,
    report: WriteReport,
    base_revision: int,
    mode: WorkspaceMode = "picker",
    now: datetime | None = None,
) -> BuildState:
    """Hop 2: ONE transaction saves the `restore` rows, the audit events, the chat line and the new
    "last tested". The frozen tests and the record version are not touched. The status stays."""
    now = now or datetime.now(UTC)
    with _turn(settings.db_path, request_id, base_revision, now) as tx:
        _require_refinable(tx.request.status, tx.state)
        run, items, left = _restore_items(tx.conn, request_id, tx.state, build_number)
        job = _restore_job(tx.conn, request_id, tx.state, items)
        try:
            verify_report(job, report)
        except FactsProblem as error:
            raise BuildError(str(error)) from error
        if report.stopped is None and [i.path for i in report.written] != [
            f.path for f in job.files
        ]:
            raise BuildError("The browser's report does not list every file. Nothing was saved.")
        for item in report.written:
            _insert_written(tx, item, mode, tx.state.approach_version)
        if report.written:
            files = {i.path: fingerprint(i.text) for i in report.written}
            tx.audit("system", "workspace_written", {"mode": mode, "files": files})
        if report.stopped is not None:
            reason = {"path": report.stopped.path, "reason": report.stopped.reason}
            tx.audit("system", "workspace_write_stopped", reason)
            tx.say("assistant", stop_message(job, report))
        else:
            _finish_restore(tx, run, build_number, left)
        tx.set()  # the revision goes up, so an old window is refused
    return get_state(settings, request_id)


def prepare_restore_download(
    settings, request_id: str, build_number: int, base_revision: int, now: datetime | None = None
) -> tuple[WriteJob, str]:
    """Download mode: the ZIP holds the code files of the set only (test 8-40)."""
    job = prepare_restore(settings, request_id, build_number, base_revision)
    report = WriteReport(
        written=[
            WrittenFile(path=f.path, text=f.text, fingerprint=fingerprint(f.text))
            for f in job.files
        ]
    )
    save_restore(settings, request_id, build_number, report, base_revision, "download", now)
    return job, readme_text(job)


def _finish_restore(tx: BuildTx, run, build_number: int, left: list[str]) -> None:
    previous = read_tested(tx.conn, tx.request.request_id)["last_tested_build"]
    tx.say("developer", f"Restore build {build_number}")
    tx.audit("developer", "version_restored", {"from": previous, "to": build_number})
    set_last_tested(tx.conn, tx.request.request_id, build_number, "restore", tx.now)
    text = (
        f"Restored build {build_number} ({run.label or run.result_status}). "
        f"Last tested is now build {build_number}."
    )
    if left:
        text += f" Files the set did not have were left as they are: {', '.join(left)}."
    tx.say("assistant", text)


def _restore_items(conn: sqlite3.Connection, request_id: str, state, build_number: int):
    """(the run, [(path, text)] in plan order, planned paths the set did not have)."""
    if state is None:
        raise BuildError("There is no build for this request yet.")
    run = read_build_run(conn, request_id, build_number)
    code = read_latest_code(conn, request_id, build_number)
    if run is None or run.ended_at is None or not code:
        raise BuildError(f"Build {build_number} has no saved code to restore.")
    planned = planned_paths_of(_approach_of(conn, request_id, state))
    write, left = build_restore_set(planned, {path: item.text for path, item in code.items()})
    if not write:
        raise BuildError(f"Build {build_number} has none of the planned files.")
    return run, list(write.items()), left


def _replaced_edits(conn: sqlite3.Connection, request_id: str, items) -> list[str]:
    """Files whose newest known text is his (a re-scan) and differs from the set's text."""
    found = []
    for path, text in items:
        versions = read_file_versions(conn, request_id, path)
        if versions and versions[-1].kind == "scanned":
            if versions[-1].fingerprint != fingerprint(text):
                found.append(path)
    return found


def _restore_job(conn: sqlite3.Connection, request_id: str, state, items) -> WriteJob:
    known = {}
    for path, _ in items:
        versions = read_file_versions(conn, request_id, path)
        if versions:
            known[path] = (versions[-1].fingerprint, versions[-1].line_ending)
    workspace = read_workspace_state(conn, request_id)
    folder = workspace.folder_name if workspace and workspace.folder_name else "your folder"
    try:
        return build_write_job(request_id, folder, items, known)
    except FactsProblem as error:
        raise BuildError(str(error)) from error


# --- helpers ---


def _require_refinable(status: str, state: BuildState | None) -> None:
    """Refine starts only at `b_written` with READY_FOR_REVIEW or NOT_PASSING (spec section 2)."""
    if state is None:
        raise BuildError("There is no build for this request yet.")
    if status not in EDIT_STATUSES:
        raise BuildError("This is only possible after a build, when the code is in your folder.")
    _require_step(state, "b_written")
