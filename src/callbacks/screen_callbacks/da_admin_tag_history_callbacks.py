"""Callbacks for the Tag history panel (Upgrade G, G5f). Admin only for Restore."""

from dash import Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from agents.da_admin_access import is_admin
from agents.da_tag_versions import compare_text, compare_versions, restore_version
from callbacks.screen_callbacks.da_admin_page_callbacks import get_admin_settings
from layouts.da_admin_tag_history_panel import (
    TAG_A,
    TAG_B,
    TAG_COMPARE_BTN,
    TAG_COMPARE_OUT,
    TAG_RESTORE,
    TAG_RESTORE_BTN,
    TAG_RESTORE_CONFIRM,
    TAG_RESTORE_LATER,
    TAG_RESTORE_MODAL,
    TAG_RESTORE_OUT,
)


def restore_action(settings, value: str | None) -> str:
    """The confirmed Restore: refuses non-admins; the words come from restore_version."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    if not value:
        return "Pick a version first."
    return restore_version(int(value), settings.developer_id)[1]


def compare_action(first: str | None, second: str | None) -> str:
    if not first or not second:
        return "Pick two versions to compare."
    a, b = int(first), int(second)
    return compare_text(compare_versions(a, b), a, b)


def register_tag_history_callbacks(app) -> None:
    @app.callback(
        Output(TAG_COMPARE_OUT, "children"),
        Input(TAG_COMPARE_BTN, "n_clicks"),
        State(TAG_A, "value"),
        State(TAG_B, "value"),
        prevent_initial_call=True,
    )
    def compare(_clicks, first, second):
        return compare_action(first, second)

    @app.callback(
        Output(TAG_RESTORE_MODAL, "opened"),
        Output(TAG_RESTORE_OUT, "children"),
        Input(TAG_RESTORE_BTN, "n_clicks"),
        Input(TAG_RESTORE_LATER, "n_clicks"),
        Input(TAG_RESTORE_CONFIRM, "n_clicks"),
        State(TAG_RESTORE, "value"),
        prevent_initial_call=True,
    )
    def answer(_open, _later, _confirm, value):
        if not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if ctx.triggered_id == TAG_RESTORE_BTN:
            return bool(value), ("" if value else "Pick a version first.")
        if ctx.triggered_id == TAG_RESTORE_CONFIRM:
            return False, restore_action(get_admin_settings(), value)
        return False, ""
