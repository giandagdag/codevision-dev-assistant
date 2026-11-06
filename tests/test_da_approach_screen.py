"""The Approach screen and the clicks that drive it (rows 4-29 fake provider, 4-30, 4-31)."""

import pytest
from dash import no_update

from agents import da_approach_flow as flow
from agents import da_understand_flow as understand
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from layouts import da_developer_assistant_page as page
from tests.da_approach_play import at_review, at_tests, discovery_confirmed_id, proposed
from tests.da_tree import all_text, by_id, components

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def request_id(settings):
    return discovery_confirmed_id(settings)


def draw(settings, request_id):
    return cb.show_page(f"?request={request_id}", 0)


def buttons(tree):
    return [
        c for c in components(tree, "Button")
        if isinstance(getattr(c, "id", None), dict) and c.id["type"] == page.CHOICE_TYPE
    ]


def click(settings, tree, index, text=None):
    state = by_id(tree, page.STATE_ID).data
    return cb.perform_action(settings, {"type": page.CHOICE_TYPE, "index": index}, text, state, 0)


def labels(tree):
    return [all_text(b) for b in buttons(tree)]


def test_4_30_the_stepper_tabs_and_chip_use_the_new_names(settings, request_id):
    proposed(settings, request_id)

    tree = draw(settings, request_id)

    text = all_text(tree)
    for name in ("Understand", "Discover", "Approach", "Build & Test", "Your review", "Handoff"):
        assert name in text
    assert "Readiness Gate" not in text and "Generate + Check" not in text
    steps = [c for c in components(tree) if isinstance(getattr(c, "id", None), dict)
             and c.id.get("type") == "da-step"]
    assert [c.style.get("fontWeight") for c in steps] == [None, None, 600, None, None, None]
    tabs = components(tree, "TabsTab")
    assert [t.children for t in tabs] == [
        "Summary", "Discovery", "Approach", "Build", "Tests", "Audit"
    ]
    assert [t.disabled for t in tabs] == [False, False, False, True, True, True]
    assert components(tree, "Tabs")[0].value == "approach"
    assert page.CODE_BANNER == "No code is written yet"
    assert "No code is written yet" in text and "No code is generated" not in text


def test_4_30_the_new_statuses_have_pills(settings, request_id):
    tree = draw(settings, request_id)
    assert "DISCOVERY CONFIRMED" in all_text(tree)
    proposed(settings, request_id)
    assert "APPROACH PROPOSED" in all_text(draw(settings, request_id))


def test_the_approach_tab_shows_each_section_in_order(settings, request_id):
    at_tests(settings, request_id)

    tree = draw(settings, request_id)

    panel = [by_id(tree, i) for i in ("da-file-plan", "da-reuse", "da-design-decisions",
                                      "da-libraries", "da-test-plan", "da-gate")]
    assert all(section is not None for section in panel)
    assert "Approach v2, built from request v1 and Discovery round 1" in all_text(
        by_id(tree, "da-approach-header")
    )
    plan = all_text(by_id(tree, "da-file-plan"))
    assert "src/agents/excel_processor.py" in plan and "New" in plan and "Change" in plan
    assert "tests/cvda_2026_0001/" in plan and "written by the Tester, frozen, in Phase 6" in plan
    assert "2 code files, limit 5" in plan
    assert "Not found in Discover" in plan  # the modify path no hit has
    reuse = all_text(by_id(tree, "da-reuse"))
    assert "PDF text extraction already exists" in reuse and "extend" in reuse
    assert "Where does Excel upload live? Existing upload screen" in all_text(
        by_id(tree, "da-design-decisions")
    )
    libraries = all_text(by_id(tree, "da-libraries"))
    assert "openpyxl" in libraries and "Not found in Discover" in libraries
    assert "9 cases cover 7 of 7 criteria" in all_text(by_id(tree, "da-test-cover"))
    gate = all_text(by_id(tree, "da-gate"))
    for name in ("Request confirmed", "Discover done", "Approach confirmed", "Test plan accepted"):
        assert name in gate


def test_a_draft_banner_shows_while_choices_are_open_and_not_after(settings, request_id):
    proposed(settings, request_id)
    assert by_id(draw(settings, request_id), "da-approach-draft") is not None

    flow_view = flow.get_approach_view(settings, request_id)
    flow.choose_design_option(settings, request_id, "Existing upload screen", flow_view.revision)

    assert by_id(draw(settings, request_id), "da-approach-draft") is None


def test_4_31_a_negative_scenario_shows_the_asterisk_and_a_success_does_not(
    settings, request_id
):
    at_tests(settings, request_id)

    tree = draw(settings, request_id)

    rows = components(by_id(tree, "da-test-plan"), "TableTr")[1:]
    by_test = {all_text(row).split("\n")[0]: row for row in rows}

    def has_mark(row):
        return any(getattr(c, "children", None) == "*" for c in components(row, "Text"))

    assert has_mark(by_test["T-5"])  # AC-4, an empty workbook: a negative scenario
    assert not has_mark(by_test["T-1"])  # AC-1 is a success
    assert "AC-4" in all_text(by_test["T-5"])
    assert "* Negative scenario testing" in all_text(by_id(tree, "da-tests-legend"))


