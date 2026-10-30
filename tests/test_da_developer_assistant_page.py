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


def test_tabs_have_tabler_icons_and_only_summary_can_be_used():
    tabs = components(page.render_new_workspace(False), "TabsTab")
    assert [t.children for t in tabs] == [name for name, _ in page.PANEL_TABS]
    assert [t.children for t in tabs] == ["Summary", "Discovery", "Gate", "Code", "Review", "Audit"]
    assert [t.disabled for t in tabs] == [False, True, True, True, True, True]
    for tab, (_, icon) in zip(tabs, page.PANEL_TABS, strict=True):
        icons = components(tab, "DashIconify")
        assert len(icons) == 1 and icons[0].icon == icon
        assert icon.startswith("tabler:")


def test_the_page_has_a_store_for_the_enter_script():
    assert by_id(page.layout(), page.KEYS_ID) is not None


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
    # From here the Discover workspace takes over (it has the active Proceed button).
    assert "coming in Phase 3" not in text
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


# --- The Discover workspace (Phase 3, spec 3.8) ---


def discover_tree(settings, *steps, **kwargs):
    """Confirm a request, run the given Discover actions, and draw the workspace."""
    from agents import da_discover_flow as discover

    request_id = da_play.to_confirmed(settings).request.request_id
    view = discover.get_discovery_view(settings, request_id)
    for step in steps:
        view = step(settings, request_id, view)
    understand = flow.get_understand_view(settings, request_id)
    return page.render_discover_workspace(understand, view), view


def start_step(settings, request_id, view):
    from agents import da_discover_flow as discover

    return discover.start_discovery(settings, request_id, view.revision)


def hint_step(settings, request_id, view):
    from agents import da_discover_flow as discover

    return discover.add_hint_and_search(settings, request_id, "batching helper", view.revision)


def tab(tree, name):
    return [c for c in components(tree, "TabsTab") if c.value == name][0]


def test_confirmed_request_shows_the_active_proceed_button_and_a_locked_discovery_tab(settings):
    tree, _ = discover_tree(settings)

    proceed = [c for c in choice_buttons(tree) if c.id["option"] == page.PROCEED_DISCOVERY_OPTION]
    assert len(proceed) == 1 and not getattr(proceed[0], "disabled", False)
    assert tab(tree, "discovery").disabled is True
    assert "Discovery" in all_text(tree) and by_id(tree, "da-outcome-banner") is None


def test_stepper_is_on_discover_and_the_discovery_tab_opens_after_a_round(settings):
    tree, _ = discover_tree(settings, start_step)

    steps = [c for c in components(tree) if isinstance(getattr(c, "id", None), dict)
             and c.id.get("type") == "da-step"]
    assert [c.style.get("fontWeight") for c in steps][:2] == [None, 600]
    assert tab(tree, "discovery").disabled is False and tab(tree, "summary").disabled is False
    tabs = components(tree, "Tabs")[0]
    assert tabs.value == "discovery"
    assert page.BUSY_TEXT in all_text(tree)


def test_discovery_tab_shows_input_search_rows_outcome_findings_limitations_and_round(settings):
    tree, view = discover_tree(settings, start_step)

    text = all_text(by_id(tree, "da-discovery-input"))
    assert text == f"Input: request {view.request.request_id}, record version 1"
    assert by_id(tree, "da-search-structural").opacity == 0.5
    assert by_id(tree, "da-outcome-banner").color == "green"
    body = all_text(tree)
    assert "PDF text extraction already exists" in body
    assert "app/ingestion/pdf_processor.py · PdfProcessor.extract_text @ fake-index-001" in body
    assert "Limitations" in body and "Round 1 of 3" in body
    assert by_id(tree, "da-fallback-banner") is None


def test_findings_look_right_choices_and_the_hint_box(settings):
    tree, view = discover_tree(settings, start_step)

    options = [c.id["option"] for c in choice_buttons(tree)]
    assert options == ["✅ Findings look right", "🙋 Escalate to a senior developer"]
    send = by_id(tree, page.SEND_ID)
    assert send.children == "✏️ Something's missing" and not send.disabled
    text_box = by_id(tree, page.TEXT_ID)
    assert text_box.label == "What's missing? Name a feature, file or term."
    assert not text_box.disabled


