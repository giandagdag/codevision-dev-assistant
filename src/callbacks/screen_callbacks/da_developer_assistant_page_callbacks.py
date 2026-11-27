"""Clicks on the Developer Assistant screen (thin: rule R12).

Each function only decides which 2A engine function to call and shows what comes back. Every
check (secret words, message length, stale revision, which input is allowed) lives in 2A code.

CodeVision defines its callback functions inside the register function. Ours are at the top of
the file and only attached inside it, so tests can call them directly.
"""

import json
from functools import lru_cache
from urllib.parse import parse_qs

from dash import ALL, Input, Output, State, ctx, dcc, no_update
from dash.exceptions import PreventUpdate

from agents import da_approach_flow as approach_flow
from agents import da_build_flow as build_flow
from agents import da_build_runner as build_runner
from agents import da_enhance_flow as enhance_flow
from agents import da_enhance_help as enhance_help
from agents import da_safety_net_flow as net_flow
from agents import da_safety_net_runner as net_runner
from agents import da_tester_flow as tester_flow
from agents import da_workspace_flow as workspace_flow
from agents.da_admin_index import storage_line
from agents.da_ai_lock import is_busy, locked_call
from agents.da_discover_flow import (
    add_hint_and_search,
    confirm_discovery,
    escalate_discovery,
    get_discovery_view,
    start_discovery,
)
from agents.da_enhance_checks import available_symbols
from agents.da_enhance_flow import get_enhance_view, start_enhance_request
from agents.da_handoff_screen import get_handoff_box
from agents.da_inbox import pill_notes
from agents.da_refine_actions import get_refine_bar
from agents.da_refine_screen import (
    get_history,
    get_refine_build_panel,
    get_tagged_build,
)
from agents.da_senior_actions import get_chat_lock
from agents.da_understand_flow import (
    EDIT_ASSUMPTION_PREFIX,
    FORM_OPTIONAL_BOX,
    NO_NEGATIVE_OPTION,
    FormError,
    ask_for_exception,
    choose_option,
    create_understand_request,
    edit_assumption,
    get_understand_view,
    list_my_requests,
    set_functions_in_scope,
    set_no_negative_reason,
    skip_optional,
    submit_answer,
    submit_form,
)
from agents.da_understand_flow import (
    PROCEED_OPTION as UNDERSTAND_PROCEED,
)
from agents.da_understand_rules import ASK_EXCEPTION_PREFIX
from callbacks.screen_callbacks.da_handoff_callbacks import register_da_handoff_callbacks
from callbacks.screen_callbacks.da_refine_callbacks import register_da_refine_callbacks, run_refine
from callbacks.screen_callbacks.da_workspace_callbacks import register_da_workspace_callbacks
from configs.da_config import ConfigError, Settings, load_settings
from da_logging import get_logger
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_discovery import DiscoveryError
from db_table_functions.db_tbl_da_rulebook import RulebookError
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
)
from layouts.da_admin_page import ADMIN_PATH
from layouts.da_build_panel import POLL_ID, POLL_MS
from layouts.da_busy_text import BUSY_JS
from layouts.da_capability_map_view import MAP_PATH
from layouts.da_developer_assistant_page import (
    BUSY_ID,
    CHOICE_TYPE,
    CONFIRM_KEY,
    DECLINE_ID,
    ENHANCE_CARD_ID,
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
    SWITCH_ID,
    TAB_KEY_ID,
    TAB_MEMORY_ID,
    TABS_ID,
    TEXT_ID,
    add_pill_note,
    approach_buttons,
    discover_buttons,
    render_approach_workspace,
    render_discover_workspace,
    render_home,
    render_message_page,
    render_new_workspace,
    render_workspace,
    replace_composer,
)
from layouts.da_enhance_panel import (
    CAP_NONE_VALUE,
    CAP_TYPE,
    KEY_CONTINUE,
    KEY_FIX,
    KEY_HELP,
    KEY_PICK,
    KEY_TRY_AGAIN,
    KEY_UNDERSTAND,
    MARK_NONE_VALUE,
    MARK_TYPE,
    PICK_CONFIRM_ID,
    PICK_GROUP_ID,
    PICK_SEPARATOR,
    SCOPE_GROUP_ID,
    SCOPE_SAVE_ID,
    enhance_buttons,
    enhance_composer,
    impact_card,
    pill_text,
    render_enhance_workspace,
    safety_net_tab,
    scope_picker,
    test_plan_net_section,
)
from layouts.da_inbox_page import INBOX_PATH
from layouts.da_lock_buttons import lock_buttons
from layouts.da_tester_panel import (
    FINDING_ACT_TYPE,
    FINDING_REASON_TYPE,
    FINDINGS_ID,
    SEE_FINDINGS_ID,
)
from pydantic_classes.da_models import (
    STATUS_APPROACH_PROPOSED,
    STATUS_BUILDING,
    STATUS_CLARIFICATION,
    STATUS_CONFIRMED,
    STATUS_DECISION_REQUIRED,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_DRAFT,
    STATUS_ESCALATION,
    STATUS_HANDED_OFF,
    STATUS_NOT_PASSING,
    STATUS_READY,
    STATUS_READY_FOR_REVIEW,
    STATUS_READY_TO_BUILD,
    STATUS_REVISION,
    STATUS_STOPPED,
    STATUS_TESTER_REVIEW,
)
from styles import da_styles

