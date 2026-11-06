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

from agents import da_approach_flow as approach_flow
from agents import da_build_flow as build_flow
from agents import da_build_runner as build_runner
from agents import da_workspace_flow as workspace_flow
from agents.da_discover_flow import (
    add_hint_and_search,
    confirm_discovery,
    escalate_discovery,
    get_discovery_view,
    start_discovery,
)
from agents.da_understand_flow import (
    FORM_OPTIONAL_BOX,
    FormError,
    choose_option,
    create_understand_request,
    get_understand_view,
    list_my_requests,
    skip_optional,
    submit_answer,
    submit_form,
)
from callbacks.screen_callbacks.da_workspace_callbacks import register_da_workspace_callbacks
from configs.da_config import ConfigError, Settings, load_settings
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_rulebook import RulebookError
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
)
from layouts.da_build_panel import POLL_ID
from layouts.da_developer_assistant_page import (
    BUSY_ID,
    CHOICE_TYPE,
    CONFIRM_KEY,
    ESCALATE_KEY,
    FORM_BOX_TYPE,
    FORM_ERROR_TYPE,
    FORM_SUBMIT_TYPE,
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
    approach_buttons,
    discover_buttons,
    render_approach_workspace,
    render_discover_workspace,
    render_home,
    render_message_page,
    render_new_workspace,
    render_workspace,
)
from pydantic_classes.da_models import (
    STATUS_APPROACH_PROPOSED,
    STATUS_BUILDING,
    STATUS_CLARIFICATION,
    STATUS_DECISION_REQUIRED,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_DRAFT,
    STATUS_ESCALATION,
    STATUS_NOT_PASSING,
    STATUS_READY,
    STATUS_READY_FOR_REVIEW,
    STATUS_READY_TO_BUILD,
)

# Problems the developer can understand and act on. Their messages are already plain words.
# Anything else is a real bug and is allowed to stop loudly.
SHOWN_ERRORS = (UnderstandError, RulebookError, DatabaseBusyError, ConfigError)

# The five boxes of the form, numbered 1 to 5 (4 mandatory questions and the optional area).
FORM_BOXES_COUNT = range(1, FORM_OPTIONAL_BOX + 1)

# Until the request is confirmed the Understand workspace is shown; from CONFIRMED_FOR_DISCOVERY
# on, the Discover workspace (Phase 3); from APPROACH_PROPOSED on, the Approach workspace
# (Phase 4). DISCOVERY_CONFIRMED stays in the Discover workspace, with the Proceed to Approach
# button. ESCALATION_REQUIRED is Approach's if an approach exists, otherwise Discover's.
UNDERSTAND_STATUSES = (STATUS_DRAFT, STATUS_CLARIFICATION, STATUS_DECISION_REQUIRED, STATUS_READY)
APPROACH_STATUSES = (
    STATUS_APPROACH_PROPOSED,
    STATUS_READY_TO_BUILD,
    STATUS_BUILDING,
    STATUS_READY_FOR_REVIEW,
    STATUS_NOT_PASSING,
)
# The statuses where the request has a workspace and a build to draw.
WORKSPACE_STATUSES = (
    STATUS_READY_TO_BUILD,
    STATUS_BUILDING,
    STATUS_READY_FOR_REVIEW,
    STATUS_NOT_PASSING,
)


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
            discovery = get_discovery_view(settings, request_id)
            status = view.request.status
            if status in APPROACH_STATUSES or (
                status == STATUS_ESCALATION and approach_flow.has_approach(settings, request_id)
            ):
                approach = approach_flow.get_approach_view(settings, request_id)
                has_build = status in WORKSPACE_STATUSES or (
                    status == STATUS_ESCALATION
                    and build_flow.get_state(settings, request_id).build_number > 0
                )
                workspace = (
                    workspace_flow.get_workspace_view(settings, request_id) if has_build else None
                )
                build = build_flow.get_build_view(settings, request_id) if has_build else None
                return render_approach_workspace(view, discovery, approach, workspace, build)
            if status == STATUS_DISCOVERY_CONFIRMED:
                approach = approach_flow.get_approach_view(settings, request_id)
                return render_discover_workspace(view, discovery, approach)
            return render_discover_workspace(view, discovery)
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
        if state.get("build") and trigger != SKIP_ID:
            _build_action(settings, trigger, request_id, revision)
        elif state.get("workspace") and trigger != SKIP_ID:
            _workspace_action(settings, trigger, request_id, revision)
        elif state.get("approach") and trigger != SKIP_ID:
            _approach_action(settings, trigger, request_id, revision, text)
        elif trigger == SEND_ID and state.get("discover"):
            # In Discover the Send button is "Something's missing": the text is the hint.
            add_hint_and_search(settings, request_id, text or "", revision)
        elif trigger == SEND_ID:
            submit_answer(settings, request_id, text or "", revision)
        elif trigger == SKIP_ID:
            skip_optional(settings, request_id, revision)
        elif _is_choice(trigger) and state.get("discover"):
            key = _discover_key_at(settings, request_id, revision, trigger["index"])
            _discover_choice(settings, request_id, key, revision)
        elif _is_choice(trigger):
            option = _option_at(settings, request_id, revision, trigger["index"])
            choose_option(settings, request_id, option, revision)
        else:
            raise PreventUpdate
    except SHOWN_ERRORS as error:
        # Nothing was written. The text stays in the box so the developer can fix it.
        return no_update, no_update, str(error)
    return (refresh or 0) + 1, no_update, ""


