"""The Refine composer on screen (Phase 8 step 13a, rows 8-1, 8-2, 8-12)."""

import pytest

from agents import da_refine_screen as screen
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from layouts import da_build_panel as bp
from layouts import da_workspace_panel as panel
from pydantic_classes.da_refine_models import RefineState
from tests.da_refine_play import written_request
from tests.da_tree import all_text, by_id, components

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def button_labels(tree):
    return [all_text(b) for b in components(tree, "Button")]


def text_box(tree):
    return [t for t in components(tree, "Textarea") if getattr(t, "id", None) == cb.TEXT_ID][0]


def test_8_1_written_request_offers_refine_rescan_restore_and_help(settings):
    request_id, _ = written_request(settings)

    tree = draw(request_id)

    labels = button_labels(tree)
    assert "Re-scan" in labels
    assert "Restore an earlier version" in labels
    assert "Get help" in labels
    assert by_id(tree, panel.ws_button_id("rescan", "bar")) is not None
    assert not text_box(tree).disabled
    assert all_text(by_id(tree, bp.EDIT_HINT_ID)) == "Edit anything, then click Re-scan."
    assert "Check my edits" not in labels  # nothing re-scanned yet


def test_8_2_no_refine_box_while_building_or_handed_off():
    for status in ("BUILDING", "HANDED_OFF", "READY_TO_BUILD"):
        box = screen.make_refine_box(status, "b_written", 0, 5)
        assert not box.offered and not box.browser_buttons and not box.buttons
    running = screen.make_refine_box("READY_FOR_REVIEW", "b_running", 0, 5)
    assert not running.offered


def test_8_2_drawn_building_screen_has_no_refine_buttons(settings):
    request_id, _ = written_request(settings)
    box = screen.get_refine_box(settings, request_id, "BUILDING", "b_running", "picker")
    assert not box.offered


def test_8_12_cap_closes_the_box_but_rescan_and_check_stay(settings, monkeypatch):
    request_id, _ = written_request(settings)
    monkeypatch.setattr(
        screen, "get_refine_state", lambda s, r: RefineState(request_id=r, refine_count=5)
    )

    tree = draw(request_id)

    box = text_box(tree)
    assert box.disabled
    assert "refined 5 times" in box.placeholder
    assert "Re-scan" in button_labels(tree)
    capped = screen.make_refine_box("READY_FOR_REVIEW", "b_written", 5, 5, has_edits=True)
    assert ("check_edits", "Check my edits") in capped.buttons


def test_download_mode_says_upload_folder_to_rescan():
    box = screen.make_refine_box("NOT_PASSING", "b_written", 0, 5, mode="download")
    assert box.browser_buttons == [("rescan", "Upload folder to re-scan")]
