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
from pydantic_classes.da_models import STATUS_DRAFT, Request, check_status_move
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


class RequestNotFoundError(Exception):
    """There is no request with the given ID."""


def create_request(
    db_path: Path, title: str, developer_id: str, now: datetime | None = None
) -> Request:
    """Save a new request with status DRAFT, pinned to the active rulebook version, and return it.

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
        request = insert_request(conn, title, developer_id, now)
    logger.info("Created request %s", request.request_id)
    return request


def insert_request(
    conn: sqlite3.Connection, title: str, developer_id: str, now: datetime
) -> Request:
    """Save a new DRAFT request on the caller's connection, so it can share a transaction.

    The caller sets up the tables and takes the write lock (begin_write) first.
    """
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
        status=STATUS_DRAFT,
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
    return request


def update_request(
    conn: sqlite3.Connection,
    request_id: str,
    now: datetime,
    title: str | None = None,
    status: str | None = None,
    version: int | None = None,
) -> Request:
    """Change a request's title, status or version on the caller's connection, and return it.

    A status change must be a move in the spec 3.1 table. Staying on the same status is not a
    move, so it is not checked. The caller writes the matching audit event in the same
    transaction (rule R6).
    """
    current = read_request(conn, request_id)
    if current is None:
        raise RequestNotFoundError(f"Request {request_id} does not exist.")
    if status is not None and status != current.status:
        check_status_move(current.status, status)
    changes = {"title": title, "status": status, "version": version}
    data = current.model_dump() | {k: v for k, v in changes.items() if v is not None}
    # Built through the model again, so an empty title or version 0 is refused before saving.
    updated = Request.model_validate(data | {"updated_at": now})
    conn.execute(
        "UPDATE da_requests SET title = ?, status = ?, version = ?, updated_at = ?"
        " WHERE request_id = ?",
        (updated.title, updated.status, updated.version, to_db_time(now), request_id),
    )
    return updated


def read_request(conn: sqlite3.Connection, request_id: str) -> Request | None:
    """Read one request on the caller's connection, inside its transaction."""
    row = conn.execute(
        "SELECT * FROM da_requests WHERE request_id = ?", (request_id,)
    ).fetchone()
    return Request(**dict(row)) if row else None


def get_request(db_path: Path, request_id: str) -> Request | None:
    """Return the request with this ID, or None if there is no such request."""
    with open_db(db_path) as conn:
        ensure_request_tables(conn)
        return read_request(conn, request_id)


def list_requests(db_path: Path) -> list[Request]:
    """Return all requests, oldest first."""
    with open_db(db_path) as conn:
        ensure_request_tables(conn)
        rows = conn.execute(
            "SELECT * FROM da_requests ORDER BY created_at, request_id"
        ).fetchall()
    return [Request(**dict(row)) for row in rows]


def list_my_requests(db_path: Path, developer_id: str) -> list[Request]:
    """Return one developer's requests, newest first (for "My recent requests")."""
    with open_db(db_path) as conn:
        ensure_request_tables(conn)
        rows = conn.execute(
            "SELECT * FROM da_requests WHERE developer_id = ?"
            " ORDER BY created_at DESC, request_id DESC",
            (developer_id,),
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