def handle_form(submit_clicks, answers, state, refresh):
    """Submit was pressed on the 4-box form."""
    if not submit_clicks or not any(submit_clicks):
        raise PreventUpdate
    return perform_form(get_settings(), answers, state, refresh)


def perform_form(settings: Settings, answers, state, refresh):
    """Call submit_form and return (refresh counter, message under the chat, one message per box).

    A box that fails shows its message on the line under it; nothing is redrawn, so every box
    keeps what was typed (U2). Any other shown problem (stale window, AI not reachable) goes to
    the line under the chat.
    """
    state = state or {}
    empty = [""] * len(FORM_BOXES_COUNT)
    try:
        submit_form(
            settings,
            state.get("request_id"),
            [(answer or "") for answer in answers or []],
            state.get("revision"),
        )
    except FormError as error:
        return no_update, "", [error.problems.get(number, "") for number in FORM_BOXES_COUNT]
    except SHOWN_ERRORS as error:
        return no_update, str(error), empty
    return (refresh or 0) + 1, "", empty


def _build_action(settings: Settings, trigger, request_id: str, revision: int) -> None:
    """The one Build engine function a server-run button stands for. An old window, or an index
    with no button behind it, is refused. A build that (re)starts is handed to the runner."""
    if not _is_choice(trigger):
        raise PreventUpdate
    view = build_flow.get_build_view(settings, request_id)
    index = trigger["index"]
    if view.revision != revision or not 0 <= index < len(view.buttons):
        raise StaleRevisionError(STALE_MESSAGE)
    actions = {
        build_flow.STOP_KEY: build_flow.stop_build,
        build_flow.TRY_AGAIN_KEY: build_flow.try_again,
        build_flow.CHANGE_APPROACH_KEY: build_flow.change_approach,
        build_flow.HELP_KEY: build_flow.request_help,
    }
    state = actions[view.buttons[index][0]](settings, request_id, revision)
    if state.step == "b_running":
        build_runner.submit_build(settings, request_id)


def poll_build(n_intervals, state, refresh):
    """Every 3 seconds while a build runs: redraw, so the progress list is current. The page
    asks again only while the Interval is on; the redraw switches it off when the build ends."""
    if not n_intervals or not state or not state.get("build"):
        raise PreventUpdate
    return (refresh or 0) + 1


