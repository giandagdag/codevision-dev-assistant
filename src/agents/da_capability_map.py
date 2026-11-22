"""Plain nodes and edges for the capability map (Upgrade G, G4b/d/e/g). No AI, no drawing library.

AS400 picture: the data behind a "work with program references" screen. This file only says WHAT to
draw (nodes and edges as plain dicts). The one layout file that draws it is
layouts/da_capability_map_view.py, so swapping the drawing library changes that file only.
Module names only (agents.limits), never a folder path.
"""

from dataclasses import dataclass, field

from agents.da_code_graph import IMPORTS
from agents.da_code_impact_graph import _capabilities, _target_module

MAX_NODES = 300
UNASSIGNED = "Unassigned"
EMPTY_TEXT = "Run a Full rebuild to draw the map"


@dataclass
class MapView:
    nodes: list[dict] = field(default_factory=list)  # id, label, kind, size, faded, capability
    edges: list[dict] = field(default_factory=list)  # source, target, weight
    note: str = ""  # "Showing 300 of N, narrow with search", or the empty-graph text
    details: dict = field(default_factory=dict)  # module view: functions, callers, callees...
    unassigned: int = 0  # G6: programs hidden in Unassigned (header count)
    chips: list[dict] = field(default_factory=list)  # G6: Shared foundations, name + used_by


def _module_capabilities(graph: dict, tags: dict) -> dict[str, str]:
    caps = _capabilities(graph, tags)
    return {e["module"]: caps.get(e["module"], UNASSIGNED) for e in graph["files"].values()}


def _module_links(graph: dict) -> dict[tuple[str, str], int]:
    """(from module, to module) -> number of provable links. Self links are left out."""
    modules = {e["module"] for e in graph["files"].values()}
    links: dict[tuple[str, str], int] = {}
    for entry in graph["files"].values():
        for kind, _source, target in entry.get("edges", []):
            owner = target if kind == IMPORTS else _target_module(target, modules)
            if owner in modules and owner != entry["module"]:
                key = (entry["module"], owner)
                links[key] = links.get(key, 0) + 1
    return links


def _empty(graph: dict | None) -> bool:
    return not graph or not graph.get("files")


def _cap_nodes(graph: dict, caps: dict[str, str]) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    for capability in caps.values():
        node = nodes.setdefault(capability, _node(capability, capability, "capability", 0))
        node["size"] += 1
    return nodes


def _node(node_id: str, label: str, kind: str, size: int, faded: bool = False) -> dict:
    return {"id": node_id, "label": label, "kind": kind, "size": size, "faded": faded}


def _cap(nodes: list[dict], edges: list[dict], links: dict[str, int]) -> MapView:
    """Keep the MAX_NODES nodes with most links; drop edges that lose an end."""
    total = len(nodes)
    if total > MAX_NODES:
        nodes = sorted(nodes, key=lambda n: (-links.get(n["id"], 0), n["id"]))[:MAX_NODES]
        kept = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in kept and e["target"] in kept]
        return MapView(nodes, edges, f"Showing {MAX_NODES} of {total}, narrow with search")
    return MapView(nodes, edges)


