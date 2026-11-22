"""Callbacks of the Admin console (Phase 11a).

Own file: it imports nothing from the developer page callbacks, so the two screens can be copied
and changed apart (spec 11-44). The logic is in plain functions (run_action, form_from_cells) that
tests call without Dash; the Dash wrappers at the bottom only read ids and values and pass them on.
"""

from contextvars import ContextVar
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
from agents.da_admin_modules import (
    add_modules_to_form,
    also_add_modules_to_form,
    count_matches,
    edit_patterns,
    module_paths,
    module_rows,
)
from agents.da_admin_overview import (
    MISSING_BACKUP_FILTER,
    REVIEW_QUEUE_FILTER,
    build_overview,
    server_settings_view,
)
from agents.da_admin_rebuild import running_since, start_rebuild
from agents.da_admin_recheck import retry_one, start_recheck
from agents.da_admin_review import (
    ReviewFilter,
    bulk_plan,
    count_line,
    filter_ai_cards,
    filter_from_values,
)
from agents.da_admin_sonar import load_snapshot, refresh_snapshot, source_pill
from agents.da_admin_starter import ACTION_ALL, ACTION_ONE, remove_starter
from agents.da_admin_suggestions import (
    assign_suggestion,
    create_and_assign,
    reject_suggestion,
    remove_from_suggestion,
    suggestions,
)
from agents.da_admin_tag_cards import (
    ai_cards,
    also_cards,
    approve_all_high,
    approve_also,
    approve_card,
    approve_pairs,
    high_confidence_counts,
    reject_also,
    reject_card,
    reject_cards,
)
from agents.da_admin_tag_store import read_tags
from agents.da_admin_watch import watch_step
from agents.da_capability_suggest_job import offer_for, start_suggest
from agents.da_group_cards import (
    assign_card,
    create_card,
    group_suggestions,
    remove_program,
)
from agents.da_group_cards import (
    reject_card as reject_group_card,
)
from agents.da_safety_release import ReleaseError, keep_stopped, release
from configs.da_config import Settings, load_settings
from db_table_functions.db_tbl_da_rulebook import (
    RulebookError,
    get_active_version,
    get_version,
    restore_version,
)
from layouts.da_admin_address import ADDRESS_TO_TABS_JS, TABS_TO_ADDRESS_JS, tab_and_view
from layouts.da_admin_builds_panel import BUILD_USE_BTN
from layouts.da_admin_catalog_meaning import (
    CAP_MEANING_ID,
    HIT_TYPE,
    meaning_results,
    no_hits_line,
)
from layouts.da_admin_catalog_panels import (
    HINT_ID,
    MOD_ALL_ID,
    MOD_CAP_ID,
    MOD_PICKED_ID,
    MOD_SEARCH_ID,
    MOD_SUMMARY_ID,
    MOD_TABLE_ID,
    MOD_TYPE,
    MOD_UNASSIGNED_ID,
    NEW_PATTERN_ID,
    add_label,
    hint_text,
    modules_table,
)
from layouts.da_admin_catalog_tab import (
    LINKS_KEY,
    Q_AI_ALL,
    Q_AI_ALL_DO,
    Q_AI_APPROVE,
    Q_AI_ASSIGN,
    Q_AI_REJECT,
    Q_AI_RETRY,
    Q_ALSO_ADD,
    Q_ALSO_REJECT,
    Q_RECHECK,
    Q_SG_ASSIGN,
    Q_SG_OPEN,
    Q_SG_REJECT,
    Q_SG_REMOVE,
    Q_SG_SAVE,
    Q_SUGGEST,
    review_items,
    view_options,
)
from layouts.da_admin_coding_tab import (
    GOLDEN_CHANGE_TYPE,
    RULE_PANEL_ID,
    RULE_PICK_TYPE,
    module_start,
    rule_panel,
)
from layouts.da_admin_common import PAT_TYPE, pat_id
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
from layouts.da_admin_job_bar import (
    BAR_CATALOG,
    BAR_QUEUE,
    JOB_STOP_TYPE,
    LOCK_NAMES,
    job_bar,
    lock_id,
    lock_state,
)
from layouts.da_admin_overview_tab import (
    ATTENTION_SCROLL_ID,
    STOP_ACT_TYPE,
    STOP_NOTE_TYPE,
    _attention_list,
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
    DATA_VERSION_ID,
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
    WATCH_ID,
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
from layouts.da_admin_queue_ids import (
    BULK_APPROVE,
    BULK_ASSIGN,
    BULK_PICK_UID,
    BULK_REJECT,
    CAT_PANE_CAPS,
    CAT_PANE_QUEUE,
    CAT_VIEW_ID,
    Q_BULK_ASK,
    Q_BULK_DO,
    Q_CLEAR_FILTERS,
    Q_SELECT_ALL,
    RQ_BAR_ID,
    RQ_CONF_ID,
    RQ_COUNT_ID,
    RQ_FOLDER_ID,
    RQ_LIST_ID,
    RQ_PROPOSAL_ID,
    RQ_SEARCH_ID,
    RQ_SEL_TYPE,
    RQ_SORT_ID,
    RQ_SOURCE_ID,
    VIEW_CAPS,
    VIEW_QUEUE,
    queue_button_id,
)
from layouts.da_admin_review_view import bulk_bar, empty_list
from layouts.da_capability_map_view import MAP_PATH
from layouts.da_inbox_page import INBOX_PATH
from layouts.da_tagger_try_panel import TRY_BTN
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


def admin_content(settings: Settings, pathname: str | None, search: str | None = None):
    """What the admin area holds for this path: nothing, the refusal, or the console.
    `search` is the address text; it names the tab and view to open (Fix G5 N5)."""
    if pathname != ADMIN_PATH:
        return None
    if not is_admin(settings, settings.developer_id):
        return refusal_page()
    active = get_active_version(settings.db_path)
    if active is None:
        return html.Div(dmc.Text(NO_RULEBOOK_MESSAGE, c=da_styles.MUTED), style=da_styles.PAGE)
    tab, view = tab_and_view(search)
    queue = queue_data(settings)
    if view:
        queue["review"] = {**(queue.get("review") or {}), "view": view}
    return admin_page(
        active,
        build_timeline(settings.db_path),
        cited_counts(settings.db_path),
        queue,
        build_overview(settings),
        health_report(settings.db_path, WINDOW_ALL),
        server_settings_view(settings),
        fires_in(settings.db_path),
        tab=tab,
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
    hidden = pathname in (ADMIN_PATH, INBOX_PATH, MAP_PATH)
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
    inputs: dict | None = None,
):
    """Returns (new tab content, True while the tab is being edited). Writes only on Save.
    `inputs` holds the side panel and pop-up values by name (newpat, cap, picked)."""
    active = get_active_version(settings.db_path)
    kind = action["type"]
    if kind == PAT_TYPE:
        inputs = inputs or {}
        return _pattern_action(settings, tab, action, form, note, base_version, active, inputs)
    if kind == "adm-act":
        name = action["action"]
        if name == ACTION_EDIT:
            return _content(settings, tab, active, editable=True), True
        if name in (ACTION_CANCEL, ACTION_RELOAD):
            return _content(settings, tab, active), False
        if name == ACTION_SAVE:
            return _save(settings, tab, form, note, base_version, active)
        if name == ACTION_ALL or name.startswith(ACTION_ONE):
            text = remove_starter(settings, settings.developer_id, name)
            saved = get_active_version(settings.db_path)
            notice = [message_notice(text, color="green")]
            return _content(settings, tab, saved, notice=notice), False
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


def _pattern_action(settings, tab, action, form, note, base_version, active, inputs):
    """Fix G4 L2, L3: the patterns side panel and the Add modules pop-up. Nothing is written until
    Save (one version); Add modules only changes the draft, so the page's Save writes it."""
    name, index = action["action"], action["index"]
    base = get_version(settings.db_path, base_version or active.version_number) or active
    typed = (inputs.get("newpat") or "").strip()
    panel = None
    if name == "open":
        panel = {"kind": "patterns", "index": index}
    elif name == "openmods":
        panel = {"kind": "modules"}
    elif name == "remove":
        form = edit_patterns(form, index, remove=action["pat"])
        panel = {"kind": "patterns", "index": index}
    elif name in ("add", "save", "force"):
        # A pattern that matches nothing is kept only through Save anyway (Fix G5 L3).
        paths = module_paths(base.rulebook.policy.index_folder_scope)
        if typed and name != "force" and count_matches(typed, paths) == 0:
            return _content(
                settings, tab, base, editable=True, draft=form,
                panel={"kind": "patterns", "index": index},
            ), True
        form = edit_patterns(form, index, add=typed)  # text typed but not yet added counts too
        if name != "add":
            return _save(settings, tab, form, note, base_version, active)
        panel = {"kind": "patterns", "index": index}
    elif name in ("addmods", "alsomods"):
        target, picked = inputs.get("cap") or "", inputs.get("picked") or []
        if target and picked:
            add = add_modules_to_form if name == "addmods" else also_add_modules_to_form
            form = add(form, target, picked)
        else:
            panel = {"kind": "modules"}  # nothing to add yet: keep the pop-up open
    return _content(settings, tab, base, editable=True, draft=form, panel=panel), True


def _content(settings: Settings, tab: str, version, **kwargs):
    """tab_content, plus the Cited counts on the Coding tab (read from the Tester's findings)."""
    cited = cited_counts(settings.db_path) if tab == TAB_CODING else None
    queue = queue_data(settings) if tab == TAB_CAPABILITY else None
    server = server_settings_view(settings) if tab in (TAB_REPO, TAB_BUILD) else None
    fires = fires_in(settings.db_path) if tab == TAB_CODING else None
    return tab_content(tab, version, cited=cited, queue=queue, server=server, fires=fires, **kwargs)


# --- Unassigned queue ---


def queue_data(
    settings: Settings, show_resolved: bool = False, dialog=None, notice=None, ai_confirm=False,
    suggest_dialog: str | None = None, review: dict | None = None,
) -> dict:
    """What the layout needs to draw the queue block. `review` is the search, filters, sort and
    selection of the Review queue view (Fix G4 L9, L10)."""
    waiting = [*group_suggestions(), *suggestions()]
    confirm = {"counts": high_confidence_counts(), "suggestions": len(waiting)}
    policy = get_active_version(settings.db_path).rulebook.policy
    cards = ai_cards()
    review = dict(review or {})
    open_paths = {c.path for c in cards}
    review["selected"] = [p for p in review.get("selected", []) if p in open_paths]
    return {
        "rows": queue_rows(settings),
        "resolved": resolved_rows(settings) if show_resolved else None,
        "dialog": dialog,
        "notice": notice or [],
        "review": review,
        "ai_cards": cards,
        "also_cards": also_cards(),
        "ai_confirm": confirm if ai_confirm else None,
        "suggestions": waiting,
        "suggest_dialog": suggest_dialog,
        "offer_suggest": offer_for(policy),
    }


def _suggest_action(
    settings: Settings, name: str, key: str, picks: dict, notes: dict, base_version: int | None,
    state: str = "",
):
    """Create and assign, Assign to, Reject and Remove on a new-capability suggestion card (S4)."""
    admin = settings.developer_id
    links = {s.name: s for s in group_suggestions()}  # Fix G6: "Suggested from code links" cards
    if name == Q_SG_REMOVE:  # `key` is the program's path; state says which kind of card
        owner = next((n for n, s in links.items() if key in s.modules), None)
        if state == LINKS_KEY and owner:
            remove_program(owner, key)
        else:
            remove_from_suggestion(key)
        done = message_notice("Removed from the suggestion.", color="green")
        return _queue_tab(settings, notice=[done])
    # a "links:" key is a code-links card; any other key is a tagger card (same names can occur)
    if key.startswith(LINKS_KEY):
        current = links.get(key.removeprefix(LINKS_KEY))
    else:
        current = next((s for s in suggestions() if s.name == key), None)
    if current is None:
        gone = message_notice("That suggestion is not open any more.")
        return _queue_tab(settings, notice=[gone])
    paths = list(current.modules)
    if name == Q_SG_OPEN:
        return _queue_tab(settings, suggest_dialog=key)
    if name == Q_SG_REJECT:
        if current.from_links:
            reject_group_card(current.name)
        else:
            reject_suggestion(paths, admin)
        return _queue_tab(settings, notice=[message_notice("Rejected.", color="green")])
    if name == Q_SG_ASSIGN:
        target = picks.get(key) or ""
        if not target:
            return _queue_tab(settings, notice=[message_notice("Choose a capability first.")])
        if current.from_links:
            result = assign_card(settings, current.name, target, admin, base_version)
        else:
            result = assign_suggestion(settings, target, paths, admin, base_version)
    else:  # Q_SG_SAVE
        text = {f: notes.get(f"{key}|{f}", "") for f in ("name", "desc", "named", "backup")}
        if current.from_links:
            result = create_card(
                settings, text["name"], text["desc"], text["named"], text["backup"], admin,
                current.name, base_version,
            )
        else:
            result = create_and_assign(
                settings, text["name"], text["desc"], text["named"], text["backup"], paths, admin,
                base_version,
            )
    if result.kind == "resolved":
        version = f" The catalog is now v{result.new_version}." if result.new_version else ""
        again = " Use Re-check to place the other programs." if current.from_links else ""
        done = message_notice(f"Done.{version}{again}", color="green")
        return _queue_tab(settings, notice=[done])
    if result.stale:
        newest = get_active_version(settings.db_path).version_number
        notice = message_notice(result.message, reload_tab=TAB_CAPABILITY, newest=newest)
        return _queue_tab(settings, notice=[notice])
    return _queue_tab(settings, notice=[problem_notice(result.problems or [result.message])])


def _ai_action(
    settings: Settings, name: str, path: str, picks: dict, base_version: int | None, cap: str
):
    """Approve, Assign to, Reject and Approve all on the AI scan cards."""
    if name == Q_AI_ALL:
        return _queue_tab(settings, ai_confirm=True)
    if name == Q_AI_REJECT:
        reject_card(path, who=settings.developer_id)
        return _queue_tab(settings, notice=[message_notice("Rejected.", color="green")])
    if name == Q_AI_RETRY:
        policy = get_active_version(settings.db_path).rulebook.policy
        done, text = retry_one(policy, settings, path, settings.developer_id)
        notice = message_notice(text, color="green") if done else message_notice(text)
        return _queue_tab(settings, notice=[notice])
    if name == Q_AI_ALL_DO:
        result = approve_all_high(settings, settings.developer_id, base_version)
    else:
        target = cap if name == Q_AI_APPROVE else (picks.get(path) or "")
        if not target:
            return _queue_tab(settings, notice=[message_notice("Choose a capability first.")])
        result = approve_card(settings, path, target, settings.developer_id, base_version)
    return _ai_result(settings, result)


def _ai_result(settings: Settings, result, **kwargs):
    """The notice for an approval result: done, stale (catalog moved on) or refused."""
    if result.kind == "resolved":
        text = "Card closed."
        if result.new_version:
            text = f"Approved. The catalog is now v{result.new_version}."
        if result.message:  # some paths were already matched: say by which capability
            text += f" {result.message}"
        return _queue_tab(settings, notice=[message_notice(text, color="green")], **kwargs)
    if result.stale:
        newest = get_active_version(settings.db_path).version_number
        notice = message_notice(result.message, reload_tab=TAB_CAPABILITY, newest=newest)
        return _queue_tab(settings, notice=[notice], **kwargs)
    return _queue_tab(
        settings, notice=[problem_notice(result.problems or [result.message])], **kwargs
    )


# The Review queue's filter, sort and selection for the click being handled, so every redraw keeps
# them (L9). Set by run_queue_action; read by _queue_tab.
_review_state: ContextVar[dict | None] = ContextVar("review_state", default=None)


def _queue_tab(settings: Settings, **kwargs):
    active = get_active_version(settings.db_path)
    kwargs.setdefault("review", _review_state.get() or {})
    return tab_content(TAB_CAPABILITY, active, queue=queue_data(settings, **kwargs))


def _bulk_action(settings: Settings, name: str, action: dict, picks: dict, base_version, review):
    """Select all shown, Clear filters, and the bulk bar's ask and do steps (L10)."""
    rf = review.get("filter") or ReviewFilter()
    cards = ai_cards()
    selected = review.get("selected", [])
    if name == Q_CLEAR_FILTERS:
        return _queue_tab(settings, review={**review, "filter": ReviewFilter()})
    if name == Q_SELECT_ALL:
        every = [c.path for c in filter_ai_cards(cards, rf)]
        return _queue_tab(settings, review={**review, "selected": every})
    kind = action["state"]
    plan = bulk_plan(selected, cards)
    open_selected = [p for p in selected if p in {c.path for c in cards}]
    target = picks.get(BULK_PICK_UID) or action["cap"] if kind == BULK_ASSIGN else ""
    if not open_selected or (kind == BULK_ASSIGN and not target) or (
        kind == BULK_APPROVE and not plan.pairs
    ):
        text = "Choose a capability first." if kind == BULK_ASSIGN and open_selected else (
            "Nothing to do: select programs that have a proposal."
        )
        return _queue_tab(settings, notice=[message_notice(text)])
    if name == Q_BULK_ASK:
        return _queue_tab(settings, review={**review, "bulk": {"kind": kind, "target": target}})
    admin = settings.developer_id  # Q_BULK_DO
    cleared = {**review, "selected": [], "bulk": None}
    if kind == BULK_REJECT:
        reject_cards(open_selected, who=admin)
        done = message_notice(f"Rejected {len(open_selected)} programs.", color="green")
        return _queue_tab(settings, notice=[done], review=cleared)
    if kind == BULK_APPROVE:
        pairs, note = plan.pairs, f"AI scan: {len(plan.pairs)} programs approved"
    else:
        pairs = [(p, target) for p in open_selected]
        note = f"AI scan: {len(pairs)} programs assigned to {target}"
    result = approve_pairs(settings, pairs, admin, note, base_version)
    return _ai_result(settings, result, review=cleared)


def run_queue_action(
    settings: Settings,
    action: dict,
    picks: dict,
    notes: dict,
    base_version: int | None,
    review: dict | None = None,
):
    """One click in the Review queue. Returns the whole Capability catalog tab, redrawn.

    `picks` is {unassigned_id: chosen capability}, `notes` {unassigned_id: change note}. `review`
    is the view, filter and selection to keep. Writes only on Resolve (and, with the pattern, one
    new catalog version)."""
    review = review or {}
    token = _review_state.set(review)
    try:
        return _run_queue_action(settings, action, picks, notes, base_version, review)
    finally:
        _review_state.reset(token)


def _run_queue_action(settings, action, picks, notes, base_version, review):
    name, uid = action["action"], action["uid"]
    if name in (Q_SELECT_ALL, Q_CLEAR_FILTERS, Q_BULK_ASK, Q_BULK_DO):
        return _bulk_action(settings, name, action, picks, base_version, review)
    if name in (Q_AI_APPROVE, Q_AI_ASSIGN, Q_AI_REJECT, Q_AI_RETRY, Q_AI_ALL, Q_AI_ALL_DO):
        return _ai_action(settings, name, uid, picks, base_version, action["cap"])
    if name == Q_ALSO_REJECT:
        reject_also(uid)
        return _queue_tab(settings, notice=[message_notice("Rejected.", color="green")])
    if name == Q_ALSO_ADD:
        result = approve_also(settings, uid, action["cap"], settings.developer_id, base_version)
        return _ai_result(settings, result)
    if name in (Q_SG_OPEN, Q_SG_SAVE, Q_SG_ASSIGN, Q_SG_REJECT, Q_SG_REMOVE):
        return _suggest_action(settings, name, uid, picks, notes, base_version, action["state"])
    if name == Q_SUGGEST:
        policy = get_active_version(settings.db_path).rulebook.policy
        started, text = start_suggest(policy, settings, settings.developer_id)
        notice = message_notice(text, color="green") if started else message_notice(text)
        return _queue_tab(settings, notice=[notice])
    if name == Q_RECHECK:
        policy = get_active_version(settings.db_path).rulebook.policy
        started, text = start_recheck(policy, settings, settings.developer_id)
        notice = message_notice(text, color="green") if started else message_notice(text)
        return _queue_tab(settings, notice=[notice])
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
        "kind": "Business",
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
        State(LOCATION_ID, "search"),
    )
    def show_page(pathname, search):
        return admin_content(get_admin_settings(), pathname, search), developer_page_style(pathname)

    # Fix G5 N5: the address and the tabs follow each other in the browser (no reload).
    app.clientside_callback(
        ADDRESS_TO_TABS_JS,
        Output(ADMIN_TABS_ID, "value", allow_duplicate=True),
        Output(CAT_VIEW_ID, "value", allow_duplicate=True),
        Input(LOCATION_ID, "search"),
        State(ADMIN_TABS_ID, "value"),
        State(CAT_VIEW_ID, "value"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        TABS_TO_ADDRESS_JS,
        Output(LOCATION_ID, "search", allow_duplicate=True),
        Input(ADMIN_TABS_ID, "value"),
        Input(CAT_VIEW_ID, "value"),
        State(LOCATION_ID, "search"),
        prevent_initial_call=True,
    )

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


def stopped_action(settings: Settings, triggered: dict, notes: dict[str, str]):
    """Fix G5: Release or Keep stopped, then the Needs attention list again (with the reason if
    the release was refused). Admin only."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    rid, message = triggered["rid"], ""
    try:
        if triggered["action"] == "release":
            release(settings, rid, settings.developer_id, notes.get(rid, ""))
        else:
            keep_stopped(settings, rid, settings.developer_id, notes.get(rid, ""))
    except ReleaseError as error:
        message = str(error)
    return _attention_list(build_overview(settings).attention, message)


def _register_overview(app) -> None:
    @app.callback(
        Output(ATTENTION_SCROLL_ID, "children", allow_duplicate=True),
        Input({"type": STOP_ACT_TYPE, "action": ALL, "rid": ALL}, "n_clicks"),
        State({"type": STOP_NOTE_TYPE, "rid": ALL}, "value"),
        prevent_initial_call=True,
    )
    def on_stopped_click(_clicks, _notes):
        if not isinstance(ctx.triggered_id, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        notes = {s["id"]["rid"]: s.get("value") or "" for s in ctx.states_list[0]}
        return stopped_action(get_admin_settings(), ctx.triggered_id, notes)

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


def modules_table_for(
    settings: Settings, target, search, unassigned, show_summary, picked, select_all=False
):
    """The Add modules table for the pop-up's filters (Fix G4 L3)."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    policy = get_active_version(settings.db_path).rulebook.policy
    paths = module_paths(policy.index_folder_scope)
    summaries = {p: str(e.get("summary", "")) for p, e in read_tags().items()}
    caps, target, search = list(policy.capabilities), target or "", search or ""
    if select_all:  # tick every row now shown
        rows = module_rows(caps, paths, summaries, target, search, unassigned)
        picked = [r["path"] for r in rows]
    return modules_table(
        caps, paths, summaries, target, search, bool(unassigned), bool(show_summary), picked
    )


def pattern_hint(settings: Settings, text) -> str:
    """The live "matches N modules" hint for the Add pattern field (Fix G4 L2)."""
    policy = get_active_version(settings.db_path).rulebook.policy
    return hint_text(text or "", module_paths(policy.index_folder_scope))


def _register_catalog_filter(app) -> None:
    @app.callback(
        Output(HINT_ID, "children"),
        Input(NEW_PATTERN_ID, "value"),
        prevent_initial_call=True,
    )
    def on_pattern_typed(text):
        return pattern_hint(get_admin_settings(), text)

    @app.callback(
        Output(MOD_TABLE_ID, "children"),
        Input(MOD_SEARCH_ID, "value"),
        Input(MOD_UNASSIGNED_ID, "checked"),
        Input(MOD_SUMMARY_ID, "checked"),
        Input(MOD_ALL_ID, "n_clicks"),
        Input(MOD_CAP_ID, "value"),
        State(MOD_PICKED_ID, "value"),
        prevent_initial_call=True,
    )
    def on_modules_filter(search, unassigned, summary, _all, target, picked):
        everything = ctx.triggered_id == MOD_ALL_ID
        return modules_table_for(
            get_admin_settings(), target, search, unassigned, summary, picked, everything
        )

    @app.callback(
        Output(pat_id(TAB_CAPABILITY, "addmods"), "children"),
        Input(MOD_PICKED_ID, "value"),
        Input(MOD_CAP_ID, "value"),
        prevent_initial_call=True,
    )
    def on_modules_ticked(picked, target):
        return add_label(len(picked or []), target or "")

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
    pick_states, note_states, *_rest = states_list
    picks = {item["id"]["uid"]: item.get("value") for item in pick_states}
    notes = {item["id"]["uid"]: item.get("value") or "" for item in note_states}
    return picks, notes


def review_from_states(states_list: list) -> dict:
    """The Review queue's view, filter and ticked cards from the callback's States (after the
    picks, notes and base store): search, source, proposal, confidence, folder, sort, view, ticks.
    """
    if len(states_list) < 11:
        return {}
    search, source, proposal, confidence, folder, sort, view = (
        item.get("value") for item in states_list[3:10]
    )
    ticked = [t["id"]["path"] for t in states_list[10] if t.get("value")]
    return {
        "view": view or VIEW_CAPS,
        "filter": filter_from_values(search, source, proposal, confidence, folder, sort),
        "selected": ticked,
    }


def _review_view_controls() -> list:
    return [
        State(RQ_SEARCH_ID, "value"),
        State(RQ_SOURCE_ID, "value"),
        State(RQ_PROPOSAL_ID, "value"),
        State(RQ_CONF_ID, "value"),
        State(RQ_FOLDER_ID, "value"),
        State(RQ_SORT_ID, "value"),
        State(CAT_VIEW_ID, "value"),
        State({"type": RQ_SEL_TYPE, "path": ALL}, "checked"),
    ]


def _register_review(app) -> None:
    """Live parts of the Review queue: the filter, the bulk bar, the view switch."""

    @app.callback(
        Output(RQ_LIST_ID, "children"),
        Output(RQ_COUNT_ID, "children"),
        Output(RQ_BAR_ID, "children", allow_duplicate=True),
        Input(RQ_SEARCH_ID, "value"),
        Input(RQ_SOURCE_ID, "value"),
        Input(RQ_PROPOSAL_ID, "value"),
        Input(RQ_CONF_ID, "value"),
        Input(RQ_FOLDER_ID, "value"),
        Input(RQ_SORT_ID, "value"),
        prevent_initial_call=True,
    )
    def on_review_filter(search, source, proposal, confidence, folder, sort):
        settings = get_admin_settings()
        rf = filter_from_values(search, source, proposal, confidence, folder, sort)
        queue = queue_data(settings)
        names = _capability_names(settings)
        items, shown, total = review_items(queue, names, False, rf, [])
        return items or empty_list(), count_line(shown, total), []

    @app.callback(
        Output(RQ_BAR_ID, "children"),
        Input({"type": RQ_SEL_TYPE, "path": ALL}, "checked"),
        prevent_initial_call=True,
    )
    def on_review_ticks(_checked):
        settings = get_admin_settings()
        ticked = [t["id"]["path"] for t in ctx.inputs_list[0] if t.get("value")]
        return bulk_bar(ticked, ai_cards(), _capability_names(settings))

    @app.callback(
        Output(CAT_PANE_CAPS, "style"),
        Output(CAT_PANE_QUEUE, "style"),
        Input(CAT_VIEW_ID, "value"),
        prevent_initial_call=True,
    )
    def on_view_switch(view):
        hidden = {"display": "none"}
        return ({}, hidden) if view == VIEW_CAPS else (hidden, {})

    @app.callback(
        Output(CAT_VIEW_ID, "value"),
        Input({"type": GOTO_TYPE, "tab": ALL, "n": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_review_queue(_clicks):
        # The Overview's "AI proposals" line carries REVIEW_QUEUE_FILTER in its "n".
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if REVIEW_QUEUE_FILTER not in str(triggered["n"]):
            raise PreventUpdate
        return VIEW_QUEUE

    # Keep the list's scroll position across a redraw (L9): remember it while scrolling and put
    # it back when the tab body is drawn again.
    app.clientside_callback(
        """function(children) {
            const box = document.getElementById('LIST_ID');
            if (!box) { return window.dash_clientside.no_update; }
            if (!box.dataset.watching) {
                box.dataset.watching = '1';
                box.addEventListener('scroll', () => { window.__rqScroll = box.scrollTop; });
            }
            if (window.__rqScroll) { box.scrollTop = window.__rqScroll; }
            return window.dash_clientside.no_update;
        }""".replace("LIST_ID", RQ_LIST_ID),
        Output(CAT_PANE_QUEUE, "data-scroll"),
        Input(body_id(TAB_CAPABILITY), "children"),
        prevent_initial_call=True,
    )


def _capability_names(settings: Settings) -> list[str]:
    return [c.name for c in get_active_version(settings.db_path).rulebook.policy.capabilities]


def watch_job(previous: dict | None):
    """Fix G5 N1: (new version store value, poll interval). The store is left alone when it did
    not change, so the redraw below fires only when a job starts or ends."""
    data, interval = watch_step(previous, running_since() is not None)
    return (no_update if data == previous else data), interval


def bars_now() -> tuple[list, list]:
    """Fix G5 N2: the same bar for the catalog header and the Review queue view."""
    status, started = job.read_status(), running_since()
    return job_bar(status, started, "catalog"), job_bar(status, started, "queue")


LOCKED_BUTTONS = (
    REBUILD_BTN, REBUILD_FULL_BTN, queue_button_id(Q_RECHECK), TRY_BTN, BUILD_USE_BTN,
    queue_button_id(Q_SUGGEST),
)  # same order as LOCK_NAMES


def locks_now(own: tuple) -> list:
    """Fix G5 N3: the job-starting buttons greyed with the job's short status as tooltip while
    a job runs. `own` is each button's own reason to be disabled (kept when the job ends)."""
    status, started = job.read_status(), running_since()
    states = [lock_state(status, started, o) for o in own]
    return [disabled for disabled, _ in states] + [title for _, title in states]


def stop_from_bar(settings: Settings):
    """Stop on the bar asks the job to end (checked between items); admin only."""
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    job.request_stop()
    return bars_now()[0]


def redraw_after_job(settings: Settings, data: dict | None, search, missing_backup, rq_values):
    """Fix G5 N1: after a job ended, redraw the lists its result changes: Overview, Capabilities,
    the Review queue and its count. The search text and filters are read back, never reset, and
    only list contents are replaced, so the scroll box stays where it is."""
    if not data or data.get("running") or not data.get("n"):
        raise PreventUpdate
    if not is_admin(settings, settings.developer_id):
        raise PreventUpdate
    overview = refresh_overview(settings, TAB_OVERVIEW)
    caps = filtered_catalog(settings, search, missing_backup)
    queue = queue_data(settings)
    items, shown, total = review_items(
        queue, _capability_names(settings), False, filter_from_values(*rq_values), []
    )
    return overview, caps, items or empty_list(), count_line(shown, total), view_options(queue)


def _register_watcher(app) -> None:
    @app.callback(
        Output(DATA_VERSION_ID, "data"),
        Output(WATCH_ID, "interval"),
        Input(WATCH_ID, "n_intervals"),
        State(DATA_VERSION_ID, "data"),
    )
    def on_watch(_ticks, previous):
        return watch_job(previous)

    @app.callback(
        Output(BAR_CATALOG, "children"),
        Output(BAR_QUEUE, "children"),
        Input(WATCH_ID, "n_intervals"),
        Input(DATA_VERSION_ID, "data"),
    )
    def on_bars(_ticks, _data):
        return bars_now()

    @app.callback(
        *[Output(button, "disabled", allow_duplicate=True) for button in LOCKED_BUTTONS],
        *[Output(lock_id(name), "title") for name in LOCK_NAMES],
        Input(WATCH_ID, "n_intervals"),
        Input(DATA_VERSION_ID, "data"),
        *[State(lock_id(name), "data-own") for name in LOCK_NAMES],
        prevent_initial_call=True,
    )
    def on_lock(_ticks, _data, *own):
        return locks_now(own)

    @app.callback(
        Output(BAR_CATALOG, "children", allow_duplicate=True),
        Input({"type": JOB_STOP_TYPE, "where": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def on_bar_stop(_clicks):
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return stop_from_bar(get_admin_settings())

    @app.callback(
        Output(body_id(TAB_OVERVIEW), "children", allow_duplicate=True),
        Output(CAP_LIST_ID, "children", allow_duplicate=True),
        Output(RQ_LIST_ID, "children", allow_duplicate=True),
        Output(RQ_COUNT_ID, "children", allow_duplicate=True),
        Output(CAT_VIEW_ID, "data"),
        Input(DATA_VERSION_ID, "data"),
        State(CAP_SEARCH_ID, "value"),
        State(CAP_MISSING_ID, "checked"),
        State(RQ_SEARCH_ID, "value"),
        State(RQ_SOURCE_ID, "value"),
        State(RQ_PROPOSAL_ID, "value"),
        State(RQ_CONF_ID, "value"),
        State(RQ_FOLDER_ID, "value"),
        State(RQ_SORT_ID, "value"),
        prevent_initial_call=True,
    )
    def on_job_ended(data, search, missing, *rq_values):
        return redraw_after_job(get_admin_settings(), data, search, missing, rq_values)


def _register_queue(app) -> None:
    _register_review(app)
    _register_watcher(app)
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
        *_review_view_controls(),
        prevent_initial_call=True,
    )
    def on_queue_click(_clicks, _picks, _notes, base_version, *_controls):
        settings = get_admin_settings()
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if not is_admin(settings, settings.developer_id):
            raise PreventUpdate
        picks, notes = queue_inputs_from_states(ctx.states_list)
        review = review_from_states(ctx.states_list)
        content = run_queue_action(settings, triggered, picks, notes, base_version, review)
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
        Input(pattern(PAT_TYPE, "action", "index", "pat"), "n_clicks"),
        State(pattern("adm-cell", "table", "row", "col"), "value"),
        State(pattern("adm-field", "name"), "value"),
        State(pattern("adm-switch", "name"), "checked"),
        State({"type": BASE_STORE_TYPE, "tab": tab}, "data"),
        State({"type": MOD_TYPE, "name": ALL}, "value"),
        prevent_initial_call=True,
    )
    def on_click(_acts, _adds, _removes, _moves, _pats, cells, fields, switches, base_version, _m):
        settings = get_admin_settings()
        triggered = ctx.triggered_id
        # Buttons that were just drawn also "trigger"; a real click has a click count.
        if not isinstance(triggered, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        if not is_admin(settings, settings.developer_id):
            raise PreventUpdate
        # ctx.states_list holds, per State, a list of {"id", "property", "value"} entries.
        cell_states, field_states, switch_states, _base, mod_states = ctx.states_list
        form, note = form_from_cells(tab, cell_states, field_states, switch_states)
        inputs = {item["id"]["name"]: item.get("value") for item in mod_states}
        content, editing = run_action(settings, tab, triggered, form, note, base_version, inputs)
        return (content, *tabs_disabled(tab if editing else None))
