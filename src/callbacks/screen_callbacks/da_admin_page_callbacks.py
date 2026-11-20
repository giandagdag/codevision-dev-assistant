"""Callbacks of the Admin console (Phase 11a).

Own file: it imports nothing from the developer page callbacks, so the two screens can be copied
and changed apart (spec 11-44). The logic is in plain functions (run_action, form_from_cells) that
tests call without Dash; the Dash wrappers at the bottom only read ids and values and pass them on.
"""

from functools import lru_cache
from pathlib import PurePosixPath

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from agents import da_admin_job as job
from agents.da_admin_access import is_admin
from agents.da_admin_catalog import (
    pattern_offer,
    queue_rows,
    resolve_row,
    resolved_rows,
)
from agents.da_admin_cited import cited_counts, fires_in
from agents.da_admin_diff import (
    build_timeline,
    diff_rulebooks,
    open_request_lines,
    plain_diff_lines,
)
from agents.da_admin_forms import (
    RESULT_PROBLEMS,
    RESULT_SAVED,
    RESULT_STALE,
    add_rule_row,
    capability_rows,
    move_row,
    save_from_form,
)
from agents.da_admin_index import recent_runs
from agents.da_admin_meaning import meaning_search
from agents.da_admin_metrics import WINDOW_ALL, WINDOW_LABELS, health_report
from agents.da_admin_modules import module_paths
from agents.da_admin_overview import (
    MISSING_BACKUP_FILTER,
    build_overview,
    server_settings_view,
)
from agents.da_admin_rebuild import running_since, start_rebuild
from agents.da_admin_sonar import load_snapshot, refresh_snapshot, source_pill
from agents.da_admin_tag_cards import (
    ai_cards,
    approve_all_high,
    approve_card,
    high_confidence_counts,
    reject_card,
)
from agents.da_admin_tag_store import read_tags
from configs.da_config import Settings, load_settings
from db_table_functions.db_tbl_da_rulebook import (
    RulebookError,
    get_active_version,
    get_version,
    restore_version,
)
from layouts.da_admin_catalog_meaning import (
    CAP_MEANING_ID,
    HIT_TYPE,
    meaning_results,
    no_hits_line,
)
from layouts.da_admin_catalog_tab import (
    Q_AI_ALL,
    Q_AI_ALL_DO,
    Q_AI_APPROVE,
    Q_AI_ASSIGN,
    Q_AI_REJECT,
)
from layouts.da_admin_coding_tab import (
    GOLDEN_CHANGE_TYPE,
    RULE_PANEL_ID,
    RULE_PICK_TYPE,
    module_start,
    rule_panel,
)
from layouts.da_admin_index_panels import (
    REBUILD_BTN,
    REBUILD_CONFIRM,
    REBUILD_FULL_BTN,
    REBUILD_FULL_CONFIRM,
    REBUILD_FULL_LATER,
    REBUILD_FULL_MODAL,
    REBUILD_LATER,
    REBUILD_MODAL,
    REBUILD_POLL,
    REBUILD_PROGRESS,
    REBUILD_STATUS,
    REBUILD_STOP,
    job_panel,
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
    HEADER_VERSION_ID,
    HEALTH_ID,
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
    Q_NEW,
    Q_REJECT,
    Q_SHOW_RESOLVED,
    QUEUE_BUTTON_TYPE,
    QUEUE_NOTE_TYPE,
    QUEUE_PICK_TYPE,
    RULE_COLUMNS,
    RULE_KIND_OF_TAB,
    RULES_TABLE,
    SONAR_FIELD_PREFIX,
    SONAR_PILL,
    SONAR_REFRESH_BTN,
    SONAR_SAMPLE_ID,
    SONAR_STATUS,
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
    header_version,
    health_numbers,
    history_view,
    message_notice,
    overview_view,
    problem_notice,
    refusal_page,
    saved_notice,
    sonar_sample_view,
    tab_button_id,
    tab_content,
)
from layouts.da_capability_map_view import MAP_PATH
from layouts.da_inbox_page import INBOX_PATH
from layouts.da_test_report_page import REPORT_PREFIX
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
    hidden = pathname in (ADMIN_PATH, INBOX_PATH, MAP_PATH) or (pathname or "").startswith(
        REPORT_PREFIX
    )
    return {"display": "none"} if hidden else {}


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
    server = server_settings_view(settings) if tab in (TAB_REPO, TAB_BUILD) else None
    fires = fires_in(settings.db_path) if tab == TAB_CODING else None
    return tab_content(tab, version, cited=cited, queue=queue, server=server, fires=fires, **kwargs)