def _degree(edges: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for edge in edges:
        for end in (edge["source"], edge["target"]):
            out[end] = out.get(end, 0) + edge["weight"]
    return out


def capabilities_view(graph: dict | None, tags: dict, highlight: str = "") -> MapView:
    """Level 1: a bubble per capability (size = modules), lines = links between capabilities.
    `highlight` is the capability filter: the other bubbles stay but fade."""
    if _empty(graph):
        return MapView(note=EMPTY_TEXT)
    caps = _module_capabilities(graph, tags)
    nodes = _cap_nodes(graph, caps)
    weights: dict[tuple[str, str], int] = {}
    for (a, b), count in _module_links(graph).items():
        pair = tuple(sorted((caps[a], caps[b])))
        if pair[0] != pair[1]:
            weights[pair] = weights.get(pair, 0) + count
    edges = [{"source": a, "target": b, "weight": w} for (a, b), w in sorted(weights.items())]
    if highlight:
        for node in nodes.values():
            node["faded"] = node["id"] != highlight
    return _cap(sorted(nodes.values(), key=lambda n: n["id"]), edges, _degree(edges))


DEFAULT_MIN_CALLS = 3  # G6 C2: slider "Show links with at least N calls" (1 to 20)
TOP_LINKS = 3  # G6 C2: "Top 3 links per capability"


def _top_links(edges: list[dict]) -> list[dict]:
    """Strongest first; an edge is drawn only while both ends have fewer than TOP_LINKS drawn."""
    drawn: dict[str, int] = {}
    kept = []
    for edge in sorted(edges, key=lambda e: (-e["weight"], e["source"], e["target"])):
        ends = (edge["source"], edge["target"])
        if all(drawn.get(end, 0) < TOP_LINKS for end in ends):
            kept.append(edge)
            for end in ends:
                drawn[end] = drawn.get(end, 0) + 1
    return sorted(kept, key=lambda e: (e["source"], e["target"]))


def readable_view(
    graph: dict | None,
    tags: dict,
    foundations: frozenset[str] = frozenset(),
    also: dict[str, list[str]] | None = None,
    show_unassigned: bool = False,
    min_calls: int = DEFAULT_MIN_CALLS,
    top_only: bool = True,
    focus: str = "",
) -> MapView:
    """G6 C1/C2/C3: the level-1 map made readable. Unassigned is hidden (its count goes to
    `view.unassigned`), links under `min_calls` and beyond the top 3 per capability are hidden,
    Shared foundations leave the picture and become `view.chips` ("Config, used by 9
    capabilities"). Around the `focus` capability every link shows. `also` maps a module name to
    the other capabilities it is in; each becomes one dashed edge (`also: True`)."""
    view = capabilities_view(graph, tags)
    if _empty(graph):
        return view
    full = view.edges
    view.unassigned = next((n["size"] for n in view.nodes if n["id"] == UNASSIGNED), 0)
    hidden = set(foundations) | ({UNASSIGNED} if not show_unassigned else set())
    # hidden ends are dropped first, so a foundation or Unassigned never uses up a "top 3" slot
    strong = [e for e in full if e["weight"] >= min_calls
              and not {e["source"], e["target"]} & (hidden - {focus})]  # fmt: skip
    edges = _top_links(strong) if top_only else strong
    if focus:
        around = [e for e in full if focus in (e["source"], e["target"])]
        edges = [e for e in edges if e not in around] + around
        hidden -= {focus}
    caps = _module_capabilities(graph, tags)
    for module, others in (also or {}).items():
        for other in others:
            main = caps.get(module, UNASSIGNED)
            if main != other:
                a, b = sorted((main, other))
                edges.append({"source": a, "target": b, "weight": 1, "also": True})
    view.chips = [
        {"name": name, "used_by": len({x for e in full for x in (e["source"], e["target"])
                                        if name in (e["source"], e["target"]) and x != name})}
        for name in sorted(foundations & {n["id"] for n in view.nodes} - {focus})
    ]  # fmt: skip
    view.nodes = [n for n in view.nodes if n["id"] not in hidden]
    kept = {n["id"] for n in view.nodes}
    view.edges = [e for e in edges if e["source"] in kept and e["target"] in kept]
    return view


def capability_view(
    graph: dict | None, tags: dict, capability: str, highlight: str = ""
) -> MapView:
    """Level 2: the modules of one capability and their links; other capabilities that they link
    to show as faded bubbles. `highlight` (the filter): only that capability's nodes stay solid."""
    if _empty(graph):
        return MapView(note=EMPTY_TEXT)
    caps = _module_capabilities(graph, tags)
    inside = sorted(m for m, c in caps.items() if c == capability)
    nodes = {m: _node(m, m, "module", 1) for m in inside}
    weights: dict[tuple[str, str], int] = {}
    for (a, b), count in _module_links(graph).items():
        if a not in nodes and b not in nodes:
            continue
        ends = []
        for m in (a, b):
            if m in nodes:
                ends.append(m)
            else:
                nodes.setdefault(caps[m], _node(caps[m], caps[m], "capability", 0, faded=True))
                ends.append(caps[m])
        weights[(ends[0], ends[1])] = weights.get((ends[0], ends[1]), 0) + count
    edges = [{"source": a, "target": b, "weight": w} for (a, b), w in sorted(weights.items())]
    if highlight:
        for node in nodes.values():
            owner = node["id"] if node["kind"] == "capability" else capability
            node["faded"] = owner != highlight
    return _cap(list(nodes.values()), edges, _degree(edges))


def module_view(graph: dict | None, tags: dict, module: str, highlight: str = "") -> MapView:
    """Level 3: one module's functions, who calls it, who it calls, capability, unresolved calls.
    `highlight` (the filter): only nodes of that capability stay solid."""
    if _empty(graph):
        return MapView(note=EMPTY_TEXT)
    caps = _module_capabilities(graph, tags)
    links = _module_links(graph)
    entry = next((e for e in graph["files"].values() if e["module"] == module), None)
    if entry is None:
        return MapView(note=f"{module} is not in the map")
    callers = sorted(a for (a, b) in links if b == module)
    callees = sorted(b for (a, b) in links if a == module)
    nodes = [_node(module, module, "module", 1)]
    nodes += [_node(f"{module}.{n}", n, "function", 1) for n in sorted(entry.get("defs", {}))]
    nodes += [_node(m, m, "module", 1, faded=True) for m in sorted({*callers, *callees})]
    edges = [{"source": a, "target": module, "weight": links[(a, module)]} for a in callers]
    edges += [{"source": module, "target": b, "weight": links[(module, b)]} for b in callees]
    if highlight:
        for node in nodes:
            owner = caps.get(node["id"], caps[module]) if node["kind"] == "module" else caps[module]
            node["faded"] = owner != highlight
    view = _cap(nodes, edges, _degree(edges))
    view.details = {
        "capability": caps[module],
        "functions": sorted(entry.get("defs", {})),
        "callers": callers,
        "callees": callees,
        "unresolved": entry.get("unresolved", 0),
    }
    return view


def search(graph: dict | None, text: str) -> list[str]:
    """Modules whose name, or one of whose function names, contains `text` (not case sensitive)."""
    needle = text.strip().lower()
    if _empty(graph) or not needle:
        return []
    found = [
        e["module"]
        for e in graph["files"].values()
        if any(needle in name.lower() for name in [e["module"], *e.get("defs", {})])
    ]
    return sorted(found)


def modules_in(graph: dict | None, tags: dict, capability: str) -> list[str]:
    """The capability filter: module names of one capability (Unassigned included)."""
    if _empty(graph):
        return []
    return sorted(m for m, c in _module_capabilities(graph, tags).items() if c == capability)
