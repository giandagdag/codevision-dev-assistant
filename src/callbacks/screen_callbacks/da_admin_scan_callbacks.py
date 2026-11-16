"""Callbacks of the AI scan buttons (fix 11-2, AG-8). Plain functions first, Dash wrappers last."""

from dash import Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from agents.da_admin_access import is_admin
from agents.da_admin_tagger_job import scan_running, start_scan, status_line
from configs.da_config import Settings, load_settings
from db_table_functions.db_tbl_da_rulebook import get_active_version
from layouts.da_admin_scan_controls import (
    SCAN_ALL_BTN,
    SCAN_CONFIRM,
    SCAN_LATER,
    SCAN_MODAL,
    SCAN_MODE,
    SCAN_NEW_BTN,
    SCAN_POLL,
    SCAN_STATUS,
)


def scan_action(settings: Settings, button: str | None, mode: str):
    """Confirm box clicks. Returns (box opened, status line). Only Scan starts a job."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    if button == SCAN_CONFIRM:
        policy = get_active_version(settings.db_path).rulebook.policy
        started, message = start_scan(
            policy, settings, settings.developer_id, only_changed=(mode == "new")
        )
        if not started:
            return False, message
    return False, status_line()


def register_scan(app, get_settings=load_settings) -> None:
    """`get_settings` is passed in so the page's test-replaceable settings reader is used."""

    @app.callback(
        Output(SCAN_MODAL, "opened"),
        Output(SCAN_MODE, "data"),
        Input(SCAN_ALL_BTN, "n_clicks"),
        Input(SCAN_NEW_BTN, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_confirm(_all, _new):
        if not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return True, "new" if ctx.triggered_id == SCAN_NEW_BTN else "all"

    @app.callback(
        Output(SCAN_MODAL, "opened", allow_duplicate=True),
        Output(SCAN_STATUS, "children", allow_duplicate=True),
        Output(SCAN_ALL_BTN, "disabled", allow_duplicate=True),
        Output(SCAN_NEW_BTN, "disabled", allow_duplicate=True),
        Input(SCAN_CONFIRM, "n_clicks"),
        Input(SCAN_LATER, "n_clicks"),
        State(SCAN_MODE, "data"),
        prevent_initial_call=True,
    )
    def answer_confirm(_confirm, _later, mode):
        if not ctx.triggered[0]["value"]:
            raise PreventUpdate
        opened, status = scan_action(get_settings(),ctx.triggered_id, mode)
        busy = scan_running() is not None
        return opened, status, busy, busy

    @app.callback(
        Output(SCAN_STATUS, "children"),
        Output(SCAN_ALL_BTN, "disabled"),
        Output(SCAN_NEW_BTN, "disabled"),
        Input(SCAN_POLL, "n_intervals"),
    )
    def poll(_ticks):
        busy = scan_running() is not None
        return status_line(), busy, busy
