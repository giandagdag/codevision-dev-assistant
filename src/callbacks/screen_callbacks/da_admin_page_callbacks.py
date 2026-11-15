"""Callbacks of the Admin console (Phase 11a).

Own file: it imports nothing from the developer page callbacks, so the two screens can be copied
and changed apart (spec 11-44). The logic is in plain functions (run_action, form_from_cells) that
tests call without Dash; the Dash wrappers at the bottom only read ids and values and pass them on.
"""

from functools import lru_cache

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, ctx, html
from dash.exceptions import PreventUpdate

from agents.da_admin_access import is_admin
from agents.da_admin_catalog import (
    pattern_offer,
    queue_rows,
    resolve_row,
    resolved_rows,
)
from agents.da_admin_cited import cited_counts, fires_in
from agents.da_admin_diff import build_timeline, diff_rulebooks, plain_diff_lines
from agents.da_admin_forms import (
    RESULT_PROBLEMS,
    RESULT_SAVED,
    RESULT_STALE,
    add_rule_row,
    move_row,
    save_from_form,
)
from agents.da_admin_index import recent_runs
from agents.da_admin_metrics import WINDOW_ALL, WINDOW_LABELS, health_report
from agents.da_admin_modules import module_paths
from agents.da_admin_overview import (
    MISSING_BACKUP_FILTER,
    build_overview,
    server_settings_view,
)
from agents.da_admin_rebuild import running_since, start_rebuild
from configs.da_config import Settings, load_settings
from db_table_functions.db_tbl_da_rulebook import (
    RulebookError,
    get_active_version,
    get_version,
    restore_version,
)
from layouts.da_admin_index_panels import (
    REBUILD_BTN,
    REBUILD_CONFIRM,
    REBUILD_LATER,
    REBUILD_MODAL,
    REBUILD_POLL,
    REBUILD_STATUS,
    rebuild_status,
)
from layouts.da_admin_page import (
    ACTION_CANCEL,
    ACTION_EDIT,
    ACTION_RELOAD,
    ACTION_SAVE,
    ADMIN_CONTENT_ID,
    ADMIN_PATH,
    ADMIN_TABS,
    ADMIN_TABS_ID,
    BASE_STORE_TYPE,
    CAP_LIST_ID,
    CAP_MISSING_ID,
    CAP_SEARCH_ID,
    CATALOG_COLUMNS,
    CATALOG_TABLE,
    EDITABLE_TABS,
    EXCLUSION_COLUMNS,
    GLOSSARY_COLUMNS,
    GOLDEN_COLUMNS,
    GOTO_TYPE,
    HEALTH_ID,
    HIST_COMPARE,
    HIST_CONFIRM,
    HIST_PICK_TYPE,
    HIST_RESTORE,
    HIST_TYPE,
    HIST_VIEW,
    MODULE_COLUMNS,
    MODULE_TABLE,
    MOVE_TYPE,
    NOTE_ID_NAME,
    Q_APPLY,
    Q_APPLY_PATTERN,
    Q_APPROVE,
    Q_CONFIRM,
    Q_MOVE,
    Q_SHOW_RESOLVED,
    QUEUE_BUTTON_TYPE,
    QUEUE_NOTE_TYPE,
    QUEUE_PICK_TYPE,
    RULE_COLUMNS,
    RULE_KIND_OF_TAB,
    RULES_TABLE,
    SONAR_FIELD_PREFIX,
    TAB_BUILD,
    TAB_CAPABILITY,
    TAB_CHARTER,
    TAB_CODING,
    TAB_HISTORY,
    TAB_OVERVIEW,
    TAB_REPO,
    TAB_UI,
    TEXT_COLUMN,
    WINDOW_ID,
    ZONE_COLUMNS,
    admin_page,
    body_id,
    catalog_list,
    health_numbers,
    history_view,
    message_notice,
    overview_view,
    problem_notice,
    refusal_page,
    saved_notice,
    tab_button_id,
    tab_content,
)
from layouts.da_inbox_page import INBOX_PATH
from styles import da_styles

