"""Coding standards, read view (fix 11-1, L3): rule list on the left 2/3, the rule card of the
selected row on the right 1/3. Click a row to see its card. Imports da_admin_common only."""

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_cited import FIRES_AMBER_ABOVE
from agents.da_admin_forms import rule_counter_text
from agents.da_admin_modules import scope_folder
from layouts.da_admin_card import admin_card, card_grid
from layouts.da_admin_common import word_chips
from layouts.da_admin_ui_standards import fires_text, severity_pill
from styles import da_admin_styles as pal
from styles import da_styles

GOLDEN_CHANGE_TYPE = "adm-golden-change"
RULE_PICK_TYPE = "adm-rule-pick"
RULE_PANEL_ID = "adm-rule-panel"


def rule_pick_id(rule_id: str) -> dict:
    return {"type": RULE_PICK_TYPE, "rule": rule_id}


def _fact_row(label: str, value: str):
    """Good and Bad examples are code: a green or red box, so names inside are not field names."""
    if label in ("Good", "Bad"):
        colour = pal.GREEN_LIGHT if label == "Good" else pal.RED_LIGHT
        body = dmc.Code(value, block=True, style={"background": colour, "whiteSpace": "pre-wrap"})
    else:
        body = dmc.Text(value, size="sm")
    return dmc.Stack([dmc.Text(label, fw=600, size="xs", c=pal.NAVY), body], gap=0)


def rule_card(rule: dict | None, fires: dict[str, int]):
    """The card for one judgement rule (AF-14): why, tags, checker, source, fires, examples."""
    if rule is None:
        return admin_card("Rule card", dmc.Text("No rule selected.", size="sm"), "📄")
    rid = rule["rule_id"]
    facts = [
        ("Why", rule["why"]),
        ("Tags", ", ".join(rule["tags"])),
        ("Checked by", "Tester (a model reads the code against this rule)"),
        ("Source", rule["source"]),
        ("Fires in", fires_text(rid, fires)),
        ("Cited", str(rule.get("cited", 0))),  # kept Tester findings that name this rule
        ("Good", rule["good_example"]),
        ("Bad", rule["bad_example"]),
    ]
    head = dmc.Group(
        [
            dmc.Code(rid),
            dmc.Text(rule["title"], fw=700, size="sm"),
            severity_pill(rule["severity"]),
        ],
        gap="xs",
    )
    # The short facts sit two per line so the card is not much taller than the rule list.
    short = [_fact_row(k, v) for k, v in facts if k not in ("Why", "Good", "Bad")]
    long = {k: _fact_row(k, v) for k, v in facts if k in ("Why", "Good", "Bad")}
    body = dmc.Stack(
        [head, long["Why"], dmc.SimpleGrid(short, cols=2, spacing="xs", verticalSpacing="xs"),
         long["Good"], long["Bad"]],
        gap="xs",
    )
    return admin_card("Rule card", body, "📄")


def rule_list(rules: list[dict], fires: dict[str, int], selected: str):
    """One clickable row per rule: ID, title, severity pill, fires-in pill (amber over 50%)."""
    rows = []
    for r in rules:
        rid = r["rule_id"]
        amber = fires.get(rid, 0) > FIRES_AMBER_ABOVE
        chosen = rid == selected
        rows.append(
            dmc.UnstyledButton(
                dmc.Group(
                    [
                        dmc.Code(rid),
                        dmc.Text(r["title"], size="sm", fw=600 if chosen else 400),
                        severity_pill(r["severity"]),
                        dmc.Badge(
                            fires_text(rid, fires),
                            variant="light",
                            style=pal.pill_style("amber" if amber else "green"),
                        ),
                    ],
                    gap="xs",
                ),
                id=rule_pick_id(rid),
                w="100%",
                p="xs",
                style={
                    "borderRadius": 6,
                    "background": pal.BLUE_LIGHT if chosen else "transparent",
                    "border": f"1px solid {pal.BLUE if chosen else 'transparent'}",
                },
            )
        )
    return dmc.Stack(rows, gap=2)


def rule_panel(rules: list[dict], fires: dict[str, int], selected: str | None = None):
    """The two columns. `selected` defaults to the first rule; a click redraws them both."""
    chosen = next((r for r in rules if r["rule_id"] == selected), rules[0] if rules else None)
    left = admin_card(
        f"Judgement rules: {rule_counter_text('judgement', len(rules))}",
        rule_list(rules, fires, chosen["rule_id"] if chosen else ""),
        "⚖️",
    )
    return card_grid([left], [rule_card(chosen, fires)])


def library_chips(words: list[str], blocked: bool = False):
    """Approved libraries as grey chips, blocked imports as red chips (read view)."""
    return word_chips(words, pal.pill_style("red") if blocked else None)


def golden_cards(examples: list[dict]):
    """Read view: one card per example, with its program type, module, the code and a Change
    button (it opens the edit form, where the module is picked from the index)."""
    if not examples:
        return dmc.Text("No golden examples yet.", style=da_styles.EMPTY_TEXT)
    cards = []
    for i, g in enumerate(examples):
        head = [
            dmc.Text(g["title"], fw=600, size="sm"),
            dmc.Badge(g["program_type"], variant="light"),
        ]
        if g.get("module_path"):
            head.append(dmc.Badge(g["module_path"], variant="outline", tt="none"))
        head.append(
            dmc.Button(
                "Change",
                id={"type": GOLDEN_CHANGE_TYPE, "n": i},
                size="compact-xs",
                variant="default",
            )
        )
        cards.append(
            html.Div(
                [
                    dmc.Group(head, gap="xs"),
                    dmc.Text(g["why"], size="xs", c=da_styles.MUTED),
                    dmc.Code("\n".join(g["code"].splitlines()[:12]), block=True),
                ],
                style=da_styles.PANEL_SECTION,
            )
        )
    return dmc.Stack(cards, gap="xs")


def module_start(path: str, folder_scope: str = "", lines: int = 12) -> str:
    """The first lines of an indexed module, for a golden example's code (empty if unreadable)."""
    try:
        text = (scope_folder(folder_scope) / path).read_text(encoding="utf-8")
    except OSError, ValueError:
        return ""
    return "\n".join(text.splitlines()[:lines])


def rule_panel_div(rules: list[dict], fires: dict[str, int], selected: str | None = None):
    return html.Div(rule_panel(rules, fires, selected), id=RULE_PANEL_ID)
