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
from agents.da_admin_forms import ADVANCED_LIMIT_FIELDS, CORE_BUILD_FIELDS, field_bounds
from pydantic_classes.da_rulebook_models import (
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
EDITABLE_TABS = (TAB_CHARTER, TAB_BUILD)

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


def admin_page(version: RulebookVersion, history_rows=()) -> html.Div:
    """The console: 8 tabs, Overview first. 11b and 11c tabs show a plain "comes later" line."""
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
                            _tab_body(tab, version, history_rows), value=tab, pt="md"
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


def _tab_body(tab: str, version: RulebookVersion, rows=()):
    if tab in EDITABLE_TABS:
        return html.Div(tab_content(tab, version), id=body_id(tab))
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
):
    """One editable tab: notice lines, the view or the form, and the buttons that fit the mode."""
    view = charter_view if tab == TAB_CHARTER else build_view
    return html.Div(
        [
            *(notice or []),
            view(version, editable, draft, active),
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


def list_table(
    tab: str, table_id: str, columns: tuple[str, ...], rows: list[dict], editable: bool
):
    """A table drawn from column names. Read mode is plain text; edit mode adds Add row and Remove.

    Edit cells carry pattern-matching ids so the callbacks can read them back.
    """
    head = dmc.TableThead(
        dmc.TableTr([dmc.TableTh(col.replace("_", " ").capitalize()) for col in columns])
    )
    body = dmc.TableTbody(
        [_table_row(tab, table_id, columns, i, row, editable) for i, row in enumerate(rows)]
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


def _table_row(tab, table_id, columns, index, row, editable):
    cells = []
    for col in columns:
        value = _cell_text(row.get(col, ""))
        if editable:
            cells.append(
                dmc.TableTd(
                    dmc.Textarea(
                        value=value,
                        id={
                            "type": "adm-cell",
                            "tab": tab,
                            "table": table_id,
                            "row": index,
                            "col": col,
                        },
                        autosize=True,
                        minRows=1,
                        size="xs",
                    )
                )
            )
        else:
            cells.append(dmc.TableTd(dmc.Text(value, size="sm", style={"whiteSpace": "pre-wrap"})))
    if editable:
        cells.append(
            dmc.TableTd(
                dmc.Button(
                    "Remove",
                    id={"type": "adm-remove", "tab": tab, "table": table_id, "index": index},
                    variant="subtle",
                    color="red",
                    size="xs",
                )
            )
        )
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
}


def _number_fields(policy: Policy, names: tuple[str, ...], editable: bool, draft: dict | None):
    return dmc.Stack([_number_field(policy, n, editable, draft) for n in names], gap=2)


def _number_field(policy: Policy, name: str, editable: bool, draft: dict | None):
    value = str(_draft(draft, name, getattr(policy, name)))
    hint = field_bounds(name)
    label = NUMBER_LABELS.get(name, name)
    if not editable:
        return dmc.Text(f"{label}: {value}" + (f"   (allowed: {hint})" if hint else ""), size="sm")
    return dmc.TextInput(
        label=label,
        description=f"allowed: {hint}" if hint else None,
        value=value,
        id={"type": "adm-field", "tab": TAB_BUILD, "name": name},
        size="xs",
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
