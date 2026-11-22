"""The capability map page (Upgrade G, G4a/c/d/f). The ONLY file that imports dash_cytoscape.

AS400 picture: a "work with program references" screen drawn as bubbles. The data comes from
agents/da_capability_map.py as plain nodes and edges; this file only draws them. If cytoscape
fails at work, replace this one file (and its tests) with a Plotly drawing.
Read only: no Admin buttons. Colors come from the brand constants, never library defaults.
"""

import math

import dash_cytoscape as cyto
import dash_mantine_components as dmc
from dash import dcc, html

from agents.da_capability_map import (
    UNASSIGNED,
    MapView,
    capabilities_view,
    capability_view,
    module_view,
    readable_view,
    search,
)
from styles import da_styles
from styles.da_admin_styles import capability_colour

BASE_PX = 36  # the smallest bubble
MAX_SIZE_RATIO = 3

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
MAP_OPEN_ID = "da-map-open"
MAP_CLEAR_ID = "da-map-clear"
MAP_UNASSIGNED_ID = "da-map-unassigned"
MAP_MIN_CALLS_ID = "da-map-min-calls"
MAP_TOP_ID = "da-map-top"
MAP_SHOW_UNASSIGNED_ID = "da-map-show-unassigned"
MAP_CHIPS_ID = "da-map-chips"
MAP_PANEL_ID = "da-map-panel"
# Hidden but still as wide as the page: cytoscape lays the bubbles out at the size it sees when the
# elements arrive, and a display:none box is 0 wide (the picture came out off centre, unfitted).
HIDDEN = {"visibility": "hidden", "height": 0, "overflow": "hidden"}
MAP_VIEW_ID = "da-map-view"
MAP_PICTURE_ID = "da-map-picture"
MAP_TABLE_ID = "da-map-table"
MAP_SORT_ID = "da-map-sort"
VIEW_MAP, VIEW_LINKS = "Map", "Links"
SORT_MOST, SORT_FEWEST = "Most calls first", "Fewest calls first"
LINK_HEADS = ["From", "To", "Calls", "Programs", "Also"]
START_STATE = {"cap": "", "module": "", "focus": "", "tap": ["", 0]}
FOUNDATION = "Shared foundation"
DOUBLE_TAP_MS = 500  # two taps this close on one bubble count as a double click
# the Review queue (Admin address of Fix G5 N5; cannot import its constant here)
ADMIN_LINK = "/admin?tab=catalog&view=queue"
CHIP_TYPE = "da-map-chip"

FONT = da_styles.FONT
LABEL_WIDTH = 90  # pixels; labels wrap here
# G6 C5: concentric puts the most-linked bubble in the middle and gives the same picture every
# time (cose moved bubbles around on each draw). Labels count in the spacing.
LAYOUT = {"name": "concentric", "nodeDimensionsIncludeLabels": True, "minNodeSpacing": 60,
          "animate": False}  # fmt: skip
STYLESHEET = [
    {"selector": "node", "style": {
        "label": "data(label)", "background-color": "data(color)", "color": da_styles.INK,
        "font-family": FONT, "font-size": 12, "width": "data(px)", "height": "data(px)",
        # Wrap at spaces only (G6-11), the label sits below the bubble on a white background.
        "text-wrap": "wrap", "text-max-width": LABEL_WIDTH, "text-valign": "bottom",
        "text-margin-y": 6, "text-background-color": "white", "text-background-opacity": 1,
        "text-background-padding": 2,
    }},
    {"selector": ".function",
     "style": {"background-color": da_styles.NAVY, "shape": "round-rectangle"}},
    {"selector": ".faded", "style": {"opacity": 0.35, "background-color": da_styles.MUTED}},
    {"selector": "edge", "style": {
        "line-color": da_styles.MUTED, "width": "data(px)", "curve-style": "bezier",
        "target-arrow-color": da_styles.MUTED,
    }},
    # G6 C4: arrows only on the links of the focused capability
    {"selector": ".focused", "style": {"target-arrow-shape": "triangle"}},
    {"selector": ".also", "style": {"line-style": "dashed"}},
]  # fmt: skip


def map_link(new_tab: bool = True) -> dmc.Anchor:
    """The 'Open capability map' link used on the Admin catalog and on Discover."""
    return dmc.Anchor(MAP_LINK_TEXT, href=MAP_PATH, target="_blank" if new_tab else "_self",
                      size="sm")  # fmt: skip


