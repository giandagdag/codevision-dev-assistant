"""Fix G9 F10: column upgrades survive two connections racing on an old database."""

import sqlite3
import threading
from contextlib import closing

import pytest

from db_table_functions import (
    db_tbl_da_approach,
    db_tbl_da_build,
    db_tbl_da_discovery,
    db_tbl_da_enhance,
    db_tbl_da_escalation,
    db_tbl_da_handoff,
    db_tbl_da_refine,
    db_tbl_da_requests,
    db_tbl_da_rulebook,
    db_tbl_da_tester,
    db_tbl_da_understand,
    db_tbl_da_workspace,
)
from db_table_functions.da_db import add_column_if_missing, open_db


def _columns(db_path, table):
    with closing(sqlite3.connect(db_path)) as conn:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def test_f10_1_two_connections_upgrading_at_once_do_not_crash(tmp_path):
    errors = []

    def upgrade(db_path, barrier):
        try:
            barrier.wait()
            with open_db(db_path) as conn:
                db_tbl_da_discovery.ensure_discovery_tables(conn)
        except Exception as error:  # noqa: BLE001 - the test reports any failure
            errors.append(error)

    for i in range(20):
        db_path = tmp_path / f"old{i}.db"
        with closing(sqlite3.connect(db_path)) as conn:  # old shape: no impact, no index_build
            conn.execute("CREATE TABLE da_discovery_results (request_id TEXT, round INTEGER)")
            conn.commit()
        barrier = threading.Barrier(2)
        threads = [threading.Thread(target=upgrade, args=(db_path, barrier)) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert _columns(db_path, "da_discovery_results").count("impact") == 1


def test_f10_helper_treats_a_duplicate_column_as_done(db_path):
    with open_db(db_path) as conn:
        conn.execute("CREATE TABLE t (a TEXT)")
        add_column_if_missing(conn, "t", "b", "TEXT")
        add_column_if_missing(conn, "t", "b", "TEXT")  # the second connection's ALTER
    assert _columns(db_path, "t") == ["a", "b"]


def test_f10_2_helper_raises_on_any_other_error(db_path):
    with open_db(db_path) as conn, pytest.raises(sqlite3.OperationalError, match="no such table"):
        add_column_if_missing(conn, "missing_table", "b", "TEXT")


def test_f10_helper_refuses_names_that_are_not_identifiers(db_path):
    with open_db(db_path) as conn, pytest.raises(AssertionError):
        add_column_if_missing(conn, "t; DROP TABLE t", "b", "TEXT")


def test_f10_3_every_ensure_function_can_run_twice(db_path):
    ensures = [
        db_tbl_da_rulebook.ensure_rulebook_tables,
        db_tbl_da_requests.ensure_request_tables,
        db_tbl_da_understand.ensure_understand_tables,
        db_tbl_da_discovery.ensure_discovery_tables,
        db_tbl_da_approach.ensure_approach_tables,
        db_tbl_da_workspace.ensure_workspace_tables,
        db_tbl_da_build.ensure_build_tables,
        db_tbl_da_tester.ensure_tester_tables,
        db_tbl_da_refine.ensure_refine_tables,
        db_tbl_da_enhance.ensure_enhance_tables,
        db_tbl_da_handoff.ensure_handoff_tables,
        db_tbl_da_escalation.ensure_escalation_tables,
    ]
    for _ in range(2):
        with open_db(db_path) as conn:
            for ensure in ensures:
                ensure(conn)
