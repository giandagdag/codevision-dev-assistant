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


def test_scope_and_principles_sit_in_two_boxes_side_by_side(published_rulebook):
    view = charter_view(published_rulebook)

    grids = [c for c in walk(view) if type(c).__name__ == "SimpleGrid"]
    assert len(grids) == 2
    assert all(len(g.children) == 2 and g.cols == 2 for g in grids)
    text = all_text(view)
    assert "✅ In scope" in text
    assert "🔴 Out of scope" in text
    assert "Architecture principles" in text
    assert "Constraints" in text
