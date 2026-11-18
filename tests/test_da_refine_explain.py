import pytest

from agents import da_refine_explain as helpers
from agents import da_refine_lanes as lanes
from agents.da_refine_actions import (
    DECIDE_KEY,
    EXPLAIN_KEY,
    SUGGESTED_TAG,
    get_refine_bar,
)
from agents.da_refine_agent import SCRIPTED_EXPLAIN
from db_table_functions.db_tbl_da_refine import RefineError
from pydantic_classes.da_models import STATUS_READY_FOR_REVIEW
from tests.da_approach_play import events_of
from tests.da_build_play import chat, request_status
from tests.da_refine_play import lane_reply, rev, written_request
from tests.da_stub_client import FailingClient, StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def at_choice(settings):
    """A request at the lane choice, with the first suggestion made."""
    request_id, _ = written_request(settings)
    first = StubClient(lane_reply("requirement", "The request itself must change."))
    lanes.suggest(settings, request_id, "Reject files over 5 MB", rev(settings, request_id), first)
    return request_id


def test_b2_3_explain_simply_prints_the_words_and_changes_nothing_else(settings, at_choice):
    before = lanes.get_refine_state(settings, at_choice)
    client = StubClient(" ".join(["word"] * 200))  # too long: plain code cuts it to 120 words

    state = helpers.explain_simply(settings, at_choice, before.revision, client)

    assert len(chat(settings, at_choice, "assistant")[-1].split()) == 120
    assert state.step == "lane_choice" and state.suggested_lane == before.suggested_lane
    assert request_status(settings, at_choice) == STATUS_READY_FOR_REVIEW
    assert events_of(settings, at_choice, "explain_simple")
    assert "Reject files over 5 MB" in client.prompts[0]


def test_the_fake_provider_explains_the_three_choices(settings, at_choice):
    helpers.explain_simply(settings, at_choice, rev(settings, at_choice))

    assert chat(settings, at_choice, "assistant")[-1] == SCRIPTED_EXPLAIN


def test_b2_4_help_me_decide_tags_one_button_and_starts_no_lane(settings, at_choice):
    reply = lane_reply("approach", "Only the design must change.")
    state = helpers.help_decide(settings, at_choice, rev(settings, at_choice), StubClient(reply))

    assert state.step == "lane_choice" and state.suggested_lane == "approach"
    assert request_status(settings, at_choice) == STATUS_READY_FOR_REVIEW
    assert "Only the design must change." in chat(settings, at_choice, "assistant")[-1]
    assert events_of(settings, at_choice, "lane_decide_help")
    buttons = dict(get_refine_bar(settings, at_choice).buttons)
    assert buttons["lane_approach"] == lanes.LANE_LABELS["approach"] + SUGGESTED_TAG
    assert buttons["lane_requirement"] == lanes.LANE_LABELS["requirement"]
    assert EXPLAIN_KEY in buttons and DECIDE_KEY in buttons


@pytest.mark.parametrize("action", [helpers.explain_simply, helpers.help_decide])
def test_a_failed_ai_call_says_so_and_changes_nothing(settings, at_choice, action):
    before = lanes.get_refine_state(settings, at_choice)
    chat_before = chat(settings, at_choice, "assistant")

    with pytest.raises(RefineError, match="Nothing was changed"):
        action(settings, at_choice, before.revision, FailingClient())

    assert lanes.get_refine_state(settings, at_choice) == before
    assert chat(settings, at_choice, "assistant") == chat_before


def test_the_buttons_need_the_lane_choice_on_screen(settings):
    request_id, _ = written_request(settings)

    with pytest.raises(RefineError, match="press Refine first"):
        helpers.explain_simply(settings, request_id, rev(settings, request_id), StubClient("x"))