def _workspace_action(settings: Settings, trigger, request_id: str, revision: int) -> None:
    """The one Workspace engine function a server-run button stands for (the browser-run buttons
    never come here). An old window, or an index with no button behind it, is refused."""
    if not _is_choice(trigger):
        raise PreventUpdate
    view = workspace_flow.get_workspace_view(settings, request_id)
    index = trigger["index"]
    if view.revision != revision or not 0 <= index < len(view.buttons):
        raise StaleRevisionError(STALE_MESSAGE)
    key = view.buttons[index][0]
    actions = {
        workspace_flow.CHANGE_APPROACH_KEY: workspace_flow.change_approach,
        workspace_flow.HELP_KEY: workspace_flow.request_help,
    }
    actions[key](settings, request_id, revision)


def _approach_action(settings: Settings, trigger, request_id: str, revision: int, text) -> None:
    """The one Approach engine function a click stands for. Every check lives in the engine."""
    if trigger == SEND_ID:
        approach_flow.submit_text(settings, request_id, text or "", revision)
        return
    if not _is_choice(trigger):
        raise PreventUpdate
    view = approach_flow.get_approach_view(settings, request_id)
    buttons = approach_buttons(view)
    index = trigger["index"]
    # An old window, or an index with no button behind it, gets the stale-window message.
    if view.revision != revision or not 0 <= index < len(buttons):
        raise StaleRevisionError(STALE_MESSAGE)
    key, label = buttons[index]
    actions = {
        approach_flow.START_KEY: approach_flow.start_approach,
        approach_flow.DECIDE_HELP_KEY: lambda s, r, v: approach_flow.choose_design_option(
            s, r, label, v
        ),
        approach_flow.CHOOSE_KEY: lambda s, r, v: approach_flow.choose_design_option(
            s, r, label, v
        ),
        approach_flow.ACCEPT_KEY: approach_flow.accept_approach,
        approach_flow.CHANGE_KEY: approach_flow.request_change,
        approach_flow.HELP_KEY: approach_flow.request_help,
        approach_flow.WRITE_PLAN_KEY: approach_flow.write_test_plan_again,
        approach_flow.ACCEPT_PLAN_KEY: approach_flow.accept_test_plan,
        approach_flow.ADD_CASE_KEY: approach_flow.request_case,
        approach_flow.CHANGE_APPROACH_KEY: approach_flow.request_plan_change,
        approach_flow.KEEP_KEY: approach_flow.keep_case,
        approach_flow.DISCARD_KEY: approach_flow.discard_case,
    }
    actions[key](settings, request_id, revision)


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


def _discover_key_at(settings: Settings, request_id: str, revision: int, index: int) -> str:
    """The key of the Discover button that was pressed, read from the request as saved now.

    Same stale-window rule as _option_at: an old window or an index with no button is refused.
    """
    view = get_discovery_view(settings, request_id)
    buttons = discover_buttons(view)
    if view.revision != revision or not 0 <= index < len(buttons):
        raise StaleRevisionError(STALE_MESSAGE)
    return buttons[index][0]


def _option_at(settings: Settings, request_id: str, revision: int, index: int) -> str:
    """The text of the choice button that was pressed, read from the request as saved now.

    A window that is out of date, or an index with no button behind it, gets the same stale-window
    message as any other out-of-date save (rule R7). Nothing is written.
    """
    view = get_understand_view(settings, request_id)
    if view.revision != revision or not 0 <= index < len(view.choices):
        raise StaleRevisionError(STALE_MESSAGE)
    return view.choices[index]


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
        Input({"type": CHOICE_TYPE, "index": ALL}, "n_clicks"),
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

    # Phase 6: while a build runs the page redraws itself every 3 seconds (spec section 10).
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Input(POLL_ID, "n_intervals"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        prevent_initial_call=True,
    )(poll_build)

    # The 4-box form (Phase 6 fixes). Pattern ids: the page has none of these on other screens.
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Output({"type": FORM_ERROR_TYPE, "index": ALL}, "children"),
        Input({"type": FORM_SUBMIT_TYPE, "index": ALL}, "n_clicks"),
        State({"type": FORM_BOX_TYPE, "index": ALL}, "value"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        running=[(Output(BUSY_ID, "style"), {"display": "block"}, {"display": "none"})],
        prevent_initial_call=True,
    )(handle_form)

    register_da_workspace_callbacks(app, lambda: get_settings())
