"""Callbacks of the senior Inbox (Phase 10 step 10b).

Own file: it imports nothing from the developer page callbacks (test 10-50), only the layout
functions and the plain flow modules. The logic is in plain functions that tests call without
Dash; the wrappers at the bottom only read ids and values and pass them on. No AI call here.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import parse_qs

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from agents import da_approach_flow as approach_flow
from agents import da_build_flow as build_flow
from agents import da_senior_actions as senior
from agents import da_tester_flow as tester_flow
from agents import da_workspace_flow as workspace_flow
from agents.da_discover_flow import get_discovery_view
from agents.da_handoff_screen import get_handoff_box
from agents.da_inbox import (
    banner_text,
    get_inbox_row,
    inbox_rows,
    menu_label,
    open_finding_options,
    senior_open_count,
)
from agents.da_refine_actions import get_refine_bar
from agents.da_refine_screen import get_history, get_refine_build_panel, get_tagged_build
from agents.da_senior_access import NOT_SENIOR_MESSAGE, is_senior
from agents.da_senior_reopen import reopen_decisions
from agents.da_understand_flow import get_understand_view
from configs.da_config import Settings, load_settings
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_discovery import DiscoveryError
from db_table_functions.db_tbl_da_understand import StaleRevisionError, UnderstandError
from layouts.da_developer_assistant_page import (
    render_approach_workspace,
    render_discover_workspace,
    render_workspace,
    replace_composer,
)
from layouts.da_inbox_page import (
    BANNER_ID,
    FILTER_MINE,
    INBOX_ACT_TYPE,
    INBOX_CANCEL_ID,
    INBOX_CLOSED_ID,
    INBOX_DETAIL_ID,
    INBOX_ERROR_ID,
    INBOX_FILTER_ID,
    INBOX_FINDING_ID,
    INBOX_LIST_ID,
    INBOX_MODAL_ID,
    INBOX_MODE_ID,
    INBOX_NOTICE_ID,
    INBOX_OUTCOME_ID,
    INBOX_PATH,
    INBOX_REFRESH_ID,
    INBOX_ROUNDS_ID,
    INBOX_SHELL_ID,
    INBOX_SUBMIT_ID,
    INBOX_TARGET_ID,
    INBOX_TEXT_ID,
    MENU_LINK_ID,
    MODE_CLOSE,
    MODE_GUIDANCE,
    MODE_OVERRULE,
    MODE_TAKE_OVER,
    MODE_TITLES,
    OUTCOME_ABANDON,
    OUTCOME_MORE,
    READ_ONLY_LINE,
    action_bar,
    inbox_list,
    read_only,
    refusal_page,
)
from pydantic_classes.da_models import (
    STATUS_BUILDING,
    STATUS_ESCALATION,
    STATUS_HANDED_OFF,
    STATUS_NOT_PASSING,
    STATUS_READY_FOR_REVIEW,
    STATUS_READY_TO_BUILD,
    STATUS_REVISION,
    STATUS_TESTER_REVIEW,
)
from styles import da_styles

LOCATION_ID = "url"  # the dcc.Location the home shell draws
SHOWN_ERRORS = (UnderstandError, StaleRevisionError, DatabaseBusyError)
# The statuses where the request has a workspace and a build to draw (same list as the
# developer page; copied so the two screens stay apart).
WORKSPACE_STATUSES = (
    STATUS_READY_TO_BUILD,
    STATUS_BUILDING,
    STATUS_TESTER_REVIEW,
    STATUS_READY_FOR_REVIEW,
    STATUS_HANDED_OFF,
    STATUS_NOT_PASSING,
    STATUS_REVISION,
)
HIDDEN = {"display": "none"}


@lru_cache(maxsize=1)
def get_inbox_settings() -> Settings:
    """Read the settings once. Tests replace this."""
    return load_settings()


def default_identify(_search: str | None) -> str:
    """Who is looking, at work: the logged-in user, and nobody else. The home shell passes its own
    function instead (it may read `?as=`); no code here reads that query (spec D-G)."""
    return get_inbox_settings().developer_id


@dataclass
class InboxView:
    """What the callback hands to the screen."""

    shell_style: dict = field(default_factory=lambda: dict(HIDDEN))
    listing: list = field(default_factory=list)
    detail: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    target: dict | None = None


def escalation_id_from(search: str | None) -> int | None:
    wanted = parse_qs((search or "").lstrip("?")).get("escalation")
    return int(wanted[0]) if wanted and wanted[0].isdigit() else None


def inbox_view(
    settings: Settings, pathname: str | None, search: str | None, user: str,
    mine: bool = True, show_closed: bool = False, link_extra: str = "",
) -> InboxView:  # fmt: skip
    """The whole inbox for this path: hidden elsewhere, the refusal for a non-senior, else the
    list and (when a row is picked) the read-only request under the action bar. `link_extra` is
    added to every row link (the home shell uses it to keep its `?as=` switch)."""
    if pathname != INBOX_PATH:
        return InboxView()
    shell = {**da_styles.PAGE}
    if not is_senior(settings, user):
        return InboxView(shell_style=shell, listing=[refusal_page()])
    try:
        return _senior_view(settings, search, user, mine, show_closed, link_extra, shell)
    except SHOWN_ERRORS as error:  # a busy database is a sentence, not a Dash error page
        return InboxView(shell_style=shell, listing=[html.Div(str(error), style={"color": "red"})])


def _senior_view(settings, search, user, mine, show_closed, link_extra, shell) -> InboxView:
    senior.route_pre_phase_10(settings)  # rows for escalations opened before this phase (10-32)
    rows = inbox_rows(settings, user, mine, show_closed)
    view = InboxView(shell_style=shell, listing=inbox_list(rows, link_extra))
    picked = escalation_id_from(search)
    row = get_inbox_row(settings, picked) if picked else None
    if row is None:
        return view
    closed = row.outcome != "open"
    view.detail = [action_bar(row, closed), *request_page(settings, row.request_id)]
    view.findings = [] if closed else open_finding_options(settings, row.request_id)
    view.target = {"escalation_id": row.escalation_id, "revision": row.revision,
                   "request_id": row.request_id}  # fmt: skip
    return view


def request_page(settings: Settings, request_id: str) -> list:
    """The developer's view of the request, read-only: same layout functions, controls removed."""
    try:
        page = _draw(settings, request_id)
    except (UnderstandError, DatabaseBusyError) as error:
        return [html.Div(str(error), style={"color": "red"})]
    return read_only(replace_composer(page, READ_ONLY_LINE))


