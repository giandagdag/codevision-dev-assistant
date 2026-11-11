"""Phase 8 fix 1 step 6: the draft before Confirm (F2, FX-5, FX-6) and the tab mapping (F3)."""

import pytest

from agents import da_refine_lanes as lanes
from agents import da_refine_screen as screen
from agents.da_refine_actions import get_refine_bar
from layouts import da_developer_assistant_page as page
from layouts import da_refine_panels as rp
from tests.da_build_play import chat
from tests.da_refine_play import lane_reply, records_of, rev, written_request
from tests.da_stub_client import StubClient
from tests.da_tree import all_text, by_id

pytestmark = pytest.mark.usefixtures("published_rulebook")

ADD_ONE = {
    "criteria_ops": [
        {
            "op": "add",
            "kind": "failure",
            "given": "a file over 5 MB",
            "when": "it is uploaded",
            "then": "a message says it is too big",
        }
    ],
    "field_updates": {},
}
CHANGE_AND_REMOVE = {
    "criteria_ops": [
        {"op": "change", "id": "AC-2", "then": "a clearer message is shown"},
        {"op": "remove", "id": "AC-1"},
    ],
    "field_updates": {},
}


@pytest.fixture
def settings(make_settings):
    return make_settings()


def at_checkpoint(settings, reply):
    request_id, _ = written_request(settings)
    lanes.suggest(
        settings, request_id, "Reject big files", rev(settings, request_id),
        StubClient(lane_reply("requirement")),
    )
    lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))
    state = lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(reply))
    assert state.step == "req_checkpoint"
    return request_id


def test_fx5_an_added_criterion_shows_in_the_chat_and_on_the_summary_tab(settings):
    request_id = at_checkpoint(settings, ADD_ONE)
    old = records_of(settings, request_id)[-1]
    new_id = f"AC-{len(old.acceptance_criteria) + 1}"

    said = chat(settings, request_id, "assistant")[-1]
    assert f"{new_id} is added: Given a file over 5 MB, when it is uploaded, then a message" in said

    history = screen.get_history(settings, request_id)
    tree = rp.version_history_blocks(history)
    text = all_text(by_id(tree, rp.DRAFT_ID))
    assert f"Draft version {old.version + 1}" in text
    assert new_id in text and f"New in v{old.version + 1} (not saved yet)" in text
    assert "a file over 5 MB" in text


def test_fx6_a_changed_criterion_shows_old_and_new_and_a_removed_one_is_struck(settings):
    request_id = at_checkpoint(settings, CHANGE_AND_REMOVE)
    old = records_of(settings, request_id)[-1]

    said = chat(settings, request_id, "assistant")[-1]
    assert "AC-2 changes." in said and "Before: Given" in said and "After: Given" in said
    assert "a clearer message is shown" in said
    assert "AC-1 is removed. It was: Given" in said

    tree = rp.version_history_blocks(screen.get_history(settings, request_id))
    text = all_text(by_id(tree, rp.DRAFT_ID))
    assert "Changed" in text and "Removed" in text
    draft = screen.get_history(settings, request_id).draft
    removed = [row for row in draft if row.tag == "removed"]
    assert [row.criterion_id for row in removed] == ["AC-1"]
    assert removed[0].text.startswith("Given")
    unchanged = [r for r in draft if not r.tag]
    assert len(unchanged) == len(old.acceptance_criteria) - 2


def test_no_draft_once_the_checkpoint_is_left(settings):
    request_id = at_checkpoint(settings, ADD_ONE)

    lanes.cancel(settings, request_id, rev(settings, request_id))

    assert screen.get_history(settings, request_id).draft == []


def test_f3_the_checkpoint_opens_the_summary_tab_and_other_steps_keep_the_old_default(settings):
    request_id = at_checkpoint(settings, ADD_ONE)

    bar = get_refine_bar(settings, request_id)

    assert bar.step == "req_checkpoint"
    assert page.refine_step_tab(bar) == "summary"
    assert page.refine_step_tab(None) is None
    assert page.refine_step_tab(type(bar)()) is None  # no Refine step: Build tab as before
    assert page.REFINE_STEP_TABS["req_findings"] == "discovery"
    assert page.REFINE_STEP_TABS["req_approach"] == "approach"