NO_RULEBOOK_MESSAGE = (
    "No rulebook has been published yet. Run the loader (smoke check or app start-up) first."
)
LOCATION_ID = "url"  # the same dcc.Location the home shell draws (spec D-B)
DEV_WRAP_ID = "da-dev-wrap"

# The tables each tab owns. An emptied table has no cells on screen, so it must still be in the
# form (otherwise removing the last row could never be saved).
TABLES: dict[str, tuple[str, ...]] = {
    TAB_CHARTER: (
        "in_scope",
        "out_of_scope",
        "architecture_principles",
        "constraints",
        "glossary",
    ),
    TAB_BUILD: ("zones", "protected_files"),
    TAB_UI: (RULES_TABLE,),
    TAB_CODING: (RULES_TABLE, "approved_libraries", "blocked_imports", "golden_examples"),
    TAB_CAPABILITY: (CATALOG_TABLE, MODULE_TABLE),
    TAB_REPO: ("allowed_folders", "workspace_markers", "index_exclusions"),
}
TABLE_COLUMNS = {  # the rest hold one "text"
    "glossary": GLOSSARY_COLUMNS,
    "zones": ZONE_COLUMNS,
    RULES_TABLE: RULE_COLUMNS,
    "golden_examples": GOLDEN_COLUMNS,
    CATALOG_TABLE: CATALOG_COLUMNS,
    MODULE_TABLE: MODULE_COLUMNS,
    "index_exclusions": EXCLUSION_COLUMNS,
}


@lru_cache(maxsize=1)
def get_admin_settings() -> Settings:
    """Read the settings once. Tests replace this."""
    return load_settings()


def admin_content(settings: Settings, pathname: str | None):
    """What the admin area holds for this path: nothing, the refusal, or the console."""
    if pathname != ADMIN_PATH:
        return None
    if not is_admin(settings, settings.developer_id):
        return refusal_page()
    active = get_active_version(settings.db_path)
    if active is None:
        return html.Div(dmc.Text(NO_RULEBOOK_MESSAGE, c=da_styles.MUTED), style=da_styles.PAGE)
    return admin_page(
        active,
        build_timeline(settings.db_path),
        cited_counts(settings.db_path),
        queue_data(settings),
        build_overview(settings),
        health_report(settings.db_path, WINDOW_ALL),
        server_settings_view(settings),
        fires_in(settings.db_path),
    )


def overview_content(settings: Settings):
    """The Overview tab body, recomputed (used when the tab opens). None without a rulebook."""
    active = get_active_version(settings.db_path)
    if active is None:
        return None
    return overview_view(
        active, build_overview(settings), health_report(settings.db_path, WINDOW_ALL)
    )


def health_content(settings: Settings, window: str):
    """Only the health numbers, for the chosen window (no Dash needed to call it)."""
    if window not in WINDOW_LABELS:
        window = WINDOW_ALL
    return health_numbers(health_report(settings.db_path, window))


def developer_page_style(pathname: str | None) -> dict:
    """The developer page stays built but hidden on /admin and /inbox (layout not touched)."""
    return {"display": "none"} if pathname in (ADMIN_PATH, INBOX_PATH) else {}


# --- Reading the form back ---


def form_from_cells(tab: str, cells: list, fields: list, switches: list) -> tuple[dict, str]:
    """Turn the screen's ids and values into the form dict of agents/da_admin_forms.py.

    Each argument is a list of {"id": {...}, "value": ...} as Dash gives them. Returns the form and
    the change note.
    """
    form: dict = {}
    note = ""
    for item in fields:
        name = item["id"]["name"]
        if name == NOTE_ID_NAME:
            note = item.get("value") or ""
        elif name.startswith(SONAR_FIELD_PREFIX):
            form.setdefault("sonar_map", {})[name[len(SONAR_FIELD_PREFIX) :]] = (
                item.get("value") or ""
            )
        else:
            form[name] = item.get("value") or ""
    if switches:
        form["triggers"] = {item["id"]["name"]: bool(item.get("value")) for item in switches}
    for table in TABLES.get(tab, ()):
        form[table] = _table_rows(table, cells)
    return form, note