# Problems the developer can understand and act on. Their messages are already plain words.
# Anything else is a real bug and is allowed to stop loudly.
SHOWN_ERRORS = (UnderstandError, RulebookError, DatabaseBusyError, ConfigError)

# The five boxes of the form, numbered 1 to 5 (4 mandatory questions and the optional area).
FORM_BOXES_COUNT = range(1, FORM_OPTIONAL_BOX + 1)

# Until the request is confirmed the Understand workspace is shown; from CONFIRMED_FOR_DISCOVERY
# on, the Discover workspace (Phase 3); from APPROACH_PROPOSED on, the Approach workspace
# (Phase 4). DISCOVERY_CONFIRMED stays in the Discover workspace, with the Proceed to Approach
# button. ESCALATION_REQUIRED is Approach's if an approach exists, otherwise Discover's.
UNDERSTAND_STATUSES = (
    STATUS_DRAFT, STATUS_CLARIFICATION, STATUS_DECISION_REQUIRED, STATUS_READY,
    STATUS_STOPPED,  # Fix G5: read-only Understand screen
)
APPROACH_STATUSES = (
    STATUS_APPROACH_PROPOSED,
    STATUS_READY_TO_BUILD,
    STATUS_BUILDING,
    STATUS_TESTER_REVIEW,
    STATUS_READY_FOR_REVIEW,
    STATUS_HANDED_OFF,  # Phase 10: locked, opens on the Audit tab
    STATUS_NOT_PASSING,
    STATUS_REVISION,  # Phase 8: a Refine lane is open; the pill shows REVISION IN PROGRESS
)
# Phase 9: the Enhance steps drawn by the Find screen (e_fresh and later use the Understand screen).
ENHANCE_FIND_STEPS = ("e_find", "e_pick", "e_stale")
# The statuses where the request has a workspace and a build to draw.
WORKSPACE_STATUSES = (
    STATUS_READY_TO_BUILD,
    STATUS_BUILDING,
    STATUS_TESTER_REVIEW,
    STATUS_READY_FOR_REVIEW,
    STATUS_HANDED_OFF,
    STATUS_NOT_PASSING,
    STATUS_REVISION,
)


# While an action runs, the page takes no clicks. A choice button stays on the screen for the 10 to
# 20 seconds the AI needs (longer since one click can start the next step too); a second click
# would carry the revision from before the first one finished, and the server rightly refuses it
# with "updated in another window" even though there is only one window. The style goes back to
# the normal page style when the action ends.
PAGE_BUSY = (
    Output(PAGE_CONTENT_ID, "style"),
    {**da_styles.PAGE, "pointerEvents": "none", "opacity": 0.75},
    da_styles.PAGE,
)

# Pages that own the address while they show (the Developer Assistant stays built but hidden).
OTHER_PAGES = (ADMIN_PATH, INBOX_PATH, MAP_PATH)

# G9 S5: "Opening..." only when the Developer Assistant page is the one showing.
OPENING_JS = f"""
function(search, pathname) {{
    if ({json.dumps(list(OTHER_PAGES))}.indexOf(pathname) >= 0) {{
        return window.dash_clientside.no_update;
    }}
    return 'Opening...';
}}
"""

# G9 S2: See the findings scrolls the findings table into view on every press.
SCROLL_TO_FINDINGS_JS = f"""
function(clicks) {{
    var table = document.getElementById('{FINDINGS_ID}');
    if (clicks && table) {{ table.scrollIntoView({{behavior: 'smooth', block: 'start'}}); }}
    return window.dash_clientside.no_update;
}}
"""

