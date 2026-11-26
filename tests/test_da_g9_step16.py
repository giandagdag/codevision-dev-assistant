"""G9 step 16 (S2, S4): the See the findings button, and a redraw that keeps the user's tab.

The scrolling and tab memory run in the browser (clientside callbacks); here we check what the
server draws for them: the button, the ids, the key store, and that the callbacks are wired."""

import pytest
from dash import Dash

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from layouts import da_developer_assistant_page as page
from layouts import da_tester_panel as tp
from tests.da_build_play import ready_with_workspace
from tests.da_tree import by_id, components

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


def draw_not_passing(settings, monkeypatch):
    request_id = ready_with_workspace(settings)[0]
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"review_must_fix_always"}))
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    return cb.show_page(f"?request={request_id}", 0)


def test_g9_15_see_the_findings_is_a_button_with_its_own_id(settings, monkeypatch):
    tree = draw_not_passing(settings, monkeypatch)

    button = by_id(tree, tp.SEE_FINDINGS_ID)

    assert button is not None and "Button" in type(button).__name__
    assert by_id(tree, tp.FINDINGS_ID) is not None  # the table it scrolls to
    assert not [a for a in components(tree, "Anchor") if "#" in str(getattr(a, "href", ""))]


def test_g9_16_every_draw_names_its_tab_and_step_so_a_redraw_can_keep_the_tab(
    settings, monkeypatch
):
    first = draw_not_passing(settings, monkeypatch)
    request_id = next(
        c for c in components(first, "Store") if c.id == page.STATE_ID
    ).data["request_id"]

    second = cb.show_page(f"?request={request_id}", 1)  # a redraw, e.g. after a Dispute

    keys = [
        c.data for t in (first, second) for c in components(t, "Store") if c.id == page.TAB_KEY_ID
    ]
    assert keys[0] == keys[1] and keys[0].endswith("|build")  # same step: the tab can be kept
    assert by_id(first, page.TABS_ID) is not None


def test_g9_16_the_tab_callbacks_are_registered_on_the_static_memory_store():
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = page.layout()
    cb.register_da_developer_assistant_page_callbacks(app)

    assert page.TAB_MEMORY_ID in str(page.layout())  # outside the redrawn content
    outputs = " ".join(app.callback_map)
    assert page.TAB_MEMORY_ID in outputs and page.TABS_ID in outputs


def test_the_restore_script_keeps_a_tab_only_for_the_same_key():
    js = cb.RESTORE_TAB_JS
    assert "memory.key === key" in js and "return [memory.tab" in js
    assert "null" in js  # a new step clears the memory