# --- Unassigned queue ---


def queue_data(
    settings: Settings, show_resolved: bool = False, dialog=None, notice=None, ai_confirm=False
) -> dict:
    """What the layout needs to draw the queue block."""
    return {
        "rows": queue_rows(settings),
        "resolved": resolved_rows(settings) if show_resolved else None,
        "dialog": dialog,
        "notice": notice or [],
        "ai_cards": ai_cards(),
        "ai_confirm": {"counts": high_confidence_counts()} if ai_confirm else None,
    }


def _ai_action(
    settings: Settings, name: str, path: str, picks: dict, base_version: int | None, cap: str
):
    """Approve, Assign to, Reject and Approve all on the AI scan cards."""
    if name == Q_AI_ALL:
        return _queue_tab(settings, ai_confirm=True)
    if name == Q_AI_REJECT:
        reject_card(path, who=settings.developer_id)
        return _queue_tab(settings, notice=[message_notice("Rejected.", color="green")])
    if name == Q_AI_ALL_DO:
        result = approve_all_high(settings, settings.developer_id, base_version)
    else:
        target = cap if name == Q_AI_APPROVE else (picks.get(path) or "")
        if not target:
            return _queue_tab(settings, notice=[message_notice("Choose a capability first.")])
        result = approve_card(settings, path, target, settings.developer_id, base_version)
    if result.kind == "resolved":
        text = "Card closed."
        if result.new_version:
            text = f"Approved. The catalog is now v{result.new_version}."
        if result.message:  # some paths were already matched: say by which capability
            text += f" {result.message}"
        return _queue_tab(settings, notice=[message_notice(text, color="green")])
    if result.stale:
        newest = get_active_version(settings.db_path).version_number
        notice = message_notice(result.message, reload_tab=TAB_CAPABILITY, newest=newest)
        return _queue_tab(settings, notice=[notice])
    return _queue_tab(settings, notice=[problem_notice(result.problems or [result.message])])


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
    if name in (Q_AI_APPROVE, Q_AI_ASSIGN, Q_AI_REJECT, Q_AI_ALL, Q_AI_ALL_DO):
        return _ai_action(settings, name, uid, picks, base_version, action["cap"])
    if name == Q_SHOW_RESOLVED:
        return _queue_tab(settings, show_resolved=True)
    if name == Q_APPROVE:  # take the suggestion: same as Move to <suggested>
        return _start_resolve(settings, Q_MOVE, uid, {uid: action["cap"]})
    if name == Q_REJECT:
        return _reject(settings, uid)
    if name == Q_NEW:
        return _new_capability(settings, uid)
    if name in (Q_CONFIRM, Q_MOVE):
        return _start_resolve(settings, name, uid, picks)
    if name in (Q_APPLY, Q_APPLY_PATTERN):
        return _apply_resolve(settings, action, notes.get(uid, ""), base_version)
    return _queue_tab(settings)  # Cancel, Hide resolved


def _reject(settings: Settings, uid: int):
    """Reject: the file belongs in no capability. Closes the row; a later change reopens it."""
    result = resolve_row(settings, uid, "rejected", "", settings.developer_id)
    if result.kind == "resolved":
        return _queue_tab(settings, notice=[message_notice("Rejected.", color="green")])
    return _queue_tab(settings, notice=[problem_notice(result.problems or [result.message])])


