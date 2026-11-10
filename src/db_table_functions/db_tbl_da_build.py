"""Save and read the Build (spec section 13). Five tables, CREATE TABLE IF NOT EXISTS.

- da_build_state: one row per request, with its own revision (stale-window check, like Approach
  and Workspace).
- da_build_runs: one row per build. Updated only to close it; a closed row never changes.
- da_build_files: contract, test and code texts, append-only. The text is kept so the frozen tests
  and each round's code can be shown and reused.
- da_build_rounds: every finished round, append-only.
- da_build_progress: the lines of the live progress list, append-only. A line that changes state
  gets a new row; the latest row of each line number is the one shown.

Like Workspace storage, every write function takes the caller's connection, so the flow can save
state, rows, audit events and chat lines in one transaction. The database, not the background
thread, is the truth about a build (spec section 10).
"""

import json
import sqlite3
from datetime import datetime

from db_table_functions.da_db import to_db_time
from db_table_functions.db_tbl_da_approach import ensure_approach_tables
from db_table_functions.db_tbl_da_enhance import ensure_enhance_tables
from db_table_functions.db_tbl_da_refine import ensure_refine_tables
from db_table_functions.db_tbl_da_tester import ensure_tester_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
)
from pydantic_classes.da_build_models import (
    BuildFile,
    BuildRun,
    BuildState,
    FailureReport,
    LayerAResult,
    LayerBResult,
    ProgressLine,
    RoundRecord,
)

