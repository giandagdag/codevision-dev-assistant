"""Save and read audit events. Append-only: there are no edit or delete functions (rule R1)."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from da_logging import get_logger
from db_table_functions.db_tbl_da_requests import ensure_request_tables, open_db, to_db_time
from pydantic_classes.da_models import Actor, AuditEvent

logger = get_logger(__name__)

# event_id is an auto-numbered row ID. It records insert order, so events that share a
# timestamp still list in the order they happened. AUTOINCREMENT means it is never reused.
#
# The triggers make the database itself refuse any edit or delete, even from code that skips
# this file. They are SQLite-only: CodeVision's database will need its own equivalent.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS da_audit_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES da_requests (request_id),
    timestamp  TEXT NOT NULL,
    actor      TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details    TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS da_audit_events_no_update
BEFORE UPDATE ON da_audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_audit_events_no_delete
BEFORE DELETE ON da_audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events are append-only and cannot be deleted.');
END;
"""


class UnknownRequestError(Exception):
    """An audit event was given for a request ID that does not exist."""


def add_audit_event(
    db_path: Path,
    request_id: str,
    actor: Actor,
    event_type: str,
    details: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> AuditEvent:
    """Append one event to a request's audit trail and return it.

    details must hold plain values only (text, numbers, lists, dicts), and never a secret such as
    an API key: audit events are kept forever and cannot be removed.
    """
    event = AuditEvent(
        request_id=request_id,
        timestamp=now or datetime.now(UTC),
        actor=actor,
        event_type=event_type,
        details=details or {},
    )
    try:
        details_text = json.dumps(event.details)
    except TypeError as error:
        raise ValueError(
            f"Audit event details for {request_id} hold a value that cannot be saved ({error}). "
            "Use plain text, numbers, lists, or dicts only."
        ) from error
    with open_db(db_path) as conn:
        _ensure_audit_table(conn)
        exists = conn.execute(
            "SELECT 1 FROM da_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if not exists:
            raise UnknownRequestError(
                f"Request {request_id} does not exist, so no audit event was recorded. "
                "Create the request first."
            )
        conn.execute(
            "INSERT INTO da_audit_events (request_id, timestamp, actor, event_type, details)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                event.request_id,
                to_db_time(event.timestamp),
                event.actor,
                event.event_type,
                details_text,
            ),
        )
    logger.info("Audit event %s recorded for %s", event.event_type, request_id)
    return event


def list_audit_events(db_path: Path, request_id: str) -> list[AuditEvent]:
    """Return a request's events in time order, then in the order they were added."""
    with open_db(db_path) as conn:
        _ensure_audit_table(conn)
        rows = conn.execute(
            "SELECT request_id, timestamp, actor, event_type, details FROM da_audit_events"
            " WHERE request_id = ? ORDER BY timestamp, event_id",
            (request_id,),
        ).fetchall()
    return [
        AuditEvent(**{**dict(row), "details": json.loads(row["details"])}) for row in rows
    ]


def _ensure_audit_table(conn: sqlite3.Connection) -> None:
    # The audit table points at da_requests, so that table must exist first.
    ensure_request_tables(conn)
    conn.executescript(_CREATE_TABLE_SQL)
