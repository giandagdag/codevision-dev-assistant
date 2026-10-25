"""Database helpers shared by every table file (SQLite at home)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

# How long to wait for another save to finish before giving up. A module setting so tests can
# shorten it instead of waiting the full time.
BUSY_TIMEOUT_SECONDS = 5.0


class DatabaseBusyError(Exception):
    """Another save held the database for too long. Trying again shortly usually works."""


@contextmanager
def open_db(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open the database, commit if the block succeeds, roll back if it fails, always close."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            yield conn
    except sqlite3.OperationalError as error:
        # SQLite's own wording is "database is locked"; turn it into a plain message.
        if "locked" in str(error):
            raise DatabaseBusyError(
                "The database is busy with another save. Nothing was changed. "
                "Try again in a moment."
            ) from error
        raise
    finally:
        # Always close, so Windows can delete the file afterwards (e.g. the smoke check's temp DB).
        conn.close()


def begin_write(conn: sqlite3.Connection) -> None:
    """Take the database write lock now, before reading anything the write depends on.

    Without this, two saves could both read "v2 is active" and both try to write v3.
    The lock is released when open_db commits or rolls back.
    """
    conn.execute("BEGIN IMMEDIATE")


def to_db_time(moment: datetime) -> str:
    # Fixed-width UTC text (always with microseconds) so text order equals time order.
    return moment.astimezone(UTC).isoformat(timespec="microseconds")
