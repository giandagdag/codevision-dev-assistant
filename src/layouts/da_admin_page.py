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

import dash_mantine_components as dmc
from dash import dcc, html

from agents.da_admin_access import NOT_ADMIN_MESSAGE
from agents.da_admin_forms import rule_counter_text
from agents.da_admin_modules import module_paths
from agents.da_admin_sonar import SAMPLE_BANNER, load_snapshot, sample_with_mapping, source_pill
from agents.da_sonar_client import NOT_CONNECTED, sonar_configured
from configs.da_config import load_settings
from layouts.da_admin_build_tab import (  # noqa: F401 (callbacks and tests import these)
    NUMBER_LABELS,
    SEVERITY_HANDOFF,
    TEST_FACTS,
    TRIGGER_LABELS,
    ZONE_COLUMNS,
    _model_field,
    _number_field,
    _number_fields,
    _severity_table,
    _tests_card,
    _triggers,
    build_view,
)
from layouts.da_admin_catalog_tab import (  # noqa: F401 (callbacks and tests import these)
    CAP_LIST_ID,
    CAP_MISSING_ID,
    CAP_SEARCH_ID,
    CATALOG_COLUMNS,
    CATALOG_HINT,
    CATALOG_TABLE,
    MODULE_COLUMNS,
    MODULE_TABLE,
    Q_APPLY,
    Q_APPLY_PATTERN,
    Q_APPROVE,
    Q_CANCEL,
    Q_CONFIRM,
    Q_HIDE_RESOLVED,
    Q_MOVE,
    Q_NEW,
    Q_REJECT,
    Q_SHOW_RESOLVED,
    QUEUE_BLOCK_ID,
    QUEUE_BUTTON_TYPE,
    QUEUE_NOTE_TYPE,
    QUEUE_PICK_TYPE,
    _add_module_panel,
    _pattern_dialog,
    _person,
    _queue_card,
    _resolved_table,
    _waiting_text,
    catalog_list,
    catalog_view,
    queue_block,
    queue_button_id,
)
from layouts.da_admin_coding_tab import golden_cards, library_chips, rule_panel_div
from layouts.da_admin_common import (  # noqa: F401 (some are re-exported for the callbacks)
    ADMIN_TABS,
    CODE_COLUMNS,
    GOTO_TYPE,
    MOVE_TYPE,
    READONLY,
    SEVERITY_WORDS,
    TAB_BUILD,
    TAB_CAPABILITY,
    TAB_CHARTER,
    TAB_CODING,
    TAB_HISTORY,
    TAB_OVERVIEW,
    TAB_REPO,
    TAB_UI,
    TEXT_COLUMN,
    _cell_text,
    _draft,
    _plain,
    _table_row,
    _text_rows,
    act_id,
    aligned_row,
    body_id,
    full_row,
    list_table,
    two_columns,
    version_pill,
    word_chips,
)
from layouts.da_admin_common import section as _section
from layouts.da_admin_common import window as _window
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
from layouts.da_admin_overview_tab import (  # noqa: F401 (callbacks import these)
    HEALTH_ID,
    WINDOW_ID,
    _attention_list,
    health_numbers,
    overview_view,
)
from layouts.da_admin_repo_tab import (  # noqa: F401 (callbacks and tests import these)
    EXCLUSION_COLUMNS,
    EXCLUSION_KINDS,
    REPO_LIST_TABLES,
    REPO_PATTERN,
    REPO_SIZE,
    _connection,
    _exclusion_rows,
    _repo_list,
    repo_view,
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

GLOSSARY_COLUMNS = ("term", "meaning")
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
    buttons = _buttons(tab, version, editable)
    if not editable:  # Edit sits top right, beside the version pill (a float, so the pill shrinks)
        buttons = html.Div(buttons, style={"float": "right", "marginLeft": "8px"})
    return html.Div(
        [
            *(notice or []),
            *([] if editable else [buttons]),
            body,
            *([buttons] if editable else []),
            dcc.Store(id={"type": BASE_STORE_TYPE, "tab": tab}, data=version.version_number),
        ]
    )


def _buttons(tab: str, version: RulebookVersion, editable: bool):
    if not editable:
        return dmc.Button("Edit", id=act_id(tab, ACTION_EDIT))
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
# The stored value stays must_fix (the server checks it); the person reads the plain words (AF-2).
SEVERITY_CHOICES = [{"value": key, "label": words} for key, words in SEVERITY_WORDS.items()]


SONAR_REFRESH_BTN = "adm-sonar-refresh-btn"
SONAR_STATUS = "adm-sonar-status"
SONAR_PILL = "adm-sonar-pill"
SONAR_SAMPLE_ID = "adm-sonar-sample"
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
        else html.Div()  # UI read view: the conventions are in the right column, not twice
        if tab == TAB_UI and not editable
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
        if not editable:  # read view: the rule panel is its own row of windows (title inside)
            parts = [parts[0], *parts[2:]]
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
    libraries = _section(
        "Approved libraries",
        list_table(TAB_CODING, "approved_libraries", (TEXT_COLUMN,), _text_rows(approved), True)
        if editable
        else library_chips(approved),
    )
    imports = _section(
        "Blocked imports",
        list_table(TAB_CODING, "blocked_imports", (TEXT_COLUMN,), _text_rows(blocked), True)
        if editable
        else library_chips(blocked, blocked=True),
    )
    examples = _section(
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
    )
    if editable:  # the edit form stays one column of tables
        sonar = _section("SonarQube severity map", _sonar_map(policy, True, draft))
        return [libraries, imports, sonar, examples]
    # Read view, as in the demo: two rows of two side-by-side panels, each in its own window.
    chosen = policy.sonar_severity_map
    checks = _window(
        "🔍 Automatic checks (SonarQube)",
        html.Div(
            [
                dmc.Group(
                    [
                        dmc.Badge("Governed in SonarQube", variant="light", tt="none"),
                        dmc.Badge(
                            source_pill(load_snapshot()),
                            id=SONAR_PILL,
                            variant="outline",
                            tt="none",
                        ),
                        dmc.Button(
                            "Refresh from SonarQube",
                            id=SONAR_REFRESH_BTN,
                            size="xs",
                            disabled=not sonar_configured(load_settings()),
                        ),
                        dmc.Text(
                            "" if sonar_configured(load_settings()) else NOT_CONNECTED,
                            id=SONAR_STATUS,
                            size="xs",
                        ),
                    ]
                ),
                html.Div(sonar_sample_view(chosen), id=SONAR_SAMPLE_ID),
            ]
        ),
    )
    severity = _window("🎚️ SonarQube severity map", _sonar_lines(chosen, False))
    golden_window = _window(
        "⭐ Golden examples (the Generator follows the one that matches the program type)",
        golden_cards(golden),
    )
    library_window = _window(
        "📦 Libraries",
        dmc.Stack(
            [
                dmc.Text("Approved libraries", fw=600, size="sm"),
                library_chips(approved),
                dmc.Text("Blocked imports", fw=600, size="sm", mt="xs"),
                library_chips(blocked, blocked=True),
            ],
            gap=4,
        ),
    )
    # The same 2/3 and 1/3 split as the rules row above, so every window edge lines up.
    # Libraries and the severity map are short, so they share the right column next to the tall
    # golden examples; the SonarQube table is wide, so it gets the full width underneath.
    return [aligned_row(golden_window, [library_window, severity]), full_row(checks)]


def _sonar_map(policy: Policy, editable: bool, draft: dict | None):
    """Edit view: the severity boxes and the sample table in one block."""
    chosen = _draft(draft, "sonar_map", policy.sonar_severity_map)
    return html.Div([_sonar_lines(chosen, editable), sonar_sample_view(chosen)])


def _sonar_lines(chosen: dict, editable: bool):
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
    return dmc.Stack(lines, gap=2)


def sonar_sample_view(chosen: dict):
    """The sample checks with the severity each would get under the map."""
    sample = sample_with_mapping(chosen)
    return html.Div(
        [
            dmc.Text(
                SAMPLE_BANNER if load_snapshot() is None else "",
                size="xs",
                c=da_styles.MUTED,
                mt="sm",
            ),
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