def _table_rows(table: str, cells: list):
    rows: dict[int, dict] = {}
    for item in cells:
        ident = item["id"]
        if ident["table"] == table:
            rows.setdefault(ident["row"], {})[ident["col"]] = item.get("value") or ""
    ordered = [rows[index] for index in sorted(rows)]
    if table in TABLE_COLUMNS:
        return ordered
    return [row.get(TEXT_COLUMN, "") for row in ordered]


def _with_new_row(form: dict, table: str) -> dict:
    new = {col: "" for col in TABLE_COLUMNS[table]} if table in TABLE_COLUMNS else ""
    return {**form, table: [*form.get(table, []), new]}


def with_added_module(form: dict) -> dict:
    """Add module: the picked path becomes an exact pattern on the picked capability. The picker's
    own row is dropped from the form. An empty pick changes nothing."""
    form = dict(form)
    pick = (form.pop(MODULE_TABLE, None) or [{}])[0]
    capability, path = pick.get("capability", ""), pick.get("path", "")
    for row in form.get(CATALOG_TABLE, []):
        patterns = row["path_patterns"].splitlines()
        if capability and path and row["name"] == capability and path not in patterns:
            row["path_patterns"] = "\n".join([*patterns, path])
    return form


def _without_row(form: dict, table: str, index: int) -> dict:
    rows = [row for i, row in enumerate(form.get(table, [])) if i != index]
    return {**form, table: rows}


# --- What a click does ---


def run_action(
    settings: Settings,
    tab: str,
    action: dict,
    form: dict,
    note: str,
    base_version: int | None,
):
    """Returns (new tab content, True while the tab is being edited). Writes only on Save."""
    active = get_active_version(settings.db_path)
    kind = action["type"]
    if kind == "adm-act":
        name = action["action"]
        if name == ACTION_EDIT:
            return _content(settings, tab, active, editable=True), True
        if name in (ACTION_CANCEL, ACTION_RELOAD):
            return _content(settings, tab, active), False
        if name == ACTION_SAVE:
            return _save(settings, tab, form, note, base_version, active)
    base = get_version(settings.db_path, base_version or active.version_number) or active
    notice = None
    if kind == "adm-add" and action["table"] == MODULE_TABLE:
        form = with_added_module(form)
    elif kind == "adm-add" and action["table"] == RULES_TABLE:
        form, notice = _with_new_rule(settings, tab, form)
    elif kind == "adm-add":
        form = _with_new_row(form, action["table"])
    elif kind == "adm-remove":
        form = _without_row(form, action["table"], action["index"])
    elif kind == MOVE_TYPE:
        table = action["table"]
        form = {**form, table: move_row(form.get(table, []), action["index"], action["step"])}
    return _content(settings, tab, base, editable=True, draft=form, notice=notice), True


def _content(settings: Settings, tab: str, version, **kwargs):
    """tab_content, plus the Cited counts on the Coding tab (read from the Tester's findings)."""
    cited = cited_counts(settings.db_path) if tab == TAB_CODING else None
    queue = queue_data(settings) if tab == TAB_CAPABILITY else None
    server = server_settings_view(settings) if tab == TAB_REPO else None
    fires = fires_in(settings.db_path) if tab == TAB_CODING else None
    return tab_content(tab, version, cited=cited, queue=queue, server=server, fires=fires, **kwargs)


# --- Unassigned queue ---


def queue_data(settings: Settings, show_resolved: bool = False, dialog=None, notice=None) -> dict:
    """What the layout needs to draw the queue block."""
    return {
        "rows": queue_rows(settings),
        "resolved": resolved_rows(settings) if show_resolved else None,
        "dialog": dialog,
        "notice": notice or [],
    }


def _queue_tab(settings: Settings, **kwargs):
    active = get_active_version(settings.db_path)
    return tab_content(TAB_CAPABILITY, active, queue=queue_data(settings, **kwargs))


