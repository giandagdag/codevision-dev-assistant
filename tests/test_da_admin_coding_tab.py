"""Fix 11-1, L3 (step 21): Coding standards read view: rule list left, rule card right."""

import pytest
from dash import no_update
from dash.exceptions import PreventUpdate

from callbacks.screen_callbacks.da_admin_page_callbacks import (
    codes_for_modules,
    open_coding_edit,
    pick_rule,
)
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


# --- Step 22 (L3b): golden Change button, module picker, library chips ---


def badges(content):
    return [c for c in walk(content) if type(c).__name__ == "Badge"]


def test_read_view_shows_one_change_button_per_golden_card_and_chips(published_rulebook):
    view = tab_content(TAB_CODING, published_rulebook)

    buttons = [
        c
        for c in walk(view)
        if isinstance(getattr(c, "id", None), dict) and c.id.get("type") == "adm-golden-change"
    ]
    assert len(buttons) == len(published_rulebook.rulebook.golden_examples) > 0
    policy = published_rulebook.rulebook.policy
    chip_text = [b.children for b in badges(view)]
    assert set(policy.approved_libraries) <= set(chip_text)
    red = [b for b in badges(view) if b.children in policy.build_blocked_imports]
    assert red and all(b.style["color"] == "#B42318" for b in red)
    # The libraries are chips now, not table cells.
    assert not [
        c for c in walk(view) if getattr(c, "id", None) and "approved_libraries" in str(c.id)
    ]


def test_edit_view_keeps_the_library_tables_and_has_a_module_picker(published_rulebook):
    view = tab_content(TAB_CODING, published_rulebook, editable=True, modules=["a/x.py"])

    cells = [c for c in walk(view) if isinstance(getattr(c, "id", None), dict)]
    assert any(c.id.get("table") == "approved_libraries" for c in cells)
    picker = next(
        c
        for c in cells
        if c.id.get("table") == "golden_examples" and c.id.get("col") == "module_path"
    )
    assert type(picker).__name__ == "Select" and "a/x.py" in picker.data


def test_change_button_opens_the_coding_tab_in_edit_mode(make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)

    content = open_coding_edit(settings)

    assert "Editing Coding standards" in all_text(content)
    with pytest.raises(PreventUpdate):
        open_coding_edit(make_settings(admin_ids=(ADMIN,), developer_id="dev-0002"))


def test_picking_a_module_fills_only_a_blank_code_box(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    (tmp_path / "m.py").write_text("\n".join(f"line {i}" for i in range(30)), encoding="utf-8")
    monkeypatch.setattr("layouts.da_admin_coding_tab.scope_folder", lambda _scope: tmp_path)
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)

    out = codes_for_modules(settings, ["m.py", "m.py", "", "gone.py"], ["", "keep me", "", ""])

    assert out[0].splitlines() == [f"line {i}" for i in range(12)]
    assert out[1] is no_update and out[2] is no_update
    assert out[3] == ""  # unreadable module: blank, not an error


def test_read_view_puts_each_area_in_its_own_window(published_rulebook):
    """Gian, 17 Nov: "a window for each section" instead of one dump on the white canvas."""
    view = tab_content(TAB_CODING, published_rulebook)

    windows = [c for c in walk(view) if getattr(c, "className", None) == "da-admin-card"]
    titles = [all_text(w.children[0]) for w in windows]
    for wanted in ("Judgement rules", "Golden examples", "Libraries", "Automatic checks",
                   "SonarQube severity map"):
        assert any(wanted in t for t in titles), wanted
    # Every row uses the same 2/3 and 1/3 split, so the window edges line up (17 Nov).
    rows = [
        c for c in walk(view)
        if isinstance(getattr(c, "style", None), dict) and c.style.get("display") == "grid"
    ]
    assert len(rows) == 2  # rules row, golden row; the SonarQube table is full width below
    assert {r.style["gridTemplateColumns"] for r in rows} == {"minmax(0, 2fr) minmax(0, 1fr)"}
    right_of_golden = all_text(rows[1].children[1])
    assert "Libraries" in right_of_golden and "SonarQube severity map" in right_of_golden
    assert "Judgement rules" in all_text(rows[0].children[0])
    assert "Rule card" in all_text(rows[0].children[1])
