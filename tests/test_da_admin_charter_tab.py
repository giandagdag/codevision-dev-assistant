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


def test_charter_is_cards_purpose_and_glossary_left_the_four_lists_right(published_rulebook):
    from layouts.da_admin_card import is_card

    view = charter_view(published_rulebook)

    main, side = view.children
    assert len(main.children) == 2 and len(side.children) == 4
    assert all(is_card(c) for c in main.children + side.children)
    text = all_text(view)
    assert "✅ In scope" in text
    assert "🔴 Out of scope" in text
    assert "Architecture principles" in text
    assert "Constraints" in text
