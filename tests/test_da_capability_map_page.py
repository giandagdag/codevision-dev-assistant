"""Upgrade G step 9: the capability map page (G-11, G-12, G-13, G-15, search, filter, back)."""

import json
from pathlib import Path

from dash import Dash

from callbacks.screen_callbacks import da_capability_map_callbacks as cb
from callbacks.screen_callbacks.da_admin_page_callbacks import developer_page_style
from layouts import da_capability_map_view as view
from layouts.da_capability_map_view import (
    MAP_BACK_ID,
    MAP_GRAPH_ID,
    MAP_PATH,
    START_STATE,
    after_tap,
    crumb_text,
    filter_options,
    go_back,
    map_link,
    map_shell,
    pick_view,
    render_map,
)
from styles import da_styles
from tests.test_da_capability_map import small


def test_link_opens_the_map_in_a_new_tab():  # G-11, G-12
    link = map_link().to_plotly_json()["props"]
    assert link["href"] == MAP_PATH == "/dev-assistant/capability-map"
    assert link["target"] == "_blank"


def test_page_starts_hidden_and_hides_the_developer_page_on_its_path():
    assert map_shell().to_plotly_json()["props"]["style"] == {"display": "none"}
    assert developer_page_style(MAP_PATH) == {"display": "none"}


def test_level_one_elements_are_plain_and_have_no_admin_buttons():  # G-11, G-12
    graph, tags = small()
    elements, crumb, note, lines = render_map(pick_view(graph, tags, START_STATE), START_STATE)
    assert {e["data"]["id"] for e in elements if "source" not in e["data"]} == {
        "Payments", "Compliance", "Unassigned"
    }
    assert crumb == "All capabilities" and not note and not lines
    text = json.dumps(map_shell().to_plotly_json(), default=str)
    assert "Approve" not in text and "Restore" not in text


def test_click_capability_then_module_then_back():  # G-13
    graph, tags = small()
    state = after_tap(START_STATE, {"id": "Payments", "kind": "capability"})
    assert state == {"cap": "Payments", "module": ""}
    state = after_tap(state, {"id": "agents.pay", "kind": "module"})
    elements, crumb, _note, lines = render_map(pick_view(graph, tags, state), state)
    assert crumb == "All capabilities > Payments > agents.pay"
    assert "Functions: send" in lines and "Called by: agents.audit" in lines
    assert "Calls: agents.fees" in lines
    assert any(e["data"]["id"] == "agents.pay.send" for e in elements)
    assert go_back(state) == {"cap": "Payments", "module": ""}
    assert go_back(go_back(state)) == START_STATE
    assert after_tap(state, {"id": "agents.pay.send", "kind": "function"}) == state


def test_next_state_back_tap_and_search_hit():
    state = {"cap": "Payments", "module": "agents.pay"}
    assert cb.next_state(MAP_BACK_ID, state, None, None)["module"] == ""
    tapped = {"id": "Compliance", "kind": "capability"}
    assert cb.next_state(MAP_GRAPH_ID, state, tapped, None)["cap"] == "Compliance"
    assert cb.next_state(cb.HIT_TYPE, START_STATE, None, "agents.fees")["module"] == "agents.fees"


def test_search_box_and_filter_use_the_graph():
    graph, tags = small()
    assert [b.to_plotly_json()["props"]["children"] for b in cb.hit_buttons(graph, "rate")] == [
        "agents.fees"
    ]
    assert cb.hit_buttons(None, "rate") == []
    assert filter_options(graph, tags) == ["Compliance", "Payments", "Unassigned"]
    faded = pick_view(graph, tags, START_STATE, "Payments").nodes
    assert {n["id"] for n in faded if n["faded"]} == {"Compliance", "Unassigned"}
    assert crumb_text(START_STATE) == "All capabilities"


def test_no_server_path_no_outside_script_and_brand_colors():  # G-15
    graph, tags = small()
    elements = render_map(pick_view(graph, tags, START_STATE), START_STATE)[0]
    page = json.dumps([elements, map_shell().to_plotly_json()], default=str)
    assert "http" not in page and ":\\" not in page and "/Users/" not in page
    colors = {s["style"].get("background-color") for s in view.STYLESHEET} - {None}
    assert colors <= {da_styles.BLUE, da_styles.NAVY, da_styles.MUTED}
    assert view.STYLESHEET[0]["style"]["color"] == da_styles.INK


def test_the_callbacks_register_on_a_dash_app():
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = map_shell()
    cb.register_da_capability_map_callbacks(app)
    assert len(app.callback_map) == 2


def test_only_the_view_file_imports_cytoscape():  # swap rule G4b
    for path in Path("src").rglob("*.py"):
        if path.name != "da_capability_map_view.py":
            assert "dash_cytoscape" not in path.read_text(encoding="utf-8"), path
