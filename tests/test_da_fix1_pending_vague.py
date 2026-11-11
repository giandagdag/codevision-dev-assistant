"""Phase 8 fix 1 step 4: the pending test row (F1, FX-3) and a VAGUE own-test reply (F1b, FX-4)."""

import pytest

from agents import da_build_agent as build_agent
from agents import da_refine_agent as agent
from agents import da_refine_lanes as lanes
from agents import da_refine_owntest as own
from agents import da_refine_screen as screen
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_refine import read_test_sets
from layouts import da_build_panel as bp
from pydantic_classes.da_build_models import BuildState, BuildView, TestRow
from tests.da_approach_play import events_of
from tests.da_build_play import chat
from tests.da_refine_play import rev, written_request
from tests.da_tree import all_text
from tests.test_da_refine_bug import Reproducer
from tests.test_da_refine_owntest import add

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def _view(tests):
    return BuildView(
        state=BuildState(request_id="CVDA-2026-0001"), revision=1, request_status="X", tests=tests
    )


def _tests_text(settings, request_id) -> str:
    base = _view([TestRow(test_id="T-1", criterion_id="AC-1", description="old", result="pass")])
    tagged = screen.get_tagged_build(settings, request_id, base, None)
    return all_text(bp.tests_tab(tagged))


def test_fx3_a_test_that_fails_today_is_the_last_row_until_he_chooses(settings):
    request_id, _ = written_request(settings)
    add(settings, request_id)

    text = _tests_text(settings, request_id)

    assert "Fails today, waiting for your choice" in text
    assert text.index("T-1") < text.index("(Yours)")

    own.drop_own_test(settings, request_id, rev(settings, request_id))
    assert "waiting for your choice" not in _tests_text(settings, request_id)


def test_fx3_yes_fix_it_makes_it_a_normal_row(settings):
    request_id, _ = written_request(settings)
    add(settings, request_id)

    own.treat_as_bug(settings, request_id, rev(settings, request_id))

    text = _tests_text(settings, request_id)
    assert "waiting for your choice" not in text
    assert "(Bug)" in text  # the bug lane's repro test, as for any repro row


def test_fx3_a_test_that_passes_today_says_so(settings, monkeypatch):
    request_id, _ = written_request(settings)
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"repro_passes_today"}))
    add(settings, request_id)

    assert "Passes today, waiting for your choice" in _tests_text(settings, request_id)


def test_fx4_vague_asks_a_question_and_uses_no_case_id(settings, monkeypatch):
    request_id, _ = written_request(settings)
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"vague"}))

    vague_client = Reproducer()
    state = own.add_test_case(
        settings, request_id, rev(settings, request_id), "AC-1", "Make it work", vague_client
    )

    assert state.step == "start" and state.repro is None
    said = chat(settings, request_id, "assistant")[-1]
    assert said.startswith("Describe the case more: ")
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []
    assert events_of(settings, request_id, "own_test_vague")
    assert not events_of(settings, request_id, "own_test_written")
    assert lanes.get_refine_state(settings, request_id).refine_count == 0

    # The same case id is offered again on the next, clear try.
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset())
    client = Reproducer()
    own.add_test_case(settings, request_id, rev(settings, request_id), "AC-1", "Check", client)
    assert agent._CASE_ID.findall(client.prompts[-1]) == agent._CASE_ID.findall(
        vague_client.prompts[-1]
    )


def test_fx4_the_question_is_cut_at_200_characters():
    reply = "VAGUE\n" + "x" * 500

    assert len(agent.parse_vague_reply(reply)) == 200
    assert agent.parse_vague_reply("CASE\ncriterion: AC-1") == ""
