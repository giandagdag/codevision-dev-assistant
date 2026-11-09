"""Add a test case (Phase 8 step 9b-2): tests 8-33 and 8-34."""

import pytest

from agents import da_build_agent as build_agent
from agents import da_build_loop as loop
from agents import da_refine_bug as bug
from agents import da_refine_lanes as lanes
from agents import da_refine_owntest as own
from agents.da_refine_flow import start_check
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import read_build_state
from db_table_functions.db_tbl_da_refine import RefineError, read_refines, read_test_sets
from pydantic_classes.da_models import STATUS_REVISION
from tests.da_approach_play import events_of
from tests.da_build_play import RecordingFactory, chat, request_status, run_row
from tests.da_refine_play import rev, written_request
from tests.test_da_refine_bug import Reproducer

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def add(settings, request_id, text="Check the book file"):
    return own.add_test_case(
        settings, request_id, rev(settings, request_id), "AC-1", text, client=Reproducer()
    )


def build_rev(settings, request_id) -> int:
    with open_db(settings.db_path) as conn:
        return read_build_state(conn, request_id).revision


def test_8_33_a_test_that_passes_today_is_added_then_a_check_run_follows(settings, monkeypatch):
    request_id, _ = written_request(settings)
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"repro_passes_today"}))

    state = add(settings, request_id)

    assert state.step == own.STEP_OWN_CONFIRM and state.repro is not None
    assert "tag Yours" in chat(settings, request_id, "assistant")[-1]
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []  # nothing before his click

    state = own.confirm_own_test(settings, request_id, rev(settings, request_id))

    assert state.step == "start" and state.repro is None
    with open_db(settings.db_path) as conn:
        sets = read_test_sets(conn, request_id)
        assert len(sets) == 1 and len(sets[0].added_case_ids) == 1
        assert read_refines(conn, request_id) == []  # not a Refine, so not counted
    assert events_of(settings, request_id, "own_test_added")

    start_check(settings, request_id, build_rev(settings, request_id), after_new_test=True)
    assert run_row(settings, request_id, 2).kind == "check"
    assert loop.run_build(settings, request_id, RecordingFactory(), build_number=2) == "done"


def test_8_34_a_test_that_fails_today_offers_bug_or_drop(settings):
    request_id, _ = written_request(settings)

    state = add(settings, request_id)

    assert state.step == own.STEP_OWN_FAILS
    text = chat(settings, request_id, "assistant")[-1]
    assert own.FAILS_LINE in text and own.YES_FIX_LABEL in text and own.DROP_LABEL in text
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []


def test_yes_fix_it_starts_a_counted_bug_lane_with_the_test_as_repro(settings):
    request_id, _ = written_request(settings)
    add(settings, request_id)

    state = own.treat_as_bug(settings, request_id, rev(settings, request_id))

    assert state.step == "bug_rebuild" and state.refine_count == 1
    assert request_status(settings, request_id) == STATUS_REVISION
    with open_db(settings.db_path) as conn:
        assert len(read_test_sets(conn, request_id)) == 1
        assert read_refines(conn, request_id)[0].source == "added_test"
    bug.start_bug_fix(settings, request_id, rev(settings, request_id))
    assert loop.run_build(settings, request_id, RecordingFactory(), build_number=2) == "done"
    assert lanes.get_refine_state(settings, request_id).step == "start"


def test_drop_this_test_saves_nothing_and_counts_nothing(settings):
    request_id, _ = written_request(settings)
    add(settings, request_id)

    state = own.drop_own_test(settings, request_id, rev(settings, request_id))

    assert state.step == "start" and state.repro is None and state.refine_count == 0
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []
    assert events_of(settings, request_id, "own_test_dropped")


def test_an_unknown_criterion_and_a_wrong_step_are_refused(settings):
    request_id, _ = written_request(settings)

    with pytest.raises(RefineError):
        own.add_test_case(
            settings, request_id, rev(settings, request_id), "AC-99", "Check it", Reproducer()
        )
    with pytest.raises(RefineError):
        own.confirm_own_test(settings, request_id, rev(settings, request_id))
