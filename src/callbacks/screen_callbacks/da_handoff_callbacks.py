"""Clicks on the Handoff parts of the Developer Assistant screen (Phase 10, step 5). Thin (R12):
every check lives in `agents/da_handoff_flow.py`.

The functions are at the top so tests can call them; `register_da_handoff_callbacks` attaches them.
The folder check (the browser reads the planned files) arrives through the Workspace chain as the
event kind `handoff_facts`; `final_check_from_facts` is what that chain calls.

AS400 picture: the function-key program of the promotion screen. A key press names an action, the
program calls the one routine for it and redraws the screen.
"""

from dash import ALL, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from agents import da_handoff_flow as flow
from agents.da_handoff_screen import FOLLOW_UP_KEY, READY_KEY
from agents.da_workspace_checks import fingerprint
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_understand import UnderstandError
from layouts.da_developer_assistant_page import (
    BUSY_ID,
    HANDOFF_TYPE,
    LOCATION_ID,
    MESSAGE_ID,
    REFRESH_ID,
    STATE_ID,
)
from pydantic_classes.da_workspace_models import FolderFacts
from web import da_web_components as parts

SHOWN_ERRORS = (UnderstandError, DatabaseBusyError)
BUSY = [(Output(BUSY_ID, "style"), {"display": "block"}, {"display": "none"})]

# Copy summary (clientside). If the browser refuses to copy, the text is selected for Ctrl+C.
COPY_JS = f"""
function(clicks) {{
    if (!clicks) {{ return window.dash_clientside.no_update; }}
    const box = document.getElementById('{parts.SUMMARY_BOX_ID}');
    if (!box) {{ return window.dash_clientside.no_update; }}
    const fallback = () => {{ box.select(); return '{parts.COPY_FALLBACK}'; }};
    if (!navigator.clipboard || !window.isSecureContext) {{ return fallback(); }}
    return navigator.clipboard.writeText(box.value).then(
        () => '{parts.COPIED_TEXT}', fallback);
}}
"""


def fingerprints_from_facts(facts: FolderFacts) -> dict[str, str]:
    """path -> fingerprint of each planned file the browser found. The server hashes the text
    itself when it has it; a file too big to read keeps the browser's hash."""
    seen: dict[str, str] = {}
    for item in facts.files:
        if not item.exists:
            continue
        if item.text is not None:
            seen[item.path] = fingerprint(item.text)
        elif item.fingerprint:
            seen[item.path] = item.fingerprint
    return seen


def final_check_from_facts(settings, request_id: str, facts: FolderFacts, revision: int) -> None:
    """H4/H5 from the browser's folder read (event kind `handoff_facts`)."""
    flow.final_check(settings, request_id, revision, fingerprints_from_facts(facts))


def handle_handoff_button(settings, trigger, clicks_value, state, refresh):
    """A server-run Handoff button was pressed. Returns (refresh counter, URL search, message).
    The URL changes only for Start a follow-up request (it opens the new request)."""
    state = state or {}
    if not isinstance(trigger, dict) or not clicks_value or not state.get("handoff"):
        raise PreventUpdate
    request_id, revision = state.get("request_id"), state.get("handoff_revision", 0)
    key = trigger["index"]
    try:
        if key == READY_KEY:
            flow.ready_for_handoff(settings, request_id, revision)
        elif key == FOLLOW_UP_KEY:
            new = flow.start_follow_up(settings, request_id, settings.developer_id)
            return no_update, f"?request={new.request_id}", ""
        else:
            raise PreventUpdate
    except SHOWN_ERRORS as error:
        return no_update, no_update, str(error)
    return (refresh or 0) + 1, no_update, ""


def register_da_handoff_callbacks(app, current_settings) -> None:
    """Attach the Handoff clicks. `current_settings` is called at click time (tests replace it)."""

    def on_handoff_button(clicks, state, refresh):
        trigger = ctx.triggered_id
        if trigger is None or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return handle_handoff_button(current_settings(), trigger, True, state, refresh)

    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(LOCATION_ID, "search", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input({"type": HANDOFF_TYPE, "index": ALL}, "n_clicks"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        running=BUSY,
        prevent_initial_call=True,
    )(on_handoff_button)
    # The Audit tab's Copy summary button. The button exists only on a handed-off request.
    app.clientside_callback(
        COPY_JS,
        Output(parts.COPY_NOTE_ID, "children"),
        Input(parts.COPY_BUTTON_ID, "n_clicks"),
        prevent_initial_call=True,
    )
