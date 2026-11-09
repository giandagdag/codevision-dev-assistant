"""Clicks on the Refine parts of the Developer Assistant screen (Phase 8 step 16b). Thin (R12):
every check lives in the engine functions that `da_refine_actions` calls.

The functions are at the top so tests can call them; `register_da_refine_callbacks` attaches them.
Re-scan and Restore build N run in the browser (step 16c), so they are not here.

AS400 picture: the function-key program of a 5250 screen. A key press names an action, the program
calls the one routine for it and then redraws the screen.
"""

from dash import ALL, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from agents import da_build_runner as build_runner
from agents.da_refine_actions import (
    SHOWN_CHAIN_ERRORS,
    Outcome,
    perform_pick,
    perform_refine,
)
from layouts.da_build_panel import ADD_CASE_FIELD_TYPE, ADD_CASE_TYPE
from layouts.da_developer_assistant_page import (
    BUSY_ID,
    MESSAGE_ID,
    REFINE_TYPE,
    REFRESH_ID,
    STATE_ID,
)
from layouts.da_refine_panels import CONFLICT_PICK_TYPE

SHOWN_ERRORS = SHOWN_CHAIN_ERRORS
BUSY = [(Output(BUSY_ID, "style"), {"display": "block"}, {"display": "none"})]


def run_refine(settings, key: str, state: dict, text: str = "", arg: str = "") -> str:
    """Call the one action a key stands for, start the build runner when the action began a build,
    and return the message line (empty when all went well). Errors the developer can read are
    raised for the caller to show."""
    request_id = state.get("request_id")
    # The build screen's revision is the BUILD revision; other screens have none to send.
    build_revision = state.get("revision") if state.get("build") else 0
    outcome: Outcome = perform_refine(
        settings, key, request_id, state.get("refine_revision", 0), text, arg, build_revision or 0
    )
    if outcome.job == "build":
        build_runner.submit_build(settings, request_id)
    return outcome.message


def handle_refine_button(settings, trigger, clicks_value, state, refresh):
    """A Refine button was pressed. `trigger` is its pattern id; the index is the action key.
    Returns (refresh counter, message under the chat)."""
    state = state or {}
    if not isinstance(trigger, dict) or not clicks_value or not state.get("refine"):
        raise PreventUpdate
    try:
        message = run_refine(settings, trigger["index"], state)
    except SHOWN_ERRORS as error:
        return no_update, str(error)
    return (refresh or 0) + 1, message


def handle_conflict_pick(settings, trigger, clicks_value, state, refresh):
    """Keep mine or Take the AI's for one place. Returns (refresh counter, message)."""
    state = state or {}
    if not isinstance(trigger, dict) or not clicks_value or not state.get("build"):
        raise PreventUpdate
    try:
        perform_pick(
            settings,
            state.get("request_id"),
            trigger["path"],
            trigger["conflict"],
            trigger["choice"],
            state.get("revision"),
        )
    except SHOWN_ERRORS as error:
        return no_update, str(error)
    return (refresh or 0) + 1, ""


def handle_add_case(settings, fields: dict, state, refresh):
    """Add a test case: `fields` holds the criterion and the typed words.
    Returns (refresh, message). The Tester call and the sandbox run take a while; the busy mode
    covers the wait."""
    state = state or {}
    if not state.get("refine"):
        raise PreventUpdate
    text, criterion = fields.get("text") or "", fields.get("criterion") or ""
    try:
        message = run_refine(settings, "add_case", state, text=text, arg=criterion)
    except SHOWN_ERRORS as error:
        return no_update, str(error)
    return (refresh or 0) + 1, message


def register_da_refine_callbacks(app, current_settings) -> None:
    """Attach the Refine clicks. `current_settings` is called at click time (tests replace it)."""

    def on_refine_button(clicks, state, refresh):
        trigger = ctx.triggered_id
        if trigger is None or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return handle_refine_button(current_settings(), trigger, True, state, refresh)

    def on_conflict_pick(clicks, state, refresh):
        trigger = ctx.triggered_id
        if trigger is None or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return handle_conflict_pick(current_settings(), trigger, True, state, refresh)

    def on_add_case(clicks, values, state, refresh):
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        boxes = ctx.states_list[0]
        fields = {box["id"]["index"]: value for box, value in zip(boxes, values, strict=True)}
        return handle_add_case(current_settings(), fields, state, refresh)

    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input({"type": REFINE_TYPE, "index": ALL}, "n_clicks"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        running=BUSY,
        prevent_initial_call=True,
    )(on_refine_button)
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input(
            {"type": CONFLICT_PICK_TYPE, "path": ALL, "conflict": ALL, "choice": ALL}, "n_clicks"
        ),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        running=BUSY,
        prevent_initial_call=True,
    )(on_conflict_pick)
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input({"type": ADD_CASE_TYPE, "index": ALL}, "n_clicks"),
        State({"type": ADD_CASE_FIELD_TYPE, "index": ALL}, "value"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        running=BUSY,
        prevent_initial_call=True,
    )(on_add_case)