def run_queue_action(
    settings: Settings,
    action: dict,
    picks: dict,
    notes: dict,
    base_version: int | None,
):
    """One click in the Unassigned queue. Returns the whole Capability catalog tab, redrawn.

    `picks` is {unassigned_id: chosen capability}, `notes` {unassigned_id: change note}. Writes only
    on Resolve (and, with the pattern, one new catalog version)."""
    name, uid = action["action"], action["uid"]
    if name == Q_SHOW_RESOLVED:
        return _queue_tab(settings, show_resolved=True)
    if name == Q_APPROVE:  # take the suggestion: same as Move to <suggested>
        return _start_resolve(settings, Q_MOVE, uid, {uid: action["cap"]})
    if name in (Q_CONFIRM, Q_MOVE):
        return _start_resolve(settings, name, uid, picks)
    if name in (Q_APPLY, Q_APPLY_PATTERN):
        return _apply_resolve(settings, action, notes.get(uid, ""), base_version)
    return _queue_tab(settings)  # Cancel, Hide resolved


def _start_resolve(settings: Settings, name: str, uid: int, picks: dict):
    row = next((r for r in queue_rows(settings) if r.unassigned_id == uid), None)
    if row is None:
        notice = [message_notice("That Unassigned row is not open any more.")]
        return _queue_tab(settings, notice=notice)
    state = "confirmed" if name == Q_CONFIRM else "changed"
    capability = row.picked_capability if name == Q_CONFIRM else (picks.get(uid) or "")
    if not capability:
        return _queue_tab(settings, notice=[message_notice("Choose a capability first.")])
    catalog = get_active_version(settings.db_path).rulebook.policy.capabilities
    reason = pattern_offer(row.path, catalog, capability)
    dialog = {
        "uid": uid,
        "state": state,
        "capability": capability,
        "path": row.path,
        "offer": not reason,
        "reason": reason,
    }
    return _queue_tab(settings, dialog=dialog)


def _apply_resolve(settings: Settings, action: dict, note: str, base_version: int | None):
    result = resolve_row(
        settings,
        action["uid"],
        action["state"],
        action["cap"],
        settings.developer_id,
        add_pattern=action["action"] == Q_APPLY_PATTERN,
        note=note,
        base_version=base_version,
    )
    if result.kind == "resolved":
        text = "Resolved."
        if result.new_version:
            text += f" The catalog is now v{result.new_version}."
        return _queue_tab(settings, notice=[message_notice(text, color="green")])
    if result.stale:
        # The catalog moved on since this screen was drawn: nothing was closed.
        newest = get_active_version(settings.db_path).version_number
        notice = message_notice(result.message, reload_tab=TAB_CAPABILITY, newest=newest)
        return _queue_tab(settings, notice=[notice])
    lines = result.problems or [result.message]
    return _queue_tab(settings, notice=[problem_notice(lines)])


def _with_new_rule(settings: Settings, tab: str, form: dict):
    """Add row on a rule table: take the next rule ID now (11-12), or the cap message (11-13)."""
    rows = list(form.get(RULES_TABLE, []))
    result = add_rule_row(settings.db_path, RULE_KIND_OF_TAB[tab], len(rows))
    if result.message:
        return {**form, RULES_TABLE: rows}, [message_notice(result.message)]
    new = {col: "" for col in RULE_COLUMNS}
    new["rule_id"] = result.rule_id
    return {**form, RULES_TABLE: [*rows, new]}, None


def _index_source_changed(before, after) -> bool:
    """Only a new folder scope or new exclusions make the old index out of date."""
    old, new = before.rulebook.policy, after.rulebook.policy
    return (old.index_folder_scope, old.index_exclusions) != (
        new.index_folder_scope,
        new.index_exclusions,
    )


