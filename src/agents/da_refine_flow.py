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
    STARTED_MESSAGE,
    BuildTx,
    _approach_of,
    _check_revision,
    _require_request,
    _require_step,
    _save,
    _save_prescan,
    _write,
    get_state,
    planned_paths_of,
)
from agents.da_refine_merge import side_by_side
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import (
    BuildError,
    ensure_build_tables,
    insert_build_run,
    next_build_number,
    read_build_state,
    read_latest_code,
)
from db_table_functions.db_tbl_da_refine import read_tested
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables, read_file_versions
from pydantic_classes.da_build_models import BuildRun, BuildState
from pydantic_classes.da_models import (
    STATUS_BUILDING,
    STATUS_NOT_PASSING,
    STATUS_READY_FOR_REVIEW,
)
from pydantic_classes.da_workspace_models import FolderFacts

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
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> BuildState:
    """Check my edits: a check run on his versions of the planned files. READY_FOR_REVIEW or
    NOT_PASSING goes to BUILDING with build kind `check` and a new build number. No Generator
    call, no fix rounds, no budget used. The loop is run by the caller (the runner)."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        _require_refinable(request.status, state)
        if not changed_paths(conn, request_id, state):
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
        tx.say("assistant", STARTED_MESSAGE)
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


# --- helpers ---


def _require_refinable(status: str, state: BuildState | None) -> None:
    """Refine starts only at `b_written` with READY_FOR_REVIEW or NOT_PASSING (spec section 2)."""
    if state is None:
        raise BuildError("There is no build for this request yet.")
    if status not in EDIT_STATUSES:
        raise BuildError("This is only possible after a build, when the code is in your folder.")
    _require_step(state, "b_written")
