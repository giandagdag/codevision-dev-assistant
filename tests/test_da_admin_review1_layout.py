"""Code review round 1 (Must fix 2 and 4): Build and test cards in two columns; Coding standards
has its lower panels side by side with an Automatic checks panel. No browser."""

from layouts.da_admin_page import (
    ACTION_EDIT,
    TAB_BUILD,
    TAB_CAPABILITY,
    TAB_CODING,
    act_id,
    build_view,
    rules_view,
    tab_content,
)
from tests.test_da_admin_page import all_text, walk


def grids(content):
    styled = [n for n in walk(content) if getattr(n, "style", None)]
    return [n for n in styled if "gridTemplateColumns" in n.style]


def test_build_read_view_is_a_two_column_grid_of_cards(published_rulebook):
    simple = [n for n in walk(build_view(published_rulebook)) if type(n).__name__ == "SimpleGrid"]

    assert len(simple) == 1 and simple[0].cols == 2
    assert len(simple[0].children) == 7  # Limits, Model, Triggers, Zones, Protected, Tests, Handoff


def test_build_edit_view_has_no_grid(published_rulebook):
    shown = build_view(published_rulebook, editable=True)

    assert not [n for n in walk(shown) if type(n).__name__ == "SimpleGrid"]


def test_coding_read_view_has_automatic_checks_beside_the_severity_map(published_rulebook):
    shown = rules_view(TAB_CODING, published_rulebook)

    text = all_text(shown)
    # rule list + card, golden examples + libraries, automatic checks + severity map
    assert len(grids(shown)) == 3
    assert "Automatic checks (SonarQube)" in text and "Governed in SonarQube" in text
    assert "SonarQube severity map" in text


def test_catalog_seniors_have_an_initials_circle_and_the_full_name(published_rulebook):
    shown = tab_content(TAB_CAPABILITY, published_rulebook, modules=[])

    avatars = [n for n in walk(shown) if type(n).__name__ == "Avatar"]
    assert avatars and all(a.children == "LC" for a in avatars[:1])  # "Limits capability lead"
    assert "Limits capability lead" in all_text(shown)


def test_edit_button_comes_before_the_tab_body_in_the_read_view(published_rulebook):
    for tab in (TAB_BUILD, TAB_CODING, TAB_CAPABILITY):
        shown = tab_content(tab, published_rulebook, modules=[])

        first = shown.children[0]
        assert first.style["float"] == "right"
        assert first.children.id == act_id(tab, ACTION_EDIT)


def test_coding_edit_view_stays_one_column_of_forms(published_rulebook):
    shown = rules_view(TAB_CODING, published_rulebook, editable=True)

    assert not grids(shown)
    assert "Automatic checks (SonarQube)" not in all_text(shown)


def test_round2_zones_are_cards_in_the_read_view_and_a_table_in_edit(published_rulebook):
    zones = published_rulebook.rulebook.policy.flag_review_zones
    read = [n for n in walk(build_view(published_rulebook)) if type(n).__name__ == "Paper"]
    zone_cards = [n for n in read if any(z.name in all_text(n) for z in zones)]
    assert len(zone_cards) >= len(zones) > 0
    edit = build_view(published_rulebook, editable=True)
    assert [n for n in walk(edit) if type(n).__name__ == "Table"]


def test_round2_ui_read_view_has_no_second_rules_table(published_rulebook):
    from layouts.da_admin_page import TAB_UI

    shown = rules_view(TAB_UI, published_rulebook)

    add_id = {"type": "adm-add", "tab": TAB_UI, "table": "rules", "index": 0}
    assert not [n for n in walk(shown) if getattr(n, "id", None) == add_id]
    assert "UI rules" in all_text(shown)


def test_round2_catalog_search_finds_a_senior_by_name():
    from agents.da_admin_modules import matches_search

    assert matches_search("Limits", "x", [], "alice", ("Alice Tan", ""))
    assert not matches_search("Limits", "x", [], "bob", ("Alice Tan", ""))
