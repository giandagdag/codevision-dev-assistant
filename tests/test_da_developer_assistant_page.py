import pytest

from agents import da_understand_flow as flow
from db_table_functions.db_tbl_da_requests import list_my_requests
from layouts import da_developer_assistant_page as page
from tests import da_play
from tests.da_tree import all_text, by_id, components

SECTIONS = [
    "Requirement summary",
    "Acceptance criteria (each one gets tested)",
    "Scope",
    "Inputs and outputs",
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
    assert text.count(page.EMPTY_TEXT) == 11  # every field that is not 'always' visible
    assert by_id(tree, page.TEXT_ID).disabled is False
    assert by_id(tree, page.STATE_ID).data == {"request_id": None, "revision": None}


def test_no_demo_banner_without_the_fake_provider():
    assert page.DEMO_BANNER not in all_text(page.render_new_workspace(demo_mode=False))


def test_tabs_have_tabler_icons_and_only_summary_can_be_used():
    tabs = components(page.render_new_workspace(False), "TabsTab")
    assert [t.children for t in tabs] == [name for name, _ in page.PANEL_TABS]
    assert [t.children for t in tabs] == [
        "Summary", "Discovery", "Approach", "Build", "Tests", "Audit"
    ]
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


def test_submitting_the_form_fills_the_panel_at_once_and_highlights_what_changed(settings):
    view = da_play.submit_form(settings, da_play.start(settings))
    tree = page.render_workspace(view)
    text = all_text(tree)
    assert "Add Excel document processing" in text  # title
    assert "Let users upload Excel workbooks" in text  # objective (question 1)
    assert "The upload screen accepts only PDF and DOCX files" in text  # current (question 2)
    assert "Excel workbooks uploaded by the user" in text  # inputs (question 4)
    styles = [c.style for c in components(tree, "Box") if getattr(c, "style", None)]
    highlighted = [s for s in styles if s.get("background") == page.da_styles.HIGHLIGHT]
    assert len(highlighted) >= 8  # every field the form answered is highlighted
    assert "Waiting for your answer" not in text.split("Requirement summary")[1].split("Scope")[0]


def test_the_form_has_five_boxes_a_submit_and_a_paused_chat_box(settings):
    view = da_play.start(settings)
    tree = page.render_workspace(view)
    assert view.input_mode == "form"
    boxes = [c for c in components(tree, "Textarea")
             if isinstance(getattr(c, "id", None), dict) and c.id["type"] == page.FORM_BOX_TYPE]
    assert [b.id["index"] for b in boxes] == [1, 2, 3, 4, 5]
    assert [b.label for b in boxes] == [
        "1. What needs to change, and why?",
        "2. What happens today? (you don't need to know the source files)",
        "3. What should happen after the change?",
        "4. What are the inputs, outputs, and important success or failure cases?",
        "Optional: constraints, exclusions, or references?",
    ]
    assert boxes[-1].description == "This box may stay empty."
    submit = [c for c in components(tree, "Button")
              if isinstance(getattr(c, "id", None), dict) and c.id["type"] == page.FORM_SUBMIT_TYPE]
    assert [b.children for b in submit] == ["Submit"]
    errors = [c for c in components(tree, "Text")
              if isinstance(getattr(c, "id", None), dict) and c.id["type"] == page.FORM_ERROR_TYPE]
    assert [e.id["index"] for e in errors] == [1, 2, 3, 4, 5]
    # The chat box is paused, Skip is gone (the optional box replaced it), no choice buttons.
    assert by_id(tree, page.TEXT_ID).disabled is True
    assert by_id(tree, page.TEXT_ID).placeholder == page.FORM_COMPOSER_TEXT
    assert by_id(tree, page.SEND_ID).disabled is True
    assert by_id(tree, page.SKIP_ID).style == {"display": "none"}
    assert choice_buttons(tree) == []
    assert by_id(tree, page.STATE_ID).data == {
        "request_id": view.request.request_id,
        "revision": view.revision,
    }


def test_the_form_disappears_after_submit(settings):
    view = da_play.submit_form(settings, da_play.start(settings))
    tree = page.render_workspace(view)
    assert by_id(tree, "da-form") is None


def test_an_old_request_in_the_middle_of_the_questions_still_shows_the_text_box(settings):
    view = da_play.start_old_way(settings)
    tree = page.render_workspace(view)
    assert view.input_mode == "text"
    assert by_id(tree, page.TEXT_ID).disabled is False
    assert by_id(tree, page.SEND_ID).disabled is False
    assert by_id(tree, "da-form") is None
    assert choice_buttons(tree) == []


def test_decision_locks_the_text_box_and_shows_the_choices(settings):
    view = da_play.to_decision(settings)
    tree = page.render_workspace(view)
    assert view.input_mode == "choices"
    # The buttons stay and the text box opens for "Other, type here" (W3).
    assert by_id(tree, page.TEXT_ID).disabled is False
    assert by_id(tree, page.TEXT_ID).placeholder == "Other, type here"
    assert by_id(tree, page.SEND_ID).disabled is False
    options = [b.children for b in choice_buttons(tree)]
    assert options == view.choices and flow.HELP_OPTION == options[-1]
    assert [b.id["index"] for b in choice_buttons(tree)] == list(range(len(options)))
    assert "Clarification required: 1 open item" in all_text(tree)


def test_checkpoint_stays_buttons_only(settings):
    view = da_play.to_checkpoint(settings)
    tree = page.render_workspace(view)
    assert by_id(tree, page.TEXT_ID).disabled is True
    assert by_id(tree, page.SEND_ID).disabled is True
    assert "Text input is paused until you choose" in by_id(tree, page.TEXT_ID).placeholder


def test_optional_area_shows_skip_for_an_old_request(settings):
    view = da_play.start_old_way(settings)
    for text in da_play.ANSWERS:
        view = da_play.answer(settings, view, text)
    view = da_play.choose(settings, view, "Visible worksheets only")
    assert view.can_skip
    tree = page.render_workspace(view)
    assert by_id(tree, page.SKIP_ID).style == {}
    assert by_id(tree, page.TEXT_ID).disabled is False
    other = page.render_workspace(da_play.start_old_way(settings))
    assert by_id(other, page.SKIP_ID).style == {"display": "none"}


def test_checkpoint_offers_the_three_choices(settings):
    view = da_play.to_checkpoint(settings)
    tree = page.render_workspace(view)
    assert [b.children for b in choice_buttons(tree)] == list(flow.CHECKPOINT_OPTIONS)
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
        update={
            "input_mode": "waiting",
            "choices": [],
            "prompt": flow.SENIOR_MESSAGE,
            "custom_choice_allowed": False,
        }
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

    proceed = [c for c in choice_buttons(tree) if c.id["index"] == 0]
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

    assert [c.id["index"] for c in choice_buttons(tree)] == [0, 1]
    assert [key for key, _ in page.discover_buttons(view)] == ["confirm", "escalate"]
    assert [c.children for c in choice_buttons(tree)] == [
        "✅ Findings look right",
        "🙋 Escalate to a senior developer",
    ]
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


def test_confirmed_discovery_shows_the_active_proceed_to_approach_button(settings):
    from agents import da_approach_flow as approach
    from agents import da_discover_flow as discover

    def confirm(settings, request_id, view):
        return discover.confirm_discovery(settings, request_id, view.revision)

    tree, view = discover_tree(settings, start_step, confirm)
    understand = flow.get_understand_view(settings, view.request.request_id)
    start = approach.get_approach_view(settings, view.request.request_id)
    tree = page.render_discover_workspace(understand, view, start)

    buttons = choice_buttons(tree)
    assert [all_text(b) for b in buttons] == ["Proceed to Approach"]
    assert not getattr(buttons[0], "disabled", False)
    assert "Readiness Gate" not in all_text(tree)
    assert "Discovery confirmed." in all_text(tree)
    assert by_id(tree, page.STATE_ID).data == {
        "request_id": view.request.request_id, "revision": 0, "approach": True
    }


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

    assert [c.id["index"] for c in choice_buttons(tree)] == [0]
    assert [c.children for c in choice_buttons(tree)] == ["Search again"]
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


def test_discover_button_ids_hold_only_the_position(settings):
    # Dash cannot read the click count of a button whose id holds an emoji (found in the browser
    # check), so the ids hold the position (P19) and only the labels carry emoji.
    for steps in ((), (start_step,)):
        tree, _ = discover_tree(settings, *steps)
        for button in choice_buttons(tree):
            assert set(button.id) == {"type", "index"} and isinstance(button.id["index"], int)


# --- Summary: criteria and step-by-step fill (Phase 2D) ---


def test_hidden_fields_say_waiting_even_though_the_record_holds_them(settings):
    view = da_play.answer(settings, da_play.start_old_way(settings), da_play.ANSWERS[0])
    assert view.record.title and view.record.objective
    # The fake script only fills question 1 fields here; make the record hold a later one too.
    sneaky = view.model_copy(
        update={"record": view.record.model_copy(update={"inputs": "SECRET-LATER-VALUE"})}
    )
    text = all_text(page.render_workspace(sneaky))
    assert "SECRET-LATER-VALUE" not in text
    assert "Let users upload Excel workbooks" in text


def test_criteria_show_id_badge_and_given_when_then(settings):
    view = da_play.to_checkpoint(settings)
    tree = page.render_workspace(view)
    text = all_text(tree)
    assert "AC-1" in text and "AC-7" in text
    assert (
        "Given an empty workbook, when it is uploaded, then it is rejected with the standard "
        "empty-file error." in text
    )
    assert "failure" not in [b.children for b in components(tree, "Badge")]  # no red tag
    assert "Important scenarios" not in text


def criteria_rows(tree):
    """Each criterion line as (id badge, the line's asterisk marks), in screen order."""
    rows = []
    for group in components(tree, "Group"):
        badges = [c for c in components(group.children, "Badge")]
        if badges and str(badges[0].children).startswith("AC-"):
            marks = [t for t in components(group.children, "Text") if t.children == "*"]
            rows.append((badges[0], marks))
    return rows


def test_id_badge_text_is_the_criterion_id_and_is_never_cut_or_shrunk(settings):
    view = da_play.to_checkpoint(settings)
    rows = criteria_rows(page.render_workspace(view))
    assert [badge.children for badge, _ in rows] == [c.id for c in view.record.acceptance_criteria]
    for badge, _ in rows:
        assert badge.style["flexShrink"] == 0
        assert badge.styles["label"]["textOverflow"] == "clip"
        assert badge.styles["label"]["overflow"] == "visible"


def test_a_negative_scenario_shows_an_asterisk_and_a_success_does_not(settings):
    view = da_play.to_checkpoint(settings)
    rows = criteria_rows(page.render_workspace(view))
    kinds = [c.kind for c in view.record.acceptance_criteria]
    assert kinds.count("failure") == 4 and kinds.count("success") == 3
    for (_, marks), kind in zip(rows, kinds, strict=True):
        assert len(marks) == (1 if kind == "failure" else 0)
    mark = next(marks[0] for _, marks in rows if marks)
    assert getattr(mark, "aria-label") == "Negative scenario"
    tooltips = components(page.render_workspace(view), "Tooltip")
    assert [t.label for t in tooltips] == ["Negative scenario"] * 4


def test_the_legend_shows_when_there_are_criteria_and_not_when_empty(settings):
    view = da_play.to_checkpoint(settings)
    full = page.render_workspace(view)
    assert by_id(full, "da-criteria-legend").children == "* Negative scenario testing"
    assert all_text(full).count("* Negative scenario testing") == 1
    # The legend is a muted line under the heading, before the first criterion.
    lines = all_text(full).splitlines()
    assert lines.index("* Negative scenario testing") == lines.index(SECTIONS[1]) + 1

    empty = page.render_new_workspace(False)
    assert by_id(empty, "da-criteria-legend") is None
    assert "* Negative scenario testing" not in all_text(empty)


def test_criteria_section_sits_under_the_requirement_summary():
    titles = all_text(page.render_new_workspace(False)).splitlines()
    assert titles.index(SECTIONS[1]) == titles.index(SECTIONS[0]) + 9


def test_empty_visible_criteria_show_the_hint_text(settings):
    view = da_play.answer(settings, da_play.start_old_way(settings), da_play.ANSWERS[0])
    visible = [*view.visible_fields, "acceptance_criteria"]
    shown = view.model_copy(update={"visible_fields": visible})
    text = all_text(page.render_workspace(shown))
    assert page.CRITERIA_EMPTY in text
    assert "Each success or negative case becomes a testable criterion" in text
