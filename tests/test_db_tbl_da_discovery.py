import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest

from db_table_functions.da_db import open_db, to_db_time
from db_table_functions.db_tbl_da_discovery import (
    DiscoveryError,
    bump_discovery_revision,
    count_rounds,
    ensure_discovery_tables,
    get_results,
    insert_result,
    read_discovery_revision,
    read_latest_result,
)
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_discovery_models import DiscoveryResult, Finding, SearchHit

T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 25, 9, 5, tzinfo=UTC)


@pytest.fixture
def request_id(db_path, published_rulebook):
    return create_request(db_path, "New change request", "dev-0001", now=T0).request_id


def make_result(request_id, round_number=1, **changes):
    values = {
        "request_id": request_id,
        "round": round_number,
        "record_version": 1,
        "rulebook_version": 1,
        "search_provider": "fake",
        "queries": ["exact: pdf"],
        "hits": [
            SearchHit(
                hit_id=1, source_path="a.py", symbol="f", kind="code", score=0.5, mode="exact"
            )
        ],
        "findings": [
            Finding(
                kind="existing_capability",
                title="T",
                explanation="E",
                hit_ids=[1],
                confidence="high",
            )
        ],
        "limitations": ["L"],
        "summary_source": "ai",
        "model": "m",
        "hint": "",
    }
    return DiscoveryResult(**(values | changes))


def save(db_path, result, now=T1):
    with open_db(db_path) as conn:
        ensure_discovery_tables(conn)
        insert_result(conn, result, now)


def raw_sql(db_path, statement):
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(statement)
        conn.commit()


def test_a_round_is_saved_and_read_back_whole(db_path, request_id):
    result = make_result(request_id, hint="batching")

    save(db_path, result)

    loaded = get_results(db_path, request_id)
    assert len(loaded) == 1
    assert loaded[0].model_dump(exclude={"created_at"}) == result.model_dump(exclude={"created_at"})
    assert loaded[0].hits[0].source_path == "a.py"


def test_created_time_is_stored_the_same_way_as_every_other_time(db_path, request_id):
    save(db_path, make_result(request_id), now=T1)

    with open_db(db_path) as conn:
        stored = conn.execute("SELECT created_at FROM da_discovery_results").fetchone()[0]
        latest = read_latest_result(conn, request_id)

    assert stored == to_db_time(T1)
    # Stored as UTC like all times; the screen shows it in Singapore time (13:05 here).
    assert latest.created_at == T1


def test_rounds_come_back_in_order_and_are_counted(db_path, request_id):
    save(db_path, make_result(request_id, 2))
    save(db_path, make_result(request_id, 1))

    with open_db(db_path) as conn:
        assert count_rounds(conn, request_id) == 2
        assert read_latest_result(conn, request_id).round == 2
    assert [r.round for r in get_results(db_path, request_id)] == [1, 2]


def test_no_rounds_gives_none_and_zero(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_discovery_tables(conn)
        assert read_latest_result(conn, request_id) is None
        assert count_rounds(conn, request_id) == 0


def test_the_same_round_cannot_be_saved_twice(db_path, request_id):
    save(db_path, make_result(request_id))

    with pytest.raises(DiscoveryError, match="Round 1.*already saved"):
        save(db_path, make_result(request_id))
    assert len(get_results(db_path, request_id)) == 1


def test_results_cannot_be_updated_or_deleted_even_with_raw_sql(db_path, request_id):
    save(db_path, make_result(request_id))

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        raw_sql(db_path, "UPDATE da_discovery_results SET hint = 'x'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        raw_sql(db_path, "DELETE FROM da_discovery_results")
    assert len(get_results(db_path, request_id)) == 1


def test_a_result_needs_a_real_request(db_path, request_id):
    with pytest.raises(sqlite3.IntegrityError):
        save(db_path, make_result("CVDA-2026-9999"))


def test_revision_starts_at_zero_and_goes_up_by_one(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_discovery_tables(conn)
        assert read_discovery_revision(conn, request_id) == 0
        assert bump_discovery_revision(conn, request_id, 0, T1) == 1
        assert bump_discovery_revision(conn, request_id, 1, T1) == 2
        assert read_discovery_revision(conn, request_id) == 2


def test_a_bump_from_an_old_revision_is_refused(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_discovery_tables(conn)
        bump_discovery_revision(conn, request_id, 0, T1)
        bump_discovery_revision(conn, request_id, 1, T1)

        with pytest.raises(StaleRevisionError):
            bump_discovery_revision(conn, request_id, 1, T1)


def test_first_bump_from_zero_is_refused_when_a_row_already_exists(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_discovery_tables(conn)
        bump_discovery_revision(conn, request_id, 0, T1)

        with pytest.raises(StaleRevisionError):
            bump_discovery_revision(conn, request_id, 0, T1)


def test_bump_for_a_revision_that_was_never_started_is_refused(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_discovery_tables(conn)

        with pytest.raises(StaleRevisionError):
            bump_discovery_revision(conn, request_id, 3, T1)


def test_index_build_is_stored_and_old_rows_read_as_not_recorded(db_path, request_id):
    # G-21: a new round keeps the build; a database from before the column reads None.
    save(db_path, make_result(request_id, 1, index_build=4))
    assert get_results(db_path, request_id)[0].index_build == 4
    raw_sql(db_path, "ALTER TABLE da_discovery_results DROP COLUMN index_build")
    with open_db(db_path) as conn:
        ensure_discovery_tables(conn)  # adds the column back, old rows get NULL
    assert get_results(db_path, request_id)[0].index_build is None
