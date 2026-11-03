"""Save and read the Workspace (spec section 10). Three tables, CREATE TABLE IF NOT EXISTS.

- da_workspace_state: one row per request, with its own revision (stale-window check, like
  Approach).
- da_workspace_files: every baseline, write and scan of a file, append-only. The text is kept
  (decision D-H) so a restore and Phase 6 patching have something to work from.
- da_workspace_scans: every re-scan result, append-only.

Like Approach's storage, every write function takes the caller's connection, so the flow can save
state, file rows, audit events and chat lines in one transaction.
"""

import json
import sqlite3
from datetime import datetime

from db_table_functions.da_db import to_db_time
from db_table_functions.db_tbl_da_approach import ensure_approach_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
)
from pydantic_classes.da_workspace_models import ScanResult, WorkspaceFile, WorkspaceState

# The triggers are SQLite-only: CodeVision's database will need its own equivalent.
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_workspace_state (
    request_id TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    state      TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS da_workspace_files (
    request_id       TEXT NOT NULL REFERENCES da_requests (request_id),
    path             TEXT NOT NULL,
    file_version     INTEGER NOT NULL,
    kind             TEXT NOT NULL,
    text             TEXT NOT NULL,
    fingerprint      TEXT NOT NULL,
    line_ending      TEXT NOT NULL,
    mode             TEXT NOT NULL,
    approach_version INTEGER NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (request_id, path, file_version)
);

CREATE TRIGGER IF NOT EXISTS da_workspace_files_no_update
BEFORE UPDATE ON da_workspace_files
BEGIN
    SELECT RAISE(ABORT, 'Workspace file versions are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_workspace_files_no_delete
BEFORE DELETE ON da_workspace_files
BEGIN
    SELECT RAISE(ABORT, 'Workspace file versions are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_workspace_scans (
    request_id  TEXT NOT NULL REFERENCES da_requests (request_id),
    scan_number INTEGER NOT NULL,
    results     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (request_id, scan_number)
);

CREATE TRIGGER IF NOT EXISTS da_workspace_scans_no_update
BEFORE UPDATE ON da_workspace_scans
BEGIN
    SELECT RAISE(ABORT, 'Workspace scans are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_workspace_scans_no_delete
BEFORE DELETE ON da_workspace_scans
BEGIN
    SELECT RAISE(ABORT, 'Workspace scans are append-only and cannot be deleted.');
END;
"""


class WorkspaceError(UnderstandError):
    """A Workspace action was refused. The message says why in plain words."""


def ensure_workspace_tables(conn: sqlite3.Connection) -> None:
    # These tables point at da_requests, which the Understand tables set up first.
    ensure_approach_tables(conn)
    conn.executescript(_CREATE_TABLES_SQL)


# --- the working state ---


def read_workspace_revision(conn: sqlite3.Connection, request_id: str) -> int:
    """The workspace revision. 0 means no workspace row yet for this request."""
    row = conn.execute(
        "SELECT revision FROM da_workspace_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    return row["revision"] if row else 0


def read_workspace_state(conn: sqlite3.Connection, request_id: str) -> WorkspaceState | None:
    row = conn.execute(
        "SELECT state, revision FROM da_workspace_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    if row is None:
        return None
    return WorkspaceState.model_validate(json.loads(row["state"]) | {"revision": row["revision"]})


def save_workspace_state(
    conn: sqlite3.Connection, state: WorkspaceState, base_revision: int, now: datetime
) -> WorkspaceState:
    """Save the state as revision base_revision + 1. Refused if the stored revision is no longer
    base_revision (another window acted first). Base 0 means the first save. The check and the
    save are one statement, so no other save can slip in between."""
    text = state.model_dump_json(exclude={"revision"})
    if base_revision == 0:
        try:
            conn.execute(
                "INSERT INTO da_workspace_state (request_id, state, revision, updated_at)"
                " VALUES (?, ?, 1, ?)",
                (state.request_id, text, to_db_time(now)),
            )
        except sqlite3.IntegrityError as error:
            raise StaleRevisionError(STALE_MESSAGE) from error
        return state.model_copy(update={"revision": 1})
    cursor = conn.execute(
        "UPDATE da_workspace_state SET state = ?, revision = ?, updated_at = ?"
        " WHERE request_id = ? AND revision = ?",
        (text, base_revision + 1, to_db_time(now), state.request_id, base_revision),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return state.model_copy(update={"revision": base_revision + 1})


# --- file versions ---


def insert_workspace_file(
    conn: sqlite3.Connection, item: WorkspaceFile, now: datetime
) -> WorkspaceFile:
    """Append the next version of a path. The version number is chosen here."""
    row = conn.execute(
        "SELECT COALESCE(MAX(file_version), 0) AS top FROM da_workspace_files"
        " WHERE request_id = ? AND path = ?",
        (item.request_id, item.path),
    ).fetchone()
    version = row["top"] + 1
    conn.execute(
        "INSERT INTO da_workspace_files (request_id, path, file_version, kind, text,"
        " fingerprint, line_ending, mode, approach_version, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.request_id,
            item.path,
            version,
            item.kind,
            item.text,
            item.fingerprint,
            item.line_ending,
            item.mode,
            item.approach_version,
            to_db_time(now),
        ),
    )
    return item.model_copy(update={"file_version": version, "created_at": now})


def read_file_versions(
    conn: sqlite3.Connection, request_id: str, path: str
) -> list[WorkspaceFile]:
    rows = conn.execute(
        "SELECT * FROM da_workspace_files WHERE request_id = ? AND path = ?"
        " ORDER BY file_version",
        (request_id, path),
    ).fetchall()
    return [_to_file(row) for row in rows]


def read_known_files(conn: sqlite3.Connection, request_id: str) -> dict[str, WorkspaceFile]:
    """For each path, its last write, else its baseline: the fingerprint a file must still have.
    A `scanned` row is the developer's change, so it is never the reference."""
    rows = conn.execute(
        "SELECT * FROM da_workspace_files WHERE request_id = ? AND kind != 'scanned'"
        " ORDER BY path, file_version",
        (request_id,),
    ).fetchall()
    return {row["path"]: _to_file(row) for row in rows}  # later versions overwrite earlier ones


def read_baseline_times(conn: sqlite3.Connection, request_id: str) -> dict[str, datetime]:
    """When each path's baseline was first taken (shown in the Build tab)."""
    rows = conn.execute(
        "SELECT path, MIN(created_at) AS taken FROM da_workspace_files"
        " WHERE request_id = ? AND kind = 'baseline' GROUP BY path",
        (request_id,),
    ).fetchall()
    return {row["path"]: datetime.fromisoformat(row["taken"]) for row in rows}


def read_scanned_paths(conn: sqlite3.Connection, request_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT path FROM da_workspace_files WHERE request_id = ? AND kind = 'scanned'",
        (request_id,),
    ).fetchall()
    return {row["path"] for row in rows}


# --- scans ---


def insert_scan(
    conn: sqlite3.Connection, request_id: str, result: ScanResult, now: datetime
) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(scan_number), 0) AS top FROM da_workspace_scans WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    number = row["top"] + 1
    conn.execute(
        "INSERT INTO da_workspace_scans (request_id, scan_number, results, created_at)"
        " VALUES (?, ?, ?, ?)",
        (request_id, number, result.model_dump_json(), to_db_time(now)),
    )
    return number


def read_latest_scan(conn: sqlite3.Connection, request_id: str) -> ScanResult | None:
    row = conn.execute(
        "SELECT results FROM da_workspace_scans WHERE request_id = ?"
        " ORDER BY scan_number DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return ScanResult.model_validate_json(row["results"]) if row else None


# --- rows to models ---


def _to_file(row: sqlite3.Row) -> WorkspaceFile:
    return WorkspaceFile(
        request_id=row["request_id"],
        path=row["path"],
        file_version=row["file_version"],
        kind=row["kind"],
        text=row["text"],
        fingerprint=row["fingerprint"],
        line_ending=row["line_ending"],
        mode=row["mode"],
        approach_version=row["approach_version"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