# G9 S4: after a redraw the user's tab stays open when the step is the same as when he chose it
# (same key); a new step clears the memory so the server's choice wins.
RESTORE_TAB_JS = """
function(children, key, memory) {
    var none = window.dash_clientside.no_update;
    if (memory && memory.key === key) {
        // Press the tab button once the new page is on screen (an Output on the tabs would fail on
        // pages that have none).
        setTimeout(function () {
            var tab = document.querySelector('[role=tab][id$="-tab-' + memory.tab + '"]');
            var shown = tab && tab.getAttribute('aria-selected') === 'true';
            if (tab && !shown && !tab.disabled) { tab.click(); }
        }, 50);
        return none;
    }
    return memory ? null : none;
}
"""

# The user pressed a tab: remember it with the key of this draw.
REMEMBER_TAB_JS = """
function(tab, key) {
    return tab ? {key: key, tab: tab} : window.dash_clientside.no_update;
}
"""

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


NET_STEPS_WITH_BUTTONS =("s_writing", "s_unable", "s_review")  # their buttons are Enhance's


def understand_extras(settings: Settings, view, enhance) -> dict | None:
    """Phase 9 (step 18c), Enhance requests in Understand: the header pill, and at the
    checkpoint the tick list of functions in scope. None for any other request."""
    if enhance is None:
        return None
    scope: list = []
    if view.record.kind != "new" and UNDERSTAND_PROCEED in view.choices:
        texts = enhance_flow.baseline_texts(settings, view.request.request_id)
        names = (name for path, text in texts.items() for name in available_symbols(path, text))
        symbols = list(dict.fromkeys(names))
        scope = scope_picker(symbols, view.record.functions_in_scope)
    return {"pill": pill_text(view.request.status, enhance.step), "scope": scope}


def discover_extras(settings: Settings, discovery, enhance) -> dict | None:
    """Phase 9 (step 18c), Enhance requests in Discover: impact card, Safety net tab, the pill,
    and for the safety-net steps their own buttons and revision."""
    if enhance is None:
        return None
    row = net_flow.get_net_row(settings, enhance.request_id)
    in_review = enhance.step == "s_review"
    criteria = _criteria_ids(settings, enhance.request_id) if in_review else None
    extras: dict = {
        "pill": pill_text(discovery.request.status, enhance.step),
        "impact": [impact_card(discovery.result.impact if discovery.result else None)],
        "net": safety_net_tab(row, criteria) if enhance.step.startswith("s_") else None,
    }
    if enhance.step in NET_STEPS_WITH_BUTTONS:
        extras["composer"] = enhance_composer(enhance)
        extras["state"] = {
            "request_id": enhance.request_id,
            "revision": enhance.revision,
            "enhance": enhance.step,
        }
    if enhance.step == "s_writing":
        extras["poll"] = dcc.Interval(id=POLL_ID, interval=POLL_MS, disabled=False)
    return extras


def approach_extras(settings: Settings, request_id: str, enhance) -> dict | None:
    """Phase 9 (step 18c), Enhance requests in Approach: the net tab and, in the test plan, the
    read-only accepted net."""
    if enhance is None:
        return None
    row = net_flow.get_net_row(settings, request_id)
    return {"net": safety_net_tab(row), "plan": test_plan_net_section(row)}


def _criteria_ids(settings: Settings, request_id: str) -> list[str]:
    """The AC IDs a case can be marked as "expected to change" for (from the saved record)."""
    record = get_understand_view(settings, request_id).record
    return [item.id for item in record.acceptance_criteria]


def confirm_picked(clicks, ticked, cap_values, cap_ids, state, refresh):
    """"Yes, these are the programs": the ticked candidates, with a capability pick for each
    program not in the catalog (Phase 9, step 18d, D-C)."""
    if not clicks:
        raise PreventUpdate
    picks = {
        item["index"]: value
        for item, value in zip(cap_ids or [], cap_values or [], strict=False)
        if value and value != CAP_NONE_VALUE
    }
    return perform_pick_confirm(get_settings(), ticked, picks, state, refresh)


def perform_pick_confirm(settings: Settings, ticked, picks: dict, state, refresh):
    """Call confirm_targets. Only the picks of ticked programs are passed on. A refusal (nothing
    ticked, too many files, a missing capability) is shown under the chat; nothing is written."""
    state = state or {}
    paths = list(ticked or [])
    try:
        enhance_flow.confirm_targets(
            settings,
            state.get("request_id"),
            paths,
            {path: name for path, name in picks.items() if path in paths},
            state.get("revision"),
        )
    except SHOWN_ERRORS as error:
        return no_update, str(error)
    return (refresh or 0) + 1, ""


def save_scope(clicks, chosen, state, refresh):
    """"Save functions in scope" under the chat at the checkpoint (Phase 9, step 18c)."""
    if not clicks:
        raise PreventUpdate
    return perform_scope_save(get_settings(), chosen, state, refresh)


