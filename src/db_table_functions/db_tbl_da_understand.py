"""Save and read the Understand conversation (SQLite at home).

Three tables:
- da_understand_sessions: the working state of each conversation, like a work file between
  screens. Editable, with a revision number so a save from an old window is refused (rule R7).
- da_chat_messages: every chat message. Append-only, like a journal (rule R5).
- da_request_records: confirmed record versions. Append-only (rule R5).

The functions that write take the caller's connection, so the flow module can save messages,
session, request status and audit events in one transaction (rule R6).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from db_table_functions.da_db import open_db, to_db_time
from db_table_functions.db_tbl_da_requests import ensure_request_tables
from pydantic_classes.da_request_record_models import (
    ChatMessage,
    RequestRecord,
    Speaker,
    UnderstandSession,
)

STALE_MESSAGE = "This request was updated in another window. Reload to continue."

# The triggers make the database itself refuse any edit or delete, even from code that skips
# this file. They are SQLite-only: CodeVision's database will need its own equivalent.
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_understand_sessions (
    request_id TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    session    TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS da_chat_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES da_requests (request_id),
    sent_at    TEXT NOT NULL,
    speaker    TEXT NOT NULL,
    text       TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS da_chat_messages_no_update
BEFORE UPDATE ON da_chat_messages
BEGIN
    SELECT RAISE(ABORT, 'Chat messages are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_chat_messages_no_delete
BEFORE DELETE ON da_chat_messages
BEGIN
    SELECT RAISE(ABORT, 'Chat messages are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_request_records (
    request_id   TEXT NOT NULL REFERENCES da_requests (request_id),
    version      INTEGER NOT NULL,
    record       TEXT NOT NULL,
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    PRIMARY KEY (request_id, version)
);

CREATE TRIGGER IF NOT EXISTS da_request_records_no_update
BEFORE UPDATE ON da_request_records
BEGIN
    SELECT RAISE(ABORT, 'Confirmed request records are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_request_records_no_delete
BEFORE DELETE ON da_request_records
BEGIN
    SELECT RAISE(ABORT, 'Confirmed request records are append-only and cannot be deleted.');
END;
"""


class UnderstandError(Exception):
    """An Understand action was refused. The message says why in plain words."""


class StaleRevisionError(UnderstandError):
    """The save was based on an old revision: another window saved first (rule R7)."""


def ensure_understand_tables(conn: sqlite3.Connection) -> None:
    # These tables point at da_requests, so that table must exist first.
    ensure_request_tables(conn)
    conn.executescript(_CREATE_TABLES_SQL)


def insert_session(conn: sqlite3.Connection, session: UnderstandSession, now: datetime) -> None:
    """Save a new conversation at revision 1."""
    conn.execute(
        "INSERT INTO da_understand_sessions (request_id, session, revision, updated_at)"
        " VALUES (?, ?, 1, ?)",
        (session.request_id, _session_json(session), to_db_time(now)),
    )


def save_session(
    conn: sqlite3.Connection, session: UnderstandSession, base_revision: int, now: datetime
) -> UnderstandSession:
    """Save the session as revision base_revision + 1 and return it.

    Refused if the stored revision is no longer base_revision. The check and the save are one
    statement, so no other save can slip in between. The caller's transaction then rolls back,
    so nothing from the action is written.
    """
    cursor = conn.execute(
        "UPDATE da_understand_sessions SET session = ?, revision = ?, updated_at = ?"
        " WHERE request_id = ? AND revision = ?",
        (
            _session_json(session),
            base_revision + 1,
            to_db_time(now),
            session.request_id,
            base_revision,
        ),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return session.model_copy(update={"revision": base_revision + 1})


def read_session(conn: sqlite3.Connection, request_id: str) -> UnderstandSession | None:
    row = conn.execute(
        "SELECT session, revision FROM da_understand_sessions WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    return UnderstandSession.model_validate(
        json.loads(row["session"]) | {"revision": row["revision"]}
    )


def get_session(db_path: Path, request_id: str) -> UnderstandSession | None:
    """Return the conversation's working state, or None if the request has none."""
    with open_db(db_path) as conn:
        ensure_understand_tables(conn)
        return read_session(conn, request_id)


def add_message(
    conn: sqlite3.Connection, request_id: str, speaker: Speaker, text: str, now: datetime
) -> ChatMessage:
    """Append one chat message on the caller's connection."""
    message = ChatMessage(request_id=request_id, sent_at=now, speaker=speaker, text=text)
    conn.execute(
        "INSERT INTO da_chat_messages (request_id, sent_at, speaker, text) VALUES (?, ?, ?, ?)",
        (message.request_id, to_db_time(message.sent_at), message.speaker, message.text),
    )
    return message


def list_messages(db_path: Path, request_id: str) -> list[ChatMessage]:
    """Return a request's chat in the order it happened."""
    with open_db(db_path) as conn:
        ensure_understand_tables(conn)
        return read_messages(conn, request_id)


def read_messages(conn: sqlite3.Connection, request_id: str) -> list[ChatMessage]:
    # message_id is the insert order. The chat is append-only, so that is the true order,
    # even if two messages carry the same time.
    rows = conn.execute(
        "SELECT request_id, sent_at, speaker, text FROM da_chat_messages"
        " WHERE request_id = ? ORDER BY message_id",
        (request_id,),
    ).fetchall()
    return [ChatMessage(**dict(row)) for row in rows]


def insert_confirmed_record(
    conn: sqlite3.Connection, record: RequestRecord, confirmed_by: str, now: datetime
) -> None:
    """Save a confirmed record version. A second save of the same version is refused."""
    try:
        conn.execute(
            "INSERT INTO da_request_records (request_id, version, record, confirmed_by,"
            " confirmed_at) VALUES (?, ?, ?, ?, ?)",
            (
                record.request_id,
                record.version,
                record.model_dump_json(),
                confirmed_by,
                to_db_time(now),
            ),
        )
    except sqlite3.IntegrityError as error:
        raise UnderstandError(
            f"Request {record.request_id} version {record.version} is already confirmed "
            "and cannot be saved again."
        ) from error


def get_confirmed_record(
    db_path: Path, request_id: str, version: int = 1
) -> RequestRecord | None:
    """Return a confirmed record version, or None if it has not been confirmed."""
    with open_db(db_path) as conn:
        ensure_understand_tables(conn)
        return read_confirmed_record(conn, request_id, version)


def read_confirmed_record(
    conn: sqlite3.Connection, request_id: str, version: int = 1
) -> RequestRecord | None:
    row = conn.execute(
        "SELECT record FROM da_request_records WHERE request_id = ? AND version = ?",
        (request_id, version),
    ).fetchone()
    return RequestRecord.model_validate_json(row["record"]) if row else None


def _session_json(session: UnderstandSession) -> str:
    # The revision lives in its own column, so it is never stored twice.
    return session.model_dump_json(exclude={"revision"})
