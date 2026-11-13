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
from agents.da_admin_diff import text_line_diff
from agents.da_admin_forms import (
    ADVANCED_LIMIT_FIELDS,
    CORE_BUILD_FIELDS,
    capability_rows,
    field_bounds,
    rule_counter_text,
)
from agents.da_admin_metrics import WINDOW_ALL, WINDOW_LABELS
from agents.da_admin_sonar import SAMPLE_BANNER, sample_with_mapping
from pydantic_classes.da_rulebook_models import (
    SONAR_SEVERITY_KEYS,
    Charter,
    Policy,
    RulebookVersion,
    check_charter_size,
)
from styles import da_styles

ADMIN_PATH = "/admin"
ADMIN_CONTENT_ID = "da-admin-content"
ADMIN_TABS_ID = "da-admin-tabs"

TAB_OVERVIEW = "overview"
TAB_CHARTER = "charter"
TAB_REPO = "repo"
TAB_CAPABILITY = "capability"
TAB_UI = "ui"
TAB_CODING = "coding"
TAB_BUILD = "build"
TAB_HISTORY = "history"

# (id, label, the phase that builds it). Overview comes first (spec section 3).
ADMIN_TABS: tuple[tuple[str, str, str], ...] = (
    (TAB_OVERVIEW, "Overview", "11c"),
    (TAB_CHARTER, "Project charter", "11a"),
    (TAB_REPO, "Repository and index", "11c"),
    (TAB_CAPABILITY, "Capability catalog", "11b"),
    (TAB_UI, "UI standards", "11b"),
    (TAB_CODING, "Coding standards", "11b"),
    (TAB_BUILD, "Build and test", "11a"),
    (TAB_HISTORY, "Version history", "11a"),
)
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


def body_id(tab: str) -> str:
    return f"adm-body-{tab}"


def act_id(tab: str, action: str) -> dict:
    return {"type": "adm-act", "tab": tab, "action": action}


