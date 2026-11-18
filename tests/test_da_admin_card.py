"""Fix 3 step 6: shared card, page titles on all 8 tabs (AH-1), card walk (AH-2)."""

import pytest

from layouts.da_admin_card import admin_card, card_grid, is_card, page_title
from layouts.da_admin_common import ADMIN_TABS
from layouts.da_admin_page import _tab_body
from styles import da_admin_styles as s


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
    if tab == "overview":  # without data the tab only says "comes later"; the card walk is in
        return  # test_da_admin_overview_rows
    inner = _tab_body(tab, published_rulebook).children[1].children  # body div -> tab content
    if is_card_row(inner):  # a tab that is the grid itself (history): both columns hold cards
        assert all(is_card(c) for col in inner.children for c in col.children)
        return
    kids = inner.children if isinstance(inner.children, list) else [inner.children]
    # the Edit button row (right aligned) and the version Store are not sections
    kids = [k for k in kids if type(k).__name__ != "Store" and not _is_edit_holder(k)]
    assert all(_is_section(k) for k in kids)


def _is_section(node) -> bool:
    """A card, a card grid, or a card stack / the rule-panel wrapper holding only those."""
    if is_card(node) or is_card_row(node):
        return True
    style = getattr(node, "style", None)
    wrapper = getattr(node, "id", None) == "adm-rule-panel"
    if style == s.CARD_STACK or wrapper:
        kids = node.children if isinstance(node.children, list) else [node.children]
        return all(_is_section(k) for k in kids)
    return False


def _is_edit_holder(node) -> bool:
    return (getattr(node, "style", None) or {}).get("justifyContent") == "flex-end"


def is_card_row(node) -> bool:
    return getattr(node, "style", None) == s.GRID
