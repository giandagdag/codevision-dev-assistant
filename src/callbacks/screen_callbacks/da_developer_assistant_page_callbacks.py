"""Clicks on the Developer Assistant screen (thin: rule R12).

Each function only decides which 2A engine function to call and shows what comes back. Every
check (secret words, message length, stale revision, which input is allowed) lives in 2A code.

CodeVision defines its callback functions inside the register function. Ours are at the top of
the file and only attached inside it, so tests can call them directly.
"""

from functools import lru_cache
from urllib.parse import parse_qs

from dash import ALL, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from agents.da_understand_flow import (
    choose_option,
    create_understand_request,
    get_understand_view,
    list_my_requests,
    skip_optional,
    submit_answer,
)
from configs.da_config import ConfigError, Settings, load_settings
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_rulebook import RulebookError
from db_table_functions.db_tbl_da_understand import UnderstandError
from layouts.da_developer_assistant_page import (
    CHOICE_TYPE,
    LOCATION_ID,
    MESSAGE_ID,
    PAGE_CONTENT_ID,
    REFRESH_ID,
    SEND_ID,
    SKIP_ID,
    STATE_ID,
    TEXT_ID,
    render_home,
    render_message_page,
    render_new_workspace,
    render_workspace,
)

# Problems the developer can understand and act on. Their messages are already plain words.
# Anything else is a real bug and is allowed to stop loudly.
SHOWN_ERRORS = (UnderstandError, RulebookError, DatabaseBusyError, ConfigError)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Read the settings once, like a data area read at job start. Tests replace this."""
    return load_settings()


def show_page(search: str | None, refresh: int | None):
    """Draw Home, the blank workspace, or one request, from the URL.

    The conversation lives in the database, so a page reload draws exactly the same thing.
    """
    settings = get_settings()
    params = parse_qs((search or "").lstrip("?"))
    if params.get("request"):
        try:
            return render_workspace(get_understand_view(settings, params["request"][0]))
        except (UnderstandError, DatabaseBusyError) as error:
            return render_message_page(str(error))
    if params.get("new"):
        return render_new_workspace(demo_mode=settings.llm_provider == "fake")
    try:
        return render_home(list_my_requests(settings))
    except DatabaseBusyError as error:
        return render_message_page(str(error))


def handle_action(send_clicks, choice_clicks, skip_clicks, text, state, refresh):
    """Send, a choice button or Skip was pressed."""
    trigger = ctx.triggered_id
    # New buttons appear with every redraw; only a real click (a count above zero) counts.
    if trigger is None or not ctx.triggered[0]["value"]:
        raise PreventUpdate
    return perform_action(get_settings(), trigger, text, state, refresh)


def perform_action(settings: Settings, trigger, text, state, refresh):
    """Call the one engine function the button stands for.

    Returns what the three outputs need: the refresh counter (redraw this request), the URL
    query (open a request that was just created) and the message line under the chat.
    """
    state = state or {}
    request_id, revision = state.get("request_id"), state.get("revision")
    try:
        if trigger == SEND_ID and request_id is None:
            view = create_understand_request(settings, text or "")
            return no_update, f"?request={view.request.request_id}", ""
        if trigger == SEND_ID:
            submit_answer(settings, request_id, text or "", revision)
        elif trigger == SKIP_ID:
            skip_optional(settings, request_id, revision)
        elif isinstance(trigger, dict) and trigger.get("type") == CHOICE_TYPE:
            choose_option(settings, request_id, trigger["option"], revision)
        else:
            raise PreventUpdate
    except SHOWN_ERRORS as error:
        # Nothing was written. The text stays in the box so the developer can fix it.
        return no_update, no_update, str(error)
    return (refresh or 0) + 1, no_update, ""


def register_da_developer_assistant_page_callbacks(app) -> None:
    # Draws on first load too, so this one does not use prevent_initial_call.
    app.callback(
        Output(PAGE_CONTENT_ID, "children"),
        Input(LOCATION_ID, "search"),
        Input(REFRESH_ID, "data"),
    )(show_page)

    # running= is the busy mode: while the engine waits for the interpreter, Send shows a
    # spinner and the text box and Skip cannot be used a second time.
    app.callback(
        Output(REFRESH_ID, "data"),
        Output(LOCATION_ID, "search"),
        Output(MESSAGE_ID, "children"),
        Input(SEND_ID, "n_clicks"),
        Input({"type": CHOICE_TYPE, "option": ALL}, "n_clicks"),
        Input(SKIP_ID, "n_clicks"),
        State(TEXT_ID, "value"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        running=[
            (Output(SEND_ID, "loading"), True, False),
            (Output(TEXT_ID, "readOnly"), True, False),
            (Output(SKIP_ID, "disabled"), True, False),
        ],
        prevent_initial_call=True,
    )(handle_action)
