"""Fix batch B1 step 6 (F6): his own test disagrees with a criterion (B1-7). Nothing is stored and
no case ID is used until he picks; the Tester never rewrites his test silently."""

import pytest

from agents import da_build_agent as build_agent
from agents import da_refine_actions as actions
from agents import da_refine_agent as agent
from agents import da_refine_lanes as lanes
from agents import da_refine_owntest as own
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_refine import read_refines, read_test_sets
from tests.da_approach_play import events_of
from tests.da_build_play import chat
from tests.da_refine_play import rev, written_request
from tests.test_da_refine_bug import Reproducer

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def conflicting(monkeypatch):
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"conflict"}))


def _add(settings, request_id, client=None):
    return own.add_test_case(
        settings, request_id, rev(settings, request_id), "AC-1", "Check the book file",
        client or Reproducer(),
    )


def test_b1_7_a_conflict_names_the_criterion_and_stores_nothing(settings, conflicting):
    request_id, _ = written_request(settings)

    state = _add(settings, request_id)

    assert state.step == own.STEP_OWN_CONFLICT and state.repro is None
    said = chat(settings, request_id, "assistant")[-1]
    assert said.startswith("Your test expects Check the book file, but AC-1 says ")
    assert said.endswith("Change the requirement, or change your test.")
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []
        assert read_refines(conn, request_id) == []
    assert events_of(settings, request_id, "own_test_conflict")
    assert not events_of(settings, request_id, "own_test_written")
    bar = actions.get_refine_bar(settings, request_id)
    assert [label for _, label in bar.buttons] == [own.CHANGE_REQ_LABEL, own.CHANGE_TEST_LABEL]


def test_b1_7_change_what_it_does_opens_the_requirement_lane_with_his_text(settings, conflicting):
    request_id, _ = written_request(settings)
    _add(settings, request_id)

    own.change_what_it_does(settings, request_id, rev(settings, request_id))
    state = lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))

    assert state.step == lanes.STEP_REQ_REVISE
    assert state.pending_feedback == "Check the book file"
    assert state.chosen_lane == "requirement"


def test_b1_7_change_my_test_asks_again_and_may_not_conflict(settings, conflicting):
    request_id, _ = written_request(settings)
    _add(settings, request_id)
    client = Reproducer()

    state = own.change_my_test(settings, request_id, rev(settings, request_id), client)

    assert state.step in (own.STEP_OWN_CONFIRM, own.STEP_OWN_FAILS)
    assert agent.NO_CONFLICT_RULE in client.prompts[-1]
    assert agent.CONFLICT_RULE not in client.prompts[-1]


def test_the_conflict_reply_is_read_only_in_its_own_format():
    assert agent.parse_conflict_reply("CONFLICT AC-2: it differs") == ("AC-2", "it differs")
    assert agent.parse_conflict_reply("CASE\ncriterion: AC-1") is None