def rebuild_action(settings: Settings, button: str | None):
    """Rebuild index clicks. Returns (modal opened, status line). Only Rebuild starts a job."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    if button == REBUILD_CONFIRM:
        policy = get_active_version(settings.db_path).rulebook.policy
        started, message = start_rebuild(
            policy, settings.developer_id, provider=settings.llm_provider
        )
        if not started:
            return False, message
    return False, current_rebuild_status()


def current_rebuild_status() -> str:
    return rebuild_status(running_since(), recent_runs())


def _register_rebuild(app) -> None:
    @app.callback(
        Output(REBUILD_MODAL, "opened"),
        Input(REBUILD_BTN, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_confirm(clicks):
        return bool(clicks)

    @app.callback(
        Output(REBUILD_MODAL, "opened", allow_duplicate=True),
        Output(REBUILD_STATUS, "children", allow_duplicate=True),
        Output(REBUILD_BTN, "disabled", allow_duplicate=True),
        Input(REBUILD_CONFIRM, "n_clicks"),
        Input(REBUILD_LATER, "n_clicks"),
        prevent_initial_call=True,
    )
    def answer_confirm(_confirm, _later):
        if not ctx.triggered[0]["value"]:
            raise PreventUpdate
        opened, status = rebuild_action(get_admin_settings(), ctx.triggered_id)
        return opened, status, running_since() is not None

    @app.callback(
        Output(REBUILD_STATUS, "children"),
        Output(REBUILD_BTN, "disabled"),
        Input(REBUILD_POLL, "n_intervals"),
    )
    def poll(_ticks):
        return current_rebuild_status(), running_since() is not None


def _save(settings, tab, form, note, base_version, active):
    base_number = base_version or active.version_number
    result = save_from_form(settings.db_path, tab, form, base_number, settings.developer_id, note)
    if result.kind == RESULT_SAVED:
        saved = get_active_version(settings.db_path)
        notice = saved_notice(saved.version_number, result.warnings)
        ask = tab == TAB_REPO and _index_source_changed(active, saved)
        return _content(settings, tab, saved, notice=[notice], ask_rebuild=ask), False
    base = get_version(settings.db_path, base_number) or active
    if result.kind == RESULT_PROBLEMS:
        notice = problem_notice(result.problems)
    elif result.kind == RESULT_STALE:
        notice = message_notice(result.message, reload_tab=tab, newest=result.newest_version)
    else:
        notice = message_notice(result.message)
    is_active = base.version_number == active.version_number
    return (
        _content(settings, tab, base, editable=True, draft=form, notice=[notice], active=is_active),
        True,
    )


# --- Version history ---


def history_content(
    settings: Settings, diff=None, restore_target=None, notice=None, selected=None
):
    rows = build_timeline(settings.db_path)
    if selected is None and rows:
        # Default: the newest older version (the one an Admin most likely wants to look at).
        selected = rows[1].version_number if len(rows) > 1 else rows[0].version_number
    changes = _selected_changes(settings, rows, selected)
    return history_view(rows, diff, restore_target, notice, selected, changes)


def _selected_changes(settings: Settings, rows, selected):
    """Plain-word lines for what version `selected` changed against the version before it."""
    numbers = [row.version_number for row in rows]
    if selected not in numbers or numbers.index(selected) + 1 >= len(numbers):
        return []  # nothing before the first version
    new = get_version(settings.db_path, selected)
    old = get_version(settings.db_path, numbers[numbers.index(selected) + 1])
    return plain_diff_lines(diff_rulebooks(old.rulebook, new.rulebook))


def run_history_action(settings: Settings, action: dict, from_number, to_number, note: str | None):
    """One click on the Version history tab. Writes only on a confirmed Restore."""
    name = action["action"]
    number = action.get("version") or 0
    if name == HIST_VIEW:
        return history_content(settings, selected=number)
    if name == HIST_RESTORE:
        return history_content(settings, restore_target=number, selected=number)
    if name == HIST_COMPARE:
        return history_content(settings, diff=_compare(settings, from_number, to_number))
    if name == HIST_CONFIRM:
        return _restore(settings, number, note)
    return history_content(settings)  # Cancel, or anything else: back to the plain timeline


def _compare(settings: Settings, from_number, to_number):
    old = get_version(settings.db_path, int(from_number)) if from_number else None
    new = get_version(settings.db_path, int(to_number)) if to_number else None
    if old is None or new is None:
        return None
    return old.version_number, new.version_number, diff_rulebooks(old.rulebook, new.rulebook)


def _restore(settings: Settings, number: int, note: str | None):
    try:
        version = restore_version(settings.db_path, number, settings.developer_id, note or "")
    except RulebookError as error:
        # The Phase 1 refusal text, shown as it is.
        notice = message_notice(str(error), color="red")
        return history_content(settings, restore_target=number, notice=[notice])
    notice = saved_notice(version.version_number, [])
    return history_content(settings, notice=[notice])


def tabs_disabled(editing_tab: str | None) -> list[bool]:
    """While one tab is edited the others are greyed out, in the order of ADMIN_TABS."""
    return [editing_tab is not None and name != editing_tab for name, _, _ in ADMIN_TABS]


# --- Dash wrappers ---


def register_da_admin_page_callbacks(app) -> None:
    @app.callback(
        Output(ADMIN_CONTENT_ID, "children"),
        Output(DEV_WRAP_ID, "style"),
        Input(LOCATION_ID, "pathname"),
    )
    def show_page(pathname):
        return admin_content(get_admin_settings(), pathname), developer_page_style(pathname)

    for tab in EDITABLE_TABS:
        _register_tab(app, tab)
    _register_history(app)
    _register_queue(app)
    _register_overview(app)
    _register_catalog_filter(app)
    _register_rebuild(app)


def refresh_overview(settings: Settings, tab: str | None):
    """A save on another tab changes the areas and the list, so redraw when the tab opens."""
    if tab != TAB_OVERVIEW or not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    content = overview_content(settings)
    if content is None:
        raise PreventUpdate
    return content.children


def change_window(settings: Settings, window: str):
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    return health_content(settings, window)


def _register_overview(app) -> None:
    @app.callback(
        Output(body_id(TAB_OVERVIEW), "children", allow_duplicate=True),
        Input(ADMIN_TABS_ID, "value"),
        prevent_initial_call=True,
    )
    def refresh_overview_on_open(tab):
        return refresh_overview(get_admin_settings(), tab)

    @app.callback(
        Output(HEALTH_ID, "children"),
        Input(WINDOW_ID, "value"),
        prevent_initial_call=True,
    )
    def on_window_change(window):
        return change_window(get_admin_settings(), window)

    @app.callback(
        Output(ADMIN_TABS_ID, "value", allow_duplicate=True),
        Input({"type": GOTO_TYPE, "tab": ALL, "n": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_tab(_clicks):
        settings = get_admin_settings()
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if not is_admin(settings, settings.developer_id):
            raise PreventUpdate
        return triggered["tab"]


def filtered_catalog(settings: Settings, search: str | None, missing_backup: bool | None):
    """The read-only catalog list for the search box and the Missing backup chip."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    policy = get_active_version(settings.db_path).rulebook.policy
    paths = module_paths(policy.index_folder_scope)
    return catalog_list(policy.capabilities, paths, search or "", bool(missing_backup))


