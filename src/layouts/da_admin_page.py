"""What is on the Admin console screen (Phase 11a): the 8 tabs and the read views.

Presentation only (rule R12), like a display file (DDS) in RPG: it says where each field goes, not
what it means. Rules about what is allowed live in the Phase 1 models and in
agents/da_admin_forms.py.
"""

import dash_mantine_components as dmc
from dash import html

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


def admin_page(version: RulebookVersion) -> html.Div:
    """The console: 8 tabs, Overview first. 11b and 11c tabs show a plain "comes later" line."""
    return html.Div(
        [
            dmc.Title("Admin console", order=3, c=da_styles.NAVY),
            dmc.Tabs(
                [
                    dmc.TabsList([dmc.TabsTab(label, value=tab) for tab, label, _ in ADMIN_TABS]),
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
    if tab == TAB_CHARTER:
        return charter_view(version)
    if tab == TAB_BUILD:
        return build_view(version)
    if tab == TAB_HISTORY:
        return dmc.Text("Version history loads here.", c=da_styles.MUTED)
    phase = next(built for name, _, built in ADMIN_TABS if name == tab)
    return dmc.Text(f"Comes in {phase}.", c=da_styles.MUTED)


# --- Shared list table (zones, protected files, glossary, charter lists; 11b reuses it) ---


def list_table(table_id: str, columns: tuple[str, ...], rows: list[dict], editable: bool):
    """A table drawn from column names. Read mode is plain text; edit mode adds Add row and Remove.

    Edit cells carry pattern-matching ids {"type": "<table_id>-cell", "row": i, "col": name} so the
    callbacks can read them back.
    """
    head = dmc.TableThead(
        dmc.TableTr([dmc.TableTh(col.replace("_", " ").capitalize()) for col in columns])
    )
    body = dmc.TableTbody(
        [_table_row(table_id, columns, i, row, editable) for i, row in enumerate(rows)]
    )
    parts: list = [dmc.Table([head, body], withTableBorder=True, withColumnBorders=True)]
    if not rows:
        parts.append(dmc.Text("Nothing here yet.", style=da_styles.EMPTY_TEXT))
    if editable:
        parts.append(
            dmc.Button(
                "Add row",
                id={"type": f"{table_id}-add", "index": 0},
                variant="default",
                size="xs",
                mt="xs",
            )
        )
    return html.Div(parts, id=f"{table_id}-table")


def _table_row(table_id, columns, index, row, editable):
    cells = []
    for col in columns:
        value = _cell_text(row.get(col, ""))
        if editable:
            cells.append(
                dmc.TableTd(
                    dmc.Textarea(
                        value=value,
                        id={"type": f"{table_id}-cell", "row": index, "col": col},
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
                    id={"type": f"{table_id}-remove", "index": index},
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


# --- Project charter ---


def charter_view(version: RulebookVersion, editable: bool = False):
    charter = version.rulebook.charter
    return html.Div(
        [
            version_line(version),
            _charter_size(charter),
            _section("Purpose", dmc.Text(charter.purpose, size="sm")),
            *[
                _section(label, _text_list(name, getattr(charter, name), editable))
                for name, label in CHARTER_LISTS
            ],
            _section(
                "Glossary",
                list_table(
                    "charter-glossary",
                    GLOSSARY_COLUMNS,
                    [entry.model_dump() for entry in charter.glossary],
                    editable,
                ),
            ),
        ]
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


def _text_list(name: str, items: list[str], editable: bool):
    rows = [{"text": item} for item in items]
    return list_table(f"charter-{name}", ("text",), rows, editable)


# --- Build and test ---


def build_view(version: RulebookVersion, editable: bool = False):
    policy = version.rulebook.policy
    return html.Div(
        [
            version_line(version),
            _section("Limits", _number_fields(policy, CORE_BUILD_FIELDS)),
            dmc.Accordion(
                [
                    dmc.AccordionItem(
                        [
                            dmc.AccordionControl("Advanced limits"),
                            dmc.AccordionPanel(_number_fields(policy, ADVANCED_LIMIT_FIELDS)),
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
                        _labelled("Generator model", policy.generator_model or "(use .env)"),
                        _labelled("Tester model", policy.tester_model or "(use .env)"),
                    ],
                    gap=2,
                ),
            ),
            _section("Escalation triggers", _triggers(policy)),
            _section(
                "Flag-for-review zones",
                list_table(
                    "build-zones",
                    ZONE_COLUMNS,
                    [zone.model_dump() for zone in policy.flag_review_zones],
                    editable,
                ),
            ),
            _section(
                "Protected files",
                list_table(
                    "build-protected",
                    ("pattern",),
                    [{"pattern": item} for item in policy.protected_files],
                    editable,
                ),
            ),
        ]
    )


def _number_fields(policy: Policy, names: tuple[str, ...]):
    return dmc.Stack(
        [_labelled(name, str(getattr(policy, name)), field_bounds(name)) for name in names], gap=2
    )


def _labelled(label: str, value: str, hint: str = ""):
    text = f"{label}: {value}" + (f"   (allowed: {hint})" if hint else "")
    return dmc.Text(text, size="sm")


def _triggers(policy: Policy):
    return dmc.Stack(
        [
            dmc.Switch(
                label=TRIGGER_LABELS.get(trigger.name, trigger.name),
                checked=trigger.on,
                disabled=True,
                id={"type": "build-trigger", "name": trigger.name},
            )
            for trigger in policy.escalation_triggers
        ],
        gap=4,
    )


def _section(title: str, body):
    return html.Div(
        [dmc.Text(title, fw=600, c=da_styles.NAVY, size="sm"), body], style=da_styles.PANEL_SECTION
    )
