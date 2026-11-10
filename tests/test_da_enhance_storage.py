"""Enhance's tables: save, read back, append-only, Unassigned queue, old databases (step 7)."""

import sqlite3
from datetime import UTC, datetime

import pytest

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_discovery import (
    ensure_discovery_tables,
    insert_result,
    read_latest_result,
)
from db_table_functions.db_tbl_da_enhance import (
    EnhanceError,
    add_unassigned,
    insert_candidates,
    insert_freshness_check,
    insert_safety_net,
    list_unassigned,
    next_net_version,
    read_accepted_net,
    read_candidates,
    read_enhance_revision,
    read_enhance_state,
    read_latest_freshness,
    read_latest_safety_net,
    resolve_unassigned,
    save_enhance_state,
)
from db_table_functions.db_tbl_da_refine import insert_test_set, read_test_sets
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_discovery_models import DiscoveryResult
from pydantic_classes.da_enhance_models import (
    Candidate,
    EnhanceState,
    FreshnessResult,
    ImpactResult,
    ImpactRow,
    PathFreshness,
    SafetyCase,
    SafetyNet,
    SafetyNetRow,
)
from pydantic_classes.da_refine_models import TestSet
from tests.da_build_play import ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def _net() -> SafetyNet:
    case = SafetyCase(id="S-1", today_behaviour="Returns the date.", function="expiry_date")
    return SafetyNet(cases=[case], test_code="def test_s1_date():\n    assert True\n")


