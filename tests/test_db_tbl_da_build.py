import sqlite3
from datetime import UTC, datetime

import pytest

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import (
    BuildError,
    add_progress,
    close_build_run,
    count_open_builds,
    ensure_build_tables,
    insert_build_file,
    insert_build_run,
    insert_round,
    next_build_number,
    read_build_files,
    read_build_revision,
    read_build_run,
    read_build_state,
    read_frozen_files,
    read_latest_code,
    read_progress,
    read_rounds,
    read_running_requests,
    save_build_state,
)
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_build_models import (
    BuildFile,
    BuildRun,
    BuildState,
    LayerAProblem,
    LayerAResult,
    LayerBResult,
    ProgressLine,
    RoundRecord,
    TestOutcome,
)

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 11, 3, 9, 5, tzinfo=UTC)


@pytest.fixture
def request_id(db_path, published_rulebook):
    return create_request(db_path, "New change request", "dev-0001", now=T0).request_id


def make_file(request_id, kind="code", text="x = 1\n", build=1, round=1, **changes):
    values = {
        "request_id": request_id,
        "build_number": build,
        "round": round,
        "path": "src/agents/a.py",
        "kind": kind,
        "text": text,
        "fingerprint": "a" * 64,
        "made_by": "generator",
    }
    values.update(changes)
    return BuildFile(**values)


def make_run(request_id, number=1, approach_version=1):
    return BuildRun(
        request_id=request_id,
        build_number=number,
        approach_version=approach_version,
        started_at=T0,
    )


def test_state_round_trip_and_revision_goes_up_by_one(db_path, request_id):
    state = BuildState(request_id=request_id, step="b_running", build_number=1, current_round=1)
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        assert read_build_revision(conn, request_id) == 0
        assert read_build_state(conn, request_id) is None
        first = save_build_state(conn, state, 0, T0)
        second = save_build_state(conn, state.model_copy(update={"step": "b_done"}), 1, T1)
        loaded = read_build_state(conn, request_id)

    assert (first.revision, second.revision) == (1, 2)
    assert (loaded.step, loaded.revision, loaded.build_number) == ("b_done", 2, 1)


def test_a_save_with_an_old_revision_is_refused(db_path, request_id):
    state = BuildState(request_id=request_id)
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        save_build_state(conn, state, 0, T0)
        with pytest.raises(StaleRevisionError):
            save_build_state(conn, state, 0, T1)  # a second "first save"
        save_build_state(conn, state, 1, T1)
        with pytest.raises(StaleRevisionError):
            save_build_state(conn, state, 1, T1)  # revision 1 is old now


