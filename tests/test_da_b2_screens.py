"""Fix batch B2 (screens and flow): lane words, Cancel look, and later steps.

B2-1 and B2-2 are step 1."""

import pytest

from agents import da_refine_lanes as lanes
from agents.da_refine_screen import RefineBox
from layouts import da_developer_assistant_page as page
from tests.da_approach_play import events_of
from tests.da_refine_play import lane_reply, rev, written_request
from tests.da_stub_client import StubClient
from tests.da_tree import components

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def _lane_box() -> RefineBox:
    buttons = [(f"lane_{lane}", label) for lane, label in lanes.LANE_LABELS.items()]
    return RefineBox(
        offered=True, lane=True, buttons=[*buttons, ("cancel", lanes.CANCEL_LABEL)],
    )


def test_b2_1_lane_words_are_the_new_ones_and_keys_are_unchanged():
    assert list(lanes.LANE_LABELS) == ["requirement", "approach", "bug"]
    assert list(lanes.LANE_LABELS.values()) == [
        "Change what it does",
        "Change how it's built",
        "It's not working as agreed",
    ]
    shown = [button.children for button in components(page.refine_buttons(_lane_box()), "Button")]
    assert shown[:3] == list(lanes.LANE_LABELS.values())


def test_b2_1_chat_and_audit_use_the_same_words(settings):
    request_id, _ = written_request(settings)
    lanes.suggest(
        settings, request_id, "Change it", rev(settings, request_id),
        StubClient(lane_reply("requirement")),
    )
    lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))
    started = events_of(settings, request_id, "refine_started")[0].details
    assert started["chosen"] == "requirement"
    assert started["chosen_words"] == "Change what it does"


def test_b2_2_cancel_is_a_grey_outline_button_after_a_divider():
    shown = page.refine_buttons(_lane_box())
    *lane_buttons, divider, cancel = shown
    assert divider.__class__.__name__ == "Divider"
    assert cancel.children == lanes.CANCEL_LABEL
    assert cancel.variant == "outline" and cancel.color == "gray"
    assert all(button.variant != "outline" for button in lane_buttons)
    assert len(lane_buttons) == 3


def test_b2_2_restore_cancel_looks_the_same():
    box = RefineBox(offered=True, buttons=[("restore_cancel", lanes.CANCEL_LABEL)])
    (cancel,) = page.refine_buttons(box)  # alone: no divider
    assert cancel.variant == "outline" and cancel.color == "gray"