def perform_scope_save(settings: Settings, chosen, state, refresh):
    """Call set_functions_in_scope; a refusal (unknown name, nothing ticked) is shown under the
    chat and nothing is written. Returns (refresh counter, message)."""
    state = state or {}
    try:
        set_functions_in_scope(
            settings, state.get("request_id"), list(chosen or []), state.get("revision")
        )
    except SHOWN_ERRORS as error:
        return no_update, str(error)
    return (refresh or 0) + 1, ""


def show_page(search: str | None, refresh: int | None, pathname: str | None = None):
    """Draw Home, the blank workspace, or one request, from the URL.

    The conversation lives in the database, so a page reload draws exactly the same thing.
    While an escalation is open (and the chat lock is on) the composer becomes the waiting line
    (Phase 10, spec section 11). G9 S6: while Admin, Inbox or the map shows, the address is theirs.
    """
    if pathname in OTHER_PAGES:
        raise PreventUpdate
    page = _draw_page(search, refresh)
    params = parse_qs((search or "").lstrip("?"))
    if params.get("request"):
        if is_busy(params["request"][0]):
            lock_buttons(page)  # B2 S5: the AI is still working on it
        try:
            lock = get_chat_lock(get_settings(), params["request"][0])
        except (UnderstandError, DatabaseBusyError):
            return page  # the page itself already shows the problem
        if lock.pill_note:
            add_pill_note(page, lock.pill_note)
        if lock.locked:
            return replace_composer(page, lock.waiting_line, lock.open_item)
    return page


def _draw_page(search: str | None, refresh: int | None):
    settings = get_settings()
    params = parse_qs((search or "").lstrip("?"))
    if params.get("request"):
        try:
            request_id = params["request"][0]
            # Phase 9: an Enhance request is drawn by its own screen while it finds the program.
            enhance = get_enhance_view(settings, request_id)
            if enhance is not None and (
                enhance.step in ENHANCE_FIND_STEPS
                or (enhance.step == "e_fresh" and not enhance.understand_started)
            ):
                return render_enhance_workspace(enhance)
            view = get_understand_view(settings, request_id)
            if view.request.status in UNDERSTAND_STATUSES:
                return render_workspace(
                    view,
                    switch_offer=enhance_flow.has_open_offer(settings, request_id),
                    enhance=understand_extras(settings, view, enhance),
                )
            try:
                discovery = get_discovery_view(settings, request_id)
            except DiscoveryError:
                if view.request.status != STATUS_ESCALATION:
                    raise
                # Phase 10: escalated from Understand before the record was confirmed. There is
                # no Discover to draw, so the Understand screen shows the (read-only) request.
                return render_workspace(
                    view,
                    switch_offer=enhance_flow.has_open_offer(settings, request_id),
                    enhance=understand_extras(settings, view, enhance),
                )
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
                build = tester_flow.get_build_view(settings, request_id) if has_build else None
                if build is not None:
                    build = get_tagged_build(settings, request_id, build, approach.plan)
                refine = get_refine_bar(settings, request_id) if build is not None else None
                history = get_history(settings, request_id) if build is not None else None
                panel = (
                    get_refine_build_panel(settings, request_id, build)
                    if build is not None
                    else None
                )
                handoff = (
                    get_handoff_box(settings, request_id, status, workspace.mode)
                    if workspace is not None
                    else None
                )
                return render_approach_workspace(
                    view, discovery, approach, workspace, build, refine, history, panel,
                    enhance=approach_extras(settings, request_id, enhance),
                    handoff=handoff,
                )
            # A requirement lane runs Discover again; the Refine bar replaces its buttons.
            lane_bar = get_refine_bar(settings, request_id)
            extras = discover_extras(settings, discovery, enhance)
            if status == STATUS_DISCOVERY_CONFIRMED:
                approach = approach_flow.get_approach_view(settings, request_id)
                return render_discover_workspace(
                    view, discovery, approach, lane_bar, enhance=extras
                )
            return render_discover_workspace(view, discovery, None, lane_bar, enhance=extras)
        except (UnderstandError, DatabaseBusyError) as error:
            return render_message_page(str(error))
    if params.get("new"):
        return render_new_workspace(demo_mode=settings.llm_provider == "fake")
    try:
        requests = list_my_requests(settings)
        notes = pill_notes(settings, [request.request_id for request in requests])
        return render_home(requests, notes)
    except DatabaseBusyError as error:
        return render_message_page(str(error))


def start_enhance(clicks):
    """Home card 2: create an Enhance request and open it (Phase 9)."""
    if not clicks:
        raise PreventUpdate  # the card is new on every redraw of Home; only a real click counts
    try:
        view = start_enhance_request(get_settings())
    except DatabaseBusyError:
        raise PreventUpdate from None
    return f"?request={view.request_id}"