def test_requests_marked_running_are_found_for_start_up(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        save_build_state(conn, BuildState(request_id=request_id, step="b_running"), 0, T0)

        assert read_running_requests(conn) == [request_id]
        save_build_state(conn, BuildState(request_id=request_id, step="b_done"), 1, T1)
        assert read_running_requests(conn) == []


def test_build_numbers_count_up_and_a_run_closes_once(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        assert next_build_number(conn, request_id) == 1
        insert_build_run(conn, make_run(request_id))
        assert next_build_number(conn, request_id) == 2
        assert count_open_builds(conn) == 1
        close_build_run(
            conn,
            request_id,
            1,
            ended_at=T1,
            rounds_used=2,
            result_status="READY_FOR_REVIEW",
            label="Ready with warnings",
            stop_reason="",
        )
        run = read_build_run(conn, request_id, 1)
        assert count_open_builds(conn) == 0
        with pytest.raises(sqlite3.DatabaseError, match="closed build"):
            close_build_run(
                conn, request_id, 1, ended_at=T1, rounds_used=3, result_status="x", label="x",
                stop_reason="",
            )

    assert (run.rounds_used, run.label, run.ended_at) == (2, "Ready with warnings", T1)


def test_closing_a_build_that_does_not_exist_is_refused(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        with pytest.raises(BuildError):
            close_build_run(
                conn, request_id, 9, ended_at=T1, rounds_used=0, result_status="", label="",
                stop_reason="",
            )


def test_the_latest_round_of_each_code_file_wins(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        insert_build_run(conn, make_run(request_id))
        insert_build_file(conn, make_file(request_id, text="old\n", round=1), T0)
        insert_build_file(conn, make_file(request_id, text="new\n", round=2), T1)
        insert_build_file(conn, make_file(request_id, path="src/agents/b.py", text="b\n"), T1)
        latest = read_latest_code(conn, request_id, 1)
        everything = read_build_files(conn, request_id, 1, "code")

    assert latest["src/agents/a.py"].text == "new\n"
    assert set(latest) == {"src/agents/a.py", "src/agents/b.py"}
    assert len(everything) == 3  # nothing was overwritten


def test_frozen_files_come_from_the_first_build_of_an_approach_version(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        insert_build_run(conn, make_run(request_id, 1, approach_version=1))
        insert_build_run(conn, make_run(request_id, 2, approach_version=1))
        insert_build_run(conn, make_run(request_id, 3, approach_version=2))
        insert_build_file(conn, make_file(request_id, "test", "t1\n", build=1, round=0), T0)
        insert_build_file(conn, make_file(request_id, "contract", "c1\n", build=1, round=0), T0)
        insert_build_file(conn, make_file(request_id, "test", "t2\n", build=3, round=0), T1)
        v1 = read_frozen_files(conn, request_id, 1)
        v2 = read_frozen_files(conn, request_id, 2)
        none = read_frozen_files(conn, request_id, 9)

    assert (v1["test"].text, v1["contract"].text) == ("t1\n", "c1\n")
    assert v2["test"].text == "t2\n" and "contract" not in v2
    assert none == {}


def test_a_round_keeps_both_layers_and_the_report(db_path, request_id):
    layer_a = LayerAResult(problems=[LayerAProblem(code="A5", path="src/a.py", text="eval")])
    layer_b = LayerBResult(
        timed_out=True,
        running_test="test_t1_ac1_x",
        tests=[TestOutcome(name="test_t1_ac1_x", result="fail", message="boom")],
    )
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        insert_round(
            conn,
            RoundRecord(
                request_id=request_id,
                build_number=1,
                round=1,
                layer_a=layer_a,
                layer_b=layer_b,
                failure_report="T-1 failed",
                timed_out=True,
            ),
            T0,
        )
        insert_round(
            conn,
            RoundRecord(request_id=request_id, build_number=1, round=2, layer_a=LayerAResult()),
            T1,
        )
        rounds = read_rounds(conn, request_id, 1)

    assert [r.round for r in rounds] == [1, 2]
    assert rounds[0].layer_a.problems[0].code == "A5"
    assert rounds[0].layer_b.running_test == "test_t1_ac1_x" and rounds[0].timed_out
    assert rounds[1].layer_b is None and not rounds[1].timed_out


def test_progress_shows_the_newest_row_of_each_line(db_path, request_id):
    def line(number, text, state):
        return ProgressLine(
            request_id=request_id, build_number=1, line_number=number, text=text, state=state
        )

    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        add_progress(conn, line(1, "Tester writes tests", "running"))
        add_progress(conn, line(2, "Writing a.py", "pending"))
        add_progress(conn, line(1, "Tester wrote 9 tests", "done"))
        shown = read_progress(conn, request_id, 1)

    assert [(p.line_number, p.state) for p in shown] == [(1, "done"), (2, "pending")]
    assert shown[0].text == "Tester wrote 9 tests"


def test_files_rounds_progress_and_runs_cannot_be_edited_or_deleted(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        insert_build_run(conn, make_run(request_id))
        insert_build_file(conn, make_file(request_id), T0)
        insert_round(
            conn,
            RoundRecord(request_id=request_id, build_number=1, round=1, layer_a=LayerAResult()),
            T0,
        )
        add_progress(
            conn,
            ProgressLine(
                request_id=request_id, build_number=1, line_number=1, text="x", state="done"
            ),
        )
        for table in ("da_build_files", "da_build_rounds", "da_build_progress"):
            with pytest.raises(sqlite3.DatabaseError, match="append-only"):
                conn.execute(f"UPDATE {table} SET request_id = request_id")
            with pytest.raises(sqlite3.DatabaseError, match="append-only"):
                conn.execute(f"DELETE FROM {table}")
        with pytest.raises(sqlite3.DatabaseError, match="cannot be deleted"):
            conn.execute("DELETE FROM da_build_runs")