def _register_catalog_filter(app) -> None:
    @app.callback(
        Output(CAP_LIST_ID, "children"),
        Input(CAP_SEARCH_ID, "value"),
        Input(CAP_MISSING_ID, "checked"),
        prevent_initial_call=True,
    )
    def on_catalog_filter(search, missing_backup):
        return filtered_catalog(get_admin_settings(), search, missing_backup)

    @app.callback(
        Output(CAP_MISSING_ID, "checked"),
        Input({"type": GOTO_TYPE, "tab": ALL, "n": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def tick_missing_backup(_clicks):
        # The Overview's Assign button carries the filter name in its "n" (see _attention_list).
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if MISSING_BACKUP_FILTER not in str(triggered["n"]):
            raise PreventUpdate
        return True


def _register_history(app) -> None:
    history_body = body_id(TAB_HISTORY)

    @app.callback(
        Output(history_body, "children", allow_duplicate=True),
        Input(ADMIN_TABS_ID, "value"),
        prevent_initial_call=True,
    )
    def refresh_on_open(tab):
        # A save on another tab adds a version, so rebuild the timeline whenever the tab opens.
        settings = get_admin_settings()
        if tab != TAB_HISTORY or not is_admin(settings, settings.developer_id):
            raise PreventUpdate
        return history_content(settings)

    @app.callback(
        Output(history_body, "children", allow_duplicate=True),
        Input({"type": HIST_TYPE, "action": ALL, "version": ALL}, "n_clicks"),
        State({"type": HIST_PICK_TYPE, "name": ALL}, "value"),
        prevent_initial_call=True,
    )
    def on_history_click(_clicks, _picks):
        settings = get_admin_settings()
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if not is_admin(settings, settings.developer_id):
            raise PreventUpdate
        picks = {item["id"]["name"]: item.get("value") for item in ctx.states_list[0]}
        return run_history_action(
            settings, triggered, picks.get("from"), picks.get("to"), picks.get("note")
        )


def queue_inputs_from_states(states_list: list) -> tuple[dict, dict]:
    """Picks and notes by Unassigned ID from the queue callback's three States (picks, notes,
    base store). The clicked button is an Input, so it is not in this list."""
    pick_states, note_states, _base = states_list
    picks = {item["id"]["uid"]: item.get("value") for item in pick_states}
    notes = {item["id"]["uid"]: item.get("value") or "" for item in note_states}
    return picks, notes


def _register_queue(app) -> None:
    button = {"type": QUEUE_BUTTON_TYPE, "action": ALL, "uid": ALL, "cap": ALL, "state": ALL}

    @app.callback(
        Output(body_id(TAB_CAPABILITY), "children", allow_duplicate=True),
        Input(button, "n_clicks"),
        State({"type": QUEUE_PICK_TYPE, "uid": ALL}, "value"),
        State({"type": QUEUE_NOTE_TYPE, "uid": ALL}, "value"),
        State({"type": BASE_STORE_TYPE, "tab": TAB_CAPABILITY}, "data"),
        prevent_initial_call=True,
    )
    def on_queue_click(_clicks, _picks, _notes, base_version):
        settings = get_admin_settings()
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if not is_admin(settings, settings.developer_id):
            raise PreventUpdate
        picks, notes = queue_inputs_from_states(ctx.states_list)
        return run_queue_action(settings, triggered, picks, notes, base_version)


def _register_tab(app, tab: str) -> None:
    def pattern(kind, *keys):
        return {"type": kind, "tab": tab, **{key: ALL for key in keys}}

    outputs = [Output(body_id(tab), "children", allow_duplicate=True)] + [
        Output(tab_button_id(name), "disabled", allow_duplicate=True) for name, _, _ in ADMIN_TABS
    ]

    @app.callback(
        *outputs,
        Input(pattern("adm-act", "action"), "n_clicks"),
        Input(pattern("adm-add", "table", "index"), "n_clicks"),
        Input(pattern("adm-remove", "table", "index"), "n_clicks"),
        Input(pattern(MOVE_TYPE, "table", "index", "step"), "n_clicks"),
        State(pattern("adm-cell", "table", "row", "col"), "value"),
        State(pattern("adm-field", "name"), "value"),
        State(pattern("adm-switch", "name"), "checked"),
        State({"type": BASE_STORE_TYPE, "tab": tab}, "data"),
        prevent_initial_call=True,
    )
    def on_click(_acts, _adds, _removes, _moves, cells, fields, switches, base_version):
        settings = get_admin_settings()
        triggered = ctx.triggered_id
        # Buttons that were just drawn also "trigger"; a real click has a click count.
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if not is_admin(settings, settings.developer_id):
            raise PreventUpdate
        # ctx.states_list holds, per State, a list of {"id", "property", "value"} entries.
        cell_states, field_states, switch_states, _base = ctx.states_list
        form, note = form_from_cells(tab, cell_states, field_states, switch_states)
        content, editing = run_action(settings, tab, triggered, form, note, base_version)
        return (content, *tabs_disabled(tab if editing else None))
