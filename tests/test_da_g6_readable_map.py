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


def test_show_unassigned_and_low_slider_bring_them_back():
    graph, tags = _star()
    view = cmap.readable_view(graph, tags, show_unassigned=True, min_calls=1, top_only=False)
    assert UNASSIGNED in {n["id"] for n in view.nodes}
    assert {e["source"] for e in view.edges if e["target"] == "Hub"} >= {"A", "E"}
