"""What is on the Admin console screen (Phase 11a): the 8 tabs, the read views and the edit forms.

Presentation only (rule R12), like a display file (DDS) in RPG: it says where each field goes, not
what it means. Rules about what is allowed live in the Phase 1 models and in
agents/da_admin_forms.py.

Ids the callbacks read back (all dictionaries, CodeVision's habit for repeated components):
  adm-field  one value per plain input   {"type","tab","name"}
  adm-switch one per trigger switch      {"type","tab","name"}
  adm-cell   one per table cell          {"type","tab","table","row","col"}
  adm-add / adm-remove  table buttons    {"type","tab","table","index"}
  adm-act    Edit, Save, Cancel, Reload  {"type","tab","action"}
"""

from datetime import datetime

import dash_mantine_components as dmc
from dash import dcc, html

from agents.da_admin_access import NOT_ADMIN_MESSAGE
from agents.da_admin_forms import (
    ADVANCED_LIMIT_FIELDS,
    CORE_BUILD_FIELDS,
    LOCK_CHAT_SWITCH,
    capability_rows,
    field_bounds,
    rule_counter_text,
)
from agents.da_admin_index import read_health, recent_runs
from agents.da_admin_labels import label as field_label
from agents.da_admin_modules import (
    matches_search,
    module_chips,
    module_paths,
    modules_by_capability,
    share_counts,
)
from agents.da_admin_rebuild import running_since
from agents.da_admin_sonar import SAMPLE_BANNER, sample_with_mapping
from layouts.da_admin_coding_tab import golden_cards, library_chips, rule_panel_div
from layouts.da_admin_common import (
    ADMIN_TABS,
    GOTO_TYPE,  # noqa: F401 (re-exported: the callbacks import it from here)
    TAB_BUILD,
    TAB_CAPABILITY,
    TAB_CHARTER,
    TAB_CODING,
    TAB_HISTORY,
    TAB_OVERVIEW,
    TAB_REPO,
    TAB_UI,
    act_id,
    body_id,
    two_columns,
    version_pill,
    word_chips,
)
from layouts.da_admin_common import section as _section
from layouts.da_admin_history_tab import (  # noqa: F401 (callbacks import these)
    HIST_CANCEL,
    HIST_CONFIRM,
    HIST_PICK_TYPE,
    HIST_RESTORE,
    HIST_TYPE,
    HIST_VIEW,
    hist_id,
    history_view,
    pick_id,
)
from layouts.da_admin_index_panels import (
    REFRESH_MODES,
    fixed_skip_rows,
    health_tiles,
    index_pill,
    rebuild_controls,
    recent_refreshes,
    refresh_tiles,
)
from layouts.da_admin_overview_tab import (  # noqa: F401 (callbacks import these)
    HEALTH_ID,
    WINDOW_ID,
    _attention_list,  # noqa: F401 (a test imports it)
    health_numbers,
    overview_view,
)
from layouts.da_admin_ui_standards import brand_panel, convention_rows
from pydantic_classes.da_rulebook_models import (
    PROGRAM_TYPES,
    SONAR_SEVERITY_KEYS,
    Charter,
    Policy,
    RulebookVersion,
    check_charter_size,
)
from styles import da_admin_styles as admin_styles
from styles import da_styles

ADMIN_PATH = "/admin"
ADMIN_CONTENT_ID = "da-admin-content"
ADMIN_TABS_ID = "da-admin-tabs"

EDITABLE_TABS = (TAB_CHARTER, TAB_REPO, TAB_CAPABILITY, TAB_UI, TAB_CODING, TAB_BUILD)

CHARTER_LISTS: tuple[tuple[str, str], ...] = (
    ("in_scope", "In scope"),
    ("out_of_scope", "Out of scope"),
    ("architecture_principles", "Architecture principles"),
    ("constraints", "Constraints"),
)

TRIGGER_LABELS = {
    "cap_hit_twice": "Cap hit twice in a row",
    "out_of_scope": "Out of scope",
    "dispute": "Dispute",
    "tester_unable_twice": "Tester unable twice",
    "get_help": "Get help",
    "escalation_lock_chat": "Lock the developer's chat during an escalation",  # Phase 10
}

ZONE_COLUMNS = ("name", "description", "examples", "path_patterns")
GLOSSARY_COLUMNS = ("term", "meaning")
# Tables with one column hold a list of plain strings. Their one column is called "text".
TEXT_COLUMN = "text"
ACTION_EDIT = "edit"
ACTION_SAVE = "save"
ACTION_CANCEL = "cancel"
ACTION_RELOAD = "reload"
NOTE_ID_NAME = "note"
BASE_STORE_TYPE = "adm-base"


def tab_button_id(tab: str) -> dict:
    return {"type": "adm-tab", "tab": tab}


def admin_page(
    version: RulebookVersion,
    history_rows=(),
    cited: dict[str, int] | None = None,
    queue: dict | None = None,
    overview=None,
    report=None,
    server: list[tuple[str, str]] | None = None,
    fires: dict[str, int] | None = None,
) -> html.Div:
    """The console: 8 tabs, Overview first. A tab not built yet shows a plain "comes later" line.
    `overview` and `report` (Phase 11c) fill the Overview tab; without them it says so."""
    return html.Div(
        [
            dmc.Title("Admin console", order=3, c=da_styles.NAVY),
            dmc.Tabs(
                [
                    dmc.TabsList(
                        [
                            dmc.TabsTab(label, value=tab, id=tab_button_id(tab))
                            for tab, label, _ in ADMIN_TABS
                        ]
                    ),
                    *[
                        dmc.TabsPanel(
                            _tab_body(
                                tab,
                                version,
                                history_rows,
                                cited,
                                queue,
                                overview,
                                report,
                                server,
                                fires,
                            ),
                            value=tab,
                            pt="md",
                        )
                        for tab, _, _ in ADMIN_TABS
                    ],
                ],
                id=ADMIN_TABS_ID,
                value=TAB_OVERVIEW,
            ),
        ],
        style=da_styles.PAGE,
    )