def test_after_the_round_cap_only_confirm_and_escalate_are_offered_with_a_reason(settings):
    tree, view = discover_tree(settings, start_step, hint_step, hint_step)

    assert view.rounds_used == 3
    assert "Round 3 of 3" in all_text(tree)
    assert by_id(tree, page.TEXT_ID).disabled is True
    assert "all 3 search rounds" in all_text(tree)
    assert len(choice_buttons(tree)) == 2


def test_bad_ai_shows_the_fallback_banner(settings, monkeypatch):
    from agents import da_discover_flow as discover
    from tests.da_stub_client import StubClient

    def bad_start(settings, request_id, view):
        return discover.start_discovery(
            settings, request_id, view.revision, client=StubClient("no", "no")
        )

    tree, _ = discover_tree(settings, bad_start)

    assert all_text(by_id(tree, "da-fallback-banner")) == (
        "AI summary unavailable. Showing plain search results."
    )
    assert "Possible match" in all_text(tree)


def test_no_match_gives_an_amber_banner_and_the_not_proof_limitation(settings):
    from agents import da_discover_flow as discover

    class NoHits:
        def search(self, query, mode, filters, top_k):
            return []

    def empty_start(settings, request_id, view):
        return discover.start_discovery(settings, request_id, view.revision, index=NoHits())

    tree, _ = discover_tree(settings, empty_start)

    assert by_id(tree, "da-outcome-banner").color == "orange"
    assert "not proof it does not exist" in all_text(by_id(tree, "da-limitations"))
    assert by_id(tree, "da-fallback-banner") is None


def test_confirmed_discovery_shows_the_disabled_readiness_gate_button(settings):
    from agents import da_discover_flow as discover

    def confirm(settings, request_id, view):
        return discover.confirm_discovery(settings, request_id, view.revision)

    tree, _ = discover_tree(settings, start_step, confirm)

    gate = [c for c in components(tree, "Button") if "Readiness Gate" in all_text(c)][0]
    assert gate.disabled is True
    assert "(coming in Phase 4)" in all_text(gate)
    assert choice_buttons(tree) == []
    assert "Discovery confirmed." in all_text(tree)


def test_escalated_discovery_shows_the_open_item(settings):
    from agents import da_discover_flow as discover

    def escalate(settings, request_id, view):
        return discover.escalate_discovery(settings, request_id, view.revision)

    tree, view = discover_tree(settings, start_step, escalate)

    assert view.open_item.startswith("Escalated in Discover: ")
    assert view.open_item in all_text(by_id(tree, "da-state-banner"))
    assert choice_buttons(tree) == []


def test_a_request_stuck_in_searching_offers_search_again(settings):
    from tests.da_discover_play import set_status

    request_id = da_play.to_confirmed(settings).request.request_id
    set_status(settings, request_id, "SEARCHING")
    from agents import da_discover_flow as discover

    tree = page.render_discover_workspace(
        flow.get_understand_view(settings, request_id),
        discover.get_discovery_view(settings, request_id),
    )

    assert [c.id["option"] for c in choice_buttons(tree)] == ["Search again"]
    assert "did not finish" in all_text(by_id(tree, "da-outcome-banner"))


def test_chat_shows_the_discover_divider(settings):
    tree, _ = discover_tree(settings, start_step)

    dividers = [c for c in components(tree, "Divider") if c.label == "🔍 Discover"]
    assert len(dividers) == 1
    assert "Searching approved sources" in all_text(tree)


def test_workspace_state_carries_the_discovery_revision_and_flag(settings):
    tree, view = discover_tree(settings, start_step)

    state = by_id(tree, page.STATE_ID).data
    assert state == {"request_id": view.request.request_id, "revision": 1, "discover": True}


def test_every_input_the_callbacks_name_exists_in_the_discover_workspace(settings):
    tree, _ = discover_tree(settings, start_step)

    for component_id in (page.TEXT_ID, page.SEND_ID, page.SKIP_ID, page.MESSAGE_ID, page.BUSY_ID):
        assert by_id(tree, component_id) is not None, component_id
