import pytest

from agents import da_ai_lock
from agents import da_refine_describe as describe
from agents import da_refine_lanes as lanes
from agents.da_refine_agent import SCRIPTED_DESCRIBE
from agents.da_refine_screen import RefineBox
from callbacks.screen_callbacks.da_refine_callbacks import handle_describe
from db_table_functions.db_tbl_da_refine import RefineError
from layouts.da_developer_assistant_page import DESCRIBE_TYPE, _approach_composer
from layouts.da_lock_buttons import lock_buttons
from tests.da_build_play import chat
from tests.da_refine_play import lane_reply, rev, written_request
from tests.da_stub_client import FailingClient, StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def at_bug(settings):
    """A request at the bug step: the lane is chosen, nothing is written yet."""
    request_id, _ = written_request(settings)
    first = StubClient(lane_reply("bug", "A criterion does not hold.", "AC-1"))
    lanes.suggest(settings, request_id, "It crashes on csv", rev(settings, request_id), first)
    lanes.choose_lane(settings, request_id, "bug", rev(settings, request_id))
    return request_id


def test_b2_5_the_draft_comes_back_for_the_box_and_nothing_is_saved(settings, at_bug):
    before = lanes.get_refine_state(settings, at_bug)
    chat_before = chat(settings, at_bug, "assistant")
    client = StubClient(" ".join(["word"] * 200))  # too long: plain code cuts it to 120 words

    draft = describe.describe_for_box(settings, at_bug, before.revision, client)

    assert len(draft.split()) == 120
    assert "It crashes on csv" in client.prompts[0]  # the last chat lines are read
    assert lanes.get_refine_state(settings, at_bug) == before  # never sent
    assert chat(settings, at_bug, "assistant") == chat_before


def test_the_fake_provider_writes_a_draft(settings, at_bug):
    assert describe.describe_for_box(settings, at_bug, rev(settings, at_bug)) == SCRIPTED_DESCRIBE


def test_a_failed_call_says_so_and_changes_nothing(settings, at_bug):
    before = lanes.get_refine_state(settings, at_bug)

    with pytest.raises(RefineError, match="not changed"):
        describe.describe_for_box(settings, at_bug, before.revision, FailingClient())

    assert lanes.get_refine_state(settings, at_bug) == before


def test_the_button_needs_the_bug_step(settings):
    request_id, _ = written_request(settings)

    with pytest.raises(RefineError, match="not possible at this step"):
        describe.describe_for_box(settings, request_id, rev(settings, request_id), StubClient("x"))


def test_the_callback_returns_the_draft_and_is_refused_while_the_ai_is_busy(settings, at_bug):
    state = {"request_id": at_bug, "refine": True, "refine_revision": rev(settings, at_bug)}

    assert handle_describe(settings, True, state) == (SCRIPTED_DESCRIBE, "")
    with da_ai_lock.ai_turn(at_bug):
        value, message = handle_describe(settings, True, state)
    assert message == da_ai_lock.BUSY_MESSAGE


def test_the_button_sits_above_the_bug_box_only_at_the_bug_step_and_locks_while_busy():
    bug = _approach_composer(None, refine=RefineBox(offered=True, step="bug_start", text_open=True))
    other = _approach_composer(None, refine=RefineBox(offered=True, step="x", text_open=True))

    first = bug.children[0]
    assert first.id["type"] == DESCRIBE_TYPE and first.children == describe.DESCRIBE_LABEL
    assert "describe_bug" not in str(other)
    lock_buttons(bug)
    assert first.disabled is True