def refusal_page() -> html.Div:
    """Shown to anyone who is not on the Admin list (11-2). No rulebook data is on it."""
    return html.Div(dmc.Text(NOT_ADMIN_MESSAGE, c=da_styles.MUTED), style=da_styles.PAGE)


version_line = version_pill  # the old name (AF-3) still works


def _tab_body(
    tab: str,
    version: RulebookVersion,
    rows=(),
    cited=None,
    queue=None,
    overview=None,
    report=None,
    server=None,
    fires=None,
):
    if tab == TAB_OVERVIEW and overview is not None and report is not None:
        return html.Div(overview_view(version, overview, report), id=body_id(TAB_OVERVIEW))
    if tab in EDITABLE_TABS:
        content = tab_content(tab, version, cited=cited, queue=queue, server=server, fires=fires)
        return html.Div(content, id=body_id(tab))
    if tab == TAB_HISTORY:
        return html.Div(history_view(rows), id=body_id(TAB_HISTORY))
    phase = next(built for name, _, built in ADMIN_TABS if name == tab)
    return dmc.Text(f"Comes in {phase}.", c=da_styles.MUTED)


def tab_content(
    tab: str,
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    notice: list | None = None,
    active: bool = True,
    cited: dict[str, int] | None = None,
    queue: dict | None = None,
    server: list[tuple[str, str]] | None = None,
    modules: list[str] | None = None,
    fires: dict[str, int] | None = None,
    ask_rebuild: bool = False,
):
    """One editable tab: notice lines, the view or the form, and the buttons that fit the mode.

    `cited` is {rule_id: count} for the Cited column of the rule tables (read only). `queue` is
    the Unassigned queue data for the Capability catalog tab (see queue_block). `server` is the
    read-only server settings list of the Repository and index tab."""
    if tab == TAB_REPO:
        body = repo_view(version, server, editable, draft, active, ask_rebuild)
    elif tab in (TAB_UI, TAB_CODING):
        if modules is None and tab == TAB_CODING and editable:  # the golden module picker
            modules = module_paths(version.rulebook.policy.index_folder_scope)
        body = rules_view(tab, version, editable, draft, active, cited or {}, fires or {}, modules)
    elif tab == TAB_CAPABILITY:
        if modules is None:
            modules = module_paths(version.rulebook.policy.index_folder_scope)
        body = catalog_view(version, editable, draft, active, queue, modules)
    else:
        view = charter_view if tab == TAB_CHARTER else build_view
        body = view(version, editable, draft, active)
    return html.Div(
        [
            *(notice or []),
            body,
            _buttons(tab, version, editable),
            dcc.Store(id={"type": BASE_STORE_TYPE, "tab": tab}, data=version.version_number),
        ]
    )


def _buttons(tab: str, version: RulebookVersion, editable: bool):
    if not editable:
        return dmc.Button("Edit", id=act_id(tab, ACTION_EDIT), mt="md")
    label = next(name for tab_id, name, _ in ADMIN_TABS if tab_id == tab)
    # The shared edit bar (AF-3): stays at the bottom of the window while the Admin scrolls.
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Text(
                    f"Editing {label}. Nothing changes for developers until you save.",
                    size="sm",
                    fw=600,
                ),
                dmc.TextInput(
                    label="Change note (required)",
                    id={"type": "adm-field", "tab": tab, "name": NOTE_ID_NAME},
                    value="",
                ),
                dmc.Group(
                    [
                        dmc.Button("Save as new version", id=act_id(tab, ACTION_SAVE)),
                        dmc.Button("Cancel", id=act_id(tab, ACTION_CANCEL), variant="default"),
                    ]
                ),
            ],
            gap="xs",
        ),
        withBorder=True,
        p="sm",
        mt="md",
        style={"position": "sticky", "bottom": 0, "zIndex": 5},
    )


def problem_notice(problems: list[str]):
    return dmc.Alert(
        [dmc.Text("The rulebook was not saved. Please fix these problems:", size="sm", fw=600)]
        + [dmc.Text(f"- {line}", size="sm") for line in problems],
        color="red",
        mb="sm",
    )


def message_notice(
    message: str,
    color: str = "yellow",
    reload_tab: str | None = None,
    newest: int | None = None,
):
    parts: list = [dmc.Text(message, size="sm")]
    if reload_tab:
        label = f"Reload v{newest}" if newest else "Reload"
        parts.append(dmc.Button(label, id=act_id(reload_tab, ACTION_RELOAD), size="xs", mt="xs"))
    return dmc.Alert(parts, color=color, mb="sm")


def saved_notice(version_number: int, warnings: list[str]):
    parts = [
        dmc.Text(
            f"Saved as v{version_number}. New requests use it from now; "
            "requests in progress keep their version.",
            size="sm",
            fw=600,
        )
    ]
    parts += [dmc.Text(f"Warning: {line}", size="sm") for line in warnings]
    return dmc.Alert(parts, color="green", mb="sm")


# --- Shared list table (zones, protected files, glossary, charter lists; 11b reuses it) ---


CODE_COLUMNS = ("good_example", "bad_example", "code")  # drawn in a code box in the read view
READONLY = "readonly"  # a cell kind: a disabled input that is still read back like any cell