def test_a_kept_case_is_tagged_yours_and_a_draft_is_highlighted(settings, request_id):
    view = at_tests(settings, request_id)
    flow.submit_text(settings, request_id, "an empty sheet", view.revision)

    drafting = draw(settings, request_id)
    draft = by_id(drafting, "da-draft-case")
    assert "Draft" in all_text(draft) and draft.style["background"] == "#FFF1C2"
    assert labels(drafting) == ["Keep this case", "Discard it"]

    view = flow.get_approach_view(settings, request_id)
    flow.keep_case(settings, request_id, view.revision)

    kept = all_text(by_id(draw(settings, request_id), "da-test-plan"))
    assert "Yours" in kept and "T-10" in kept and "10 cases cover 7 of 7" in kept


def test_the_composer_opens_the_text_box_only_where_the_step_takes_text(settings, request_id):
    proposed(settings, request_id)
    tree = draw(settings, request_id)
    assert by_id(tree, page.TEXT_ID).disabled is False
    assert by_id(tree, page.TEXT_ID).placeholder == "Other, type here"
    assert labels(tree) == ["Existing upload screen", "New upload screen", "I need help deciding"]

    view = flow.get_approach_view(settings, request_id)
    flow.choose_design_option(settings, request_id, "Existing upload screen", view.revision)
    tree = draw(settings, request_id)
    # At review the box is open and Send says "Change something" (Phase 6 fixes, section 2).
    assert by_id(tree, page.TEXT_ID).disabled is False
    assert by_id(tree, page.TEXT_ID).placeholder == (
        "Type what should change, then press Change something."
    )
    assert all_text(by_id(tree, page.SEND_ID)) == "Change something"
    assert labels(tree) == ["Accept approach", "Get help"]


def test_every_input_the_callbacks_name_exists_in_the_approach_workspace(settings, request_id):
    proposed(settings, request_id)
    tree = draw(settings, request_id)

    for component_id in (page.TEXT_ID, page.SEND_ID, page.SKIP_ID, page.MESSAGE_ID, page.BUSY_ID):
        assert by_id(tree, component_id) is not None, component_id
    assert by_id(tree, page.STATE_ID).data["approach"] is True
    for button in buttons(tree):
        assert set(button.id) == {"type", "index"} and isinstance(button.id["index"], int)


def test_4_29_a_whole_request_runs_through_the_buttons_to_ready_to_build(settings, request_id):
    tree = draw(settings, request_id)
    assert labels(tree) == ["Proceed to Approach"]
    assert by_id(tree, page.STATE_ID).data["revision"] == 0

    assert click(settings, tree, 0) == (1, no_update, "")           # Proceed to Approach
    tree = draw(settings, request_id)
    assert "APPROACH PROPOSED" in all_text(tree)
    click(settings, tree, 0)                                         # Existing upload screen
    tree = draw(settings, request_id)
    click(settings, tree, 0)                                         # Accept approach
    tree = draw(settings, request_id)
    assert labels(tree) == [
        "Accept test plan", "Go back and change the approach", "Get help"
    ]
    assert all_text(by_id(tree, page.SEND_ID)) == "Add a test case"
    state = by_id(tree, page.STATE_ID).data
    cb.perform_action(settings, page.SEND_ID, "An empty sheet", state, 0)  # the typed case
    tree = draw(settings, request_id)
    click(settings, tree, 0)                                         # Keep this case
    tree = draw(settings, request_id)
    click(settings, tree, 0)                                         # Accept test plan

    tree = draw(settings, request_id)
    text = all_text(tree)
    assert "READY TO BUILD" in text and by_id(tree, "da-ready-banner") is not None
    # Phase 5 replaced the disabled Phase 4 button with the real folder button.
    assert "Choose workspace folder" in text and "coming in Phase 5" not in text
    chooser = [b for b in components(tree, "Button") if all_text(b) == "Choose workspace folder"][0]
    assert not chooser.disabled
    assert buttons(tree) == []
    assert flow.get_approach_view(settings, request_id).request.status == "READY_TO_BUILD"


def test_a_stale_click_in_approach_gets_the_stale_message(settings, request_id):
    tree = draw(settings, request_id)
    state = by_id(tree, page.STATE_ID).data

    result = cb.perform_action(
        settings, {"type": page.CHOICE_TYPE, "index": 0}, None, state | {"revision": 4}, 0
    )

    assert result[2] == "This request was updated in another window. Reload to continue."
    assert flow.get_approach_view(settings, request_id).request.status == "DISCOVERY_CONFIRMED"


