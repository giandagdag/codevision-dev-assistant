"""Fix 11-1, L3 (step 21): Coding standards read view: rule list left, rule card right."""

import pytest
from dash.exceptions import PreventUpdate

from callbacks.screen_callbacks.da_admin_page_callbacks import pick_rule
from layouts.da_admin_page import TAB_CODING, tab_content
from tests.test_da_admin_page import all_text, walk

ADMIN = "admin-0001"


def judgement_rules(version):
    return [r for r in version.rulebook.rules if r.kind == "judgement"]


def panel_of(content):
    return next(c for c in walk(content) if getattr(c, "id", None) == "adm-rule-panel")


def test_read_view_has_the_list_on_the_left_and_the_first_rules_card_on_the_right(
    published_rulebook,
):
    rules = judgement_rules(published_rulebook)
    first = rules[0]

    grid = panel_of(tab_content(TAB_CODING, published_rulebook)).children
    left, right = grid.children

    assert "2fr" in grid.style["gridTemplateColumns"]
    left_text, right_text = all_text(left), all_text(right)
    assert all(r.rule_id in left_text for r in rules)
    assert first.why in right_text and "Checked by" in right_text
    assert rules[1].why not in right_text  # only the selected rule has a card
    assert not [c for c in walk(grid) if type(c).__name__ == "Accordion"]


def test_clicking_a_row_shows_that_rules_card(make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    rules = judgement_rules(published_rulebook)

    grid = pick_rule(settings, rules[1].rule_id)

    left, right = grid.children
    assert rules[1].why in all_text(right) and rules[0].why not in all_text(right)
    ids = [c.id["rule"] for c in walk(left) if isinstance(getattr(c, "id", None), dict)]
    assert ids == [r.rule_id for r in rules]


def test_a_non_admin_cannot_pick_a_rule(make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id="dev-0002")

    with pytest.raises(PreventUpdate):
        pick_rule(settings, judgement_rules(published_rulebook)[0].rule_id)


def test_the_edit_view_keeps_the_rule_table(published_rulebook):
    view = tab_content(TAB_CODING, published_rulebook, editable=True)

    cells = [c for c in walk(view) if isinstance(getattr(c, "id", None), dict)]
    assert any(c.id.get("type") == "adm-cell" and c.id.get("table") == "rules" for c in cells)
    assert not [c for c in walk(view) if getattr(c, "id", None) == "adm-rule-panel"]
