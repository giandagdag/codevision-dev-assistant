"""Home check fixes: every right-panel tab scrolls (item 1) and the help and escalation buttons use
one outlined style, never the grey that reads as disabled (item 2, P21)."""

import dash_mantine_components as dmc
import pytest

from agents import da_approach_flow as approach
from agents import da_discover_flow as discover
from agents import da_understand_flow as understand
from agents import da_workspace_flow as workspace_flow
from layouts import da_developer_assistant_page as page
from styles import da_styles
from tests import da_play
from tests.da_approach_play import at_tests, discovery_confirmed_id, proposed
from tests.da_tree import all_text, components
from tests.da_workspace_play import good_folder, pick
from web import da_web_components as parts

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def button(tree, label):
    found = [b for b in components(tree, "Button") if all_text(b) == label]
    assert len(found) == 1, label
    return found[0]


def draw_approach(settings, request_id):
    status = approach.get_approach_view(settings, request_id).request.status
    return page.render_approach_workspace(
        understand.get_understand_view(settings, request_id),
        discover.get_discovery_view(settings, request_id),
        approach.get_approach_view(settings, request_id),
        workspace_flow.get_workspace_view(settings, request_id)
        if status == "READY_TO_BUILD"
        else None,
    )


# --- item 1: scrolling ---


def test_the_scroll_box_may_shrink_below_its_content():
    assert da_styles.PANEL_BODY["overflow"] == "auto"
    assert da_styles.PANEL_BODY["minHeight"] == 0 and da_styles.PANEL_BODY["flex"] == 1


def test_every_tab_panel_takes_the_remaining_height_and_holds_a_scroll_box(settings):
    request_id = discovery_confirmed_id(settings)
    proposed(settings, request_id)

    tree = draw_approach(settings, request_id)

    panels = components(tree, "TabsPanel")
    assert [p.value for p in panels] == ["summary", "discovery", "approach"]
    for panel in panels:
        assert panel.style == da_styles.TAB_PANEL
        assert da_styles.TAB_PANEL["minHeight"] == 0 and da_styles.TAB_PANEL["flex"] == 1
        body = panel.children
        assert isinstance(body, dmc.Box) and body.style == da_styles.PANEL_BODY


def test_the_discover_workspace_tabs_scroll_the_same_way(settings):
    request_id = da_play.to_confirmed(settings).request.request_id
    view = discover.start_discovery(settings, request_id, 0)

    tree = page.render_discover_workspace(
        understand.get_understand_view(settings, request_id), view
    )

    panels = components(tree, "TabsPanel")
    assert [p.value for p in panels] == ["summary", "discovery"]
    assert all(p.style == da_styles.TAB_PANEL for p in panels)


# --- item 2: outlined secondary buttons ---


def test_secondary_is_outlined_and_enabled_looks_clickable():
    secondary = parts.choice_button("Get help", {"type": "t", "index": 0}, parts.SECONDARY)

    assert secondary.variant == "default"  # white background, dark text, thin border
    assert secondary.color == "blue" and secondary.style == da_styles.SECONDARY_BUTTON_BORDER
    assert "gray" not in str(secondary.to_plotly_json())


def test_primary_and_normal_keep_their_blue_looks():
    primary = parts.choice_button("Go", {"type": "t", "index": 0}, parts.PRIMARY)
    normal = parts.choice_button("Other", {"type": "t", "index": 1}, parts.NORMAL)

    assert (primary.variant, normal.variant) == ("filled", "light")
    assert primary.style is None and normal.style is None


def test_a_disabled_secondary_keeps_the_disabled_look(settings):
    secondary = parts.choice_button(
        "Get help", {"type": "t", "index": 0}, parts.SECONDARY, disabled=True
    )

    # No border colour of our own, so Mantine's greyed-out disabled look is what shows.
    assert secondary.disabled is True and secondary.style is None


def test_understand_i_need_help_deciding_is_outlined(settings):
    tree = page.render_workspace(da_play.to_decision(settings))

    help_button = button(tree, "I need help deciding")
    assert help_button.variant == "default"
    assert help_button.style == da_styles.SECONDARY_BUTTON_BORDER
    choices = [
        b for b in components(tree, "Button")
        if isinstance(getattr(b, "id", None), dict) and b is not help_button
    ]
    assert choices and all(b.variant == "light" for b in choices)


def test_discover_escalate_is_outlined_and_confirm_is_not(settings):
    request_id = da_play.to_confirmed(settings).request.request_id
    view = discover.start_discovery(settings, request_id, 0)

    tree = page.render_discover_workspace(
        understand.get_understand_view(settings, request_id), view
    )

    escalate = button(tree, discover.ESCALATE_OPTION)
    assert escalate.variant == "default" and escalate.style == da_styles.SECONDARY_BUTTON_BORDER
    assert button(tree, discover.CONFIRM_OPTION).variant == "filled"


def test_approach_help_buttons_are_outlined_at_the_choice_and_test_plan_steps(settings):
    request_id = discovery_confirmed_id(settings)
    proposed(settings, request_id)
    at_choice = draw_approach(settings, request_id)

    deciding = button(at_choice, "I need help deciding")
    assert deciding.variant == "default" and deciding.style == da_styles.SECONDARY_BUTTON_BORDER
    assert button(at_choice, "Existing upload screen").variant == "filled"

    settings_two = settings
    request_two = discovery_confirmed_id(settings_two)
    at_tests(settings_two, request_two)
    at_test_plan = draw_approach(settings_two, request_two)

    get_help = button(at_test_plan, "Get help")
    assert get_help.variant == "default" and get_help.style == da_styles.SECONDARY_BUTTON_BORDER
    assert button(at_test_plan, "Accept test plan").variant == "filled"
    assert button(at_test_plan, "Add a test case").variant == "light"


def test_a_really_disabled_button_still_differs_from_the_outlined_ones(settings):
    request_id = discovery_confirmed_id(settings)
    view = at_tests(settings, request_id)
    approach.accept_test_plan(settings, request_id, view.revision)
    # The Build button shows once the workspace is ready (Phase 5), so reach that step first.
    pick(settings, request_id, good_folder())

    tree = draw_approach(settings, request_id)

    # Send is disabled while the text box is paused (Approach is button-driven at this step).
    send = [b for b in components(tree, "Button") if getattr(b, "id", "") == "da-send"][0]
    # No border colour of our own and no outlined variant: Mantine draws it greyed out.
    assert send.disabled is True
    assert getattr(send, "style", None) is None and getattr(send, "variant", None) is None