def list_table(
    tab: str,
    table_id: str,
    columns: tuple[str, ...],
    rows: list[dict],
    editable: bool,
    kinds: dict | None = None,
    static: tuple[str, ...] = (),
    movable: bool = False,
):
    """A table drawn from column names. Read mode is plain text; edit mode adds Add row and Remove.

    Edit cells carry pattern-matching ids so the callbacks can read them back.
    `kinds` says a column is READONLY or a dropdown (a list of choices). A `static` column is plain
    text in both modes and is never read back (the Cited counts).
    """
    kinds = kinds or {}
    head = dmc.TableThead(
        dmc.TableTr([dmc.TableTh(col.replace("_", " ").capitalize()) for col in columns])
    )
    body = dmc.TableTbody(
        [
            _table_row(tab, table_id, columns, i, row, editable, kinds, static, movable)
            for i, row in enumerate(rows)
        ]
    )
    parts: list = [dmc.Table([head, body], withTableBorder=True, withColumnBorders=True)]
    if not rows:
        parts.append(dmc.Text("Nothing here yet.", style=da_styles.EMPTY_TEXT))
    if editable:
        parts.append(
            dmc.Button(
                "Add row",
                id={"type": "adm-add", "tab": tab, "table": table_id, "index": 0},
                variant="default",
                size="xs",
                mt="xs",
            )
        )
    return html.Div(parts)


def _table_row(tab, table_id, columns, index, row, editable, kinds, static, movable=False):
    cells = []
    for col in columns:
        value = _cell_text(row.get(col, ""))
        if editable and col not in static:
            cell_id = {
                "type": "adm-cell",
                "tab": tab,
                "table": table_id,
                "row": index,
                "col": col,
            }
            kind = kinds.get(col)
            if kind == READONLY:
                widget = dmc.TextInput(value=value, id=cell_id, disabled=True, size="xs")
            elif kind:
                widget = dmc.Select(
                    data=kind, value=value or None, id=cell_id, size="xs", searchable=True
                )
            else:
                widget = dmc.Textarea(value=value, id=cell_id, autosize=True, minRows=1, size="xs")
            cells.append(dmc.TableTd(widget))
        else:
            shown = _plain(value) if col == "severity" else value
            if col in CODE_COLUMNS or table_id == "protected_files":  # code and paths: code box
                cells.append(dmc.TableTd(dmc.Code(shown, block=True)))
            else:
                cells.append(
                    dmc.TableTd(dmc.Text(shown, size="sm", style={"whiteSpace": "pre-wrap"}))
                )
    if editable:
        buttons = [
            dmc.Button(
                "Remove",
                id={"type": "adm-remove", "tab": tab, "table": table_id, "index": index},
                variant="subtle",
                color="red",
                size="xs",
            )
        ]
        if movable:
            for label, step in (("Move up", -1), ("Move down", 1)):
                move_id = {
                    "type": MOVE_TYPE,
                    "tab": tab,
                    "table": table_id,
                    "index": index,
                    "step": step,
                }
                buttons.append(dmc.Button(label, id=move_id, variant="default", size="xs"))
        cells.append(dmc.TableTd(dmc.Group(buttons, gap="xs") if movable else buttons[0]))
    return dmc.TableTr(cells)


def _cell_text(value) -> str:
    # A list cell (examples, path patterns) is one item per line.
    return "\n".join(value) if isinstance(value, list) else str(value)


def _text_rows(items) -> list[dict]:
    return [{TEXT_COLUMN: item} for item in items]


def _draft(draft: dict | None, key: str, default):
    return default if draft is None or key not in draft else draft[key]


# --- Project charter ---


def charter_view(
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
):
    charter = version.rulebook.charter
    purpose = _draft(draft, "purpose", charter.purpose)
    return html.Div(
        [
            version_line(version, active),
            _charter_size(charter),
            _section("Purpose", _purpose(purpose, editable)),
            # Scope, then principles and constraints: two boxes side by side each.
            *[
                dmc.SimpleGrid(
                    [_charter_box(charter, draft, editable, *entry) for entry in pair],
                    cols=2,
                    mb="sm",
                )
                for pair in (CHARTER_LISTS[:2], CHARTER_LISTS[2:])
            ],
            _section(
                "Glossary",
                list_table(
                    TAB_CHARTER,
                    "glossary",
                    GLOSSARY_COLUMNS,
                    _draft(draft, "glossary", [entry.model_dump() for entry in charter.glossary]),
                    editable,
                ),
            ),
        ]
    )


def _purpose(purpose: str, editable: bool):
    if not editable:
        return dmc.Text(purpose, size="sm")
    return dmc.Textarea(
        value=purpose,
        id={"type": "adm-field", "tab": TAB_CHARTER, "name": "purpose"},
        autosize=True,
        minRows=2,
    )


CHARTER_BOX_ICONS = {"in_scope": "✅ ", "out_of_scope": "🔴 "}


def _charter_box(charter: Charter, draft: dict | None, editable: bool, name: str, label: str):
    rows = _text_rows(_draft(draft, name, getattr(charter, name)))
    table = list_table(TAB_CHARTER, name, (TEXT_COLUMN,), rows, editable)
    return _section(CHARTER_BOX_ICONS.get(name, "") + label, table)


def _charter_size(charter: Charter):
    """The size meter: a coloured pill and a bar (green under 80%, amber to 100%, red over)."""
    size = check_charter_size(charter)
    return dmc.Group(
        [
            dmc.Badge(
                f"Charter size: {size.characters} characters ({size.percent:.0f}% of the limit)",
                variant="light",
                style=admin_styles.pill_style(size.status),
            ),
            dmc.Progress(
                value=min(size.percent, 100),
                color=admin_styles.pill_style(size.status)["color"],
                w=160,
            ),
        ],
        my="xs",
    )


# --- UI standards and Coding standards (Phase 11b) ---