def _elements(view: MapView) -> list[dict]:
    """Plain nodes and edges to cytoscape elements."""
    out = []
    smallest = min((n["size"] for n in view.nodes if n["size"] > 0), default=1)
    for node in view.nodes:
        classes = " ".join(c for c in (node["kind"], "faded" if node["faded"] else "") if c)
        # bubble size by program count, never more than 3 times the smallest bubble
        px = round(BASE_PX * min(max(node["size"], smallest) / smallest, MAX_SIZE_RATIO))
        colour = capability_colour(node["label"])
        data = {"id": node["id"], "label": node["label"], "kind": node["kind"], "px": px,
                "color": colour}  # fmt: skip
        out.append({"data": data, "classes": classes})
    for i, edge in enumerate(view.edges):
        # width 1 to 6 px by the log of the calls: one hot link cannot drown the rest
        data = {"id": f"e{i}", "source": edge["source"], "target": edge["target"],
                "px": min(6, 1 + int(math.log2(max(edge["weight"], 1))))}  # fmt: skip
        # levels 2 and 3 have no "focused" key: their calls keep their arrows
        classes = " ".join(c for c in ("focused" if edge.get("focused", True) else "",
                                       "also" if edge.get("also") else "") if c)  # fmt: skip
        out.append({"data": data, "classes": classes})
    return out


def pick_view(
    graph: dict | None, tags: dict, state: dict, highlight: str = "",
    capabilities: list | None = None, opts: dict | None = None,
) -> MapView:  # fmt: skip
    """Which level the state asks for: capabilities, one capability, one module. At the top level
    `opts` (G6: show_unassigned, min_calls, top_only) asks for the readable map."""
    if state.get("module"):
        view = module_view(graph, tags, state["module"], highlight)
    elif state.get("cap"):
        view = capability_view(graph, tags, state["cap"], highlight)
    elif opts is not None:
        view = _readable(graph, tags, state, highlight, capabilities or [], opts)
    else:
        view = capabilities_view(graph, tags, highlight)
    return _short_labels(view, graph, state.get("module", ""))


def also_map(graph: dict | None, capabilities: list) -> dict[str, list[str]]:
    """Module name -> the other capabilities it is also in (main one left out)."""
    from agents.da_admin_meaning import capabilities_of  # late: heavy module

    also = {}
    for path, entry in (graph or {}).get("files", {}).items():
        extra = capabilities_of(path, capabilities)[1]
        if extra:
            also[entry["module"]] = extra
    return also


def _readable(graph, tags, state, highlight, capabilities, opts) -> MapView:
    foundations = frozenset(c.name for c in capabilities if c.kind == FOUNDATION)
    also = also_map(graph, capabilities)
    view = readable_view(graph, tags, foundations, also, focus=state.get("focus", ""), **opts)
    if highlight:
        for node in view.nodes:
            node["faded"] = node["id"] != highlight
    return view


def _short_labels(view: MapView, graph: dict | None, module: str) -> MapView:
    """P39: a module bubble shows the file name without folders and `.py` (the last part of the
    dotted module name); the full path is added to the details that a click opens."""
    for node in view.nodes:
        if node["kind"] == "module":
            node["label"] = node["id"].rsplit(".", 1)[-1]
    paths = {e["module"]: path for path, e in (graph or {}).get("files", {}).items()}
    if view.details and module in paths:
        view.details["path"] = paths[module]
    return view


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
    return dict(START_STATE)


def panel_lines(name: str, panel: dict) -> list[str]:
    """G6 C4 side panel text for the focused capability."""
    if not name:
        return []
    lines = [name]
    for side, word in (("out", "Calls"), ("in", "Called by")):
        rows = [
            f"{r['capability']}: {r['calls']} calls ({r['programs']} programs)" for r in panel[side]
        ]
        lines.append(f"{word}: " + ("; ".join(rows) or "none"))
    top = ", ".join(f"{p['module']} ({p['calls']})" for p in panel["top_programs"])
    lines.append("Top programs: " + (top or "none"))
    return lines