def answer_switch_offer(switch_clicks, decline_clicks, state, refresh):
    """Card 1: "Switch to Enhance or fix" or "No, this is new" (Phase 9, D-N)."""
    trigger = ctx.triggered_id
    if trigger not in (SWITCH_ID, DECLINE_ID) or not ctx.triggered[0]["value"]:
        raise PreventUpdate
    return perform_switch_answer(get_settings(), trigger, state, refresh)


def perform_switch_answer(settings: Settings, trigger, state, refresh):
    """Call the engine for the answer; a problem is shown under the chat, nothing is written."""
    state = state or {}
    request_id, revision = state.get("request_id"), state.get("revision")
    try:
        if trigger == SWITCH_ID:
            enhance_flow.switch_to_enhance(settings, request_id, revision)
        else:
            enhance_flow.decline_switch(settings, request_id, revision)
    except SHOWN_ERRORS as error:
        return no_update, str(error)
    return (refresh or 0) + 1, ""


def change_mark(values, state, refresh):
    """A dropdown of the "After the change" column changed on the Safety net tab (step 18b)."""
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or trigger.get("type") != MARK_TYPE:
        raise PreventUpdate
    value = ctx.triggered[0]["value"]
    if value is None:
        raise PreventUpdate
    return perform_mark(get_settings(), trigger["index"], value, state, refresh)


def perform_mark(settings: Settings, case_id: str, value: str, state, refresh):
    """Call mark_expected_change. A mark that is already saved (the dropdown fires when it is
    drawn) changes nothing and shows no message. Returns (refresh counter, message)."""
    state = state or {}
    mark = "" if value == MARK_NONE_VALUE else value
    try:
        net_flow.mark_expected_change(
            settings, state.get("request_id"), case_id, mark, state.get("revision")
        )
    except SHOWN_ERRORS as error:
        if "already marked" in str(error):
            raise PreventUpdate from None
        return no_update, str(error)
    return (refresh or 0) + 1, ""


def handle_action(send_clicks, choice_clicks, skip_clicks, text, state, refresh):
    """Send, a choice button or Skip was pressed."""
    trigger = ctx.triggered_id
    # New buttons appear with every redraw; only a real click (a count above zero) counts.
    if trigger is None or not ctx.triggered[0]["value"]:
        raise PreventUpdate
    return perform_action(get_settings(), trigger, text, state, refresh)


def perform_action(settings: Settings, trigger, text, state, refresh):
    """One AI call at a time per request (B2 S5): a busy request gets a plain message."""
    return locked_call(
        (state or {}).get("request_id"),
        lambda: _perform_action(settings, trigger, text, state, refresh),
        lambda message: (no_update, no_update, message),
    )


def _perform_action(settings: Settings, trigger, text, state, refresh):
    """Call the one engine function the button stands for.

    Returns what the three outputs need: the refresh counter (redraw this request), the URL
    query (open a request that was just created) and the message line under the chat.
    """
    state = state or {}
    request_id, revision = state.get("request_id"), state.get("revision")
    message = ""  # a problem of the step that started by itself, shown under the chat
    try:
        if trigger == SEND_ID and request_id is None:
            view = create_understand_request(settings, text or "")
            return no_update, f"?request={view.request.request_id}", ""
        if state.get("refine") and trigger == SEND_ID:
            # Phase 8: Send is Refine's (the Refine box, a correction, the bug description).
            message = run_refine(settings, "send", state, text or "")
        elif state.get("enhance") and trigger != SKIP_ID:
            message = _enhance_action(settings, trigger, request_id, revision, text)
        elif state.get("build") and trigger != SKIP_ID:
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
            message = _discover_choice(settings, request_id, key, revision)
        elif _is_choice(trigger):
            option = _option_at(settings, request_id, revision, trigger["index"])
            if option == NO_NEGATIVE_OPTION:  # B2 S8: the box holds the reason
                set_no_negative_reason(settings, request_id, text or "", revision)
                return (refresh or 0) + 1, no_update, ""
            if option.startswith(EDIT_ASSUMPTION_PREFIX):  # B2 P34: the box holds the new sentence
                edit_assumption(settings, request_id, option, text or "", revision)
                return (refresh or 0) + 1, no_update, ""
            if option.startswith(ASK_EXCEPTION_PREFIX):  # G9 U6: the box holds the reason
                ask_for_exception(settings, request_id, option, text or "", revision)
                return (refresh or 0) + 1, no_update, ""
            view = choose_option(settings, request_id, option, revision)
            if view.request.status == STATUS_CONFIRMED:
                # Proceed worked: Discover starts by itself (Phase 6 fixes, section 3).
                message = _start_by_itself(lambda: _start_discovery_now(settings, request_id))
        else:
            raise PreventUpdate
    except SHOWN_ERRORS as error:
        # Nothing was written. The text stays in the box so the developer can fix it.
        return no_update, no_update, str(error)
    return (refresh or 0) + 1, no_update, message