RULE_COLUMNS = (
    "rule_id",
    "title",
    "tags",
    "severity",
    "why",
    "good_example",
    "bad_example",
    "source",
)
GOLDEN_COLUMNS = ("title", "program_type", "module_path", "tags", "code", "why")
SEVERITY_WORDS = {"must_fix": "Must fix", "should_fix": "Should fix", "fyi": "FYI"}
# The stored value stays must_fix (the server checks it); the person reads the plain words (AF-2).
SEVERITY_CHOICES = [{"value": key, "label": words} for key, words in SEVERITY_WORDS.items()]


def _plain(text: str) -> str:
    return SEVERITY_WORDS.get(text, text)
SONAR_FIELD_PREFIX = "sonar_"  # a field named sonar_MAJOR holds the severity for MAJOR
RULES_TABLE = "rules"
RULE_KIND_OF_TAB = {TAB_UI: "ui_convention", TAB_CODING: "judgement"}
RULE_TITLE_OF_TAB = {TAB_UI: "UI rules", TAB_CODING: "Judgement rules"}
RULE_ID_HINT = (
    "Add row hands out the next rule ID at once. The number stays used up even if you Cancel."
)
CITED_COLUMN = "cited"


def _rule_rows(version: RulebookVersion, kind: str, draft: dict | None) -> list[dict]:
    mine = [r.model_dump() for r in version.rulebook.rules if r.kind == kind]
    return _draft(draft, RULES_TABLE, mine)


def _tags_hint(version: RulebookVersion, kind: str) -> str:
    tags = sorted({tag for r in version.rulebook.rules if r.kind == kind for tag in r.tags})
    return "Tags in use: " + (", ".join(tags) if tags else "none yet") + ". One tag per line."


def rules_view(
    tab: str,
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
    cited: dict[str, int] | None = None,
    fires: dict[str, int] | None = None,
    modules: list[str] | None = None,
):
    """UI standards (ui_convention rules) or Coding standards (judgement rules plus lists)."""
    kind = RULE_KIND_OF_TAB[tab]
    cited = cited or {}
    rows = _rule_rows(version, kind, draft)
    columns = RULE_COLUMNS
    if tab == TAB_CODING:
        # Cited is read only and not part of the form: the Tester's kept findings are counted.
        columns = (*RULE_COLUMNS, CITED_COLUMN)
        rows = [{**row, CITED_COLUMN: cited.get(str(row.get("rule_id", "")), 0)} for row in rows]
    parts: list = [
        version_line(version, active),
        dmc.Text(
            f"{RULE_TITLE_OF_TAB[tab]}: {rule_counter_text(kind, len(rows))}",
            size="sm",
            fw=600,
            mt="xs",
        ),
        rule_panel_div(rows, fires or {})  # read view of Coding standards: list left, card right
        if tab == TAB_CODING and not editable
        else list_table(
            tab,
            RULES_TABLE,
            columns,
            rows,
            editable,
            kinds={"rule_id": READONLY, "severity": SEVERITY_CHOICES},
            static=(CITED_COLUMN,) if tab == TAB_CODING else (),
        ),
        dmc.Text(_tags_hint(version, kind), size="xs", c=da_styles.MUTED),
    ]
    if editable:
        parts.append(dmc.Text(RULE_ID_HINT, size="xs", c=da_styles.MUTED))
    if tab == TAB_UI:
        brand = brand_panel(version.rulebook.brand_constants)
        # Read view: brand constants left 2/3, UI conventions right 1/3. Edit keeps them stacked.
        parts.insert(1, brand if editable else two_columns(brand, convention_rows(rows)))
    if tab == TAB_CODING:
        parts += _coding_extras(version, editable, draft, modules)
    return html.Div(parts)


def _coding_extras(
    version: RulebookVersion, editable: bool, draft: dict | None, modules: list[str] | None
):
    policy = version.rulebook.policy
    golden = _draft(
        draft, "golden_examples", [g.model_dump() for g in version.rulebook.golden_examples]
    )
    approved = _draft(draft, "approved_libraries", policy.approved_libraries)
    blocked = _draft(draft, "blocked_imports", policy.build_blocked_imports)
    # The picker lists the index plus each example's own path (it may have left the index).
    picks = sorted({*(modules or []), *(g.get("module_path", "") for g in golden)} - {""})
    return [
        _section(
            "Approved libraries",
            list_table(TAB_CODING, "approved_libraries", (TEXT_COLUMN,), _text_rows(approved), True)
            if editable
            else library_chips(approved),
        ),
        _section(
            "Blocked imports",
            list_table(TAB_CODING, "blocked_imports", (TEXT_COLUMN,), _text_rows(blocked), True)
            if editable
            else library_chips(blocked, blocked=True),
        ),
        _section("SonarQube severity map", _sonar_map(policy, editable, draft)),
        _section(
            "Golden examples (the Generator follows the one that matches the program type)",
            list_table(
                TAB_CODING,
                "golden_examples",
                GOLDEN_COLUMNS,
                golden,
                editable,
                kinds={"program_type": list(PROGRAM_TYPES), "module_path": picks},
            )
            if editable
            else golden_cards(golden),
        ),
    ]


