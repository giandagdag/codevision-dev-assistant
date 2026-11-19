"""Upgrade G step 8: capability map data (G-13 data part, G-14, G-16, G4g, search, filter)."""

from pathlib import Path

from agents import da_capability_map as cmap
from agents.da_capability_map import (
    EMPTY_TEXT,
    MAX_NODES,
    UNASSIGNED,
    capabilities_view,
    capability_view,
    module_view,
    modules_in,
    search,
)


def entry(module, defs=("run",), edges=(), unresolved=0):
    return {
        "module": module,
        "defs": {name: "function" for name in defs},
        "edges": [list(e) for e in edges],
        "unresolved": unresolved,
    }


def tag(capability):
    return {"state": "approved", "proposed_capability": capability}


def small():
    pay_calls = [("calls", "agents.pay.send", "agents.fees.rate")]
    audit_imports = [("imports", "agents.audit", "agents.pay")]
    graph = {"files": {
        "agents/pay.py": entry("agents.pay", ("send",), pay_calls),
        "agents/fees.py": entry("agents.fees", ("rate",), unresolved=2),
        "agents/audit.py": entry("agents.audit", ("log",), audit_imports),
        "agents/misc.py": entry("agents.misc", ("odd",)),
    }}
    tags = {
        "agents/pay.py": tag("Payments"),
        "agents/fees.py": tag("Payments"),
        "agents/audit.py": tag("Compliance"),
    }
    return graph, tags


def test_level_one_has_capability_bubbles_unassigned_and_links():
    graph, tags = small()
    view = capabilities_view(graph, tags)
    sizes = {n["id"]: n["size"] for n in view.nodes}
    assert sizes == {"Payments": 2, "Compliance": 1, UNASSIGNED: 1}
    assert [(e["source"], e["target"], e["weight"]) for e in view.edges] == [
        ("Compliance", "Payments", 1)
    ]


def test_capability_filter_fades_the_other_bubbles():
    graph, tags = small()
    view = capabilities_view(graph, tags, highlight="Payments")
    assert {n["id"]: n["faded"] for n in view.nodes} == {
        "Payments": False, "Compliance": True, UNASSIGNED: True
    }


def test_capability_click_shows_modules_links_and_faded_neighbours():  # G-13 data
    graph, tags = small()
    view = capability_view(graph, tags, "Payments")
    nodes = {n["id"]: n for n in view.nodes}
    assert set(nodes) == {"agents.pay", "agents.fees", "Compliance"}
    assert nodes["Compliance"]["faded"] and not nodes["agents.pay"]["faded"]
    pairs = {(e["source"], e["target"]) for e in view.edges}
    assert pairs == {("agents.pay", "agents.fees"), ("Compliance", "agents.pay")}


def test_module_click_shows_functions_callers_callees():  # G-13 data
    graph, tags = small()
    view = module_view(graph, tags, "agents.pay")
    assert view.details == {
        "capability": "Payments",
        "functions": ["send"],
        "callers": ["agents.audit"],
        "callees": ["agents.fees"],
        "unresolved": 0,
    }
    assert module_view(graph, tags, "agents.fees").details["unresolved"] == 2


def test_over_300_nodes_shows_300_with_a_note():  # G-14
    files = {
        f"m{n}.py": entry(f"m{n}", edges=[("imports", f"m{n}", "m0")] if n else [])
        for n in range(1000)
    }
    graph = {"files": files}
    view = capability_view(graph, {}, UNASSIGNED)
    assert len(view.nodes) == MAX_NODES
    assert view.note == "Showing 300 of 1000, narrow with search"
    assert "m0" in {n["id"] for n in view.nodes}  # most linked module survives the cut
    kept = {n["id"] for n in view.nodes}
    assert all(e["source"] in kept and e["target"] in kept for e in view.edges)


def test_empty_or_missing_graph_says_run_a_full_rebuild():  # G4g
    for graph in (None, {"files": {}}):
        assert capabilities_view(graph, {}).note == EMPTY_TEXT
        assert capability_view(graph, {}, "X").note == EMPTY_TEXT
        assert module_view(graph, {}, "x").note == EMPTY_TEXT
    assert EMPTY_TEXT == "Run a Full rebuild to draw the map"


def test_search_finds_module_or_function_names():
    graph, _ = small()
    assert search(graph, "FEES") == ["agents.fees"]
    assert search(graph, "send") == ["agents.pay"]
    assert search(graph, "  ") == [] and search(None, "x") == []


def test_capability_filter_lists_modules_including_unassigned():
    graph, tags = small()
    assert modules_in(graph, tags, "Payments") == ["agents.fees", "agents.pay"]
    assert modules_in(graph, tags, UNASSIGNED) == ["agents.misc"]


def test_no_path_in_the_data():
    graph, tags = small()
    text = str(capabilities_view(graph, tags)) + str(module_view(graph, tags, "agents.pay"))
    assert "/" not in text and "\\" not in text


def test_map_data_does_not_import_cytoscape():  # G-16
    imports = [
        line for line in Path(cmap.__file__).read_text(encoding="utf-8").splitlines()
        if line.startswith(("import ", "from "))
    ]
    assert not any("cytoscape" in line for line in imports)