def test_the_enhance_state_has_its_own_revision_and_refuses_a_stale_save(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        assert read_enhance_revision(conn, request_id) == 0
        saved = save_enhance_state(conn, EnhanceState(request_id=request_id), 0, NOW)
        again = save_enhance_state(conn, saved.model_copy(update={"step": "e_pick"}), 1, NOW)

        assert (saved.revision, again.revision) == (1, 2)
        assert read_enhance_state(conn, request_id).step == "e_pick"
        assert read_enhance_state(conn, request_id).revision == 2
        with pytest.raises(StaleRevisionError):
            save_enhance_state(conn, again, 1, NOW)
        with pytest.raises(StaleRevisionError):
            save_enhance_state(conn, again, 0, NOW)  # first-save twice


def test_candidates_are_append_only_and_a_round_is_saved_once(settings, request_id):
    found = [Candidate(path="reports/limits_expiry_report.py", how_found="name", best_match=True)]
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        insert_candidates(conn, request_id, 1, found, NOW)
        insert_candidates(conn, request_id, 2, [], NOW)

        assert [len(item) for item in read_candidates(conn, request_id)] == [1, 0]
        with pytest.raises(EnhanceError):
            insert_candidates(conn, request_id, 1, found, NOW)
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE da_enhance_candidates SET candidates = '[]'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM da_enhance_candidates")


def test_freshness_checks_are_numbered_and_the_latest_wins(settings, request_id):
    differs = FreshnessResult(paths=[PathFreshness(path="a.py", state="differs")])
    overridden = differs.model_copy(update={"override": "intentional"})
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        first = insert_freshness_check(conn, request_id, 1, differs, NOW)
        second = insert_freshness_check(conn, request_id, 1, overridden, NOW)

        assert (first.check_number, second.check_number) == (1, 2)
        assert read_latest_freshness(conn, request_id).result.override == "intentional"
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM da_freshness_checks")


def test_safety_nets_are_append_only_and_the_latest_accepted_row_is_in_force(
    settings, request_id
):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        assert next_net_version(conn, request_id) == 1
        first = SafetyNetRow(request_id=request_id, net_version=1, record_version=1, net=_net())
        insert_safety_net(conn, first, NOW)
        assert read_accepted_net(conn, request_id, 1) is None

        accepted = first.model_copy(update={"net_version": 2, "accepted": True})
        insert_safety_net(conn, accepted, NOW)

        assert read_latest_safety_net(conn, request_id).net_version == 2
        assert read_accepted_net(conn, request_id, 1).net.cases[0].id == "S-1"
        assert read_accepted_net(conn, request_id, 2) is None  # another record version
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE da_safety_nets SET accepted = 0")


def test_9_9_one_open_unassigned_row_per_path_and_it_is_updated_only_to_resolve(
    settings, request_id
):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        first = add_unassigned(conn, "util/odd.py", "Limits", request_id, NOW)
        again = add_unassigned(conn, "util/odd.py", "Reports", request_id, NOW)

        assert again.unassigned_id == first.unassigned_id
        assert again.picked_capability == "Limits"  # the first pick stays
        assert len(list_unassigned(conn)) == 1

        resolve_unassigned(conn, first.unassigned_id, "confirmed", "Admin", NOW)
        assert list_unassigned(conn) == []
        assert list_unassigned(conn, "confirmed")[0].resolved_by == "Admin"
        with pytest.raises(EnhanceError):
            resolve_unassigned(conn, first.unassigned_id, "changed", "Admin", NOW)
        with pytest.raises(sqlite3.DatabaseError, match="cannot be edited"):
            conn.execute("UPDATE da_unassigned_files SET picked_capability = 'X'")
        with pytest.raises(sqlite3.DatabaseError, match="cannot be deleted"):
            conn.execute("DELETE FROM da_unassigned_files")

        # Once resolved, a new request on the same path opens a new row.
        assert add_unassigned(conn, "util/odd.py", "Reports", request_id, NOW).state == "open"


def test_the_impact_is_saved_with_a_discovery_round_and_an_old_database_gets_the_column(
    settings, request_id
):
    row = ImpactRow(
        caller_path="reports/a.py",
        caller_function="run",
        line=4,
        function_in_scope="expiry_date",
        kind="direct",
    )
    base = DiscoveryResult(
        request_id=request_id,
        round=9,  # the ready request already holds round 1
        record_version=1,
        rulebook_version=1,
        search_provider="fake",
        queries=[],
        hits=[],
        findings=[],
        limitations=[],
        summary_source="fallback",
    )
    with open_db(settings.db_path) as conn:
        ensure_discovery_tables(conn)
        insert_result(conn, base.model_copy(update={"impact": ImpactResult(rows=[row])}), NOW)
        latest = read_latest_result(conn, request_id)
        assert latest.round == 9
        assert latest.impact.rows[0].caller_function == "run"

    # An old database: the column is dropped, then ensure adds it back. Old rows read as none.
    with open_db(settings.db_path) as conn:
        conn.execute("DROP TRIGGER da_discovery_results_no_update")
        conn.execute("ALTER TABLE da_discovery_results DROP COLUMN impact")
        ensure_discovery_tables(conn)
        assert read_latest_result(conn, request_id).impact is None


def test_a_test_set_keeps_its_net_marks_and_an_old_database_gets_the_columns(
    settings, request_id
):
    item = TestSet(
        request_id=request_id,
        test_set_version=1,
        approach_version=1,
        text="x",
        fingerprint="f",
        net_methods=["test_s1_date"],
        expected_to_change_methods=["test_s1_date"],
    )
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        insert_test_set(conn, item, NOW)
        assert read_test_sets(conn, request_id)[0].expected_to_change_methods == ["test_s1_date"]

    with open_db(settings.db_path) as conn:
        conn.execute("ALTER TABLE da_test_sets DROP COLUMN net_methods")
        conn.execute("ALTER TABLE da_test_sets DROP COLUMN expected_to_change_methods")
        ensure_build_tables(conn)
        assert read_test_sets(conn, request_id)[0].net_methods == []


def test_9_46_a_stale_enhance_state_is_refused_with_the_stale_message(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        first = save_enhance_state(conn, EnhanceState(request_id=request_id), 0, NOW)
        save_enhance_state(conn, first, 1, NOW)
        with pytest.raises(StaleRevisionError, match="another window"):
            save_enhance_state(conn, first, 1, NOW)
