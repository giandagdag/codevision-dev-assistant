"""Save and read Developer Assistant requests (SQLite at home)."""

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from da_logging import get_logger
from db_table_functions.da_db import begin_write, open_db, to_db_time
from db_table_functions.db_tbl_da_rulebook import (
    RulebookError,
    ensure_rulebook_tables,
    get_active_version_number,
    get_version,
)
from pydantic_classes.da_models import STATUS_NEW, Request
from pydantic_classes.da_rulebook_models import RulebookVersion

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
    rulebook_version INTEGER
);

-- One row per year holding the last number handed out.
-- Numbers come from here, not from counting requests, so a number is never reused.
CREATE TABLE IF NOT EXISTS da_request_counters (
    year        INTEGER PRIMARY KEY,
    last_number INTEGER NOT NULL
);
"""


def ensure_request_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_CREATE_TABLES_SQL)


def create_request(
    db_path: Path, title: str, developer_id: str, now: datetime | None = None
) -> Request:
    """Save a new request with status NEW, pinned to the active rulebook version, and return it.

    Refused if no rulebook has been published yet, because every request must know which
    house rules it is generated and reviewed under.
    """
    now = now or datetime.now(UTC)
    with open_db(db_path) as conn:
        ensure_request_tables(conn)
        ensure_rulebook_tables(conn)
        # Lock first, so a rulebook save cannot slip in between reading the active version
        # and saving the request: the pin is exactly the version active at that moment.
        begin_write(conn)
        pinned_version = get_active_version_number(conn)
        if pinned_version is None:
            raise RulebookError(
                "No rulebook has been published yet, so the request was not created. "
                "Ask an Admin to publish the first rulebook version."
            )
        request = Request(
            request_id=_next_request_id(conn, now),
            title=title,
            developer_id=developer_id,
            status=STATUS_NEW,
            created_at=now,
            updated_at=now,
            rulebook_version=pinned_version,
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


def get_rulebook_for_request(db_path: Path, request_id: str) -> RulebookVersion:
    """Return the rulebook version this request is pinned to. It never changes once set."""
    request = get_request(db_path, request_id)
    if request is None:
        raise RulebookError(f"Request {request_id} does not exist, so it has no rulebook.")
    if request.rulebook_version is None:
        raise RulebookError(
            f"Request {request_id} was created before rulebooks existed, "
            "so it is not pinned to any version."
        )
    version = get_version(db_path, request.rulebook_version)
    if version is None:
        # Cannot happen through our functions (versions are never deleted), so say so plainly.
        raise RulebookError(
            f"Request {request_id} is pinned to v{request.rulebook_version}, "
            "but that version is missing from the database."
        )
    return version


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
