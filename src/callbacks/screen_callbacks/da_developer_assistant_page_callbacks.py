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

from agents.da_discover_flow import (
    add_hint_and_search,
    confirm_discovery,
    escalate_discovery,
    get_discovery_view,
    start_discovery,
)
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
    BUSY_ID,
    CHOICE_TYPE,
    CONFIRM_KEY,
    ESCALATE_KEY,
    KEYS_ID,
    LOCATION_ID,
    MESSAGE_ID,
    PAGE_CONTENT_ID,
    REFRESH_ID,
    SEND_ID,
    SKIP_ID,
    START_KEY,
    STATE_ID,
    TEXT_ID,
    render_discover_workspace,
    render_home,
    render_message_page,
    render_new_workspace,
    render_workspace,
)
from pydantic_classes.da_models import (
    STATUS_CLARIFICATION,
    STATUS_DECISION_REQUIRED,
    STATUS_DRAFT,
    STATUS_READY,
)

# Problems the developer can understand and act on. Their messages are already plain words.
# Anything else is a real bug and is allowed to stop loudly.
SHOWN_ERRORS = (UnderstandError, RulebookError, DatabaseBusyError, ConfigError)

# Until the request is confirmed the Understand workspace is shown; from CONFIRMED_FOR_DISCOVERY
# on, the Discover workspace (Phase 3).
UNDERSTAND_STATUSES = (STATUS_DRAFT, STATUS_CLARIFICATION, STATUS_DECISION_REQUIRED, STATUS_READY)


# Enter sends, Shift+Enter makes a new line. Dash cannot tell them apart in Python, so this small
# browser script (a Dash clientside callback) does the one thing a function key does on a 5250
# screen: it presses the Send button. Everything after that is the normal Send path (handle_action
# and the 2A checks), so no rule lives here (R12). It does nothing while the text box is locked
# (disabled), a reply is running (the box is read-only and Send is loading), or for Shift, Ctrl,
# Alt, Meta, or an input-method key press. The listener is added once for the whole page.
ENTER_TO_SEND_JS = f"""
function(content) {{
    if (!window.daEnterToSend) {{
        window.daEnterToSend = true;
        document.addEventListener('keydown', function(event) {{
            var box = event.target;
            if (!box || box.id !== '{TEXT_ID}' || event.key !== 'Enter') {{ return; }}
            if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey
                    || event.isComposing) {{ return; }}
            event.preventDefault();
            var send = document.getElementById('{SEND_ID}');
            if (!send || box.disabled || box.readOnly) {{ return; }}
            if (send.disabled || send.hasAttribute('data-loading')
                    || send.hasAttribute('data-disabled')) {{ return; }}
            send.click();
        }});
    }}
    return window.dash_clientside.no_update;
}}
"""


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
            request_id = params["request"][0]
            view = get_understand_view(settings, request_id)
            if view.request.status in UNDERSTAND_STATUSES:
                return render_workspace(view)
            return render_discover_workspace(view, get_discovery_view(settings, request_id))
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
        if trigger == SEND_ID and state.get("discover"):
            # In Discover the Send button is "Something's missing": the text is the hint.
            add_hint_and_search(settings, request_id, text or "", revision)
        elif trigger == SEND_ID:
            submit_answer(settings, request_id, text or "", revision)
        elif trigger == SKIP_ID:
            skip_optional(settings, request_id, revision)
        elif state.get("discover") and _is_choice(trigger):
            _discover_choice(settings, request_id, trigger["option"], revision)
        elif _is_choice(trigger):
            choose_option(settings, request_id, trigger["option"], revision)
        else:
            raise PreventUpdate
    except SHOWN_ERRORS as error:
        # Nothing was written. The text stays in the box so the developer can fix it.
        return no_update, no_update, str(error)
    return (refresh or 0) + 1, no_update, ""


def _is_choice(trigger) -> bool:
    return isinstance(trigger, dict) and trigger.get("type") == CHOICE_TYPE


def _discover_choice(settings: Settings, request_id: str, key: str, revision: int) -> None:
    """The one Discover engine function a button stands for."""
    if key == START_KEY:
        start_discovery(settings, request_id, revision)
    elif key == CONFIRM_KEY:
        confirm_discovery(settings, request_id, revision)
    elif key == ESCALATE_KEY:
        escalate_discovery(settings, request_id, revision)
    else:
        raise PreventUpdate


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
            # The "searching" line, hidden in every other workspace (it has no text there).
            (Output(BUSY_ID, "style"), {"display": "block"}, {"display": "none"}),
        ],
        prevent_initial_call=True,
    )(handle_action)

    # Runs after every redraw; the script installs its listener only the first time.
    app.clientside_callback(
        ENTER_TO_SEND_JS,
        Output(KEYS_ID, "data"),
        Input(PAGE_CONTENT_ID, "children"),
    )
