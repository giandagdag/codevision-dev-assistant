"""Callbacks for the index builds panel (Upgrade G, G5c/d). Admin only for "Use build"."""

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from agents.da_admin_access import is_admin
from agents.da_admin_index import index_dir
from agents.da_index_builds import build_confirm_text, compare_builds, compare_text, read_manifest
from agents.da_index_rollback import roll_back
from callbacks.screen_callbacks.da_admin_page_callbacks import get_admin_settings
from layouts.da_admin_builds_panel import (
    BUILD_A,
    BUILD_B,
    BUILD_COMPARE_BTN,
    BUILD_COMPARE_OUT,
    BUILD_USE,
    BUILD_USE_BTN,
    BUILD_USE_CONFIRM,
    BUILD_USE_LATER,
    BUILD_USE_MODAL,
    BUILD_USE_NAME,
    BUILD_USE_OUT,
)


def use_build(settings, value: str | None) -> str:
    """The confirmed "Use build K": refuses non-admins; the words come from roll_back."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    if not value:
        return "Pick a build first."
    return roll_back(index_dir(), int(value), settings.developer_id)[1]


def compare_action(first: str | None, second: str | None) -> str:
    if not first or not second:
        return "Pick two builds to compare."
    a, b = int(first), int(second)
    return compare_text(compare_builds(index_dir(), a, b), a, b)


def register_builds_callbacks(app) -> None:
    @app.callback(
        Output(BUILD_COMPARE_OUT, "children"),
        Input(BUILD_COMPARE_BTN, "n_clicks"),
        State(BUILD_A, "value"),
        State(BUILD_B, "value"),
        prevent_initial_call=True,
    )
    def compare(_clicks, first, second):
        return compare_action(first, second)

    @app.callback(
        Output(BUILD_USE_MODAL, "opened"),
        Output(BUILD_USE_OUT, "children"),
        Output(BUILD_USE_NAME, "children"),
        Input(BUILD_USE_BTN, "n_clicks"),
        Input(BUILD_USE_LATER, "n_clicks"),
        Input(BUILD_USE_CONFIRM, "n_clicks"),
        State(BUILD_USE, "value"),
        prevent_initial_call=True,
    )
    def answer(_open, _later, _confirm, value):
        if not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if ctx.triggered_id == BUILD_USE_BTN:
            number = int(value) if value else 0
            name = build_confirm_text(read_manifest(index_dir(), number), number) if value else ""
            return bool(value), ("" if value else "Pick a build first."), name
        if ctx.triggered_id == BUILD_USE_CONFIRM:
            return False, use_build(get_admin_settings(), value), no_update
        return False, "", no_update