def admin_page(
    version: RulebookVersion,
    history_rows=(),
    cited: dict[str, int] | None = None,
    queue: dict | None = None,
    overview=None,
    report=None,
    server: list[tuple[str, str]] | None = None,
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
                                tab, version, history_rows, cited, queue, overview, report, server
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


def version_line(version: RulebookVersion, active: bool = True) -> dmc.Text:
    saved = version.saved_at.strftime("%Y-%m-%d %H:%M")
    # After a stale save the form shows the version the Admin started from, which is not active.
    state = "active" if active else "the version you started from"
    return dmc.Text(
        f"Showing v{version.version_number} ({state}), saved by {version.saved_by} on {saved}: "
        f"{version.change_note}",
        size="sm",
        c=da_styles.MUTED,
    )


def _tab_body(
    tab: str,
    version: RulebookVersion,
    rows=(),
    cited=None,
    queue=None,
    overview=None,
    report=None,
    server=None,
):
    if tab == TAB_OVERVIEW and overview is not None and report is not None:
        return html.Div(overview_view(version, overview, report), id=body_id(TAB_OVERVIEW))
    if tab in EDITABLE_TABS:
        content = tab_content(tab, version, cited=cited, queue=queue, server=server)
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
):
    """One editable tab: notice lines, the view or the form, and the buttons that fit the mode.

    `cited` is {rule_id: count} for the Cited column of the rule tables (read only). `queue` is
    the Unassigned queue data for the Capability catalog tab (see queue_block). `server` is the
    read-only server settings list of the Repository and index tab."""
    if tab == TAB_REPO:
        body = repo_view(version, server, editable, draft, active)
    elif tab in (TAB_UI, TAB_CODING):
        body = rules_view(tab, version, editable, draft, active, cited or {})
    elif tab == TAB_CAPABILITY:
        body = catalog_view(version, editable, draft, active, queue)
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
    return dmc.Stack(
        [
            dmc.TextInput(
                label="Change note (required)",
                id={"type": "adm-field", "tab": tab, "name": NOTE_ID_NAME},
                value="",
            ),
            dmc.Group(
                [
                    dmc.Button("Save", id=act_id(tab, ACTION_SAVE)),
                    dmc.Button("Cancel", id=act_id(tab, ACTION_CANCEL), variant="default"),
                ]
            ),
        ],
        mt="md",
        gap="xs",
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
        parts.append(
            dmc.Button(label, id=act_id(reload_tab, ACTION_RELOAD), size="xs", mt="xs")
        )
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
                widget = dmc.Select(data=kind, value=value or None, id=cell_id, size="xs")
            else:
                widget = dmc.Textarea(
                    value=value, id=cell_id, autosize=True, minRows=1, size="xs"
                )
            cells.append(dmc.TableTd(widget))
        else:
            cells.append(dmc.TableTd(dmc.Text(value, size="sm", style={"whiteSpace": "pre-wrap"})))
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
            *[
                _section(
                    label,
                    list_table(
                        TAB_CHARTER,
                        name,
                        (TEXT_COLUMN,),
                        _text_rows(_draft(draft, name, getattr(charter, name))),
                        editable,
                    ),
                )
                for name, label in CHARTER_LISTS
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


def _charter_size(charter: Charter):
    size = check_charter_size(charter)
    color = {"green": "green", "amber": "yellow", "red": "red"}[size.status]
    return dmc.Badge(
        f"Charter size: {size.characters} characters ({size.percent:.0f}% of the limit)",
        color=color,
        variant="light",
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
GOLDEN_COLUMNS = ("title", "tags", "code", "why")
SEVERITY_CHOICES = ["must_fix", "should_fix", "fyi"]
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
        list_table(
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
    if tab == TAB_CODING:
        parts += _coding_extras(version, editable, draft)
    return html.Div(parts)


def _coding_extras(version: RulebookVersion, editable: bool, draft: dict | None):
    policy = version.rulebook.policy
    golden = _draft(
        draft, "golden_examples", [g.model_dump() for g in version.rulebook.golden_examples]
    )
    return [
        _section(
            "Approved libraries",
            list_table(
                TAB_CODING,
                "approved_libraries",
                (TEXT_COLUMN,),
                _text_rows(_draft(draft, "approved_libraries", policy.approved_libraries)),
                editable,
            ),
        ),
        _section(
            "Blocked imports",
            list_table(
                TAB_CODING,
                "blocked_imports",
                (TEXT_COLUMN,),
                _text_rows(_draft(draft, "blocked_imports", policy.build_blocked_imports)),
                editable,
            ),
        ),
        _section("SonarQube severity map", _sonar_map(policy, editable, draft)),
        _section(
            "Golden examples (stored only, not sent to any AI call yet)",
            list_table(TAB_CODING, "golden_examples", GOLDEN_COLUMNS, golden, editable),
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
            lines.append(dmc.Text(f"{key}: {value}", size="sm"))
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
                                    dmc.TableTd(dmc.Text(row[k], size="xs"))
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
):
    """The catalog table (editable) with the Unassigned queue under it (read view only)."""
    policy = version.rulebook.policy
    rows = _draft(draft, CATALOG_TABLE, capability_rows(policy))
    return html.Div(
        [
            version_line(version, active),
            dmc.Text(CATALOG_HINT, size="xs", c=da_styles.MUTED),
            list_table(
                TAB_CAPABILITY, CATALOG_TABLE, CATALOG_COLUMNS, rows, editable, movable=True
            ),
            queue_block(queue, [c.name for c in policy.capabilities], disabled=editable),
        ]
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
        header = ("Path", "Developer's pick", "Request", "Waiting since", "Would match", "")
        parts.append(
            dmc.Table(
                [
                    dmc.TableThead(dmc.TableTr([dmc.TableTh(h) for h in header])),
                    dmc.TableTbody(
                        [_queue_row(r, capability_names, disabled) for r in rows]
                    ),
                ],
                withTableBorder=True,
            )
        )
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


def _queue_row(row, capability_names: list[str], disabled: bool):
    start = row.would_match or row.picked_capability
    return dmc.TableTr(
        [
            dmc.TableTd(dmc.Text(row.path, size="sm")),
            dmc.TableTd(dmc.Text(row.picked_capability, size="sm")),
            dmc.TableTd(dmc.Text(row.request_id, size="sm")),
            dmc.TableTd(dmc.Text(_waiting_text(row), size="sm")),
            dmc.TableTd(dmc.Text(row.would_match or "(none)", size="sm")),
            dmc.TableTd(
                dmc.Group(
                    [
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
                    ],
                    gap="xs",
                )
            ),
        ]
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
        dmc.Button(
            "Cancel", id=queue_button_id(Q_CANCEL, uid), size="xs", variant="subtle"
        )
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
        ]
    )


# Plain names for the three core limits (spec section 8, "Shown as").
# Advanced limits keep their field names.
NUMBER_LABELS = {
    "build_max_rounds": "Max fix rounds",
    "build_test_timeout_seconds": "Test time limit (seconds)",
    "max_files": "Max files per request",
    "workspace_max_file_kb": "Largest file the scan reads (KB)",
}


def _number_fields(policy: Policy, names: tuple[str, ...], editable: bool, draft: dict | None):
    return dmc.Stack([_number_field(policy, n, editable, draft) for n in names], gap=2)


def _number_field(
    policy: Policy, name: str, editable: bool, draft: dict | None, tab: str = TAB_BUILD
):
    value = str(_draft(draft, name, getattr(policy, name)))
    hint = field_bounds(name)
    label = NUMBER_LABELS.get(name, name)
    if not editable:
        return dmc.Text(f"{label}: {value}" + (f"   (allowed: {hint})" if hint else ""), size="sm")
    return dmc.TextInput(
        label=label,
        description=f"allowed: {hint}" if hint else None,
        value=value,
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
):
    """Read-only server settings, then the four editable fields. `server` is (name, shown value)."""
    policy = version.rulebook.policy
    settings_lines = [
        dmc.Text(f"{name}: {value}", size="sm") for name, value in (server or [])
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
    return html.Div(
        [
            version_line(version, active),
            _section(
                "Server settings (read only; they live in .env, not in the rulebook)",
                dmc.Stack(settings_lines, gap=2),
            ),
            *[
                _section(
                    title,
                    list_table(
                        TAB_REPO,
                        table,
                        (TEXT_COLUMN,),
                        _text_rows(_draft(draft, table, getattr(policy, table))),
                        editable,
                    ),
                )
                for table, title in REPO_LIST_TABLES
            ],
            _section("New file name pattern", pattern_widget),
            _section(
                "Largest file the laptop scan reads",
                _number_field(policy, REPO_SIZE, editable, draft, TAB_REPO),
            ),
        ]
    )


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
    chosen = _draft(draft, "triggers", {t.name: t.on for t in policy.escalation_triggers})
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


# --- Version history ---

HIST_TYPE = "adm-hist"
HIST_PICK_TYPE = "adm-hist-pick"
HIST_COMPARE = "compare"
HIST_RESTORE = "restore"
HIST_CONFIRM = "confirm"
HIST_CANCEL = "cancel"


def hist_id(action: str, version: int = 0) -> dict:
    return {"type": HIST_TYPE, "action": action, "version": version}


def pick_id(name: str) -> dict:
    return {"type": HIST_PICK_TYPE, "name": name}


def history_view(rows, diff=None, restore_target: int | None = None, notice=None):
    """Timeline (newest first), the "what changed" picker and, when asked, the Restore dialog.

    `diff` is (from_number, to_number, RulebookDiff) or None.
    """
    numbers = [str(row.version_number) for row in rows]
    return html.Div(
        [
            *(notice or []),
            *([_restore_dialog(restore_target)] if restore_target else []),
            dmc.Stack([_timeline_row(row) for row in rows], gap="xs"),
            _section("What changed", _compare_picker(numbers, diff)),
        ]
    )


def _timeline_row(row):
    saved = row.saved_at.strftime("%Y-%m-%d %H:%M")
    head = f"v{row.version_number}  {saved}  {row.saved_by}"
    if row.is_active:
        head += "  (active)"
    lines = [dmc.Text(head, fw=600, size="sm"), dmc.Text(row.change_note, size="sm")]
    if row.restored_from is not None:
        lines.append(dmc.Text(f"Restored from v{row.restored_from}", size="xs", c=da_styles.MUTED))
    if row.areas:
        lines.append(dmc.Text("Touched: " + ", ".join(row.areas), size="xs", c=da_styles.MUTED))
    lines.append(_pinned(row))
    if not row.is_active:
        lines.append(
            dmc.Button(
                "Restore",
                id=hist_id(HIST_RESTORE, row.version_number),
                size="xs",
                variant="default",
            )
        )
    return html.Div(lines, style=da_styles.PANEL_SECTION)


def _pinned(row):
    count = row.pinned_count
    if not count:
        return dmc.Text("No requests pinned", size="xs", c=da_styles.MUTED)
    label = f"{count} request{'s' if count != 1 else ''} pinned"
    return dmc.Accordion(
        [
            dmc.AccordionItem(
                [
                    dmc.AccordionControl(label),
                    dmc.AccordionPanel(dmc.Text(", ".join(row.pinned_request_ids), size="xs")),
                ],
                value="pinned",
            )
        ],
        value=None,
    )


def _restore_dialog(number: int):
    return dmc.Alert(
        [
            dmc.Text(f"Restore v{number} as a new version?", size="sm", fw=600),
            dmc.TextInput(
                label="Change note (required)",
                id=pick_id("note"),
                value=f"Restored from v{number}",
            ),
            dmc.Group(
                [
                    dmc.Button("Restore", id=hist_id(HIST_CONFIRM, number), size="xs"),
                    dmc.Button(
                        "Cancel", id=hist_id(HIST_CANCEL, number), size="xs", variant="default"
                    ),
                ],
                mt="xs",
            ),
        ],
        color="blue",
        mb="sm",
    )


def _compare_picker(numbers: list[str], diff):
    # Newest first: the default compares the newest version with the one before it.
    first = numbers[1] if len(numbers) > 1 else (numbers[0] if numbers else None)
    parts: list = [
        dmc.Group(
            [
                dmc.Select(label="From", data=numbers, value=first, id=pick_id("from"), w=100),
                dmc.Select(
                    label="To",
                    data=numbers,
                    value=numbers[0] if numbers else None,
                    id=pick_id("to"),
                    w=100,
                ),
                dmc.Button("Compare", id=hist_id(HIST_COMPARE), size="xs"),
            ],
            align="flex-end",
        )
    ]
    if diff is not None:
        parts.append(_diff_lines(*diff))
    return html.Div(parts)


def _diff_lines(old_number: int, new_number: int, diff):
    title = dmc.Text(f"What changed v{old_number} to v{new_number}", size="sm", fw=600, mt="sm")
    if diff.is_empty:
        return html.Div([title, dmc.Text("No changes.", size="sm")])
    lines: list = [title]
    for path, value in diff.added.items():
        lines.append(dmc.Text(f"+ {path}: {value}", size="xs"))
    for path, value in diff.removed.items():
        lines.append(dmc.Text(f"- {path}: {value}", size="xs"))
    for path, (old, new) in diff.changed.items():
        lines.append(dmc.Text(f"~ {path}: {old} -> {new}", size="xs"))
        for line in text_line_diff(old, new):
            lines.append(dmc.Text(line, size="xs", style={"whiteSpace": "pre-wrap"}))
    return html.Div(lines)


def _section(title: str, body):
    return html.Div(
        [dmc.Text(title, fw=600, c=da_styles.NAVY, size="sm"), body], style=da_styles.PANEL_SECTION
    )


# --- Overview (Phase 11c): rulebook areas, Needs attention, health numbers. Read only. ---

HEALTH_ID = "adm-health"
WINDOW_ID = "adm-window"
GOTO_TYPE = "adm-goto"
STATUS_COLORS = {"green": "green", "amber": "yellow", "red": "red"}


def goto_id(tab: str, n: int) -> dict:
    # n keeps every id unique; the callback reads only "tab" from the clicked button.
    return {"type": GOTO_TYPE, "tab": tab, "n": n}


def _tab_of_area(area: str) -> str:
    return next(tab for tab, label, _ in ADMIN_TABS if label == area)


def overview_view(version: RulebookVersion, overview, report, active: bool = True):
    """The Overview tab. `overview` is an Overview (da_admin_overview), `report` a HealthReport."""
    return html.Div(
        [
            version_line(version, active),
            _section("Rulebook areas", _areas_table(overview.areas)),
            _section("Needs attention", _attention_list(overview.attention)),
            _section("Health numbers", health_block(report)),
        ]
    )


def _areas_table(areas):
    head = dmc.TableThead(
        dmc.TableTr([dmc.TableTh(name) for name in ("Area", "Summary", "Status", "Last changed")])
    )
    rows = [
        dmc.TableTr(
            [
                dmc.TableTd(
                    dmc.Button(
                        row.area,
                        id=goto_id(_tab_of_area(row.area), 1000 + index),
                        variant="subtle",
                        size="xs",
                    )
                ),
                dmc.TableTd(row.summary),
                dmc.TableTd(dmc.Badge(row.status, color=STATUS_COLORS.get(row.status, "gray"))),
                dmc.TableTd(row.last_changed),
            ]
        )
        for index, row in enumerate(areas)
    ]
    return dmc.Table([head, dmc.TableTbody(rows)])


def _attention_list(items):
    if not items:
        return dmc.Text("Nothing needs attention.", size="sm", c=da_styles.MUTED)
    return dmc.Stack(
        [
            dmc.Group(
                [
                    dmc.Badge(item.level, color="red" if item.level == "red" else "yellow"),
                    dmc.Text(item.text, size="sm"),
                    dmc.Button(
                        f"Open {item.area}",
                        id=goto_id(_tab_of_area(item.area), index),
                        variant="subtle",
                        size="xs",
                    ),
                ]
            )
            for index, item in enumerate(items)
        ],
        gap="xs",
    )


def health_block(report, window: str = WINDOW_ALL):
    """The window chooser plus the numbers. The chooser re-draws only the part inside adm-health."""
    return html.Div(
        [
            dmc.SegmentedControl(
                id=WINDOW_ID,
                value=window,
                data=[{"value": key, "label": label} for key, label in WINDOW_LABELS.items()],
            ),
            html.Div(health_numbers(report), id=HEALTH_ID),
        ]
    )


def health_numbers(report):
    lines = []
    for metric in report.all_metrics:
        parts = [dmc.Text(f"{metric.label}: {metric.text}", size="sm")]
        if metric.items:
            shown = ", ".join(f"{name} {count}" for name, count in metric.items)
            parts.append(dmc.Text(shown, size="xs", c=da_styles.MUTED))
        if metric.note:
            parts.append(dmc.Text(metric.note, size="xs", c=da_styles.MUTED))
        lines.append(html.Div(parts))
    return dmc.Stack(lines, gap="xs")
