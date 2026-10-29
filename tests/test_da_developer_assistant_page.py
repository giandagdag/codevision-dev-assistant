import pytest

from agents import da_understand_flow as flow
from db_table_functions.db_tbl_da_requests import list_my_requests
from layouts import da_developer_assistant_page as page
from tests import da_play
from tests.da_tree import all_text, by_id, components

SECTIONS = [
    "Requirement summary",
    "Scope",
    "Inputs and outputs",
    "Important scenarios",
    "Functional flow",
    "Assumptions",
    "Open items",
    "References",
]


@pytest.fixture
def settings(make_settings, published_rulebook):
    return make_settings()


def choice_buttons(tree):
    return [
        c
        for c in components(tree, "Button")
        if isinstance(getattr(c, "id", None), dict) and c.id["type"] == page.CHOICE_TYPE
    ]


def test_layout_has_a_content_area_and_a_refresh_store():
    ids = [getattr(c, "id", None) for c in components(page.layout())]
    assert page.PAGE_CONTENT_ID in ids and page.REFRESH_ID in ids


def test_home_has_two_cards_and_the_second_is_disabled():
    home = page.render_home([])
    text = all_text(home)
    assert "Start a change request" in text and "Review my code" in text
    assert "Coming in a later phase" in text
    start_link = by_id(home, "da-start-card")
    assert start_link.href == "?new=1"
    assert "No requests yet" in text


def test_home_rows_link_to_the_request_and_show_the_pill(settings):
    done = da_play.to_confirmed(settings)
    da_play.start(settings)
    home = page.render_home(list_my_requests(settings.db_path, settings.developer_id))
    links = [c for c in components(home, "Link") if c.href.startswith("?request=")]
    assert {link.href for link in links} == {
        f"?request={r.request_id}" for r in list_my_requests(settings.db_path, "dev-home-01")
    }
    assert len(links) == 6  # 2 requests x 3 cells
    text = all_text(home)
    assert done.request.request_id in text
    assert "CONFIRMED FOR DISCOVERY" in text and "CLARIFICATION IN PROGRESS" in text


def test_new_workspace_is_blank_with_the_banners(settings):
    tree = page.render_new_workspace(demo_mode=True)
    text = all_text(tree)
    assert page.CODE_BANNER in text and page.DEMO_BANNER in text
    assert "New change request" in text and "DRAFT" in text
    assert "0 of 4 mandatory questions answered" in text
    assert text.count(page.EMPTY_TEXT) == 10
    assert by_id(tree, page.TEXT_ID).disabled is False
    assert by_id(tree, page.STATE_ID).data == {"request_id": None, "revision": None}


def test_no_demo_banner_without_the_fake_provider():
    assert page.DEMO_BANNER not in all_text(page.render_new_workspace(demo_mode=False))


def test_only_the_summary_tab_can_be_used():
    tabs = components(page.render_new_workspace(False), "TabsTab")
    assert [t.children for t in tabs] == list(page.PANEL_TABS)
    assert [t.disabled for t in tabs] == [False, True, True, True, True, True]


def test_panel_has_every_section_in_order():
    titles = all_text(page.render_new_workspace(False)).splitlines()
    positions = [titles.index(section) for section in SECTIONS]
    assert positions == sorted(positions)


def test_first_answer_fills_the_panel_and_highlights_what_changed(settings):
    view = da_play.answer(settings, da_play.start(settings), da_play.ANSWERS[0])
    tree = page.render_workspace(view)
    text = all_text(tree)
    assert "Add Excel document processing" in text  # title
    assert "1 of 4 mandatory questions answered" in text
    assert "Let users upload Excel workbooks" in text  # objective
    styles = [c.style for c in components(tree, "Box") if getattr(c, "style", None)]
    highlighted = [s for s in styles if s.get("background") == page.da_styles.HIGHLIGHT]
    # Objective and reason are highlighted. The title (header) and answered_questions
    # (the progress bar) have no panel field of their own.
    assert len(highlighted) == 2
    assert text.count(page.EMPTY_TEXT) < 10


def test_text_mode_composer_is_open(settings):
    view = da_play.start(settings)
    tree = page.render_workspace(view)
    assert view.input_mode == "text"
    assert by_id(tree, page.TEXT_ID).disabled is False
    assert by_id(tree, page.SEND_ID).disabled is False
    assert choice_buttons(tree) == []
    assert by_id(tree, page.STATE_ID).data == {
        "request_id": view.request.request_id,
        "revision": view.revision,
    }


def test_decision_locks_the_text_box_and_shows_the_choices(settings):
    view = da_play.to_decision(settings)
    tree = page.render_workspace(view)
    assert view.input_mode == "choices"
    assert by_id(tree, page.TEXT_ID).disabled is True
    assert by_id(tree, page.SEND_ID).disabled is True
    options = [b.id["option"] for b in choice_buttons(tree)]
    assert options == view.choices and flow.HELP_OPTION == options[-1]
    assert "Text input is paused until you choose" in by_id(tree, page.TEXT_ID).placeholder
    assert "Clarification required: 1 open item" in all_text(tree)


def test_optional_area_shows_skip(settings):
    view = da_play.choose(settings, da_play.to_decision(settings), "Visible worksheets only")
    assert view.can_skip
    tree = page.render_workspace(view)
    assert by_id(tree, page.SKIP_ID).style == {}
    assert by_id(tree, page.TEXT_ID).disabled is False
    other = page.render_workspace(da_play.start(settings))
    assert by_id(other, page.SKIP_ID).style == {"display": "none"}


def test_checkpoint_offers_the_three_choices(settings):
    view = da_play.to_checkpoint(settings)
    tree = page.render_workspace(view)
    assert [b.id["option"] for b in choice_buttons(tree)] == list(flow.CHECKPOINT_OPTIONS)
    assert "Ready for confirmation" in all_text(tree)
    assert "READY FOR CONFIRMATION" in all_text(tree)


def test_confirmed_request_is_done(settings):
    view = da_play.to_confirmed(settings)
    tree = page.render_workspace(view)
    text = all_text(tree)
    assert view.input_mode == "done"
    assert "Confirmed and saved as version 1" in text
    assert "CONFIRMED FOR DISCOVERY" in text
    assert "Proceed to Discovery (coming in Phase 3)" in text
    button = [c for c in components(tree, "Button") if "Phase 3" in all_text(c)][0]
    assert button.disabled is True
    assert by_id(tree, page.TEXT_ID).disabled is True
    assert choice_buttons(tree) == []


def test_senior_stop_is_locked_and_shows_why(settings):
    view = da_play.to_decision(settings)
    waiting = view.model_copy(
        update={"input_mode": "waiting", "choices": [], "prompt": flow.SENIOR_MESSAGE}
    )
    tree = page.render_workspace(waiting)
    assert by_id(tree, page.TEXT_ID).disabled is True
    assert by_id(tree, page.TEXT_ID).placeholder == flow.SENIOR_MESSAGE


def test_message_page_links_home():
    tree = page.render_message_page("Request CVDA-2026-9999 does not exist.")
    assert "does not exist" in all_text(tree)
    assert by_id(tree, "da-back-home").href == "?"
