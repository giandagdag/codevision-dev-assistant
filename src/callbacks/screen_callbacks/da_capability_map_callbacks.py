"""Wires the capability map page (Upgrade G, G4c/d). Read only: nothing here writes anything."""

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, ctx

from agents.da_admin_index import index_dir
from agents.da_admin_tag_store import read_tags
from agents.da_code_graph import load_graph
from layouts.da_capability_map_view import (
    MAP_BACK_ID,
    MAP_CRUMB_ID,
    MAP_DETAILS_ID,
    MAP_FILTER_ID,
    MAP_GRAPH_ID,
    MAP_HITS_ID,
    MAP_NOTE_ID,
    MAP_PATH,
    MAP_SEARCH_ID,
    MAP_SHELL_ID,
    MAP_STATE_ID,
    START_STATE,
    after_tap,
    filter_options,
    go_back,
    pick_view,
    render_map,
    search_hits,
)
from layouts.da_developer_assistant_page import LOCATION_ID

HIT_TYPE = "da-map-hit"


def next_state(trigger, state: dict, tapped: dict | None, picked: str | None) -> dict:
    """One place that decides the new state, so it can be tested without a browser."""
    state = state or START_STATE
    if trigger == MAP_BACK_ID:
        return go_back(state)
    if trigger == MAP_GRAPH_ID:
        return after_tap(state, tapped)
    if picked:
        return {**state, "module": picked}
    return state


def hit_buttons(graph: dict | None, text: str) -> list:
    return [
        dmc.Button(m, id={"type": HIT_TYPE, "name": m}, variant="subtle", size="xs")
        for m in search_hits(graph, text)
    ]


def register_da_capability_map_callbacks(app) -> None:
    @app.callback(
        Output(MAP_STATE_ID, "data"),
        Input(MAP_BACK_ID, "n_clicks"),
        Input(MAP_GRAPH_ID, "tapNodeData"),
        Input({"type": HIT_TYPE, "name": ALL}, "n_clicks"),
        State(MAP_STATE_ID, "data"),
        prevent_initial_call=True,
    )
    def move(_back, tapped, _hits, state):
        trigger = ctx.triggered_id
        picked = trigger["name"] if isinstance(trigger, dict) else None
        if isinstance(trigger, dict) and not any(_hits):
            return state  # the hit list was redrawn: not a real click
        return next_state(MAP_BACK_ID if trigger == MAP_BACK_ID else
                          (MAP_GRAPH_ID if trigger == MAP_GRAPH_ID else HIT_TYPE),
                          state, tapped, picked)  # fmt: skip

    @app.callback(
        Output(MAP_SHELL_ID, "style"),
        Output(MAP_GRAPH_ID, "elements"),
        Output(MAP_CRUMB_ID, "children"),
        Output(MAP_NOTE_ID, "children"),
        Output(MAP_DETAILS_ID, "children"),
        Output(MAP_HITS_ID, "children"),
        Output(MAP_FILTER_ID, "data"),
        Input(LOCATION_ID, "pathname"),
        Input(MAP_STATE_ID, "data"),
        Input(MAP_SEARCH_ID, "value"),
        Input(MAP_FILTER_ID, "value"),
    )
    def show_map(pathname, state, text, chosen):
        if pathname != MAP_PATH:
            return {"display": "none"}, [], "", "", [], [], []
        graph, tags = load_graph(index_dir()), read_tags()
        state = state or START_STATE
        view = pick_view(graph, tags, state, chosen or "")
        elements, crumb, note, lines = render_map(view, state)
        details = [dmc.Text(line, size="sm") for line in lines]
        return ({}, elements, crumb, note, details, hit_buttons(graph, text or ""),
                filter_options(graph, tags))  # fmt: skip
