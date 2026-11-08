"""Refine's tables: save, read back, append-only, and the build `kind` column (Phase 8 step 4)."""

import sqlite3
from datetime import UTC, datetime

import pytest

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import (
    ensure_build_tables,
    insert_build_run,
    read_build_run,
)
from db_table_functions.db_tbl_da_refine import (
    add_build_result,
    close_refine,
    insert_conflict_row,
    insert_refine,
    insert_test_set,
    next_test_set_version,
    read_conflicts,
    read_latest_test_set,
    read_refine_revision,
    read_refine_state,
    read_refines,
    read_test_sets,
    read_tested,
    save_refine_state,
    set_last_tested,
)
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_build_models import BuildRun
from pydantic_classes.da_refine_models import Conflict, RefineRow, RefineState, TestSet
from tests.da_build_play import ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")
NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def test_the_refine_state_has_its_own_revision_and_refuses_a_stale_save(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        assert read_refine_revision(conn, request_id) == 0
        saved = save_refine_state(conn, RefineState(request_id=request_id), 0, NOW)
        again = save_refine_state(conn, saved.model_copy(update={"step": "lane"}), 1, NOW)

        assert (saved.revision, again.revision) == (1, 2)
        assert read_refine_state(conn, request_id).step == "lane"
        with pytest.raises(StaleRevisionError):
            save_refine_state(conn, again, 1, NOW)
        with pytest.raises(StaleRevisionError):
            save_refine_state(conn, again, 0, NOW)


def test_a_refine_row_is_updated_only_to_close_it(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        insert_refine(
            conn,
            RefineRow(
                request_id=request_id, refine_number=1, chosen_lane="bug", feedback="It crashes."
            ),
            NOW,
        )
        close_refine(
            conn,
            request_id,
            1,
            result="READY_FOR_REVIEW",
            record_version_after=1,
            approach_version_after=1,
            build_number=2,
            repro_passed_today=1,
            now=NOW,
        )

        row = read_refines(conn, request_id)[0]
        assert row.closed_at is not None
        assert (row.build_number, row.repro_passed_today) == (2, 1)
        with pytest.raises(sqlite3.DatabaseError, match="closed Refine"):
            close_refine(
                conn,
                request_id,
                1,
                result="x",
                record_version_after=1,
                approach_version_after=1,
                build_number=3,
                repro_passed_today=0,
                now=NOW,
            )


def test_test_sets_are_append_only_and_the_latest_of_an_approach_version_is_found(
    settings, request_id
):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        assert next_test_set_version(conn, request_id) == 1
        first = TestSet(
            request_id=request_id,
            test_set_version=1,
            approach_version=1,
            text="a",
            fingerprint="f1",
        )
        insert_test_set(conn, first, NOW)
        insert_test_set(
            conn,
            first.model_copy(
                update={"test_set_version": 2, "added_case_ids": ["T-9"], "text": "ab"}
            ),
            NOW,
        )

        assert next_test_set_version(conn, request_id) == 3
        assert [s.test_set_version for s in read_test_sets(conn, request_id)] == [1, 2]
        assert read_latest_test_set(conn, request_id, 1).added_case_ids == ["T-9"]
        assert read_latest_test_set(conn, request_id, 2) is None
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE da_test_sets SET text = 'x'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM da_test_sets")


def test_the_newest_conflict_row_is_its_state_and_rows_are_never_edited(settings, request_id):
    conflict = Conflict(
        path="src/a.py",
        conflict_id="C-1",
        his_start=10,
        his_end=11,
        his_lines=["mine"],
        ai_lines=["ai"],
        context_before=["b"],
        context_after=["a"],
    )
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        insert_conflict_row(conn, request_id, 2, conflict, NOW)
        assert read_conflicts(conn, request_id, 2)[0].choice is None

        insert_conflict_row(conn, request_id, 2, conflict.model_copy(update={"choice": "ai"}), NOW)

        found = read_conflicts(conn, request_id, 2)
        assert len(found) == 1
        assert found[0].choice == "ai"
        assert (found[0].his_start, found[0].context_before) == (10, ["b"])
        assert read_conflicts(conn, request_id, 3) == []
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM da_refine_conflicts")


def test_8_38_two_rebuilds_in_a_row_ending_not_passing_count_two_and_a_pass_resets(
    settings, request_id
):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        assert read_tested(conn, request_id)["not_passing_in_a_row"] == 0

        assert add_build_result(conn, request_id, True, NOW) == 1
        assert add_build_result(conn, request_id, True, NOW) == 2
        assert read_tested(conn, request_id)["not_passing_in_a_row"] == 2
        assert add_build_result(conn, request_id, False, NOW) == 0


def test_last_tested_changes_after_a_build_a_check_run_and_a_restore(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        seen = []
        for number, kind in ((1, "build"), (2, "check"), (1, "restore")):
            set_last_tested(conn, request_id, number, kind, NOW)
            tested = read_tested(conn, request_id)
            seen.append((tested["last_tested_build"], tested["last_tested_kind"]))

        assert seen == [(1, "build"), (2, "check"), (1, "restore")]
        # Setting it does not reset the in-a-row count, and the state row is not touched.
        add_build_result(conn, request_id, True, NOW)
        set_last_tested(conn, request_id, 3, "check", NOW)
        assert read_tested(conn, request_id)["not_passing_in_a_row"] == 1
        assert read_refine_revision(conn, request_id) == 0


def test_the_state_reads_back_last_tested_and_the_count(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        save_refine_state(conn, RefineState(request_id=request_id), 0, NOW)
        set_last_tested(conn, request_id, 4, "rebuild", NOW)
        add_build_result(conn, request_id, True, NOW)

        state = read_refine_state(conn, request_id)

        assert (state.last_tested_build, state.last_tested_kind) == (4, "rebuild")
        assert state.not_passing_in_a_row == 1
        assert state.revision == 1


def test_a_build_run_keeps_its_kind_and_an_old_database_gets_the_column(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        insert_build_run(
            conn,
            BuildRun(
                request_id=request_id,
                build_number=7,
                approach_version=1,
                started_at=NOW,
                kind="check",
            ),
        )
        assert read_build_run(conn, request_id, 7).kind == "check"

    # An old database: the column is dropped, then ensure_build_tables adds it back. Old rows
    # read as `build`.
    with open_db(settings.db_path) as conn:
        conn.execute("ALTER TABLE da_build_runs DROP COLUMN kind")
        ensure_build_tables(conn)
        assert read_build_run(conn, request_id, 7).kind == "build"
