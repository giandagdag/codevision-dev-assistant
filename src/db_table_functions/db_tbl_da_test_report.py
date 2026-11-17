"""Save and read test reports (Fix D1 spec E7). One table, append-only like the audit trail:
a round that reached Layer B adds a row, nothing is ever edited or deleted. The report page
builds its view from these saved results, never from a new run.
"""

import json
import sqlite3
from datetime import datetime
from typing import Any

from db_table_functions.da_db import to_db_time

# The triggers are SQLite-only: CodeVision's database will need its own equivalent.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS da_test_reports (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number INTEGER NOT NULL,
    round        INTEGER NOT NULL,
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS da_test_reports_no_update
BEFORE UPDATE ON da_test_reports
BEGIN
    SELECT RAISE(ABORT, 'Test reports are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_test_reports_no_delete
BEFORE DELETE ON da_test_reports
BEGIN
    SELECT RAISE(ABORT, 'Test reports are append-only and cannot be deleted.');
END;
"""


def ensure_test_report_table(conn: sqlite3.Connection) -> None:
    """Called by ensure_build_tables, after da_requests exists."""
    conn.executescript(_CREATE_TABLE_SQL)


def insert_test_report(
    conn: sqlite3.Connection,
    request_id: str,
    build_number: int,
    round_number: int,
    body: dict[str, Any],
    now: datetime,
) -> None:
    """Add one report row on the caller's connection (saved in the round's transaction)."""
    conn.execute(
        "INSERT INTO da_test_reports (request_id, build_number, round, body, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (request_id, build_number, round_number, json.dumps(body), to_db_time(now)),
    )


def read_test_reports(
    conn: sqlite3.Connection, request_id: str, build_number: int
) -> list[dict[str, Any]]:
    """Every report row of a build, oldest first: round, body (a dict) and created_at."""
    rows = conn.execute(
        "SELECT round, body, created_at FROM da_test_reports"
        " WHERE request_id = ? AND build_number = ? ORDER BY seq",
        (request_id, build_number),
    ).fetchall()
    return [
        {
            "round": row["round"],
            "body": json.loads(row["body"]),
            "created_at": datetime.fromisoformat(row["created_at"]),
        }
        for row in rows
    ]