def test_a_button_index_with_nothing_behind_it_is_stale(settings, request_id):
    tree = draw(settings, request_id)
    state = by_id(tree, page.STATE_ID).data

    result = cb.perform_action(
        settings, {"type": page.CHOICE_TYPE, "index": 7}, None, state, 0
    )

    assert "updated in another window" in result[2]


def test_typed_text_at_the_wrong_step_shows_a_plain_message(settings, request_id):
    state = by_id(draw(settings, request_id), page.STATE_ID).data  # before Proceed to Approach

    result = cb.perform_action(settings, page.SEND_ID, "hello", state, 0)

    assert "Please press Proceed to Approach first" in result[2]


def test_send_at_the_review_step_is_the_change(settings, request_id):
    at_review(settings, request_id)
    state = by_id(draw(settings, request_id), page.STATE_ID).data

    result = cb.perform_action(settings, page.SEND_ID, "Also log skipped sheets", state, 0)

    assert result == (1, no_update, "")
    view = flow.get_approach_view(settings, request_id)
    assert view.approach.approach_version == 3 and view.change_count == 1


def test_empty_send_at_the_review_and_tests_steps_does_nothing(settings, request_id):
    view = at_review(settings, request_id)
    state = by_id(draw(settings, request_id), page.STATE_ID).data
    assert cb.perform_action(settings, page.SEND_ID, "", state, 0)[2] == (
        "Please type a message first."
    )
    flow.accept_approach(settings, request_id, view.revision)
    state = by_id(draw(settings, request_id), page.STATE_ID).data
    assert cb.perform_action(settings, page.SEND_ID, "  ", state, 0)[2] == (
        "Please type a message first."
    )
    after = flow.get_approach_view(settings, request_id)
    assert after.step == "tests" and after.draft_case is None


def test_a_capped_review_box_is_disabled_and_shows_the_cap_message(settings, request_id):
    from tests.da_approach_play import Tweaked

    view = at_review(settings, request_id)
    for number in range(3):
        view = flow.submit_text(
            settings, request_id, f"Change {number}", view.revision, generator=Tweaked("change")
        )

    tree = draw(settings, request_id)

    assert by_id(tree, page.TEXT_ID).disabled is True
    assert by_id(tree, page.TEXT_ID).placeholder == flow.CAP_MESSAGE
    assert by_id(tree, page.SEND_ID).disabled is True


def test_the_go_back_button_is_outlined_and_the_accept_buttons_are_the_main_ones(
    settings, request_id
):
    at_tests(settings, request_id)
    tree = draw(settings, request_id)
    by_label = {all_text(b): b for b in buttons(tree)}

    assert by_label["Accept test plan"].variant == "filled"
    assert by_label["Go back and change the approach"].variant == "default"
    assert by_label["Get help"].variant == "default"


def test_design_choice_buttons_all_look_equal(settings, request_id):
    proposed(settings, request_id)
    tree = draw(settings, request_id)
    choices = [b for b in buttons(tree) if all_text(b) != "I need help deciding"]

    assert len(choices) >= 2
    assert {b.variant for b in choices} == {"light"}  # none is filled just for being first


def test_no_approach_chat_says_noted_as_a_confirmed_decision(settings, request_id):
    view = proposed(settings, request_id)
    flow.choose_design_option(settings, request_id, "Existing upload screen", view.revision)

    messages = flow.get_approach_view(settings, request_id).messages

    assert all("Noted as a confirmed decision." not in m.text for m in messages)


def test_a_too_long_custom_answer_shows_the_300_character_message(settings, request_id):
    proposed(settings, request_id)
    state = by_id(draw(settings, request_id), page.STATE_ID).data

    result = cb.perform_action(settings, page.SEND_ID, "x" * 301, state, 0)

    assert result[2] == "Please keep your own answer under 300 characters, or choose a button."


def test_get_help_shows_the_open_item_in_the_approach_workspace(settings, request_id):
    view = at_review(settings, request_id)
    flow.request_help(settings, request_id, view.revision)

    tree = draw(settings, request_id)

    assert "Escalated in Approach: review" in all_text(tree)
    assert "ESCALATION REQUIRED" in all_text(tree)
    assert buttons(tree) == []


def test_an_escalation_in_discover_still_draws_the_discover_workspace(settings):
    from agents import da_discover_flow as discover
    from tests.da_play import to_confirmed

    understood = to_confirmed(settings).request.request_id
    view = discover.start_discovery(settings, understood, 0)
    discover.escalate_discovery(settings, understood, view.revision)

    tree = draw(settings, understood)

    assert by_id(tree, page.STATE_ID).data.get("discover") is True


def test_the_fake_flow_and_understand_view_are_untouched(settings, request_id):
    assert understand.get_understand_view(settings, request_id).request.status == (
        "DISCOVERY_CONFIRMED"
    )
