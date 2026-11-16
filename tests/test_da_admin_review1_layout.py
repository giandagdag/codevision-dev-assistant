"""Code review round 1 (Must fix 2 and 4): Build and test cards in two columns; Coding standards
has its lower panels side by side with an Automatic checks panel. No browser."""

from layouts.da_admin_page import TAB_CODING, build_view, rules_view
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


def test_coding_edit_view_stays_one_column_of_forms(published_rulebook):
    shown = rules_view(TAB_CODING, published_rulebook, editable=True)

    assert not grids(shown)
    assert "Automatic checks (SonarQube)" not in all_text(shown)