def _draw(settings: Settings, request_id: str) -> list:
    view = get_understand_view(settings, request_id)
    status = view.request.status
    try:
        discovery = get_discovery_view(settings, request_id)
    except DiscoveryError:
        return render_workspace(view)  # escalated before Discover: the Understand screen
    if not approach_flow.has_approach(settings, request_id):
        lane_bar = get_refine_bar(settings, request_id)
        return render_discover_workspace(view, discovery, None, lane_bar)
    approach = approach_flow.get_approach_view(settings, request_id)
    has_build = status in WORKSPACE_STATUSES or (
        status == STATUS_ESCALATION and build_flow.get_state(settings, request_id).build_number > 0
    )
    workspace = workspace_flow.get_workspace_view(settings, request_id) if has_build else None
    build = tester_flow.get_build_view(settings, request_id) if has_build else None
    if build is not None:
        build = get_tagged_build(settings, request_id, build, approach.plan)
    refine = get_refine_bar(settings, request_id) if build is not None else None
    history = get_history(settings, request_id) if build is not None else None
    panel = get_refine_build_panel(settings, request_id, build) if build is not None else None
    handoff = (
        get_handoff_box(settings, request_id, status, workspace.mode)
        if workspace is not None
        else None
    )
    return render_approach_workspace(
        view, discovery, approach, workspace, build, refine, history, panel, handoff=handoff
    )


# --- the four actions ---


