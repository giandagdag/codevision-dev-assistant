"""Save and read escalations (Phase 10 spec section 15). CREATE TABLE IF NOT EXISTS.

One open row per request (a unique index), with its own revision for the stale check. Rows are
never deleted. Every write function takes the caller's connection, so a flow can move the status,
save the row, audit and chat in ONE transaction (rule B3).
AS400 picture: a message on the help-desk queue; one open message per job.
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
from pydantic_classes.da_escalation_models import EscalationRow

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS da_escalations (
    escalation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT NOT NULL REFERENCES da_requests (request_id),
    body          TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    revision      INTEGER NOT NULL,
    opened_at     TEXT NOT NULL,
    closed_at     TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS da_escalations_one_open
ON da_escalations (request_id) WHERE outcome = 'open';
"""

# Left out of the JSON body: these live in their own columns.
_COLUMN_FIELDS = {"escalation_id", "outcome", "revision", "opened_at", "closed_at"}


class EscalationAlreadyOpenError(UnderstandError):
    """A second open escalation for one request (rule X1: add a reason to the open row instead)."""


def ensure_escalation_tables(conn: sqlite3.Connection) -> None:
    """Called by ensure_build_tables, after da_requests exists."""
    conn.executescript(_CREATE_SQL)


def ensure_escalation_table_in_transaction(conn: sqlite3.Connection) -> None:
    """The same tables, made INSIDE an open write transaction. `executescript` would end the
    caller's transaction (it commits first), so the statements run one by one here. A flow that
    never ran a build has no escalations table yet, and its Get help must still work."""
    for statement in _CREATE_SQL.split(";"):
        if statement.strip():
            conn.execute(statement)


def _row_from_db(row: sqlite3.Row) -> EscalationRow:
    data = json.loads(row["body"])
    data.update(
        escalation_id=row["escalation_id"],
        outcome=row["outcome"],
        revision=row["revision"],
        opened_at=row["opened_at"],
        closed_at=row["closed_at"],
    )
    return EscalationRow.model_validate(data)


def insert_escalation(
    conn: sqlite3.Connection, item: EscalationRow, now: datetime
) -> EscalationRow:
    """Open a new row (revision 1). Refused when the request already has an open one."""
    body = item.model_dump_json(exclude=_COLUMN_FIELDS)
    try:
        cursor = conn.execute(
            "INSERT INTO da_escalations (request_id, body, outcome, revision, opened_at)"
            " VALUES (?, ?, 'open', 1, ?)",
            (item.request_id, body, to_db_time(now)),
        )
    except sqlite3.IntegrityError as error:
        raise EscalationAlreadyOpenError(
            "This request already has an open escalation."
        ) from error
    return item.model_copy(
        update={
            "escalation_id": cursor.lastrowid,
            "outcome": "open",
            "revision": 1,
            "opened_at": now,
        }
    )


def update_escalation(
    conn: sqlite3.Connection, item: EscalationRow, base_revision: int, now: datetime
) -> EscalationRow:
    """Save a changed row (a reason, guidance, a take-over, or the close) as base_revision + 1.
    Refused if the stored revision moved on. Check and save are one statement."""
    closed = item.outcome != "open"
    cursor = conn.execute(
        "UPDATE da_escalations SET body = ?, outcome = ?, revision = ?, closed_at = ?"
        " WHERE escalation_id = ? AND revision = ?",
        (
            item.model_dump_json(exclude=_COLUMN_FIELDS),
            item.outcome,
            base_revision + 1,
            to_db_time(now) if closed else None,
            item.escalation_id,
            base_revision,
        ),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return item.model_copy(
        update={"revision": base_revision + 1, "closed_at": now if closed else None}
    )


def read_open_escalation(conn: sqlite3.Connection, request_id: str) -> EscalationRow | None:
    row = conn.execute(
        "SELECT * FROM da_escalations WHERE request_id = ? AND outcome = 'open'", (request_id,)
    ).fetchone()
    return _row_from_db(row) if row else None


def mark_guidance_used(conn: sqlite3.Connection, item: EscalationRow, used_in: str) -> None:
    """Write `used_in` on every unused piece of guidance of a (closed) row. The row stays closed
    and keeps its closing time; only the revision goes up."""
    marked = [
        piece if piece.used_in else piece.model_copy(update={"used_in": used_in})
        for piece in item.guidance
    ]
    body = item.model_copy(update={"guidance": marked}).model_dump_json(exclude=_COLUMN_FIELDS)
    conn.execute(
        "UPDATE da_escalations SET body = ?, revision = revision + 1 WHERE escalation_id = ?",
        (body, item.escalation_id),
    )


def read_escalation(conn: sqlite3.Connection, escalation_id: int) -> EscalationRow | None:
    row = conn.execute(
        "SELECT * FROM da_escalations WHERE escalation_id = ?", (escalation_id,)
    ).fetchone()
    return _row_from_db(row) if row else None


def list_escalations(conn: sqlite3.Connection) -> list[EscalationRow]:
    """Every escalation of every request, newest first (the inbox list, spec section 9)."""
    rows = conn.execute("SELECT * FROM da_escalations ORDER BY escalation_id DESC").fetchall()
    return [_row_from_db(row) for row in rows]


def read_escalations(conn: sqlite3.Connection, request_id: str) -> list[EscalationRow]:
    """Every escalation of the request, oldest first."""
    rows = conn.execute(
        "SELECT * FROM da_escalations WHERE request_id = ? ORDER BY escalation_id", (request_id,)
    ).fetchall()
    return [_row_from_db(row) for row in rows]


def last_fired_count(
    conn: sqlite3.Connection,
    request_id: str,
    trigger: str,
    outcomes: tuple[str, ...] = ("open", "returned", "abandoned"),
) -> int:
    """The count that fired the newest row of this trigger (rule X2), 0 if none. `outcomes`
    narrows the rows looked at: trigger 1 leaves out returned rows, because Return reset the
    count."""
    for item in reversed(read_escalations(conn, request_id)):
        if trigger in item.triggers and item.outcome in outcomes:
            return item.fired_count
    return 0
