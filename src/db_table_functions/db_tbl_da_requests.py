"""Save and read Developer Assistant requests (SQLite at home)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from da_logging import get_logger
from pydantic_classes.da_models import STATUS_NEW, Request

logger = get_logger(__name__)

# Request ID years follow the bank's local calendar. Singapore has no daylight saving,
# so a fixed UTC+8 offset is exact and needs no extra time zone library.
SINGAPORE_TIME = timezone(timedelta(hours=8), "SGT")

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_requests (
    request_id       TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    developer_id     TEXT NOT NULL,
    status           TEXT NOT NULL,
    version          INTEGER NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    rulebook_version TEXT
);

-- One row per year holding the last number handed out.
-- Numbers come from here, not from counting requests, so a number is never reused.
CREATE TABLE IF NOT EXISTS da_request_counters (
    year        INTEGER PRIMARY KEY,
    last_number INTEGER NOT NULL
);
"""


@contextmanager
def open_db(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open the database, commit if the block succeeds, roll back if it fails, always close."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def to_db_time(moment: datetime) -> str:
    # Fixed-width UTC text (always with microseconds) so text order equals time order.
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def ensure_request_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_CREATE_TABLES_SQL)


def create_request(
    db_path: Path, title: str, developer_id: str, now: datetime | None = None
) -> Request:
    """Save a new request with status NEW and return it with its new ID."""
    now = now or datetime.now(UTC)
    with open_db(db_path) as conn:
        ensure_request_tables(conn)
        request = Request(
            request_id=_next_request_id(conn, now),
            title=title,
            developer_id=developer_id,
            status=STATUS_NEW,
            created_at=now,
            updated_at=now,
        )
        conn.execute(
            "INSERT INTO da_requests (request_id, title, developer_id, status, version,"
            " created_at, updated_at, rulebook_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.request_id,
                request.title,
                request.developer_id,
                request.status,
                request.version,
                to_db_time(request.created_at),
                to_db_time(request.updated_at),
                request.rulebook_version,
            ),
        )
    logger.info("Created request %s", request.request_id)
    return request


def get_request(db_path: Path, request_id: str) -> Request | None:
    """Return the request with this ID, or None if there is no such request."""
    with open_db(db_path) as conn:
        ensure_request_tables(conn)
        row = conn.execute(
            "SELECT * FROM da_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
    return Request(**dict(row)) if row else None


def list_requests(db_path: Path) -> list[Request]:
    """Return all requests, oldest first."""
    with open_db(db_path) as conn:
        ensure_request_tables(conn)
        rows = conn.execute(
            "SELECT * FROM da_requests ORDER BY created_at, request_id"
        ).fetchall()
    return [Request(**dict(row)) for row in rows]


def _next_request_id(conn: sqlite3.Connection, now: datetime) -> str:
    year = now.astimezone(SINGAPORE_TIME).year
    # Add 1 to this year's counter (or start it at 1) and read the result in one statement,
    # inside the same transaction as the insert, so two requests can never get the same number.
    row = conn.execute(
        "INSERT INTO da_request_counters (year, last_number) VALUES (?, 1)"
        " ON CONFLICT(year) DO UPDATE SET last_number = last_number + 1"
        " RETURNING last_number",
        (year,),
    ).fetchone()
    return f"CVDA-{year}-{row['last_number']:04d}"