def run_senior_action(
    settings: Settings, mode: str, target: dict | None, user: str, text: str | None = None,
    finding: str | None = None, outcome: str | None = None, rounds: str | int | None = None,
) -> str:  # fmt: skip
    """Do one action and return the green line. Raises SeniorActionError (or the stale error)
    with words the senior can read."""
    if not is_senior(settings, user):
        raise senior.SeniorActionError(NOT_SENIOR_MESSAGE)
    if not target:
        raise senior.SeniorActionError("Open an escalation from the list first.")
    escalation_id, revision = target["escalation_id"], target["revision"]
    request_id = target["request_id"]
    if mode == MODE_OVERRULE:
        if not finding:
            raise senior.SeniorActionError("Pick the finding to overrule.")
        senior.overrule_finding(settings, escalation_id, revision, user, finding, text or "")
        return f"Overruled {finding} on {request_id}"
    if mode == MODE_GUIDANCE:
        senior.send_guidance(settings, escalation_id, revision, user, text or "")
        return f"Guidance sent to {request_id}"
    if mode == MODE_TAKE_OVER:
        senior.take_over(settings, escalation_id, revision, user)
        return f"You have taken over {request_id}"
    if mode == MODE_CLOSE:
        chosen = outcome or "returned"
        if chosen == OUTCOME_MORE:
            reopen_decisions(settings, escalation_id, revision, user, int(rounds or 0), text or "")
            return f"Returned to the developer with {rounds} more decision rounds: {request_id}"
        senior.close_escalation(settings, escalation_id, revision, user, chosen, text or "")
        done = "Closed" if chosen == OUTCOME_ABANDON else "Returned to the developer:"
        return f"{done} {request_id}"
    raise senior.SeniorActionError("That action is not known.")


def menu_and_banner(
    settings: Settings, user: str, pathname: str | None, search: str | None = ""
):
    """The menu label (with the count for a senior) and the home banner text (or None). The
    banner is for Home itself, not for a request or the blank workspace."""
    try:
        count = senior_open_count(settings, user)
    except SHOWN_ERRORS:
        return menu_label(0), None  # the menu runs on every page: never an error page
    params = parse_qs((search or "").lstrip("?"))
    home = pathname in (None, "/") and not (params.get("request") or params.get("new"))
    return menu_label(count), (banner_text(count) if home else None)


# --- Dash wrappers ---


def register_da_inbox_page_callbacks(app, identify=None, keep_query=None) -> None:
    """`identify(search)` says who is looking; `keep_query(search)` is added to the row links.
    Both default to plain work behaviour (the logged-in user, no extra query). Only the home
    shell passes its own, to support `?as=<id>` (spec D-G)."""
    who = identify or default_identify
    keep = keep_query or (lambda _search: "")
    @app.callback(
        Output(INBOX_SHELL_ID, "style"),
        Output(INBOX_LIST_ID, "children"),
        Output(INBOX_DETAIL_ID, "children"),
        Output(INBOX_FINDING_ID, "data"),
        Output(INBOX_TARGET_ID, "data"),
        Input(LOCATION_ID, "pathname"),
        Input(LOCATION_ID, "search"),
        Input(INBOX_FILTER_ID, "value"),
        Input(INBOX_CLOSED_ID, "checked"),
        Input(INBOX_REFRESH_ID, "data"),
    )
    def show_inbox(pathname, search, filter_value, closed, _refresh):
        settings = get_inbox_settings()
        view = inbox_view(
            settings, pathname, search, who(search),
            mine=filter_value == FILTER_MINE, show_closed=bool(closed), link_extra=keep(search),
        )  # fmt: skip
        return view.shell_style, view.listing, view.detail, view.findings, view.target

    @app.callback(
        Output(MENU_LINK_ID, "label"),
        Output(BANNER_ID, "children"),
        Output(BANNER_ID, "style"),
        Input(LOCATION_ID, "pathname"),
        Input(LOCATION_ID, "search"),
        Input(INBOX_REFRESH_ID, "data"),
    )
    def show_menu_and_banner(pathname, search, _refresh):
        label, banner = menu_and_banner(get_inbox_settings(), who(search), pathname, search)
        if not banner:
            return label, None, HIDDEN
        extra = keep(search)  # "&as=x" in the home shell: the link starts a query with "?"
        href = f"{INBOX_PATH}?{extra[1:]}" if extra else INBOX_PATH
        return label, [f"{banner}. ", dcc.Link("Open the Inbox", href=href)], {}

    _register_actions(app, who)