def _sonar_map(policy: Policy, editable: bool, draft: dict | None):
    chosen = _draft(draft, "sonar_map", policy.sonar_severity_map)
    lines = []
    for key in SONAR_SEVERITY_KEYS:
        value = chosen.get(key, "")
        if editable:
            lines.append(
                dmc.Select(
                    label=f"SonarQube {key}",
                    data=SEVERITY_CHOICES,
                    value=value or None,
                    id={"type": "adm-field", "tab": TAB_CODING, "name": SONAR_FIELD_PREFIX + key},
                    size="xs",
                    w=220,
                )
            )
        else:
            lines.append(dmc.Text(f"{key}: {_plain(value)}", size="sm"))
    sample = sample_with_mapping(chosen)
    return html.Div(
        [
            dmc.Stack(lines, gap=2),
            dmc.Text(SAMPLE_BANNER, size="xs", c=da_styles.MUTED, mt="sm"),
            dmc.Table(
                [
                    dmc.TableThead(
                        dmc.TableTr([dmc.TableTh(h) for h in ("Check", "Name", "Sonar", "Mapped")])
                    ),
                    dmc.TableTbody(
                        [
                            dmc.TableTr(
                                [
                                    dmc.TableTd(dmc.Text(_plain(row[k]), size="xs"))
                                    for k in ("key", "name", "sonar", "mapped")
                                ]
                            )
                            for row in sample
                        ]
                    ),
                ],
                withTableBorder=True,
            ),
        ]
    )


# --- Capability catalog and the Unassigned queue (Phase 11b) ---

CATALOG_TABLE = "capabilities"
CATALOG_COLUMNS = ("name", "description", "named_senior", "backup_senior", "path_patterns")
MOVE_TYPE = "adm-move"
QUEUE_BUTTON_TYPE = "adm-q"
QUEUE_PICK_TYPE = "adm-q-pick"
QUEUE_NOTE_TYPE = "adm-q-note"
QUEUE_BLOCK_ID = "adm-queue"
Q_CONFIRM = "confirm"
Q_MOVE = "move"
Q_APPROVE = "approve"  # take the suggested capability (the id's `cap` carries it)
Q_REJECT = "reject"  # the file belongs in no capability: closes the row as rejected
Q_NEW = "new_capability"  # open the catalog in edit mode with one new row for this file
Q_APPLY = "apply"
Q_APPLY_PATTERN = "apply_pattern"
Q_CANCEL = "cancel"
Q_SHOW_RESOLVED = "show_resolved"
Q_HIDE_RESOLVED = "hide_resolved"
CATALOG_HINT = (
    "First match wins: a file goes to the first capability in this list whose pattern matches. "
    "Use Move up and Move down to change the order."
)


def queue_button_id(action: str, uid: int = 0, cap: str = "", state: str = "") -> dict:
    # Every queue button has the same four keys so one callback pattern matches them all.
    return {"type": QUEUE_BUTTON_TYPE, "action": action, "uid": uid, "cap": cap, "state": state}


def catalog_view(
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
    queue: dict | None = None,
    modules: list[str] | None = None,
    missing_backup: bool = False,
):
    """The catalog table (editable) with the Unassigned queue under it (read view only).
    `modules` is every indexed path (da_admin_modules.module_paths)."""
    policy = version.rulebook.policy
    rows = _draft(draft, CATALOG_TABLE, capability_rows(policy))
    paths = modules or []
    if editable:
        table = html.Div(
            [
                list_table(
                    TAB_CAPABILITY, CATALOG_TABLE, CATALOG_COLUMNS, rows, editable, movable=True
                ),
                _add_module_panel([r["name"] for r in rows if r.get("name")], paths),
            ]
        )
    else:
        table = html.Div(
            [
                dmc.Group(
                    [
                        dmc.TextInput(
                            id=CAP_SEARCH_ID, placeholder="Search name or module", size="xs"
                        ),
                        dmc.Chip("Missing backup", id=CAP_MISSING_ID, checked=missing_backup),
                    ],
                    mb="xs",
                ),
                html.Div(
                    catalog_list(policy.capabilities, paths, "", missing_backup), id=CAP_LIST_ID
                ),
            ]
        )
    return html.Div(
        [
            version_line(version, active),
            dmc.Text(CATALOG_HINT, size="xs", c=da_styles.MUTED),
            two_columns(
                table,
                queue_block(queue, [c.name for c in policy.capabilities], disabled=editable),
            ),
        ]
    )


CAP_SEARCH_ID = "adm-cat-search"
CAP_MISSING_ID = "adm-cat-missing"
CAP_LIST_ID = "adm-cat-list"
MODULE_TABLE = "capmodule"  # the Add module picker: one row, a capability and a path
MODULE_COLUMNS = ("capability", "path")


def catalog_list(capabilities, paths: list[str], search: str = "", missing_backup: bool = False):
    """The read-only catalog: one row per capability with its module chips (max 6, then +N more).
    A module claimed by two capabilities shows "×2". Search matches name, description or module."""
    by_capability = modules_by_capability(list(capabilities), paths)
    counts = share_counts(by_capability)
    rows = []
    for c in capabilities:
        mine = by_capability[c.name]
        if missing_backup and c.backup_senior.strip():
            continue
        if not matches_search(c.name, c.description, mine, search):
            continue
        labels, more = module_chips(mine, counts)
        chips = [dmc.Badge(label, variant="outline", tt="none") for label in labels]
        if more:
            chips.append(dmc.Badge(f"+{more} more", variant="light", tt="none"))
        backup = c.backup_senior.strip() or "none"
        rows.append(
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Text(c.name, fw=600, size="sm")),
                    dmc.TableTd(dmc.Text(c.description, size="sm")),
                    dmc.TableTd(dmc.Text(c.named_senior, size="sm")),
                    dmc.TableTd(
                        dmc.Badge(
                            backup,
                            variant="light",
                            style=admin_styles.pill_style("green" if c.backup_senior else "amber"),
                        )
                    ),
                    dmc.TableTd(dmc.Group(chips or [dmc.Text("none", size="xs")], gap=4)),
                ]
            )
        )
    head = dmc.TableThead(
        dmc.TableTr(
            [
                dmc.TableTh(h)
                for h in ("Capability", "Description", "Named senior", "Backup senior", "Modules")
            ]
        )
    )
    parts: list = [dmc.Table([head, dmc.TableTbody(rows)])]
    if not rows:
        parts.append(dmc.Text("No capability matches.", style=da_styles.EMPTY_TEXT))
    return html.Div(parts)


