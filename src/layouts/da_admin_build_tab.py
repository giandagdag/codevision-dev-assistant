"""Build and test tab: limits, model per role, triggers, zones, protected files."""

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_forms import (
    ADVANCED_LIMIT_FIELDS,
    CORE_BUILD_FIELDS,
    LOCK_CHAT_SWITCH,
    field_bounds,
)
from agents.da_admin_labels import label as field_label
from layouts.da_admin_common import (
    TAB_BUILD,
    TEXT_COLUMN,
    _draft,
    _text_rows,
    list_table,
    version_pill,
    word_chips,
)
from layouts.da_admin_common import section as _section
from pydantic_classes.da_rulebook_models import Policy, RulebookVersion
from styles import da_styles

TRIGGER_LABELS = {
    "cap_hit_twice": "Cap hit twice in a row",
    "out_of_scope": "Out of scope",
    "dispute": "Dispute",
    "tester_unable_twice": "Tester unable twice",
    "get_help": "Get help",
    "escalation_lock_chat": "Lock the developer's chat during an escalation",  # Phase 10
}

ZONE_COLUMNS = ("name", "description", "examples", "path_patterns")


# --- Build and test ---


def build_view(
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
):
    policy = version.rulebook.policy
    limits = dmc.Stack(
        [
            _number_fields(policy, CORE_BUILD_FIELDS, editable, draft),
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
        ],
        gap="xs",
    )
    cards = [
        _section("Limits", limits),
        *[
            _section(
                "Model per role",
                dmc.Stack(
                    [
                        _model_field(policy, "generator_model", "Generator model", editable, draft),
                        _model_field(policy, "tester_model", "Tester model", editable, draft),
                        _model_field(policy, "tagger_model", "Program tagger", editable, draft),
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
                    True,
                )
                if editable
                else _zone_cards(policy.flag_review_zones),
            ),
            _section(
                "Protected files",
                list_table(  # edit keeps the table; the read view is chips, as in the demo
                    TAB_BUILD,
                    "protected_files",
                    (TEXT_COLUMN,),
                    _text_rows(_draft(draft, "protected_files", policy.protected_files)),
                    True,
                )
                if editable
                else word_chips(policy.protected_files, variant="outline"),
            ),
            _section("Tests", _tests_card()),
            _section("Can a request be handed off?", _severity_table()),
        ],
    ]
    # Read view: cards in two equal columns, as in the demo. Edit keeps one column of forms.
    body = html.Div(cards) if editable else dmc.SimpleGrid(cards, cols=2, spacing="md")
    return html.Div([version_pill(version, active), body])


def _zone_cards(zones):
    """Read view: one card per zone, the name as a pill, then description, examples, patterns."""
    if not zones:
        return dmc.Text("Nothing here yet.", style=da_styles.EMPTY_TEXT)
    return dmc.Stack(
        [
            dmc.Paper(
                [
                    dmc.Badge(z.name, variant="light", tt="none"),
                    dmc.Text(z.description, size="sm", mt=4),
                    word_chips(list(z.examples), variant="outline"),
                    word_chips(list(z.path_patterns), variant="outline"),
                ],
                withBorder=True,
                p="xs",
            )
            for z in zones
        ],
        gap="xs",
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