def _register_actions(app, who) -> None:
    @app.callback(
        Output(INBOX_MODAL_ID, "opened", allow_duplicate=True),
        Output(INBOX_MODAL_ID, "title"),
        Output(INBOX_MODE_ID, "data"),
        Output(INBOX_FINDING_ID, "style"),
        Output(INBOX_OUTCOME_ID, "style"),
        Output(INBOX_TEXT_ID, "value", allow_duplicate=True),
        Output(INBOX_ERROR_ID, "children", allow_duplicate=True),
        Output(INBOX_NOTICE_ID, "children", allow_duplicate=True),
        Output(INBOX_NOTICE_ID, "c", allow_duplicate=True),
        Output(INBOX_REFRESH_ID, "data", allow_duplicate=True),
        Output(INBOX_ROUNDS_ID, "style"),
        Input({"type": INBOX_ACT_TYPE, "action": ALL}, "n_clicks"),
        State(INBOX_TARGET_ID, "data"),
        State(INBOX_REFRESH_ID, "data"),
        State(LOCATION_ID, "search"),
        prevent_initial_call=True,
    )
    def on_action_button(_clicks, target, refresh, search):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        mode = triggered["action"]
        if mode == MODE_TAKE_OVER:  # no text needed: do it now
            try:
                line = run_senior_action(get_inbox_settings(), mode, target, who(search))
            except SHOWN_ERRORS as error:
                return (no_update, no_update, no_update, no_update, no_update, no_update,
                        no_update, str(error), "red", (refresh or 0) + 1, no_update)  # fmt: skip
            return (no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, line, "green", (refresh or 0) + 1, no_update)  # fmt: skip
        return (
            True, MODE_TITLES[mode], mode,
            {} if mode == MODE_OVERRULE else HIDDEN,
            {} if mode == MODE_CLOSE else HIDDEN,
            "", "", no_update, no_update, no_update,
            {} if mode == MODE_CLOSE else HIDDEN,
        )  # fmt: skip

    @app.callback(
        Output(INBOX_MODAL_ID, "opened", allow_duplicate=True),
        Output(INBOX_ERROR_ID, "children", allow_duplicate=True),
        Output(INBOX_NOTICE_ID, "children", allow_duplicate=True),
        Output(INBOX_NOTICE_ID, "c", allow_duplicate=True),
        Output(INBOX_REFRESH_ID, "data", allow_duplicate=True),
        Input(INBOX_SUBMIT_ID, "n_clicks"),
        Input(INBOX_CANCEL_ID, "n_clicks"),
        State(INBOX_MODE_ID, "data"),
        State(INBOX_TEXT_ID, "value"),
        State(INBOX_FINDING_ID, "value"),
        State(INBOX_OUTCOME_ID, "value"),
        State(INBOX_ROUNDS_ID, "value"),
        State(INBOX_TARGET_ID, "data"),
        State(INBOX_REFRESH_ID, "data"),
        State(LOCATION_ID, "search"),
        prevent_initial_call=True,
    )
    def on_submit(submit, cancel, mode, text, finding, outcome, rounds, target, refresh, search):
        if ctx.triggered_id == INBOX_CANCEL_ID:
            return False, "", no_update, no_update, no_update
        if not submit:
            raise PreventUpdate
        try:
            line = run_senior_action(
                get_inbox_settings(), mode, target, who(search), text, finding, outcome, rounds
            )
        except SHOWN_ERRORS as error:
            return no_update, str(error), no_update, no_update, no_update  # dialog stays open
        return False, "", line, "green", (refresh or 0) + 1
