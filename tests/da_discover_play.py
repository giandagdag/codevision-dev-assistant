"""Test helper: a confirmed request, plus easy reading of what Discover saved."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_requests import update_request
from tests.da_play import to_confirmed

T0 = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def confirmed_id(settings) -> str:
    return to_confirmed(settings).request.request_id


def event_types(settings, request_id) -> list[str]:
    return [event.event_type for event in list_audit_events(settings.db_path, request_id)]


def events_of(settings, request_id, event_type):
    events = list_audit_events(settings.db_path, request_id)
    return [e for e in events if e.event_type == event_type]


def table_text(settings, table, request_id) -> str:
    """All rows of a table for one request as one text, to compare before and after."""
    with closing(sqlite3.connect(settings.db_path)) as conn:
        query = f"SELECT * FROM {table} WHERE request_id = ?"
        rows = conn.execute(query, (request_id,)).fetchall()
    return repr(rows)


def record_state(settings, request_id) -> tuple[str, str]:
    """The stored record v1 and the Understand session, exactly as saved (rule R4)."""
    return (
        table_text(settings, "da_request_records", request_id),
        table_text(settings, "da_understand_sessions", request_id),
    )


def set_status(settings, request_id, *statuses) -> None:
    """Move the request through these statuses directly, as a crash would leave it."""
    with open_db(settings.db_path) as conn:
        for status in statuses:
            update_request(conn, request_id, now=T0, status=status)


def moves(settings, request_id) -> list[tuple[str, str]]:
    """Every status move audited for the request, oldest first."""
    return [
        (e.details["from"], e.details["to"])
        for e in events_of(settings, request_id, "status_changed")
    ]