# The triggers are SQLite-only: CodeVision's database will need its own equivalent.
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_build_state (
    request_id TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    state      TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS da_build_runs (
    request_id       TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number     INTEGER NOT NULL,
    approach_version INTEGER NOT NULL,
    started_at       TEXT NOT NULL,
    ended_at         TEXT,
    rounds_used      INTEGER NOT NULL DEFAULT 0,
    result_status    TEXT NOT NULL DEFAULT '',
    label            TEXT NOT NULL DEFAULT '',
    stop_reason      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (request_id, build_number)
);

CREATE TRIGGER IF NOT EXISTS da_build_runs_closed_no_update
BEFORE UPDATE ON da_build_runs
WHEN OLD.ended_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'A closed build cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_build_runs_no_delete
BEFORE DELETE ON da_build_runs
BEGIN
    SELECT RAISE(ABORT, 'Builds cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_build_files (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number INTEGER NOT NULL,
    round        INTEGER NOT NULL,
    path         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    text         TEXT NOT NULL,
    fingerprint  TEXT NOT NULL,
    made_by      TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS da_build_files_no_update
BEFORE UPDATE ON da_build_files
BEGIN
    SELECT RAISE(ABORT, 'Build files are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_build_files_no_delete
BEFORE DELETE ON da_build_files
BEGIN
    SELECT RAISE(ABORT, 'Build files are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_build_rounds (
    request_id     TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number   INTEGER NOT NULL,
    round          INTEGER NOT NULL,
    layer_a        TEXT NOT NULL,
    layer_b        TEXT,
    failure_report TEXT NOT NULL,
    timed_out      INTEGER NOT NULL,
    files_to_fix   TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL,
    PRIMARY KEY (request_id, build_number, round)
);

CREATE TRIGGER IF NOT EXISTS da_build_rounds_no_update
BEFORE UPDATE ON da_build_rounds
BEGIN
    SELECT RAISE(ABORT, 'Build rounds are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_build_rounds_no_delete
BEFORE DELETE ON da_build_rounds
BEGIN
    SELECT RAISE(ABORT, 'Build rounds are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_build_progress (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number INTEGER NOT NULL,
    line_number  INTEGER NOT NULL,
    text         TEXT NOT NULL,
    state        TEXT NOT NULL,
    started_at   TEXT,
    ended_at     TEXT
);

CREATE TRIGGER IF NOT EXISTS da_build_progress_no_update
BEFORE UPDATE ON da_build_progress
BEGIN
    SELECT RAISE(ABORT, 'Build progress is append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_build_progress_no_delete
BEFORE DELETE ON da_build_progress
BEGIN
    SELECT RAISE(ABORT, 'Build progress is append-only and cannot be deleted.');
END;
"""


class BuildError(UnderstandError):
    """A Build action was refused. The message says why in plain words."""


def ensure_build_tables(conn: sqlite3.Connection) -> None:
    # These tables point at da_requests, which the Understand tables set up first.
    ensure_approach_tables(conn)
    conn.executescript(_CREATE_TABLES_SQL)
    ensure_tester_tables(conn)  # Phase 7: the Tester's three tables ride along
    ensure_refine_tables(conn)  # Phase 8: Refine's tables ride along
    ensure_enhance_tables(conn)  # Phase 9: Enhance's tables ride along
    _add_kind_column(conn)


def _add_kind_column(conn: sqlite3.Connection) -> None:
    """Phase 8: da_build_runs gets a `kind` column. CREATE TABLE IF NOT EXISTS does not change a
    table that already exists, so an older database gets the column here. Old rows read as
    `build`."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(da_build_runs)")}
    if "kind" not in columns:
        conn.execute("ALTER TABLE da_build_runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'build'")


# --- the working state ---


def read_build_revision(conn: sqlite3.Connection, request_id: str) -> int:
    """The build revision. 0 means no build row yet for this request."""
    row = conn.execute(
        "SELECT revision FROM da_build_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    return row["revision"] if row else 0


def read_build_state(conn: sqlite3.Connection, request_id: str) -> BuildState | None:
    row = conn.execute(
        "SELECT state, revision FROM da_build_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    if row is None:
        return None
    return BuildState.model_validate(json.loads(row["state"]) | {"revision": row["revision"]})


def save_build_state(
    conn: sqlite3.Connection, state: BuildState, base_revision: int, now: datetime
) -> BuildState:
    """Save the state as revision base_revision + 1. Refused if the stored revision is no longer
    base_revision (another window, or the background thread, acted first). Base 0 means the
    first save. The check and the save are one statement, so nothing can slip in between."""
    text = state.model_dump_json(exclude={"revision"})
    if base_revision == 0:
        try:
            conn.execute(
                "INSERT INTO da_build_state (request_id, state, revision, updated_at)"
                " VALUES (?, ?, 1, ?)",
                (state.request_id, text, to_db_time(now)),
            )
        except sqlite3.IntegrityError as error:
            raise StaleRevisionError(STALE_MESSAGE) from error
        return state.model_copy(update={"revision": 1})
    cursor = conn.execute(
        "UPDATE da_build_state SET state = ?, revision = ?, updated_at = ?"
        " WHERE request_id = ? AND revision = ?",
        (text, base_revision + 1, to_db_time(now), state.request_id, base_revision),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return state.model_copy(update={"revision": base_revision + 1})


def read_running_requests(conn: sqlite3.Connection) -> list[str]:
    """Requests whose build is marked running (including between rounds). Used at server
    start-up, when no build can really still be running (spec section 10)."""
    rows = conn.execute("SELECT request_id, state FROM da_build_state").fetchall()
    running = ("b_running", "b_round_failed", "b_tester_review")
    return [row["request_id"] for row in rows if json.loads(row["state"]).get("step") in running]


# --- builds ---


def next_build_number(conn: sqlite3.Connection, request_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(build_number), 0) AS top FROM da_build_runs WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row["top"] + 1


def insert_build_run(conn: sqlite3.Connection, run: BuildRun) -> None:
    conn.execute(
        "INSERT INTO da_build_runs (request_id, build_number, approach_version, started_at, kind)"
        " VALUES (?, ?, ?, ?, ?)",
        (
            run.request_id,
            run.build_number,
            run.approach_version,
            to_db_time(run.started_at),
            run.kind,
        ),
    )


def close_build_run(
    conn: sqlite3.Connection,
    request_id: str,
    build_number: int,
    *,
    ended_at: datetime,
    rounds_used: int,
    result_status: str,
    label: str,
    stop_reason: str,
) -> None:
    """Close a build. A build that is already closed is refused by the database."""
    cursor = conn.execute(
        "UPDATE da_build_runs SET ended_at = ?, rounds_used = ?, result_status = ?, label = ?,"
        " stop_reason = ? WHERE request_id = ? AND build_number = ?",
        (
            to_db_time(ended_at),
            rounds_used,
            result_status,
            label,
            stop_reason,
            request_id,
            build_number,
        ),
    )
    if cursor.rowcount != 1:
        raise BuildError("That build does not exist.")


def read_build_run(conn: sqlite3.Connection, request_id: str, build_number: int) -> BuildRun | None:
    row = conn.execute(
        "SELECT * FROM da_build_runs WHERE request_id = ? AND build_number = ?",
        (request_id, build_number),
    ).fetchone()
    return _to_run(row) if row else None


def read_build_runs(conn: sqlite3.Connection, request_id: str) -> list[BuildRun]:
    rows = conn.execute(
        "SELECT * FROM da_build_runs WHERE request_id = ? ORDER BY build_number", (request_id,)
    ).fetchall()
    return [_to_run(row) for row in rows]


def count_open_builds(conn: sqlite3.Connection) -> int:
    """Builds started and not yet closed, on this server (the parallel limit, plan P8)."""
    row = conn.execute("SELECT COUNT(*) AS n FROM da_build_runs WHERE ended_at IS NULL").fetchone()
    return row["n"]


# --- files ---


def insert_build_file(conn: sqlite3.Connection, item: BuildFile, now: datetime) -> BuildFile:
    conn.execute(
        "INSERT INTO da_build_files (request_id, build_number, round, path, kind, text,"
        " fingerprint, made_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.request_id,
            item.build_number,
            item.round,
            item.path,
            item.kind,
            item.text,
            item.fingerprint,
            item.made_by,
            to_db_time(now),
        ),
    )
    return item.model_copy(update={"created_at": now})


def read_build_files(
    conn: sqlite3.Connection, request_id: str, build_number: int, kind: str | None = None
) -> list[BuildFile]:
    sql = "SELECT * FROM da_build_files WHERE request_id = ? AND build_number = ?"
    values: list = [request_id, build_number]
    if kind is not None:
        sql += " AND kind = ?"
        values.append(kind)
    rows = conn.execute(sql + " ORDER BY seq", values).fetchall()
    return [_to_file(row) for row in rows]


def read_latest_code(
    conn: sqlite3.Connection, request_id: str, build_number: int
) -> dict[str, BuildFile]:
    """For each code path of a build, its newest saved version (the latest round wins)."""
    return {item.path: item for item in read_build_files(conn, request_id, build_number, "code")}


def read_frozen_files(
    conn: sqlite3.Connection, request_id: str, approach_version: int
) -> dict[str, BuildFile]:
    """The contract and test file frozen for an approach version, from its first build that saved
    them (spec section 3: a later build reuses them). Keyed by kind: `contract` and `test`."""
    rows = conn.execute(
        "SELECT f.* FROM da_build_files f JOIN da_build_runs r"
        " ON r.request_id = f.request_id AND r.build_number = f.build_number"
        " WHERE f.request_id = ? AND r.approach_version = ? AND f.kind IN ('contract', 'test')"
        " ORDER BY f.seq",
        (request_id, approach_version),
    ).fetchall()
    frozen: dict[str, BuildFile] = {}
    for row in rows:
        frozen.setdefault(row["kind"], _to_file(row))  # the first one stays
    return frozen


# --- rounds ---


def insert_round(conn: sqlite3.Connection, item: RoundRecord, now: datetime) -> None:
    conn.execute(
        "INSERT INTO da_build_rounds (request_id, build_number, round, layer_a, layer_b,"
        " failure_report, timed_out, files_to_fix, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.request_id,
            item.build_number,
            item.round,
            item.layer_a.model_dump_json(),
            item.layer_b.model_dump_json() if item.layer_b else None,
            item.failure_report.model_dump_json() if item.failure_report else "",
            1 if item.timed_out else 0,
            json.dumps(item.files_to_fix),
            to_db_time(now),
        ),
    )


def read_rounds(conn: sqlite3.Connection, request_id: str, build_number: int) -> list[RoundRecord]:
    rows = conn.execute(
        "SELECT * FROM da_build_rounds WHERE request_id = ? AND build_number = ? ORDER BY round",
        (request_id, build_number),
    ).fetchall()
    return [_to_round(row) for row in rows]


# --- progress ---


def add_progress(conn: sqlite3.Connection, line: ProgressLine) -> None:
    conn.execute(
        "INSERT INTO da_build_progress (request_id, build_number, line_number, text, state,"
        " started_at, ended_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            line.request_id,
            line.build_number,
            line.line_number,
            line.text,
            line.state,
            to_db_time(line.started_at) if line.started_at else None,
            to_db_time(line.ended_at) if line.ended_at else None,
        ),
    )


def read_progress(
    conn: sqlite3.Connection, request_id: str, build_number: int
) -> list[ProgressLine]:
    """The newest row of each line number, in line order."""
    rows = conn.execute(
        "SELECT * FROM da_build_progress WHERE request_id = ? AND build_number = ? ORDER BY seq",
        (request_id, build_number),
    ).fetchall()
    latest = {row["line_number"]: row for row in rows}  # later rows overwrite earlier ones
    return [_to_progress(latest[number]) for number in sorted(latest)]


# --- rows to models ---


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _to_run(row: sqlite3.Row) -> BuildRun:
    return BuildRun(
        request_id=row["request_id"],
        build_number=row["build_number"],
        approach_version=row["approach_version"],
        started_at=datetime.fromisoformat(row["started_at"]),
        ended_at=_time(row["ended_at"]),
        rounds_used=row["rounds_used"],
        result_status=row["result_status"],
        label=row["label"],
        stop_reason=row["stop_reason"],
        kind=row["kind"],
    )


def _to_file(row: sqlite3.Row) -> BuildFile:
    return BuildFile(
        request_id=row["request_id"],
        build_number=row["build_number"],
        round=row["round"],
        path=row["path"],
        kind=row["kind"],
        text=row["text"],
        fingerprint=row["fingerprint"],
        made_by=row["made_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _to_round(row: sqlite3.Row) -> RoundRecord:
    return RoundRecord(
        request_id=row["request_id"],
        build_number=row["build_number"],
        round=row["round"],
        layer_a=LayerAResult.model_validate_json(row["layer_a"]),
        layer_b=LayerBResult.model_validate_json(row["layer_b"]) if row["layer_b"] else None,
        failure_report=(
            FailureReport.model_validate_json(row["failure_report"])
            if row["failure_report"]
            else None
        ),
        timed_out=bool(row["timed_out"]),
        files_to_fix=json.loads(row["files_to_fix"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _to_progress(row: sqlite3.Row) -> ProgressLine:
    return ProgressLine(
        request_id=row["request_id"],
        build_number=row["build_number"],
        line_number=row["line_number"],
        text=row["text"],
        state=row["state"],
        started_at=_time(row["started_at"]),
        ended_at=_time(row["ended_at"]),
    )
