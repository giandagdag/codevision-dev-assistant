import sqlite3
from contextlib import closing

import pytest

from db_table_functions import da_db
from db_table_functions.da_db import DatabaseBusyError, begin_write, open_db


def test_missing_data_folder_is_created(tmp_path):
    db_path = tmp_path / "new_folder" / "devassist.db"

    with open_db(db_path) as conn:
        conn.execute("SELECT 1")

    assert db_path.exists()


def test_failed_block_rolls_back(db_path):
    with open_db(db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")

    with pytest.raises(RuntimeError):
        with open_db(db_path) as conn:
            conn.execute("INSERT INTO t VALUES (1)")
            raise RuntimeError("something went wrong half way")

    with open_db(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


def test_locked_database_gives_plain_message(db_path, monkeypatch):
    monkeypatch.setattr(da_db, "BUSY_TIMEOUT_SECONDS", 0.1)
    with open_db(db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")

    # Another connection holds the write lock, as a second Admin's save would.
    with closing(sqlite3.connect(db_path)) as other:
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(DatabaseBusyError, match="busy with another save"):
            with open_db(db_path) as conn:
                begin_write(conn)
        other.rollback()


def test_connection_is_closed_after_the_block(db_path):
    # Windows cannot delete a database file that still has an open connection.
    with open_db(db_path) as conn:
        conn.execute("SELECT 1")

    db_path.unlink()

    assert not db_path.exists()
