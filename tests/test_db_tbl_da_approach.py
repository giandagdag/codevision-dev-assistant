import sqlite3
from datetime import UTC, datetime

import pytest

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import (
    ApproachError,
    confirmed_discovery_round,
    ensure_approach_tables,
    first_call_failed,
    highest_test_number,
    insert_approach_version,
    insert_test_plan,
    read_approach_revision,
    read_approach_state,
    read_approach_versions,
    read_latest_approach,
    read_latest_plan,
    save_approach_state,
)
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_approach_models import (
    ApproachDecision,
    ApproachReply,
    ApproachState,
    ApproachVersion,
    TestCase,
    TestPlanVersion,
)

T0 = datetime(2026, 10, 31, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 31, 9, 5, tzinfo=UTC)


@pytest.fixture
def request_id(db_path, published_rulebook):
    return create_request(db_path, "New change request", "dev-0001", now=T0).request_id


def make_version(request_id, number=1, **changes):
    values = {
        "request_id": request_id,
        "approach_version": number,
        "source": "proposal",
        "record_version": 1,
        "rulebook_version": 1,
        "discovery_round": 1,
        "plan": ApproachReply(summary="Add Excel"),
        "decisions": [
            ApproachDecision(question="Q", choice="A", custom=False, decided_at=T0)
        ],
        "warnings": ["w"],
        "zones_touched": ["Login"],
        "model": "m",
    }
    values.update(changes)
    return ApproachVersion(**values)


def make_plan(request_id, number=1, ids=("T-1",), approach=1):
    cases = [
        TestCase(test_id=i, criterion_id="AC-1", given="g", expect="e", source="tester")
        for i in ids
    ]
    return TestPlanVersion(
        request_id=request_id,
        plan_version=number,
        approach_version=approach,
        cases=cases,
        source_of_change="tester_plan",
    )


def test_versions_round_trip_and_the_old_one_is_kept(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_approach_tables(conn)
        insert_approach_version(conn, make_version(request_id, 1), T0)
        insert_approach_version(conn, make_version(request_id, 2, source="settled"), T1)
        versions = read_approach_versions(conn, request_id)
        latest = read_latest_approach(conn, request_id)

    assert [v.approach_version for v in versions] == [1, 2]
    assert latest.source == "settled" and latest.plan.summary == "Add Excel"
    assert latest.decisions[0].choice == "A" and latest.zones_touched == ["Login"]


def test_the_same_version_cannot_be_saved_twice(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_approach_tables(conn)
        insert_approach_version(conn, make_version(request_id), T0)
        with pytest.raises(ApproachError, match="already saved"):
            insert_approach_version(conn, make_version(request_id), T1)


def test_versions_and_plans_are_append_only(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_approach_tables(conn)
        insert_approach_version(conn, make_version(request_id), T0)
        insert_test_plan(conn, make_plan(request_id), T0)
        for sql in (
            "UPDATE da_approach_versions SET model = 'x'",
            "DELETE FROM da_approach_versions",
            "UPDATE da_test_plans SET model = 'x'",
            "DELETE FROM da_test_plans",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                conn.execute(sql)


def test_test_plans_round_trip_and_numbers_are_never_reused(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_approach_tables(conn)
        insert_test_plan(conn, make_plan(request_id, 1, ("T-1", "T-2", "T-3")), T0)
        insert_test_plan(conn, make_plan(request_id, 2, ("T-3", "T-4")), T1)
        latest = read_latest_plan(conn, request_id)
        highest = highest_test_number(conn, request_id)

    assert latest.plan_version == 2 and [c.test_id for c in latest.cases] == ["T-3", "T-4"]
    assert highest == 4


def test_state_first_save_then_revision_goes_up_by_one(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_approach_tables(conn)
        assert read_approach_revision(conn, request_id) == 0
        assert read_approach_state(conn, request_id) is None
        saved = save_approach_state(conn, ApproachState(request_id=request_id), 0, T0)
        saved = save_approach_state(conn, saved.model_copy(update={"step": "tests"}), 1, T1)
        stored = read_approach_state(conn, request_id)

    assert (saved.revision, stored.revision, stored.step) == (2, 2, "tests")


def test_a_save_from_an_old_window_is_refused(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_approach_tables(conn)
        state = ApproachState(request_id=request_id)
        save_approach_state(conn, state, 0, T0)
        save_approach_state(conn, state, 1, T1)
        with pytest.raises(StaleRevisionError):
            save_approach_state(conn, state, 1, T1)
        with pytest.raises(StaleRevisionError):
            save_approach_state(conn, state, 0, T1)


def test_audit_readers(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_approach_tables(conn)
        ensure_audit_table(conn)
        assert not first_call_failed(conn, request_id)
        assert confirmed_discovery_round(conn, request_id) == 0
        insert_audit_event(conn, request_id, "developer", "discovery_confirmed", {"round": 2}, T0)
        insert_audit_event(conn, request_id, "system", "approach_failed", {}, T0)
        assert first_call_failed(conn, request_id)
        insert_audit_event(conn, request_id, "llm", "approach_proposed", {}, T1)
        assert not first_call_failed(conn, request_id)
        assert confirmed_discovery_round(conn, request_id) == 2
