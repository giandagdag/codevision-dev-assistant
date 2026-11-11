"""Save and read Refine (Phase 8 spec section 13). CREATE TABLE IF NOT EXISTS.

- da_refine_state: one row per request, with its own revision for the stale check (F1).
- da_refines: one row per Refine. Updated only to close it.
- da_test_sets: append-only. A new row for every appended repro or Yours test.
- da_refine_conflicts: append-only. The newest row per conflict is its state.
- da_refine_tested: "last tested" and the NOT_PASSING-in-a-row count. Kept apart from the Refine
  state so the build loop can update them without making an open Refine window stale.

Every write function takes the caller's connection, so a flow can save state, rows, audit events
and chat lines in ONE transaction. Like a job log kept next to the job: history is only added to.
"""

import json
import sqlite3
from datetime import datetime

from db_table_functions.da_db import to_db_time
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
)
from pydantic_classes.da_refine_models import (
    Conflict,
    RefineRow,
    RefineState,
    TestSet,
)
from pydantic_classes.da_request_record_models import RequestRecord

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_refine_state (
    request_id TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    state      TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS da_refines (
    request_id             TEXT NOT NULL REFERENCES da_requests (request_id),
    refine_number          INTEGER NOT NULL,
    source                 TEXT NOT NULL,
    feedback               TEXT NOT NULL,
    suggested_lane         TEXT NOT NULL,
    reason                 TEXT NOT NULL,
    chosen_lane            TEXT NOT NULL,
    from_status            TEXT NOT NULL,
    record_version_before  INTEGER NOT NULL,
    record_version_after   INTEGER NOT NULL,
    approach_version_before INTEGER NOT NULL,
    approach_version_after INTEGER NOT NULL,
    build_number           INTEGER NOT NULL,
    repro_passed_today     INTEGER NOT NULL,
    result                 TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    closed_at              TEXT,
    PRIMARY KEY (request_id, refine_number)
);

CREATE TRIGGER IF NOT EXISTS da_refines_closed_no_update
BEFORE UPDATE ON da_refines
WHEN OLD.closed_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'A closed Refine cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_refines_no_delete
BEFORE DELETE ON da_refines
BEGIN
    SELECT RAISE(ABORT, 'Refines cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_test_sets (
    request_id       TEXT NOT NULL REFERENCES da_requests (request_id),
    test_set_version INTEGER NOT NULL,
    approach_version INTEGER NOT NULL,
    added_case_ids   TEXT NOT NULL,
    text             TEXT NOT NULL,
    fingerprint      TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (request_id, test_set_version)
);

CREATE TRIGGER IF NOT EXISTS da_test_sets_no_update
BEFORE UPDATE ON da_test_sets
BEGIN
    SELECT RAISE(ABORT, 'Test sets are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_test_sets_no_delete
BEFORE DELETE ON da_test_sets
BEGIN
    SELECT RAISE(ABORT, 'Test sets are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_refine_conflicts (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number  INTEGER NOT NULL,
    path          TEXT NOT NULL,
    conflict_id   TEXT NOT NULL,
    his_lines     TEXT NOT NULL,
    ai_lines      TEXT NOT NULL,
    context       TEXT NOT NULL,
    choice        TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS da_refine_conflicts_no_update
BEFORE UPDATE ON da_refine_conflicts
BEGIN
    SELECT RAISE(ABORT, 'Conflict rows are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_refine_conflicts_no_delete
BEFORE DELETE ON da_refine_conflicts
BEGIN
    SELECT RAISE(ABORT, 'Conflict rows are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_refine_tested (
    request_id            TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    last_tested_build     INTEGER NOT NULL,
    last_tested_kind      TEXT NOT NULL,
    not_passing_in_a_row  INTEGER NOT NULL,
    updated_at            TEXT NOT NULL
);
"""


class RefineError(UnderstandError):
    """A Refine action was refused. The message says why in plain words."""


def ensure_refine_tables(conn: sqlite3.Connection) -> None:
    """Called by ensure_build_tables, after da_requests exists."""
    conn.executescript(_CREATE_TABLES_SQL)
    _add_net_columns(conn)


def _add_net_columns(conn: sqlite3.Connection) -> None:
    """Phase 9: da_test_sets records which methods are safety-net and which are expected to
    change. An older database gets the two columns here; old rows read as none."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(da_test_sets)")}
    for name in ("net_methods", "expected_to_change_methods"):
        if name not in columns:
            conn.execute(f"ALTER TABLE da_test_sets ADD COLUMN {name} TEXT NOT NULL DEFAULT '[]'")


# --- the working state ---


def read_refine_revision(conn: sqlite3.Connection, request_id: str) -> int:
    """0 means no Refine row yet for this request."""
    row = conn.execute(
        "SELECT revision FROM da_refine_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    return row["revision"] if row else 0


def read_refine_state(conn: sqlite3.Connection, request_id: str) -> RefineState | None:
    row = conn.execute(
        "SELECT state, revision FROM da_refine_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    tested = read_tested(conn, request_id)
    if row is None:
        return None
    data = json.loads(row["state"]) | {"revision": row["revision"]} | tested
    return RefineState.model_validate(data)


def save_refine_state(
    conn: sqlite3.Connection, state: RefineState, base_revision: int, now: datetime
) -> RefineState:
    """Save as revision base_revision + 1; refused if the stored revision moved on. Base 0 means
    the first save. Check and save are one statement, so nothing can slip in between."""
    text = state.model_dump_json(
        exclude={"revision", "last_tested_build", "last_tested_kind", "not_passing_in_a_row"}
    )
    if base_revision == 0:
        try:
            conn.execute(
                "INSERT INTO da_refine_state (request_id, state, revision, updated_at)"
                " VALUES (?, ?, 1, ?)",
                (state.request_id, text, to_db_time(now)),
            )
        except sqlite3.IntegrityError as error:
            raise StaleRevisionError(STALE_MESSAGE) from error
        return state.model_copy(update={"revision": 1})
    cursor = conn.execute(
        "UPDATE da_refine_state SET state = ?, revision = ?, updated_at = ?"
        " WHERE request_id = ? AND revision = ?",
        (text, base_revision + 1, to_db_time(now), state.request_id, base_revision),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return state.model_copy(update={"revision": base_revision + 1})


# --- "last tested" and the NOT_PASSING count ---


def read_tested(conn: sqlite3.Connection, request_id: str) -> dict:
    row = conn.execute(
        "SELECT last_tested_build, last_tested_kind, not_passing_in_a_row"
        " FROM da_refine_tested WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return {"last_tested_build": 0, "last_tested_kind": "", "not_passing_in_a_row": 0}
    return dict(row)


def set_last_tested(
    conn: sqlite3.Connection, request_id: str, build_number: int, kind: str, now: datetime
) -> None:
    """The set of files the last finished build, check run or restore tested (spec section 3).
    Phase 10's final fingerprint check compares with it."""
    current = read_tested(conn, request_id)
    _write_tested(conn, request_id, build_number, kind, current["not_passing_in_a_row"], now)


def add_build_result(
    conn: sqlite3.Connection, request_id: str, not_passing: bool, now: datetime
) -> int:
    """Count a finished rebuild: NOT_PASSING adds one to the in-a-row count, anything else resets
    it (F4). Returns the new count. Acts as an escalation trigger in Phase 10."""
    current = read_tested(conn, request_id)
    count = current["not_passing_in_a_row"] + 1 if not_passing else 0
    _write_tested(
        conn, request_id, current["last_tested_build"], current["last_tested_kind"], count, now
    )
    return count


def _write_tested(
    conn: sqlite3.Connection, request_id: str, build: int, kind: str, count: int, now: datetime
) -> None:
    conn.execute(
        "INSERT INTO da_refine_tested (request_id, last_tested_build, last_tested_kind,"
        " not_passing_in_a_row, updated_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT (request_id) DO UPDATE SET last_tested_build = excluded.last_tested_build,"
        " last_tested_kind = excluded.last_tested_kind,"
        " not_passing_in_a_row = excluded.not_passing_in_a_row, updated_at = excluded.updated_at",
        (request_id, build, kind, count, to_db_time(now)),
    )


# --- record versions (read only; the Understand file saves them) ---


def read_all_records(conn: sqlite3.Connection, request_id: str) -> list[RequestRecord]:
    """Every confirmed version of the request record, oldest first. Used for numbering criteria
    (an ID is never reused) and for the Summary tab's version history."""
    rows = conn.execute(
        "SELECT record FROM da_request_records WHERE request_id = ? ORDER BY version",
        (request_id,),
    ).fetchall()
    return [RequestRecord.model_validate(json.loads(row["record"])) for row in rows]


# --- Refines ---


def insert_refine(conn: sqlite3.Connection, row: RefineRow, now: datetime) -> RefineRow:
    conn.execute(
        "INSERT INTO da_refines (request_id, refine_number, source, feedback, suggested_lane,"
        " reason, chosen_lane, from_status, record_version_before, record_version_after,"
        " approach_version_before, approach_version_after, build_number, repro_passed_today,"
        " result, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            row.request_id,
            row.refine_number,
            row.source,
            row.feedback,
            row.suggested_lane,
            row.reason,
            row.chosen_lane,
            row.from_status,
            row.record_version_before,
            row.record_version_after,
            row.approach_version_before,
            row.approach_version_after,
            row.build_number,
            row.repro_passed_today,
            row.result,
            to_db_time(now),
        ),
    )
    return row.model_copy(update={"created_at": now})


def close_refine(
    conn: sqlite3.Connection,
    request_id: str,
    refine_number: int,
    *,
    result: str,
    record_version_after: int,
    approach_version_after: int,
    build_number: int,
    repro_passed_today: int,
    now: datetime,
) -> None:
    """Close a Refine. A Refine that is already closed is refused by the database."""
    cursor = conn.execute(
        "UPDATE da_refines SET result = ?, record_version_after = ?, approach_version_after = ?,"
        " build_number = ?, repro_passed_today = ?, closed_at = ?"
        " WHERE request_id = ? AND refine_number = ?",
        (
            result,
            record_version_after,
            approach_version_after,
            build_number,
            repro_passed_today,
            to_db_time(now),
            request_id,
            refine_number,
        ),
    )
    if cursor.rowcount != 1:
        raise RefineError("That Refine does not exist.")


def read_refines(conn: sqlite3.Connection, request_id: str) -> list[RefineRow]:
    rows = conn.execute(
        "SELECT * FROM da_refines WHERE request_id = ? ORDER BY refine_number", (request_id,)
    ).fetchall()
    return [_to_refine(row) for row in rows]


# --- test sets ---


def next_test_set_version(conn: sqlite3.Connection, request_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(test_set_version), 0) AS top FROM da_test_sets WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row["top"] + 1


def insert_test_set(conn: sqlite3.Connection, item: TestSet, now: datetime) -> TestSet:
    conn.execute(
        "INSERT INTO da_test_sets (request_id, test_set_version, approach_version, added_case_ids,"
        " text, fingerprint, created_at, net_methods, expected_to_change_methods)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.request_id,
            item.test_set_version,
            item.approach_version,
            json.dumps(item.added_case_ids),
            item.text,
            item.fingerprint,
            to_db_time(now),
            json.dumps(item.net_methods),
            json.dumps(item.expected_to_change_methods),
        ),
    )
    return item.model_copy(update={"created_at": now})


def read_test_sets(conn: sqlite3.Connection, request_id: str) -> list[TestSet]:
    rows = conn.execute(
        "SELECT * FROM da_test_sets WHERE request_id = ? ORDER BY test_set_version", (request_id,)
    ).fetchall()
    return [
        TestSet(
            request_id=row["request_id"],
            test_set_version=row["test_set_version"],
            approach_version=row["approach_version"],
            added_case_ids=json.loads(row["added_case_ids"]),
            text=row["text"],
            fingerprint=row["fingerprint"],
            net_methods=json.loads(row["net_methods"]),
            expected_to_change_methods=json.loads(row["expected_to_change_methods"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


def read_latest_test_set(
    conn: sqlite3.Connection, request_id: str, approach_version: int
) -> TestSet | None:
    """The newest test set of one approach version (the frozen set plus appended methods)."""
    found = [
        item
        for item in read_test_sets(conn, request_id)
        if item.approach_version == approach_version
    ]
    return found[-1] if found else None


# --- conflicts ---


def insert_conflict_row(
    conn: sqlite3.Connection, request_id: str, build_number: int, item: Conflict, now: datetime
) -> None:
    """A new row for a new conflict, or for a pick (the newest row per conflict wins)."""
    conn.execute(
        "INSERT INTO da_refine_conflicts (request_id, build_number, path, conflict_id, his_lines,"
        " ai_lines, context, choice, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            request_id,
            build_number,
            item.path,
            item.conflict_id,
            json.dumps(item.his_lines),
            json.dumps(item.ai_lines),
            json.dumps(
                {
                    "start": item.his_start,
                    "end": item.his_end,
                    "before": item.context_before,
                    "after": item.context_after,
                }
            ),
            item.choice or "",
            to_db_time(now),
        ),
    )


def read_conflicts(conn: sqlite3.Connection, request_id: str, build_number: int) -> list[Conflict]:
    """The state of every conflict of one build: the newest row per (path, conflict id)."""
    rows = conn.execute(
        "SELECT * FROM da_refine_conflicts WHERE request_id = ? AND build_number = ? ORDER BY seq",
        (request_id, build_number),
    ).fetchall()
    newest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        newest[(row["path"], row["conflict_id"])] = row
    out = []
    for row in newest.values():
        context = json.loads(row["context"])
        out.append(
            Conflict(
                path=row["path"],
                conflict_id=row["conflict_id"],
                his_start=context["start"],
                his_end=context["end"],
                his_lines=json.loads(row["his_lines"]),
                ai_lines=json.loads(row["ai_lines"]),
                context_before=context["before"],
                context_after=context["after"],
                choice=row["choice"] or None,
            )
        )
    return out


# --- rows to models ---


def _to_refine(row: sqlite3.Row) -> RefineRow:
    closed = row["closed_at"]
    return RefineRow(
        request_id=row["request_id"],
        refine_number=row["refine_number"],
        source=row["source"],
        feedback=row["feedback"],
        suggested_lane=row["suggested_lane"],
        reason=row["reason"],
        chosen_lane=row["chosen_lane"],
        from_status=row["from_status"],
        record_version_before=row["record_version_before"],
        record_version_after=row["record_version_after"],
        approach_version_before=row["approach_version_before"],
        approach_version_after=row["approach_version_after"],
        build_number=row["build_number"],
        repro_passed_today=row["repro_passed_today"],
        result=row["result"],
        created_at=datetime.fromisoformat(row["created_at"]),
        closed_at=datetime.fromisoformat(closed) if closed else None,
    )
