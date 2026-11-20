"""The capability map page (Upgrade G, G4a/c/d/f). The ONLY file that imports dash_cytoscape.

AS400 picture: a "work with program references" screen drawn as bubbles. The data comes from
agents/da_capability_map.py as plain nodes and edges; this file only draws them. If cytoscape
fails at work, replace this one file (and its tests) with a Plotly drawing.
Read only: no Admin buttons. Colors come from the brand constants, never library defaults.
"""

import dash_cytoscape as cyto
import dash_mantine_components as dmc
from dash import dcc, html

from agents.da_capability_map import (
    UNASSIGNED,
    MapView,
    capabilities_view,
    capability_view,
    module_view,
    search,
)
from styles import da_styles

MAP_PATH = "/dev-assistant/capability-map"
MAP_SHELL_ID = "da-map-shell"
MAP_GRAPH_ID = "da-map-graph"
MAP_STATE_ID = "da-map-state"
MAP_BACK_ID = "da-map-back"
MAP_CRUMB_ID = "da-map-crumb"
MAP_NOTE_ID = "da-map-note"
MAP_DETAILS_ID = "da-map-details"
MAP_SEARCH_ID = "da-map-search"
MAP_FILTER_ID = "da-map-filter"
MAP_HITS_ID = "da-map-hits"
MAP_LINK_TEXT = "Open capability map"
START_STATE = {"cap": "", "module": ""}

FONT = da_styles.FONT
STYLESHEET = [
    {"selector": "node", "style": {
        "label": "data(label)", "background-color": da_styles.BLUE, "color": da_styles.INK,
        "font-family": FONT, "font-size": 12, "width": "data(px)", "height": "data(px)",
    }},
    {"selector": ".function",
     "style": {"background-color": da_styles.NAVY, "shape": "round-rectangle"}},
    {"selector": ".faded", "style": {"opacity": 0.35, "background-color": da_styles.MUTED}},
    {"selector": "edge", "style": {
        "line-color": da_styles.MUTED, "width": "data(px)", "curve-style": "bezier",
        "target-arrow-shape": "triangle", "target-arrow-color": da_styles.MUTED,
    }},
]  # fmt: skip


def map_link(new_tab: bool = True) -> dmc.Anchor:
    """The 'Open capability map' link used on the Admin catalog and on Discover."""
    return dmc.Anchor(MAP_LINK_TEXT, href=MAP_PATH, target="_blank" if new_tab else "_self",
                      size="sm")  # fmt: skip


def _elements(view: MapView) -> list[dict]:
    """Plain nodes and edges to cytoscape elements."""
    out = []
    for node in view.nodes:
        classes = " ".join(c for c in (node["kind"], "faded" if node["faded"] else "") if c)
        px = 30 + min(node["size"], 40) * 3
        data = {"id": node["id"], "label": node["label"], "kind": node["kind"], "px": px}
        out.append({"data": data, "classes": classes})
    for i, edge in enumerate(view.edges):
        data = {"id": f"e{i}", "source": edge["source"], "target": edge["target"],
                "px": 1 + min(edge["weight"], 10)}  # fmt: skip
        out.append({"data": data})
    return out


def pick_view(graph: dict | None, tags: dict, state: dict, highlight: str = "") -> MapView:
    """Which level the state asks for: capabilities, one capability, one module."""
    if state.get("module"):
        return module_view(graph, tags, state["module"], highlight)
    if state.get("cap"):
        return capability_view(graph, tags, state["cap"], highlight)
    return capabilities_view(graph, tags, highlight)


def crumb_text(state: dict) -> str:
    parts = ["All capabilities"]
    if state.get("cap"):
        parts.append(state["cap"])
    if state.get("module"):
        parts.append(state["module"])
    return " > ".join(parts)


def go_back(state: dict) -> dict:
    if state.get("module"):
        return {**state, "module": ""}
    return {"cap": "", "module": ""}


def after_tap(state: dict, node: dict | None) -> dict:
    """A click on a bubble goes one level down; functions do nothing."""
    if not node:
        return state
    if node.get("kind") == "capability":
        return {"cap": node["id"], "module": ""}
    if node.get("kind") == "module":
        return {**state, "module": node["id"]}
    return state


def search_hits(graph: dict | None, text: str) -> list[str]:
    return search(graph, text)[:20]


def filter_options(graph: dict | None, tags: dict) -> list[str]:
    """Capability names for the filter, 'Unassigned' always last."""
    nodes = capabilities_view(graph, tags).nodes
    names = {n["id"] for n in nodes} - {UNASSIGNED}
    return [*sorted(names), UNASSIGNED] if nodes else []


def details_lines(view: MapView) -> list[str]:
    """The module click: functions, callers, callees, capability, unresolved calls."""
    d = view.details
    if not d:
        return []
    return [
        f"Capability: {d['capability']}",
        "Functions: " + (", ".join(d["functions"]) or "none"),
        "Called by: " + (", ".join(d["callers"]) or "none"),
        "Calls: " + (", ".join(d["callees"]) or "none"),
        f"Calls we could not resolve: {d['unresolved']}",
    ]


def render_map(view: MapView, state: dict) -> tuple[list[dict], str, str, list]:
    """(elements, crumb text, note, detail lines) for the page."""
    return _elements(view), crumb_text(state), view.note, details_lines(view)


def map_shell() -> html.Div:
    """Drawn once at start-up, hidden until the URL is the map path."""
    graph = cyto.Cytoscape(
        id=MAP_GRAPH_ID, elements=[], stylesheet=STYLESHEET, layout={"name": "cose"},
        style={"width": "100%", "height": "560px", "background": da_styles.CANVAS},
        userZoomingEnabled=True, userPanningEnabled=True,
    )  # fmt: skip
    bar = dmc.Group(
        [dmc.Button("Back", id=MAP_BACK_ID, variant="light", size="xs"),
         dmc.Text(id=MAP_CRUMB_ID, size="sm", c=da_styles.MUTED),
         dmc.TextInput(id=MAP_SEARCH_ID, placeholder="Search module or function name",
                       debounce=True, size="xs", w=280),
         dmc.Select(id=MAP_FILTER_ID, placeholder="Capability filter", data=[], clearable=True,
                    size="xs", w=220)],
        p="md",
    )  # fmt: skip
    return html.Div(
        [bar, html.Div(id=MAP_HITS_ID, style={"padding": "0 16px"}),
         dmc.Text(id=MAP_NOTE_ID, size="sm", c=da_styles.MUTED, px="md"),
         graph, html.Div(id=MAP_DETAILS_ID, style={"padding": "16px"}),
         dcc.Store(id=MAP_STATE_ID, data=START_STATE)],
        id=MAP_SHELL_ID, style={"display": "none"},
    )  # fmt: skip
