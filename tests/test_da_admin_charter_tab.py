"""Fix 11-1 step 7: Project charter tab (two boxes side by side, size meter colours)."""

import pytest

from layouts.da_admin_page import _charter_size, charter_view
from styles import da_admin_styles as colours
from tests.test_da_admin_page import all_text, walk
from tests.test_da_rulebook_models import charter_of_length


@pytest.mark.parametrize(
    ("characters", "colour"),
    [
        (4740, colours.GREEN),  # 79%
        (4800, colours.AMBER),  # 80%
        (6000, colours.AMBER),  # 100%
        (6060, colours.RED),  # 101%
    ],
)
def test_size_meter_colour_at_the_boundaries(characters, colour):
    meter = _charter_size(charter_of_length(characters))

    bar = next(c for c in walk(meter) if type(c).__name__ == "Progress")
    badge = next(c for c in walk(meter) if type(c).__name__ == "Badge")
    assert bar.color == colour
    assert badge.style["color"] == colour


def test_charter_rows_purpose_two_pairs_glossary(published_rulebook):
    from layouts.da_admin_card import is_card

    purpose, pair1, pair2, glossary = charter_view(published_rulebook).children

    assert is_card(purpose) and is_card(glossary)
    assert all(is_card(c) for c in pair1.children + pair2.children)
    titles = [[c.children[0].children[0].children for c in p.children] for p in (pair1, pair2)]
    assert titles == [["In scope", "Out of scope"], ["Architecture principles", "Constraints"]]


def test_charter_lists_are_rows_without_a_text_header(published_rulebook):
    text = all_text(charter_view(published_rulebook))
    edit = all_text(charter_view(published_rulebook, editable=True))

    assert "✓" in text and "●" in text
    assert "Text" not in text.split() and "Text" not in edit.split()
    assert "Add row" in edit and "Remove" in edit