def _add_module_panel(names: list[str], paths: list[str]):
    """Edit mode: pick a capability and an indexed path; Add module makes it an exact pattern."""

    def cell(col, data):
        return dmc.Select(
            data=data,
            searchable=True,
            size="xs",
            id={
                "type": "adm-cell",
                "tab": TAB_CAPABILITY,
                "table": MODULE_TABLE,
                "row": 0,
                "col": col,
            },
        )

    return dmc.Group(
        [
            cell("capability", names),
            cell("path", paths),
            dmc.Button(
                "Add module",
                id={"type": "adm-add", "tab": TAB_CAPABILITY, "table": MODULE_TABLE, "index": 0},
                variant="default",
                size="xs",
            ),
        ],
        mt="xs",
    )


def _waiting_text(row) -> str:
    return row.waiting_since.strftime("%Y-%m-%d") if row.waiting_since else ""


def queue_block(queue: dict | None, capability_names: list[str], disabled: bool = False):
    """Open Unassigned files, what each would match today, and the buttons to resolve them.

    `queue` is {"rows": [QueueRow], "resolved": [UnassignedFile] or None, "dialog": dict or None,
    "notice": [component]}. While the catalog is edited the buttons are disabled (one change at
    a time)."""
    queue = queue or {"rows": [], "resolved": None, "dialog": None, "notice": []}
    rows = queue["rows"]
    parts: list = [
        dmc.Text("Unassigned queue", fw=600, c=da_styles.NAVY, size="sm"),
        *queue.get("notice", []),
    ]
    if queue.get("dialog"):
        parts.append(_pattern_dialog(queue["dialog"]))
    if rows:
        parts.extend(_queue_card(r, capability_names, disabled) for r in rows)
    else:
        parts.append(dmc.Text("No Unassigned files are waiting.", style=da_styles.EMPTY_TEXT))
    if queue.get("resolved") is None:
        parts.append(
            dmc.Button(
                "Show resolved",
                id=queue_button_id(Q_SHOW_RESOLVED),
                variant="default",
                size="xs",
                mt="xs",
                disabled=disabled,
            )
        )
    else:
        parts.append(_resolved_table(queue["resolved"]))
        parts.append(
            dmc.Button(
                "Hide resolved",
                id=queue_button_id(Q_HIDE_RESOLVED),
                variant="default",
                size="xs",
                disabled=disabled,
            )
        )
    return html.Div(parts, id=QUEUE_BLOCK_ID, style=da_styles.PANEL_SECTION)


def _queue_card(row, capability_names: list[str], disabled: bool):
    """One Unassigned file as a card (L6): facts on top, the same buttons below."""
    start = row.would_match or row.picked_capability
    return dmc.Paper(
        [
            dmc.Text(row.path, size="sm", fw=600),
            dmc.Text(f"Developer's pick: {row.picked_capability}", size="xs", c=da_styles.MUTED),
            dmc.Text(
                f"Request {row.request_id}, waiting since {_waiting_text(row)}",
                size="xs",
                c=da_styles.MUTED,
            ),
            dmc.Text(f"Would match: {row.would_match or '(none)'}", size="xs", c=da_styles.MUTED),
            dmc.Text(f"Suggestion: {row.suggested or '(none)'}", size="xs", fw=600),
            dmc.Text(row.reason, size="xs", style=da_styles.EMPTY_TEXT),
            html.Div(
                dmc.Group(
                    [
                        *(
                            [
                                dmc.Button(
                                    "Approve",
                                    id=queue_button_id(Q_APPROVE, row.unassigned_id, row.suggested),
                                    size="xs",
                                    disabled=disabled,
                                )
                            ]
                            if row.suggested
                            else []
                        ),
                        dmc.Button(
                            "Confirm",
                            id=queue_button_id(Q_CONFIRM, row.unassigned_id),
                            size="xs",
                            disabled=disabled,
                        ),
                        dmc.Select(
                            data=capability_names,
                            value=start if start in capability_names else None,
                            id={"type": QUEUE_PICK_TYPE, "uid": row.unassigned_id},
                            size="xs",
                            w=150,
                            disabled=disabled,
                        ),
                        dmc.Button(
                            "Move to...",
                            id=queue_button_id(Q_MOVE, row.unassigned_id),
                            size="xs",
                            variant="default",
                            disabled=disabled,
                        ),
                        dmc.Button(
                            "New capability",
                            id=queue_button_id(Q_NEW, row.unassigned_id),
                            size="xs",
                            variant="default",
                            disabled=disabled,
                        ),
                        dmc.Button(
                            "Reject",
                            id=queue_button_id(Q_REJECT, row.unassigned_id),
                            size="xs",
                            variant="default",
                            color="red",
                            disabled=disabled,
                        ),
                    ],
                    gap="xs",
                ),
                style={"marginTop": "8px"},
            ),
        ],
        withBorder=True,
        p="sm",
        mb="xs",
    )


