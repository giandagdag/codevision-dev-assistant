"""Fix 11-1, L4 (step 23): UI standards read view has brand constants left, conventions right."""

from layouts.da_admin_page import TAB_UI, tab_content
from tests.test_da_admin_page import all_text, walk


def grids(content):
    return [
        c
        for c in walk(content)
        if "gridTemplateColumns" in (getattr(c, "style", None) or {})
    ]


def test_read_view_has_brand_left_and_conventions_right(published_rulebook):
    grid = grids(tab_content(TAB_UI, published_rulebook))[0]

    left, right = grid.children
    assert "Brand constants" in all_text(left) and "UI conventions" not in all_text(left)
    assert "UI conventions" in all_text(right) and "Brand constants" not in all_text(right)


def test_edit_view_keeps_brand_and_rules_stacked(published_rulebook):
    view = tab_content(TAB_UI, published_rulebook, editable=True)

    assert not grids(view)
    assert "Brand constants" in all_text(view)
