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
from agents.da_admin_diff import build_timeline, diff_rulebooks
from agents.da_admin_forms import (
    RESULT_PROBLEMS,
    RESULT_SAVED,
    RESULT_STALE,
    save_from_form,
)
from configs.da_config import Settings, load_settings
from db_table_functions.db_tbl_da_rulebook import (
    RulebookError,
    get_active_version,
    get_version,
    restore_version,
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
    EDITABLE_TABS,
    GLOSSARY_COLUMNS,
    HIST_COMPARE,
    HIST_CONFIRM,
    HIST_PICK_TYPE,
    HIST_RESTORE,
    HIST_TYPE,
    NOTE_ID_NAME,
    TAB_BUILD,
    TAB_CHARTER,
    TAB_HISTORY,
    TEXT_COLUMN,
    ZONE_COLUMNS,
    admin_page,
    body_id,
    history_view,
    message_notice,
    problem_notice,
    refusal_page,
    saved_notice,
    tab_button_id,
    tab_content,
)
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
}
TABLE_COLUMNS = {"glossary": GLOSSARY_COLUMNS, "zones": ZONE_COLUMNS}  # the rest hold one "text"


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
        return html.Div(
            dmc.Text(NO_RULEBOOK_MESSAGE, c=da_styles.MUTED), style=da_styles.PAGE
        )
    return admin_page(active, build_timeline(settings.db_path))


def developer_page_style(pathname: str | None) -> dict:
    """The developer page stays built but hidden on /admin, so its layout is not touched."""
    return {"display": "none"} if pathname == ADMIN_PATH else {}


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
            return tab_content(tab, active, editable=True), True
        if name in (ACTION_CANCEL, ACTION_RELOAD):
            return tab_content(tab, active), False
        if name == ACTION_SAVE:
            return _save(settings, tab, form, note, base_version, active)
    base = get_version(settings.db_path, base_version or active.version_number) or active
    if kind == "adm-add":
        form = _with_new_row(form, action["table"])
    elif kind == "adm-remove":
        form = _without_row(form, action["table"], action["index"])
    return tab_content(tab, base, editable=True, draft=form), True


def _save(settings, tab, form, note, base_version, active):
    base_number = base_version or active.version_number
    result = save_from_form(settings.db_path, tab, form, base_number, settings.developer_id, note)
    if result.kind == RESULT_SAVED:
        saved = get_active_version(settings.db_path)
        notice = saved_notice(saved.version_number, result.warnings)
        return tab_content(tab, saved, notice=[notice]), False
    base = get_version(settings.db_path, base_number) or active
    if result.kind == RESULT_PROBLEMS:
        notice = problem_notice(result.problems)
    elif result.kind == RESULT_STALE:
        notice = message_notice(result.message, reload_tab=tab, newest=result.newest_version)
    else:
        notice = message_notice(result.message)
    return tab_content(tab, base, editable=True, draft=form, notice=[notice]), True


# --- Version history ---


def history_content(settings: Settings, diff=None, restore_target=None, notice=None):
    return history_view(build_timeline(settings.db_path), diff, restore_target, notice)


def run_history_action(
    settings: Settings, action: dict, from_number, to_number, note: str | None
):
    """One click on the Version history tab. Writes only on a confirmed Restore."""
    name = action["action"]
    number = action.get("version") or 0
    if name == HIST_RESTORE:
        return history_content(settings, restore_target=number)
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
        State(pattern("adm-cell", "table", "row", "col"), "value"),
        State(pattern("adm-field", "name"), "value"),
        State(pattern("adm-switch", "name"), "checked"),
        State({"type": BASE_STORE_TYPE, "tab": tab}, "data"),
        prevent_initial_call=True,
    )
    def on_click(_acts, _adds, _removes, cells, fields, switches, base_version):
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