def _enhance_action(settings: Settings, trigger, request_id: str, revision: int, text) -> str:
    """The one Enhance engine function a click stands for (Phase 9, step 16c). Send is a search.
    A button is looked up again from the saved request: an old window, or an index with no
    button behind it, gets the stale-window message. Every check lives in the engine."""
    if trigger == SEND_ID:
        view = enhance_flow.get_enhance_view(settings, request_id)
        if view is not None and view.step == "s_review":
            # "Correct something": slow (an AI call and a proof), the busy mode covers the wait.
            net_flow.correct_safety_net(settings, request_id, text or "", revision)
            return ""
        enhance_flow.find_program(settings, request_id, text or "", revision)
        return ""
    if not _is_choice(trigger):
        raise PreventUpdate
    view = enhance_flow.get_enhance_view(settings, request_id)
    buttons = enhance_buttons(view) if view is not None else []
    index = trigger["index"]
    if view is None or view.revision != revision or not 0 <= index < len(buttons):
        raise StaleRevisionError(STALE_MESSAGE)
    key = buttons[index][0]
    if key == KEY_FIX:
        enhance_flow.mark_as_fix(settings, request_id, revision)
    elif key == KEY_HELP:
        enhance_help.request_help(settings, request_id, revision)
    elif key == KEY_UNDERSTAND:
        enhance_flow.start_understand(settings, request_id, revision)
    elif key == KEY_TRY_AGAIN:
        # The write runs in the background; the screen shows "writing" while it does (F3).
        net_runner.submit_safety_net(settings, request_id, revision)
    elif key == KEY_CONTINUE:
        net_flow.accept_safety_net(settings, request_id, revision)
        return _start_by_itself(lambda: _start_approach_now(settings, request_id))
    elif key.startswith(KEY_PICK + PICK_SEPARATOR):
        _, path, capability = key.split(PICK_SEPARATOR, 2)
        picks = {path: capability} if capability else {}
        enhance_flow.confirm_targets(settings, request_id, [path], picks, revision)
    else:
        raise PreventUpdate
    return ""


def _start_by_itself(step) -> str:
    """Run the next step right after the one the developer clicked, which is already saved.

    If it fails, its own screen offers "Try again", so the page is redrawn and the plain message
    shows under the chat. Returns that message, or "" when all went well."""
    try:
        step()
    except SHOWN_ERRORS as error:
        return str(error)
    return ""


def _start_discovery_now(settings: Settings, request_id: str) -> None:
    start_discovery(settings, request_id, get_discovery_view(settings, request_id).revision)


def _start_approach_now(settings: Settings, request_id: str) -> None:
    approach_flow.start_approach(
        settings, request_id, approach_flow.get_approach_view(settings, request_id).revision
    )


def handle_form(submit_clicks, answers, state, refresh):
    """Submit was pressed on the 4-box form."""
    if not submit_clicks or not any(submit_clicks):
        raise PreventUpdate
    return perform_form(get_settings(), answers, state, refresh)


def perform_form(settings: Settings, answers, state, refresh):
    return locked_call(
        (state or {}).get("request_id"),
        lambda: _perform_form(settings, answers, state, refresh),
        lambda message: (no_update, message, [""] * len(FORM_BOXES_COUNT)),
    )


def _perform_form(settings: Settings, answers, state, refresh):
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
    view = tester_flow.get_build_view(settings, request_id)
    index = trigger["index"]
    if view.revision != revision or not 0 <= index < len(view.buttons):
        raise StaleRevisionError(STALE_MESSAGE)
    key = view.buttons[index][0]
    if key == tester_flow.RERUN_KEY:  # Phase 7: a synchronous review; the busy mode covers the wait
        tester_flow.rerun_review(settings, request_id, revision)
        return
    actions = {
        build_flow.STOP_KEY: build_flow.stop_build,
        build_flow.TRY_AGAIN_KEY: build_flow.try_again,
        build_flow.CHANGE_APPROACH_KEY: build_flow.change_approach,
        build_flow.HELP_KEY: build_flow.request_help,
    }
    state = actions[key](settings, request_id, revision)
    if state.step == "b_running":
        build_runner.submit_build(settings, request_id)


