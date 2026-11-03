import sqlite3
from datetime import UTC, datetime

import pytest

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from db_table_functions.db_tbl_da_workspace import (
    ensure_workspace_tables,
    insert_scan,
    insert_workspace_file,
    read_baseline_times,
    read_file_versions,
    read_known_files,
    read_latest_scan,
    read_scanned_paths,
    read_workspace_revision,
    read_workspace_state,
    save_workspace_state,
)
from pydantic_classes.da_workspace_models import (
    CheckResult,
    ScanItem,
    ScanResult,
    WorkspaceFile,
    WorkspaceState,
)

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 11, 1, 9, 5, tzinfo=UTC)
PATH = "src/callbacks/da_demo.py"


@pytest.fixture
def request_id(db_path, published_rulebook):
    return create_request(db_path, "New change request", "dev-0001", now=T0).request_id


def make_file(request_id, kind="baseline", text="x\n", fingerprint="a" * 64, **changes):
    values = {
        "request_id": request_id,
        "path": PATH,
        "file_version": 1,
        "kind": kind,
        "text": text,
        "fingerprint": fingerprint,
    }
    values.update(changes)
    return WorkspaceFile(**values)


def test_state_round_trip_and_revision_goes_up_by_one(db_path, request_id):
    state = WorkspaceState(
        request_id=request_id,
        step="ws_ready",
        folder_name="codevision",
        last_check=CheckResult(passed=True, folder_name="codevision"),
        linked_at=T0,
    )
    with open_db(db_path) as conn:
        ensure_workspace_tables(conn)
        assert read_workspace_revision(conn, request_id) == 0
        first = save_workspace_state(conn, state, 0, T0)
        second = save_workspace_state(conn, state, 1, T1)
        loaded = read_workspace_state(conn, request_id)

    assert (first.revision, second.revision) == (1, 2)
    assert loaded.revision == 2
    assert loaded.folder_name == "codevision"
    assert loaded.last_check.passed


def test_a_save_with_an_old_revision_is_refused(db_path, request_id):
    state = WorkspaceState(request_id=request_id)
    with open_db(db_path) as conn:
        ensure_workspace_tables(conn)
        save_workspace_state(conn, state, 0, T0)
        with pytest.raises(StaleRevisionError):
            save_workspace_state(conn, state, 0, T1)  # a second "first save"
        save_workspace_state(conn, state, 1, T1)
        with pytest.raises(StaleRevisionError):
            save_workspace_state(conn, state, 1, T1)  # revision 1 is old now


def test_file_versions_count_up_per_path_and_keep_the_text(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_workspace_tables(conn)
        one = insert_workspace_file(conn, make_file(request_id), T0)
        two = insert_workspace_file(
            conn, make_file(request_id, "written", "y\n", "b" * 64, line_ending="\r\n"), T1
        )
        other = insert_workspace_file(conn, make_file(request_id, path="src/web/da_b.py"), T1)
        versions = read_file_versions(conn, request_id, PATH)

    assert (one.file_version, two.file_version, other.file_version) == (1, 2, 1)
    assert [v.kind for v in versions] == ["baseline", "written"]
    assert versions[1].text == "y\n" and versions[1].line_ending == "\r\n"


def test_files_and_scans_are_append_only(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_workspace_tables(conn)
        insert_workspace_file(conn, make_file(request_id), T0)
        insert_scan(conn, request_id, ScanResult(), T0)
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE da_workspace_files SET text = 'z'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM da_workspace_files")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE da_workspace_scans SET results = '{}'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM da_workspace_scans")


def test_the_known_file_is_the_last_write_else_the_baseline_never_a_scan(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_workspace_tables(conn)
        insert_workspace_file(conn, make_file(request_id, "baseline", fingerprint="1" * 64), T0)
        known = read_known_files(conn, request_id)
        assert known[PATH].fingerprint == "1" * 64
        insert_workspace_file(conn, make_file(request_id, "written", fingerprint="2" * 64), T1)
        insert_workspace_file(conn, make_file(request_id, "scanned", fingerprint="3" * 64), T1)
        known = read_known_files(conn, request_id)
        scanned = read_scanned_paths(conn, request_id)

    assert known[PATH].fingerprint == "2" * 64
    assert scanned == {PATH}


def test_the_baseline_time_is_the_first_baseline(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_workspace_tables(conn)
        insert_workspace_file(conn, make_file(request_id, "baseline"), T0)
        insert_workspace_file(conn, make_file(request_id, "baseline"), T1)
        times = read_baseline_times(conn, request_id)

    assert times[PATH] == T0


def test_scans_are_numbered_and_the_latest_is_read_back(db_path, request_id):
    first = ScanResult(items=[ScanItem(path=PATH, outcome="unchanged")])
    second = ScanResult(items=[ScanItem(path=PATH, outcome="changed")])
    with open_db(db_path) as conn:
        ensure_workspace_tables(conn)
        assert read_latest_scan(conn, request_id) is None
        assert insert_scan(conn, request_id, first, T0) == 1
        assert insert_scan(conn, request_id, second, T1) == 2
        latest = read_latest_scan(conn, request_id)

    assert latest.count("changed") == 1