def _pattern_dialog(dialog: dict):
    """Asked after Confirm or Move: close the row, and (if it helps) also add the path as a
    pattern. dialog: uid, state, capability, path, offer (True when a pattern helps), reason."""
    uid, state, cap = dialog["uid"], dialog["state"], dialog["capability"]
    verb = "Confirm" if state == "confirmed" else f"Move to {cap}"
    parts: list = [
        dmc.Text(f"{verb}: {dialog['path']}", size="sm", fw=600),
        dmc.TextInput(
            label="Change note (needed only if you add the pattern)",
            id={"type": QUEUE_NOTE_TYPE, "uid": uid},
            value="",
        ),
    ]
    buttons = []
    if dialog["offer"]:
        parts.insert(
            1, dmc.Text(f"Also add this path as a pattern to '{cap}'? Next files then match.")
        )
        buttons.append(
            dmc.Button(
                "Add pattern and resolve",
                id=queue_button_id(Q_APPLY_PATTERN, uid, cap, state),
                size="xs",
            )
        )
    else:
        parts.insert(1, dmc.Text(dialog["reason"], size="sm"))
    buttons.append(
        dmc.Button(
            "Resolve without pattern",
            id=queue_button_id(Q_APPLY, uid, cap, state),
            size="xs",
            variant="default",
        )
    )
    buttons.append(
        dmc.Button("Cancel", id=queue_button_id(Q_CANCEL, uid), size="xs", variant="subtle")
    )
    return dmc.Alert([*parts, dmc.Group(buttons, mt="xs")], color="blue", mb="sm")


def _resolved_table(rows):
    if not rows:
        return dmc.Text("Nothing resolved yet.", style=da_styles.EMPTY_TEXT)
    header = ("Path", "State", "By", "When", "Moved to")
    body = []
    for row in rows:
        when = row.resolved_at.strftime("%Y-%m-%d %H:%M") if row.resolved_at else ""
        values = (row.path, row.state, row.resolved_by, when, row.resolved_capability)
        body.append(dmc.TableTr([dmc.TableTd(dmc.Text(v, size="sm")) for v in values]))
    return dmc.Table(
        [dmc.TableThead(dmc.TableTr([dmc.TableTh(h) for h in header])), dmc.TableTbody(body)],
        withTableBorder=True,
    )


# --- Build and test ---


def build_view(
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
):
    policy = version.rulebook.policy
    return html.Div(
        [
            version_line(version, active),
            _section("Limits", _number_fields(policy, CORE_BUILD_FIELDS, editable, draft)),
            dmc.Accordion(
                [
                    dmc.AccordionItem(
                        [
                            dmc.AccordionControl("Advanced limits"),
                            dmc.AccordionPanel(
                                _number_fields(policy, ADVANCED_LIMIT_FIELDS, editable, draft)
                            ),
                        ],
                        value="advanced",
                    )
                ],
                value=None,
            ),
            _section(
                "Model per role",
                dmc.Stack(
                    [
                        _model_field(policy, "generator_model", "Generator model", editable, draft),
                        _model_field(policy, "tester_model", "Tester model", editable, draft),
                    ],
                    gap=2,
                ),
            ),
            _section("Escalation triggers", _triggers(policy, editable, draft)),
            _section(
                "Flag-for-review zones",
                list_table(
                    TAB_BUILD,
                    "zones",
                    ZONE_COLUMNS,
                    _draft(draft, "zones", [z.model_dump() for z in policy.flag_review_zones]),
                    editable,
                ),
            ),
            _section(
                "Protected files",
                list_table(
                    TAB_BUILD,
                    "protected_files",
                    (TEXT_COLUMN,),
                    _text_rows(_draft(draft, "protected_files", policy.protected_files)),
                    editable,
                ),
            ),
            _section("Tests", _tests_card()),
            _section("Can a request be handed off?", _severity_table()),
        ]
    )


# Read only: how the build and test loop works (fixed in code, not set by an Admin).
TEST_FACTS = (
    "Requirement tests from the criteria, frozen before the code",
    "Code tests after the build, for branches and edge cases",
    "Tests run only in the server sandbox, never in the developer's folder",
    "A test with no result counts as Not proven and blocks the pass",
)
SEVERITY_HANDOFF = (
    ("Must fix", "No"),
    ("Should fix", "Yes, listed in the PR summary"),
    ("FYI", "Yes"),
)


def _tests_card():
    return dmc.Stack([dmc.Text(f"✅ {fact}", size="sm") for fact in TEST_FACTS], gap=2)


def _severity_table():
    head = dmc.TableThead(dmc.TableTr([dmc.TableTh("Severity"), dmc.TableTh("Can hand off?")]))
    body = dmc.TableTbody(
        [dmc.TableTr([dmc.TableTd(s), dmc.TableTd(answer)]) for s, answer in SEVERITY_HANDOFF]
    )
    return dmc.Table([head, body], withTableBorder=True)


# Plain names for the three core limits (spec section 8, "Shown as").
# Advanced limits keep their field names.
NUMBER_LABELS = {
    "build_max_rounds": "Max fix rounds",
    "build_test_timeout_seconds": "Test time limit (seconds)",
    "max_files": "Max files per request",
    "max_material_decisions": "Decision limit",
    "workspace_max_file_kb": "Largest file the scan reads (KB)",
}


def _number_fields(policy: Policy, names: tuple[str, ...], editable: bool, draft: dict | None):
    return dmc.Stack([_number_field(policy, n, editable, draft) for n in names], gap=2)


def _number_field(
    policy: Policy, name: str, editable: bool, draft: dict | None, tab: str = TAB_BUILD
):
    value = str(_draft(draft, name, getattr(policy, name)))
    hint = field_bounds(name)
    label = NUMBER_LABELS.get(name) or field_label(name)
    if not editable:
        return dmc.Text(f"{label}: {value}" + (f"   (allowed: {hint})" if hint else ""), size="sm")
    # A number box with − / + buttons; the server still checks the bounds on save.
    return dmc.NumberInput(
        label=label,
        description=f"allowed: {hint}" if hint else None,
        value=int(value) if value.lstrip("-").isdigit() else value,
        id={"type": "adm-field", "tab": tab, "name": name},
        size="xs",
    )