def _new_capability(settings: Settings, uid: int):
    """New capability: the catalog in edit mode with one extra row whose pattern is the file's
    folder. The name stays empty (the suggestion is an existing capability); Save is the normal
    Save with a note, and the queue row stays open until Admin resolves it."""
    row = next((r for r in queue_rows(settings) if r.unassigned_id == uid), None)
    if row is None:
        notice = [message_notice("That Unassigned row is not open any more.")]
        return _queue_tab(settings, notice=notice)
    active = get_active_version(settings.db_path)
    folder, _, _ = row.path.replace("\\", "/").rpartition("/")
    new = {
        "name": "",
        "description": "",
        "named_senior": "",
        "backup_senior": "",
        "path_patterns": f"{folder}/*" if folder else row.path,
    }
    rows = [*capability_rows(active.rulebook.policy), new]
    return _content(settings, TAB_CAPABILITY, active, editable=True, draft={CATALOG_TABLE: rows})


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
    if button == REBUILD_STOP:
        job.request_stop()  # checked between pieces; the old index and tags stay
    elif button in (REBUILD_CONFIRM, REBUILD_FULL_CONFIRM):
        policy = get_active_version(settings.db_path).rulebook.policy
        started, message = start_rebuild(
            policy,
            settings.developer_id,
            provider=settings.llm_provider,
            settings=settings,
            mode="full" if button == REBUILD_FULL_CONFIRM else "delta",
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
        Output(REBUILD_FULL_MODAL, "opened"),
        Input(REBUILD_FULL_BTN, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_full_confirm(clicks):
        return bool(clicks)

    @app.callback(
        Output(REBUILD_MODAL, "opened", allow_duplicate=True),
        Output(REBUILD_FULL_MODAL, "opened", allow_duplicate=True),
        Output(REBUILD_STATUS, "children", allow_duplicate=True),
        Output(REBUILD_BTN, "disabled", allow_duplicate=True),
        Output(REBUILD_FULL_BTN, "disabled", allow_duplicate=True),
        Output(REBUILD_STOP, "disabled", allow_duplicate=True),
        Input(REBUILD_CONFIRM, "n_clicks"),
        Input(REBUILD_LATER, "n_clicks"),
        Input(REBUILD_FULL_CONFIRM, "n_clicks"),
        Input(REBUILD_FULL_LATER, "n_clicks"),
        Input(REBUILD_STOP, "n_clicks"),
        prevent_initial_call=True,
    )
    def answer_confirm(*_clicks):
        if not ctx.triggered[0]["value"]:
            raise PreventUpdate
        opened, status = rebuild_action(get_admin_settings(), ctx.triggered_id)
        running = running_since() is not None
        return opened, opened, status, running, running, not running

    @app.callback(
        Output(REBUILD_STATUS, "children"),
        Output(REBUILD_BTN, "disabled"),
        Output(REBUILD_FULL_BTN, "disabled"),
        Output(REBUILD_STOP, "disabled"),
        Output(REBUILD_PROGRESS, "children"),
        Input(REBUILD_POLL, "n_intervals"),
    )
    def poll(_ticks):
        started = running_since()
        running = started is not None
        panel = job_panel(job.read_status(), started)
        return current_rebuild_status(), running, running, not running, panel


def _save(settings, tab, form, note, base_version, active):
    base_number = base_version or active.version_number
    result = save_from_form(settings.db_path, tab, form, base_number, settings.developer_id, note)
    if result.kind == RESULT_SAVED:
        saved = get_active_version(settings.db_path)
        open_lines = open_request_lines(settings.db_path, saved.version_number)
        notice = saved_notice(saved.version_number, result.warnings, open_lines)
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


def history_content(settings: Settings, restore_target=None, notice=None, selected=None):
    rows = build_timeline(settings.db_path)
    if selected is None and rows:
        # Default: the newest older version (the one an Admin most likely wants to look at).
        selected = rows[1].version_number if len(rows) > 1 else rows[0].version_number
    changes = _selected_changes(settings, rows, selected)
    active = rows[0].version_number if rows else 0
    open_lines = open_request_lines(settings.db_path, active) if restore_target else None
    return history_view(rows, restore_target, notice, selected, changes, open_lines)


def _selected_changes(settings: Settings, rows, selected):
    """Plain-word lines for what version `selected` changed against the version before it."""
    numbers = [row.version_number for row in rows]
    if selected not in numbers or numbers.index(selected) + 1 >= len(numbers):
        return []  # nothing before the first version
    new = get_version(settings.db_path, selected)
    old = get_version(settings.db_path, numbers[numbers.index(selected) + 1])
    return plain_diff_lines(diff_rulebooks(old.rulebook, new.rulebook))


def run_history_action(settings: Settings, action: dict, note: str | None):
    """One click on the Version history tab. Writes only on a confirmed Restore."""
    name = action["action"]
    number = action.get("version") or 0
    if name == HIST_VIEW:
        return history_content(settings, selected=number)
    if name == HIST_RESTORE:
        return history_content(settings, restore_target=number, selected=number)
    if name == HIST_CONFIRM:
        return _restore(settings, number, note)
    return history_content(settings)  # Cancel, or anything else: back to the plain timeline


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
    _register_rule_pick(app)
    _register_golden(app)
    _register_rebuild(app)
    # late import: that file reads get_admin_settings from this one
    from callbacks.screen_callbacks.da_admin_builds_callbacks import register_builds_callbacks

    register_builds_callbacks(app)
    from callbacks.screen_callbacks.da_admin_tag_history_callbacks import (
        register_tag_history_callbacks,
    )

    register_tag_history_callbacks(app)

    @app.callback(
        Output(SONAR_STATUS, "children"),
        Output(SONAR_PILL, "children"),
        Output(SONAR_SAMPLE_ID, "children"),
        Input(SONAR_REFRESH_BTN, "n_clicks"),
        prevent_initial_call=True,
    )
    def refresh_sonar(clicks):
        settings = get_admin_settings()
        message = sonar_refresh_action(settings, clicks)
        chosen = get_active_version(settings.db_path).rulebook.policy.sonar_severity_map
        # pill, banner and table all show the new list at once
        return message, source_pill(load_snapshot()), sonar_sample_view(chosen)


def sonar_refresh_action(settings: Settings, clicks):
    """Admin only. The message says saved, or why not; the old list stays on any error."""
    if not clicks or not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    return refresh_snapshot(settings)


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


def catalog_search(settings: Settings, search: str | None, missing_backup: bool | None):
    """(table, results) for the one search box (fix 11-3, D-E). The table is the name search
    (capability, senior, module); the meaning matches come under it, labelled."""
    table = filtered_catalog(settings, search, missing_backup)
    if not (search and search.strip()):
        return table, None
    policy = get_active_version(settings.db_path).rulebook.policy
    hits, message = meaning_search(search, settings, policy.capabilities, read_tags())
    if not hits and not message:
        return table, no_hits_line()
    return table, meaning_results(hits, message)


def catalog_for_module(settings: Settings, path: str):
    """A clicked result: the table shows only the capability that holds this module."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    policy = get_active_version(settings.db_path).rulebook.policy
    paths = module_paths(policy.index_folder_scope)
    return catalog_list(policy.capabilities, paths, PurePosixPath(path).name, False)


def pick_rule(settings: Settings, rule_id: str):
    """The Coding standards rule list and card with `rule_id` selected (L3, read view only)."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    rules = get_active_version(settings.db_path).rulebook.rules
    cited = cited_counts(settings.db_path)
    mine = [
        {**r.model_dump(), "cited": cited.get(r.rule_id, 0)}
        for r in rules
        if r.kind == RULE_KIND_OF_TAB[TAB_CODING]
    ]
    return rule_panel(mine, fires_in(settings.db_path), rule_id)


def open_coding_edit(settings: Settings):
    """The golden card's Change button: the same as Edit on the Coding standards tab."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    action = {"type": "adm-act", "action": ACTION_EDIT}
    content, _editing = run_action(settings, TAB_CODING, action, {}, "", None)
    return content


def codes_for_modules(settings: Settings, modules: list, codes: list) -> list:
    """The code box of each golden row after a module pick: a blank box gets the module's first
    lines; a box with code in it is left alone (also when the form is just drawn)."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    scope = get_active_version(settings.db_path).rulebook.policy.index_folder_scope
    return [
        module_start(module, scope) if module and not (code or "").strip() else no_update
        for module, code in zip(modules, codes, strict=True)
    ]


def _register_golden(app) -> None:
    cell = {"type": "adm-cell", "tab": TAB_CODING, "table": "golden_examples", "row": ALL}

    @app.callback(
        Output(body_id(TAB_CODING), "children", allow_duplicate=True),
        *[Output(tab_button_id(n), "disabled", allow_duplicate=True) for n, _, _ in ADMIN_TABS],
        Input({"type": GOLDEN_CHANGE_TYPE, "n": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def on_golden_change(_clicks):
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return (open_coding_edit(get_admin_settings()), *tabs_disabled(TAB_CODING))

    @app.callback(
        Output({**cell, "col": "code"}, "value"),
        Input({**cell, "col": "module_path"}, "value"),
        State({**cell, "col": "code"}, "value"),
        prevent_initial_call=True,
    )
    def on_golden_module(modules, codes):
        return codes_for_modules(get_admin_settings(), modules, codes)


def _register_rule_pick(app) -> None:
    @app.callback(
        Output(RULE_PANEL_ID, "children"),
        Input({"type": RULE_PICK_TYPE, "rule": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def on_rule_pick(_clicks):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return pick_rule(get_admin_settings(), triggered["rule"])


def _register_catalog_filter(app) -> None:
    @app.callback(
        Output(CAP_LIST_ID, "children"),
        Output(CAP_MEANING_ID, "children"),
        Input(CAP_SEARCH_ID, "value"),
        Input(CAP_MISSING_ID, "checked"),
        prevent_initial_call=True,
    )
    def on_catalog_filter(search, missing_backup):
        return catalog_search(get_admin_settings(), search, missing_backup)

    @app.callback(
        Output(CAP_LIST_ID, "children", allow_duplicate=True),
        Input({"type": HIT_TYPE, "path": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def on_meaning_hit(_clicks):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return catalog_for_module(get_admin_settings(), triggered["path"])

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
    @app.callback(
        Output(HEADER_VERSION_ID, "children"),
        *[Input(body_id(name), "children") for name, _, _ in ADMIN_TABS],
        prevent_initial_call=True,
    )
    def refresh_header_version(*_bodies):
        # Any tab redraw may follow a save, a restore or an approval: show the active version.
        settings = get_admin_settings()
        active = get_active_version(settings.db_path)
        if active is None:
            raise PreventUpdate
        return header_version(active).children

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
        return run_history_action(settings, triggered, picks.get("note"))


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
        *[
            Output(tab_button_id(name), "disabled", allow_duplicate=True)
            for name, _, _ in ADMIN_TABS
        ],
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
        content = run_queue_action(settings, triggered, picks, notes, base_version)
        if triggered["action"] == Q_NEW:  # now editing: lock the other tabs (11-4)
            return (content, *tabs_disabled(TAB_CAPABILITY))
        return (content, *[no_update] * len(ADMIN_TABS))


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
