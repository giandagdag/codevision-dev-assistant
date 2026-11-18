"""Fix 3 step 6: shared card, page titles on all 8 tabs (AH-1), card walk (AH-2)."""

import pytest

from layouts.da_admin_card import admin_card, card_grid, is_card, page_title
from layouts.da_admin_common import ADMIN_TABS
from layouts.da_admin_page import _tab_body
from styles import da_admin_styles as s

# Tabs not moved onto cards yet; steps 7 and 8 empty this set, then the xfail goes.
PENDING = {t for t, _, _ in ADMIN_TABS}


def _text(node) -> str:
    kids = getattr(node, "children", None)
    if isinstance(kids, str):
        return kids
    if isinstance(kids, (list, tuple)):
        return " ".join(_text(k) for k in kids)
    return _text(kids) if kids is not None else ""


def test_card_has_look_header_and_count():
    card = admin_card("Connection", "body", icon="C", count=3, actions="act")
    assert is_card(card)
    assert card.style["borderRadius"] == "12px" and card.style["padding"] == "20px"
    assert "Connection" in _text(card) and "3" in _text(card)


def test_card_grid_has_two_columns():
    grid = card_grid([admin_card("A", "x")], [admin_card("B", "y")])
    assert grid.style == s.GRID and len(grid.children) == 2


def test_page_title_has_name_and_purpose():
    box = page_title("Overview", "Plain line.")
    assert box.children[0].style["fontSize"] == "22px"
    assert "Plain line." in _text(box)


@pytest.mark.parametrize("tab,label,_", ADMIN_TABS)
def test_every_tab_starts_with_its_title(published_rulebook, tab, label, _):
    body = _tab_body(tab, published_rulebook)
    assert body.children[0].children[0].children == label
    assert _text(body.children[0].children[1])  # a purpose line


@pytest.mark.parametrize("tab,label,_", ADMIN_TABS)
def test_every_top_level_section_is_a_card(published_rulebook, tab, label, _):
    if tab in PENDING:
        pytest.xfail("moved onto cards in steps 7 and 8")
    inner = _tab_body(tab, published_rulebook).children[1]
    kids = inner.children if isinstance(inner.children, list) else [inner.children]
    assert all(is_card(k) or is_card_row(k) for k in kids)


def is_card_row(node) -> bool:
    return getattr(node, "style", None) == s.GRID
