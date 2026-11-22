"""Wires the capability map page (Upgrade G, G4c/d). Read only: nothing here writes anything."""

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, ctx

from agents.da_admin_index import index_dir
from agents.da_admin_tag_store import read_tags
from agents.da_capability_map import focus_panel
from agents.da_code_graph import load_graph
from agents.da_code_impact_graph import with_catalog_tags
from callbacks.screen_callbacks.da_developer_assistant_page_callbacks import get_settings
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_rulebook import RulebookError, get_active_version
from layouts.da_capability_map_view import (
    ADMIN_LINK,
    MAP_BACK_ID,
    MAP_CHIPS_ID,
    MAP_CLEAR_ID,
    MAP_CRUMB_ID,
    MAP_DETAILS_ID,
    MAP_FILTER_ID,
    MAP_GRAPH_ID,
    MAP_HITS_ID,
    MAP_MIN_CALLS_ID,
    MAP_NOTE_ID,
    MAP_OPEN_ID,
    MAP_PANEL_ID,
    MAP_PATH,
    MAP_SEARCH_ID,
    MAP_SHELL_ID,
    MAP_SHOW_UNASSIGNED_ID,
    MAP_STATE_ID,
    MAP_TOP_ID,
    MAP_UNASSIGNED_ID,
    START_STATE,
    chip_text,
    clear_focus,
    filter_options,
    go_back,
    open_focus,
    panel_lines,
    pick_view,
    render_map,
    search_hits,
    tap_state,
    unassigned_text,
)
from layouts.da_developer_assistant_page import LOCATION_ID

HIT_TYPE = "da-map-hit"


def next_state(
    trigger, state: dict, tapped: dict | None, picked: str | None, stamp: float = 0
) -> dict:
    """One place that decides the new state, so it can be tested without a browser."""
    state = state or START_STATE
    if trigger == MAP_BACK_ID:
        return go_back(state)
    if trigger == MAP_OPEN_ID:
        return open_focus(state)
    if trigger == MAP_CLEAR_ID:
        return clear_focus(state)
    if trigger == MAP_GRAPH_ID:
        return tap_state(state, tapped, stamp)
    if picked:
        return {**state, "module": picked}
    return state


def catalog_capabilities() -> list:
    """The active rulebook's capabilities (the Admin catalog's source). None yet: no patterns."""
    try:
        version = get_active_version(get_settings().db_path)
    except (RulebookError, DatabaseBusyError):
        return []
    return version.rulebook.policy.capabilities if version else []


def hit_buttons(graph: dict | None, text: str) -> list:
    return [
        dmc.Button(m, id={"type": HIT_TYPE, "name": m}, variant="subtle", size="xs")
        for m in search_hits(graph, text)
    ]


def register_da_capability_map_callbacks(app) -> None:
    @app.callback(
        Output(MAP_STATE_ID, "data"),
        Input(MAP_BACK_ID, "n_clicks"),
        Input(MAP_OPEN_ID, "n_clicks"),
        Input(MAP_CLEAR_ID, "n_clicks"),
        Input(MAP_GRAPH_ID, "tapNode"),  # has a time stamp, so a second tap on a node still fires
        Input({"type": HIT_TYPE, "name": ALL}, "n_clicks"),
        State(MAP_STATE_ID, "data"),
        prevent_initial_call=True,
    )
    def move(_back, _open, _clear, tap, _hits, state):
        tapped = (tap or {}).get("data")
        stamp = (tap or {}).get("timeStamp") or 0
        trigger = ctx.triggered_id
        picked = trigger["name"] if isinstance(trigger, dict) else None
        if isinstance(trigger, dict) and not any(_hits):
            return state  # the hit list was redrawn: not a real click
        known = (MAP_BACK_ID, MAP_OPEN_ID, MAP_CLEAR_ID, MAP_GRAPH_ID)
        kind = trigger if trigger in known else HIT_TYPE
        return next_state(kind, state, tapped, picked, stamp)

    @app.callback(
        Output(MAP_SHELL_ID, "style"),
        Output(MAP_GRAPH_ID, "elements"),
        Output(MAP_CRUMB_ID, "children"),
        Output(MAP_NOTE_ID, "children"),
        Output(MAP_DETAILS_ID, "children"),
        Output(MAP_HITS_ID, "children"),
        Output(MAP_FILTER_ID, "data"),
        Output(MAP_UNASSIGNED_ID, "children"),
        Output(MAP_CHIPS_ID, "children"),
        Output(MAP_PANEL_ID, "children"),
        Input(LOCATION_ID, "pathname"),
        Input(MAP_STATE_ID, "data"),
        Input(MAP_SEARCH_ID, "value"),
        Input(MAP_FILTER_ID, "value"),
        Input(MAP_SHOW_UNASSIGNED_ID, "checked"),
        Input(MAP_TOP_ID, "checked"),
        Input(MAP_MIN_CALLS_ID, "value"),
    )
    def show_map(pathname, state, text, chosen, show_unassigned, top_only, min_calls):
        if pathname != MAP_PATH:
            return {"display": "none"}, [], "", "", [], [], [], [], [], []
        graph = load_graph(index_dir())
        capabilities = catalog_capabilities()
        tags = with_catalog_tags(graph, read_tags(), capabilities) if graph else {}
        state = state or START_STATE
        opts = {"show_unassigned": bool(show_unassigned), "top_only": bool(top_only),
                "min_calls": int(min_calls or 1)}  # fmt: skip
        view = pick_view(graph, tags, state, chosen or "", capabilities, opts)
        elements, crumb, note, lines = render_map(view, state)
        details = [dmc.Text(line, size="sm") for line in lines]
        focus = state.get("focus", "")
        panel = panel_lines(focus, focus_panel(graph, tags, focus))
        head = unassigned_text(view.unassigned)
        header = [dmc.Anchor(head, href=ADMIN_LINK, size="sm")] if head else []
        chips = [dmc.Badge(chip_text(c), variant="light", mr="xs") for c in view.chips]
        return ({}, elements, crumb, note, details, hit_buttons(graph, text or ""),
                filter_options(graph, tags), header, chips,
                [dmc.Text(line, size="sm") for line in panel])  # fmt: skip