def handle_finding(clicks, reasons, state, refresh):
    """A finding button was pressed on the Tests tab (Accept, Reopen or Dispute)."""
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not ctx.triggered[0]["value"]:
        raise PreventUpdate
    boxes = ctx.states_list[0]
    typed = {box["id"]["index"]: value for box, value in zip(boxes, reasons, strict=True)}
    return perform_finding_action(get_settings(), trigger["index"], typed, state, refresh)


def perform_finding_action(settings: Settings, index: str, reasons: dict, state, refresh):
    return locked_call(
        (state or {}).get("request_id"),
        lambda: _perform_finding_action(settings, index, reasons, state, refresh),
        lambda message: (no_update, message),
    )


def _perform_finding_action(settings: Settings, index: str, reasons: dict, state, refresh):
    """Call the one Tester flow function the button stands for. `index` is `action:F-n`.
    Returns (refresh counter, message under the chat). Every check lives in the flow."""
    state = state or {}
    action, _, finding_id = index.partition(":")
    request_id, revision = state.get("request_id"), state.get("revision")
    try:
        if not state.get("build") or action not in (
            "accept", "reopen", "dispute", "withdraw", "send", "fixit",
        ):  # fmt: skip
            raise PreventUpdate
        reason = reasons.get(finding_id) or ""
        if action == "fixit":
            if state.get("refine_revision") is None:
                raise PreventUpdate  # no Refine state on the page: nothing to compare with
            # Phase 8: Fix it starts a fix build; the runner is started like for any build.
            return (refresh or 0) + 1, run_refine(settings, "fixit", state, arg=finding_id)
        if action == "accept":
            tester_flow.accept_finding(settings, request_id, revision, finding_id, reason)
        elif action == "reopen":
            tester_flow.reopen_finding(settings, request_id, revision, finding_id)
        elif action == "send":
            tester_flow.send_disputes(settings, request_id, revision)
        elif action == "withdraw":
            tester_flow.withdraw_dispute(settings, request_id, revision, finding_id)
        else:
            tester_flow.dispute_finding(settings, request_id, revision, finding_id, reason)
    except SHOWN_ERRORS as error:
        return no_update, str(error)
    return (refresh or 0) + 1, ""


def poll_needs_redraw(server_step: str | None, drawn_step: str | None) -> bool:
    """Redraw while a build step is running, or when the server step is not the one on screen.
    No build (no step, or `start`) never redraws. The Interval is always on (bug B6), so this
    decision, not the Interval's `disabled` flag, keeps a finished page from redrawing forever."""
    if not server_step or server_step == "start":
        return False
    return server_step in build_flow.RUNNING_STEPS or server_step != drawn_step


def poll_build(n_intervals, state, refresh):
    """Every 3 seconds: redraw when the build is running or its step changed since the draw."""
    writing_net = bool(state) and state.get("enhance") == "s_writing"  # Phase 9: net being written
    if not n_intervals or not state or not (state.get("build") or writing_net):
        raise PreventUpdate
    if not writing_net:
        server_step = build_flow.get_state(get_settings(), state.get("request_id")).step
        if not poll_needs_redraw(server_step, state.get("build_step")):
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
        # Fix G7 D1: a new Discover round; it uses the Discover revision, not the Approach one.
        approach_flow.SEARCH_AGAIN_KEY: lambda s, r, v: start_discovery(
            s, r, get_discovery_view(s, r).revision
        ),
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
        approach_flow.CHANGE_APPROACH_KEY: approach_flow.request_plan_change,
        approach_flow.KEEP_KEY: approach_flow.keep_case,
        approach_flow.DISCARD_KEY: approach_flow.discard_case,
    }
    actions[key](settings, request_id, revision)


def _is_choice(trigger) -> bool:
    return isinstance(trigger, dict) and trigger.get("type") == CHOICE_TYPE