# --- Repository and index (Phase 11c, spec 11) ---

REPO_LIST_TABLES = (
    ("allowed_folders", "Allowed folders"),
    ("workspace_markers", "Workspace markers"),
)
REPO_PATTERN = "new_file_name_pattern"
REPO_SIZE = "workspace_max_file_kb"


def repo_view(
    version: RulebookVersion,
    server: list[tuple[str, str]] | None,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
    ask_rebuild: bool = False,
):
    """Read-only server settings, then the four editable fields. `server` is (name, shown value)."""
    policy = version.rulebook.policy
    settings_lines = [
        dmc.Text(f"{field_label(name)}: {value}", size="sm") for name, value in (server or [])
    ]
    pattern = _draft(draft, REPO_PATTERN, policy.new_file_name_pattern)
    if editable:
        pattern_widget = dmc.TextInput(
            label="New file name pattern (a regular expression)",
            value=pattern,
            id={"type": "adm-field", "tab": TAB_REPO, "name": REPO_PATTERN},
            size="xs",
        )
    else:
        pattern_widget = dmc.Text(f"New file name pattern: {pattern}", size="sm")
    health = read_health()
    left = [
        _section("Connection", _connection(policy, editable, draft)),
        _section(
            "Refresh",
            refresh_tiles(_draft(draft, "index_refresh_mode", policy.index_refresh_mode)),
        ),
        _section(
            "Exclusions",
            dmc.Stack(
                [
                    fixed_skip_rows(),
                    list_table(
                        TAB_REPO,
                        "index_exclusions",
                        EXCLUSION_COLUMNS,
                        _draft(draft, "index_exclusions", _exclusion_rows(policy)),
                        editable,
                        kinds={"kind": list(EXCLUSION_KINDS)},
                    ),
                ]
            ),
        ),
        *[
            _section(title, _repo_list(table, policy, editable, draft))
            for table, title in REPO_LIST_TABLES
        ],
        _section("New file name pattern", pattern_widget),
        _section(
            "Largest file the laptop scan reads",
            _number_field(policy, REPO_SIZE, editable, draft, TAB_REPO),
        ),
        dmc.Accordion(
            [
                dmc.AccordionItem(
                    [
                        dmc.AccordionControl("Server settings (read only, set in .env)"),
                        dmc.AccordionPanel(dmc.Stack(settings_lines, gap=2)),
                    ],
                    value="server",
                )
            ],
            value=None,
        ),
    ]
    right = [
        _section("Index health", health_tiles(health)),
        _section("Recent refreshes", recent_refreshes(recent_runs())),
    ]
    return html.Div(
        [
            version_line(version, active),
            index_pill(health, datetime.now()),
            rebuild_controls(running_since(), recent_runs(), ask_rebuild),
            two_columns(html.Div(left), html.Div(right)),  # spec 7: connection left, health right
        ]
    )


def _repo_list(table: str, policy: Policy, editable: bool, draft: dict | None):
    """Allowed folders and markers: chips to read, a table to edit."""
    words = _draft(draft, table, getattr(policy, table))
    if not editable:
        return word_chips(words)
    return list_table(TAB_REPO, table, (TEXT_COLUMN,), _text_rows(words), True)


EXCLUSION_COLUMNS = ("pattern", "reason", "kind")
EXCLUSION_KINDS = ("Config", "Build", "Scratch")


def _exclusion_rows(policy: Policy) -> list[dict]:
    return [e.model_dump() for e in policy.index_exclusions]


def _connection(policy: Policy, editable: bool, draft: dict | None):
    scope = _draft(draft, "index_folder_scope", policy.index_folder_scope)
    lines = [
        dmc.Text(f"Bitbucket repository: {policy.index_repo or '(not set)'}", size="sm"),
        dmc.Text(f"Branch indexed: {policy.index_branch} 🔒", size="sm"),
    ]
    if editable:
        lines.append(
            dmc.TextInput(
                label="Folder scope (empty = the server's default source folder)",
                value=scope,
                id={"type": "adm-field", "tab": TAB_REPO, "name": "index_folder_scope"},
                size="xs",
            )
        )
        lines.append(
            dmc.Select(
                label="Refresh",
                data=[{"value": k, "label": t} for k, t, _ in REFRESH_MODES],
                value=_draft(draft, "index_refresh_mode", policy.index_refresh_mode),
                id={"type": "adm-field", "tab": TAB_REPO, "name": "index_refresh_mode"},
                size="xs",
            )
        )
    else:
        lines.append(
            dmc.Group([dmc.Text("Folder scope:", size="sm"), dmc.Code(scope or "(default)")], gap=4)
        )
    return dmc.Stack(lines, gap=2)


def _model_field(policy: Policy, name: str, label: str, editable: bool, draft: dict | None):
    value = _draft(draft, name, getattr(policy, name))
    if not editable:
        return dmc.Text(f"{label}: {value or '(use .env)'}", size="sm")
    return dmc.TextInput(
        label=label,
        description="empty = use the model from .env",
        value=value,
        id={"type": "adm-field", "tab": TAB_BUILD, "name": name},
        size="xs",
    )


def _triggers(policy: Policy, editable: bool, draft: dict | None):
    chosen = _draft(
        draft,
        "triggers",
        {t.name: t.on for t in policy.escalation_triggers}
        | {LOCK_CHAT_SWITCH: policy.escalation_lock_chat},  # Phase 10: the sixth switch
    )
    return dmc.Stack(
        [
            dmc.Switch(
                label=TRIGGER_LABELS.get(name, name),
                checked=bool(on),
                disabled=not editable,
                id={"type": "adm-switch", "tab": TAB_BUILD, "name": name},
            )
            for name, on in chosen.items()
        ],
        gap=4,
    )