def links_table_view(rows: list[dict]) -> dmc.Table:
    """G6 C6: from, to, calls, programs; a row that is only an also-in membership says "also"."""
    head = dmc.TableThead(dmc.TableTr([dmc.TableTh(h) for h in LINK_HEADS]))
    body = dmc.TableTbody([
        dmc.TableTr([dmc.TableTd(r["from"]), dmc.TableTd(r["to"]), dmc.TableTd(r["calls"]),
                     dmc.TableTd(r["programs"]), dmc.TableTd("also" if r["also"] else "")])
        for r in rows
    ])  # fmt: skip
    return dmc.Table([head, body], striped=True, withTableBorder=True)


def chip_text(chip: dict) -> str:
    return f"{chip['name']}, used by {chip['used_by']} capabilities"


def after_tap(state: dict, node: dict | None) -> dict:
    """A click on a bubble goes one level down; functions do nothing."""
    if not node:
        return state
    if node.get("kind") == "capability":
        return {"cap": node["id"], "module": ""}
    if node.get("kind") == "module":
        return {**state, "module": node["id"]}
    return state


def tap_state(state: dict, node: dict | None, stamp: float = 0) -> dict:
    """G6 C4. At the top level one tap focuses a bubble; a second tap on the same bubble within
    DOUBLE_TAP_MS moves in (the Open button is the sure way). Deeper levels keep today's tap."""
    if not node or state.get("cap") or state.get("module"):
        return after_tap(state, node)
    if node.get("kind") != "capability":
        return state
    last_id, last_stamp = state.get("tap") or ["", 0]
    if node["id"] == last_id and 0 < stamp - last_stamp <= DOUBLE_TAP_MS:
        return {**START_STATE, "cap": node["id"]}
    return {**state, "focus": node["id"], "tap": [node["id"], stamp]}


def open_focus(state: dict) -> dict:
    return {**START_STATE, "cap": state["focus"]} if state.get("focus") else state


def clear_focus(state: dict) -> dict:
    return {**state, "focus": "", "tap": ["", 0]}


def unassigned_text(count: int) -> str:
    return f"{count} programs unassigned" if count else ""


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
        *([f"File: {d['path']}"] if d.get("path") else []),
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
        id=MAP_GRAPH_ID, elements=[], stylesheet=STYLESHEET, layout=LAYOUT,
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
    focus_bar = dmc.Group(
        [dmc.Switch(id=MAP_SHOW_UNASSIGNED_ID, label="Show unassigned programs", checked=False),
         dmc.Switch(id=MAP_TOP_ID, label="Top 3 links per capability", checked=True),
         dmc.Text("Show links with at least N calls", size="sm"),
         dmc.Slider(id=MAP_MIN_CALLS_ID, min=1, max=20, step=1, value=3, w=200),
         dmc.Button("Open", id=MAP_OPEN_ID, variant="light", size="xs"),
         dmc.Button("Clear focus", id=MAP_CLEAR_ID, variant="subtle", size="xs")],
        px="md",
    )  # fmt: skip
    switch = dmc.Group(
        [dmc.SegmentedControl(id=MAP_VIEW_ID, data=[VIEW_MAP, VIEW_LINKS], value=VIEW_MAP,
                              size="xs"),
         dmc.Select(id=MAP_SORT_ID, data=[SORT_MOST, SORT_FEWEST], value=SORT_MOST,
                    allowDeselect=False, size="xs", w=180)],
        px="md",
    )  # fmt: skip
    picture = html.Div(
        [focus_bar, html.Div(id=MAP_UNASSIGNED_ID, style={"padding": "0 16px"}),
         html.Div(id=MAP_HITS_ID, style={"padding": "0 16px"}),
         dmc.Text(id=MAP_NOTE_ID, size="sm", c=da_styles.MUTED, px="md"),
         graph, html.Div(id=MAP_CHIPS_ID, style={"padding": "8px 16px"}),
         html.Div(id=MAP_PANEL_ID, style={"padding": "0 16px"}),
         html.Div(id=MAP_DETAILS_ID, style={"padding": "16px"})],
        id=MAP_PICTURE_ID,
    )  # fmt: skip
    return html.Div(
        [bar, switch, picture,
         html.Div(id=MAP_TABLE_ID, style={"display": "none", "padding": "16px"}),
         dcc.Store(id=MAP_STATE_ID, data=START_STATE)],
        id=MAP_SHELL_ID, style=HIDDEN,
    )  # fmt: skip
