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


def admin_page(version: RulebookVersion) -> html.Div:
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
                        dmc.TabsPanel(_tab_body(tab, version), value=tab, pt="md")
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


def version_line(version: RulebookVersion) -> dmc.Text:
    saved = version.saved_at.strftime("%Y-%m-%d %H:%M")
    return dmc.Text(
        f"Showing v{version.version_number} (active), saved by {version.saved_by} on {saved}: "
        f"{version.change_note}",
        size="sm",
        c=da_styles.MUTED,
    )


def _tab_body(tab: str, version: RulebookVersion):
    if tab in EDITABLE_TABS:
        return html.Div(tab_content(tab, version), id=body_id(tab))
    if tab == TAB_HISTORY:
        return dmc.Text("Version history loads here.", c=da_styles.MUTED)
    phase = next(built for name, _, built in ADMIN_TABS if name == tab)
    return dmc.Text(f"Comes in {phase}.", c=da_styles.MUTED)


def tab_content(
    tab: str,
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    notice: list | None = None,
):
    """One editable tab: notice lines, the view or the form, and the buttons that fit the mode."""
    view = charter_view if tab == TAB_CHARTER else build_view
    return html.Div(
        [
            *(notice or []),
            view(version, editable, draft),
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


def message_notice(message: str, color: str = "yellow", reload_tab: str | None = None):
    parts: list = [dmc.Text(message, size="sm")]
    if reload_tab:
        parts.append(
            dmc.Button("Reload", id=act_id(reload_tab, ACTION_RELOAD), size="xs", mt="xs")
        )
    return dmc.Alert(parts, color=color, mb="sm")


def saved_notice(version_number: int, warnings: list[str]):
    parts = [dmc.Text(f"Saved as v{version_number}", size="sm", fw=600)]
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


def charter_view(version: RulebookVersion, editable: bool = False, draft: dict | None = None):
    charter = version.rulebook.charter
    purpose = _draft(draft, "purpose", charter.purpose)
    return html.Div(
        [
            version_line(version),
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


def build_view(version: RulebookVersion, editable: bool = False, draft: dict | None = None):
    policy = version.rulebook.policy
    return html.Div(
        [
            version_line(version),
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


def _number_fields(policy: Policy, names: tuple[str, ...], editable: bool, draft: dict | None):
    return dmc.Stack([_number_field(policy, n, editable, draft) for n in names], gap=2)


def _number_field(policy: Policy, name: str, editable: bool, draft: dict | None):
    value = str(_draft(draft, name, getattr(policy, name)))
    hint = field_bounds(name)
    if not editable:
        return dmc.Text(f"{name}: {value}" + (f"   (allowed: {hint})" if hint else ""), size="sm")
    return dmc.TextInput(
        label=name,
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


def _section(title: str, body):
    return html.Div(
        [dmc.Text(title, fw=600, c=da_styles.NAVY, size="sm"), body], style=da_styles.PANEL_SECTION
    )
