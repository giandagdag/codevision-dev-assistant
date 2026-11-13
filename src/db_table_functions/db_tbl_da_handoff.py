"""Save and read Handoff (Phase 10 spec section 15). CREATE TABLE IF NOT EXISTS.

- da_handoff_state: one row per request, with its own revision for the stale check.
- da_handoffs: one row per request, append-only (a request is handed off once).

Every write function takes the caller's connection, so a flow can save the state, the handoff row,
audit events and chat lines in ONE transaction (rule B3).
"""

import sqlite3
from datetime import datetime

from db_table_functions.da_db import to_db_time
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE, StaleRevisionError
from pydantic_classes.da_handoff_models import HandoffRow, HandoffState

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_handoff_state (
    request_id TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    state      TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS da_handoffs (
    request_id         TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    record_version     INTEGER NOT NULL,
    approach_version   INTEGER NOT NULL,
    last_tested_build  INTEGER NOT NULL,
    last_tested_kind   TEXT NOT NULL,
    summary_text       TEXT NOT NULL,
    handed_off_by      TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS da_handoffs_no_update
BEFORE UPDATE ON da_handoffs
BEGIN
    SELECT RAISE(ABORT, 'A handoff is append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_handoffs_no_delete
BEFORE DELETE ON da_handoffs
BEGIN
    SELECT RAISE(ABORT, 'A handoff is append-only and cannot be deleted.');
END;
"""


def ensure_handoff_tables(conn: sqlite3.Connection) -> None:
    """Called by ensure_build_tables, after da_requests exists."""
    conn.executescript(_CREATE_TABLES_SQL)


# --- the working state ---


def read_handoff_state(conn: sqlite3.Connection, request_id: str) -> HandoffState | None:
    row = conn.execute(
        "SELECT state, revision FROM da_handoff_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    if row is None:
        return None
    loaded = HandoffState.model_validate_json(row["state"])
    return loaded.model_copy(update={"revision": row["revision"]})


def save_handoff_state(
    conn: sqlite3.Connection, state: HandoffState, base_revision: int, now: datetime
) -> HandoffState:
    """Save as revision base_revision + 1; refused if the stored revision moved on. Base 0 means
    the first save. Check and save are one statement, so nothing can slip in between."""
    text = state.model_dump_json(exclude={"revision"})
    if base_revision == 0:
        try:
            conn.execute(
                "INSERT INTO da_handoff_state (request_id, state, revision, updated_at)"
                " VALUES (?, ?, 1, ?)",
                (state.request_id, text, to_db_time(now)),
            )
        except sqlite3.IntegrityError as error:
            raise StaleRevisionError(STALE_MESSAGE) from error
        return state.model_copy(update={"revision": 1})
    cursor = conn.execute(
        "UPDATE da_handoff_state SET state = ?, revision = ?, updated_at = ?"
        " WHERE request_id = ? AND revision = ?",
        (text, base_revision + 1, to_db_time(now), state.request_id, base_revision),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return state.model_copy(update={"revision": base_revision + 1})


# --- the signed form ---


def insert_handoff(conn: sqlite3.Connection, item: HandoffRow, now: datetime) -> HandoffRow:
    """A request is handed off once: a second row for the same request is refused."""
    conn.execute(
        "INSERT INTO da_handoffs (request_id, record_version, approach_version,"
        " last_tested_build, last_tested_kind, summary_text, handed_off_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.request_id,
            item.record_version,
            item.approach_version,
            item.last_tested_build,
            item.last_tested_kind,
            item.summary_text,
            item.handed_off_by,
            to_db_time(now),
        ),
    )
    return item.model_copy(update={"created_at": now})


# --- the last tested fingerprints (spec H4) ---


def get_last_tested_fingerprints(conn: sqlite3.Connection, request_id: str) -> dict[str, str]:
    """Path -> fingerprint of the code the last tested run tested.

    Confirmed in the code (Phase 8): every kind (build, rebuild, check, restore) leaves its tested
    text as `code` rows of the last tested build, so one read covers all of them. A request with no
    Refine yet has no tested row, and then the current build is the last tested one."""
    # Local imports: db_tbl_da_build imports this file at the top, so a top import would be a loop.
    from db_table_functions.db_tbl_da_build import read_build_state, read_latest_code
    from db_table_functions.db_tbl_da_refine import read_tested

    build = read_tested(conn, request_id)["last_tested_build"]
    if not build:
        state = read_build_state(conn, request_id)
        build = state.build_number if state else 0
    if not build:
        return {}
    code = read_latest_code(conn, request_id, build)
    return {path: item.fingerprint for path, item in code.items()}


def read_handoff(conn: sqlite3.Connection, request_id: str) -> HandoffRow | None:
    row = conn.execute("SELECT * FROM da_handoffs WHERE request_id = ?", (request_id,)).fetchone()
    return HandoffRow.model_validate(dict(row)) if row else None
