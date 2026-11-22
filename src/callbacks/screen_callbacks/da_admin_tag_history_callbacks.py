"""Callbacks for the Tag history panel (Upgrade G, G5f). Admin only for Restore."""

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from agents.da_admin_access import is_admin
from agents.da_tag_versions import (
    compare_text,
    compare_versions,
    restore_confirm_text,
    restore_version,
)
from agents.da_tagger_try import try_tagger, try_text
from callbacks.screen_callbacks.da_admin_page_callbacks import get_admin_settings
from db_table_functions.db_tbl_da_rulebook import get_active_version
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
    TAG_RESTORE_NAME,
    TAG_RESTORE_OUT,
)
from layouts.da_tagger_try_panel import TRY_BTN, TRY_OUT, TRY_PICK, TRY_RAW


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


def try_action(settings, path: str | None, client=None):
    """Try the tagger (Fix G5 R7): (one line, the raw reply, style of the raw box). Admin only."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    if not path:
        return "Pick a program first.", "", {"display": "none"}
    policy = get_active_version(settings.db_path).rulebook.policy
    result = try_tagger(policy, settings, path, client=client)
    return try_text(result), result.raw, {} if result.raw else {"display": "none"}


def register_tag_history_callbacks(app) -> None:
    @app.callback(
        Output(TRY_OUT, "children"),
        Output(TRY_RAW, "children"),
        Output(TRY_RAW, "style"),
        Input(TRY_BTN, "n_clicks"),
        State(TRY_PICK, "value"),
        prevent_initial_call=True,
        running=[(Output(TRY_BTN, "disabled"), True, False)],
    )
    def try_one(_clicks, path):
        return try_action(get_admin_settings(), path)

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
        Output(TAG_RESTORE_NAME, "children"),
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
            name = restore_confirm_text(int(value)) if value else ""
            return bool(value), ("" if value else "Pick a version first."), name
        if ctx.triggered_id == TAG_RESTORE_CONFIRM:
            return False, restore_action(get_admin_settings(), value), no_update
        return False, "", no_update