def _discover_choice(settings: Settings, request_id: str, key: str, revision: int) -> str:
    """The one Discover engine function a button stands for. "Findings look right" is followed
    by Approach starting by itself (Phase 6 fixes, section 3); the returned text is a problem of
    that second step, or "" when all went well."""
    if key == START_KEY:
        start_discovery(settings, request_id, revision)
    elif key == CONFIRM_KEY:
        confirm_discovery(settings, request_id, revision)
        enhance = enhance_flow.get_enhance_view(settings, request_id)
        if enhance is not None and enhance.step == "s_writing":
            # Phase 9: an enhance request writes its safety net first; Approach comes after OK.
            net_runner.submit_safety_net(settings, request_id, enhance.revision)
            return ""
        return _start_by_itself(lambda: _start_approach_now(settings, request_id))
    elif key == ESCALATE_KEY:
        escalate_discovery(settings, request_id, revision)
    else:
        raise PreventUpdate
    return ""


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
    # Fix G5 R9: one start-up line, so a new ZIP that lost the data is easy to spot.
    try:
        get_logger(__name__).info(storage_line(get_settings().db_path))
    except ConfigError:
        pass  # the page itself shows the settings problem
    # Draws on first load too, so this one does not use prevent_initial_call.
    # G9 S5: the pathname is an input too, so a menu change always redraws the request page.
    app.callback(
        Output(PAGE_CONTENT_ID, "children"),
        Input(LOCATION_ID, "search"),
        Input(REFRESH_ID, "data"),
        Input(LOCATION_ID, "pathname"),
    )(show_page)

    # Fix G5 N6: the old page (Home and its subtitle) stayed on screen while a slow server built the
    # request page. The browser clears it at once when the address changes; show_page then fills it.
    # G9 S5: only while the Developer Assistant page is the one showing.
    app.clientside_callback(
        OPENING_JS,
        Output(PAGE_CONTENT_ID, "children", allow_duplicate=True),
        Input(LOCATION_ID, "search"),
        Input(LOCATION_ID, "pathname"),
        prevent_initial_call=True,
    )

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
            PAGE_BUSY,
        ],
        prevent_initial_call=True,
    )(handle_action)

    app.callback(
        Output(LOCATION_ID, "search", allow_duplicate=True),
        Input(ENHANCE_CARD_ID, "n_clicks"),
        prevent_initial_call=True,
    )(start_enhance)

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
        running=[
            (Output(BUSY_ID, "style"), {"display": "block"}, {"display": "none"}),
            PAGE_BUSY,
        ],
        prevent_initial_call=True,
    )(handle_form)

    # Phase 7: Accept, Reopen and Dispute on the Tests tab. Pattern ids exist only on that tab.
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input({"type": FINDING_ACT_TYPE, "index": ALL}, "n_clicks"),
        State({"type": FINDING_REASON_TYPE, "index": ALL}, "value"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        running=[
            (Output(BUSY_ID, "style"), {"display": "block"}, {"display": "none"}),
            PAGE_BUSY,
        ],
        prevent_initial_call=True,
    )(handle_finding)

    register_da_workspace_callbacks(app, lambda: get_settings())
    register_da_refine_callbacks(app, lambda: get_settings())
    register_da_handoff_callbacks(app, lambda: get_settings())

    # Card 1 switch offer (Phase 9 step 18a). Registered last so the order tests above still hold.
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input(SWITCH_ID, "n_clicks"),
        Input(DECLINE_ID, "n_clicks"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        prevent_initial_call=True,
    )(answer_switch_offer)

    # Tick more than one program at Find (step 18d).
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input(PICK_CONFIRM_ID, "n_clicks"),
        State(PICK_GROUP_ID, "value"),
        State({"type": CAP_TYPE, "index": ALL}, "value"),
        State({"type": CAP_TYPE, "index": ALL}, "id"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        prevent_initial_call=True,
    )(confirm_picked)

    # F12: each button puts its own waiting line on the busy text when pressed.
    app.clientside_callback(
        BUSY_JS,
        Output(KEYS_ID, "data", allow_duplicate=True),
        Input(PAGE_CONTENT_ID, "children"),
        prevent_initial_call="initial_duplicate",
    )

    # The functions-in-scope tick list at the Understand checkpoint (step 18c).
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input(SCOPE_SAVE_ID, "n_clicks"),
        State(SCOPE_GROUP_ID, "value"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        prevent_initial_call=True,
    )(save_scope)

    # The "After the change" dropdowns of the Safety net tab (step 18b).
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input({"type": MARK_TYPE, "index": ALL}, "value"),
        State(STATE_ID, "data"),
        State(REFRESH_ID, "data"),
        prevent_initial_call=True,
    )(change_mark)

    # Fix G9 S2 and S4 (registered last so the order tests above still hold). The Home screen has
    # no key store, so that State is optional: a missing key clears the tab memory.
    app.clientside_callback(
        SCROLL_TO_FINDINGS_JS,
        Output(KEYS_ID, "data", allow_duplicate=True),
        Input(SEE_FINDINGS_ID, "n_clicks"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        RESTORE_TAB_JS,
        Output(TAB_MEMORY_ID, "data", allow_duplicate=True),
        Input(PAGE_CONTENT_ID, "children"),
        State(TAB_KEY_ID, "data", allow_optional=True),
        State(TAB_MEMORY_ID, "data"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        REMEMBER_TAB_JS,
        Output(TAB_MEMORY_ID, "data"),
        Input(TABS_ID, "value"),
        State(TAB_KEY_ID, "data", allow_optional=True),
        prevent_initial_call=True,
    )
