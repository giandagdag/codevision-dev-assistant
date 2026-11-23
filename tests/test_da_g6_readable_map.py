"""Fix G6 step 12 (C1/C2/C3): the readable level-1 capability map data (G6-9)."""

from agents import da_capability_map as cmap
from agents.da_capability_map import UNASSIGNED


def _entry(module, edges=()):
    return {"module": module, "defs": {"run": "function"}, "edges": [list(e) for e in edges]}


def _star():
    """Hub calls A..E (5,4,3,2,1 links) and Config (6). Each of A..E also uses Config (4)."""
    hub_edges = [("imports", "m.hub", t) for t in ["m.a"] * 5 + ["m.b"] * 4 + ["m.c"] * 3]
    hub_edges += [("imports", "m.hub", t) for t in ["m.d"] * 2 + ["m.e"] + ["m.cfg"] * 6]
    files = {"m/hub.py": _entry("m.hub", hub_edges)}
    tags = {"m/hub.py": {"state": "approved", "proposed_capability": "Hub"}}
    for name in "abcde":
        path = f"m/{name}.py"
        files[path] = _entry(f"m.{name}", [("imports", f"m.{name}", "m.cfg")] * 4)
        tags[path] = {"state": "approved", "proposed_capability": name.upper()}
    files["m/cfg.py"] = _entry("m.cfg")
    tags["m/cfg.py"] = {"state": "approved", "proposed_capability": "Config"}
    files["m/lone.py"] = _entry("m.lone")  # no tag: Unassigned
    return {"files": files}, tags


def test_defaults_hide_unassigned_foundations_weak_and_extra_links():
    graph, tags = _star()
    view = cmap.readable_view(graph, tags, foundations=frozenset({"Config"}))
    ids = {n["id"] for n in view.nodes}
    assert UNASSIGNED not in ids and "Config" not in ids and view.unassigned == 1
    assert [(c["name"], c["used_by"]) for c in view.chips] == [("Config", 6)]
    # edge ends are sorted by name, so the hub is the target
    assert {e["source"]: e["weight"] for e in view.edges} == {"A": 5, "B": 4, "C": 3}


def test_focus_shows_weak_links_and_also_edge_is_dashed():
    graph, tags = _star()
    view = cmap.readable_view(
        graph, tags, frozenset({"Config"}), {"m.a": ["B"]}, focus="Hub"
    )
    pairs = {(e["source"], e["target"]): e.get("also", False) for e in view.edges}
    assert ("E", "Hub") in pairs and pairs[("A", "B")] is True


def test_also_edge_obeys_the_top_3_cut_unless_around_the_focus():  # G6-b
    graph, tags = _star()
    also = {"m.e": ["Hub"], "m.a": ["B"]}  # Hub already has A, B, C drawn: full; A has Hub only
    view = cmap.readable_view(graph, tags, frozenset({"Config"}), also)
    assert not [e for e in view.edges if e.get("also") and "Hub" in (e["source"], e["target"])]
    free = cmap.readable_view(graph, tags, frozenset({"Config"}), {"m.a": ["B"], "m.b": ["A"]})
    assert [(e["source"], e["target"]) for e in free.edges if e.get("also")] == [("A", "B")]  # one
    around = cmap.readable_view(graph, tags, frozenset({"Config"}), also, focus="Hub")
    assert [e for e in around.edges if e.get("also") and "Hub" in (e["source"], e["target"])]


def test_empty_space_click_clears_the_focus_and_is_wired():
    from callbacks.screen_callbacks.da_capability_map_callbacks import next_state
    from layouts import da_capability_map_view as v

    state = {**v.START_STATE, "focus": "Hub"}
    assert next_state(v.MAP_BG_ID, state, None, None)["focus"] == ""
    assert "cy.on('tap'" in v.BACKGROUND_TAP_JS and "e.target === cy" in v.BACKGROUND_TAP_JS


def test_click_focus_keeps_neighbours_bright_and_panel_lists_links_g6_10():
    graph, tags = _star()
    view = cmap.readable_view(graph, tags, frozenset({"Config"}), focus="A")
    faded = {n["id"]: n["faded"] for n in view.nodes}
    assert faded == {"A": False, "Hub": False, "B": True, "C": True, "D": True, "E": True}
    assert [(e["source"], e["target"]) for e in view.edges if e["focused"]] == [("A", "Hub")]
    panel = cmap.focus_panel(graph, tags, "Hub")
    assert {"capability": "A", "calls": 5, "programs": 1} in panel["out"]
    assert panel["top_programs"][0] == {"module": "m.hub", "calls": 21}
    assert len(panel["top_programs"]) <= 5


def test_one_tap_focuses_two_quick_taps_or_open_move_in_and_clear_resets():
    from layouts import da_capability_map_view as v

    node = {"id": "Hub", "kind": "capability"}
    one = v.tap_state(v.START_STATE, node, 1000)
    assert one["focus"] == "Hub" and one["cap"] == ""
    assert v.tap_state(one, node, 1900)["focus"] == "Hub"  # too slow: still a single tap
    assert v.tap_state(one, node, 1300)["cap"] == "Hub"  # double click moves in
    assert v.open_focus(one)["cap"] == "Hub"
    assert v.clear_focus(one)["focus"] == ""
    assert "Calls: " in "\n".join(v.panel_lines("Hub", cmap.focus_panel(*_star(), "Hub")))


def test_drawing_rules_g6_11_g6_12():
    from layouts import da_capability_map_view as v
    from styles.da_admin_styles import CAPABILITY_PALETTE, capability_colour

    node_style = v.STYLESHEET[0]["style"]
    assert node_style["text-wrap"] == "wrap" and "text-overflow-wrap" not in node_style  # G6-11
    assert node_style["text-valign"] == "bottom" and node_style["font-size"] == 12
    assert v.LAYOUT["name"] == "concentric"
    graph, tags = _star()
    state = v.START_STATE
    draw = lambda: v.render_map(v.pick_view(graph, tags, state, "", [], {}), state)[0]  # noqa: E731
    assert draw() == draw()  # G6-12: same data, same drawing
    nodes = [e["data"] for e in draw() if "source" not in e["data"]]
    assert max(n["px"] for n in nodes) <= 3 * min(n["px"] for n in nodes)
    assert all(1 <= e["data"]["px"] <= 6 for e in draw() if "source" in e["data"])
    assert capability_colour("Embedding and Vector") == capability_colour("Embedding and Vector")
    assert capability_colour("Hub") in CAPABILITY_PALETTE


def test_show_unassigned_and_low_slider_bring_them_back():
    graph, tags = _star()
    view = cmap.readable_view(graph, tags, show_unassigned=True, min_calls=1, top_only=False)
    assert UNASSIGNED in {n["id"] for n in view.nodes}
    assert {e["source"] for e in view.edges if e["target"] == "Hub"} >= {"A", "E"}
