"""AF-13: UI standards show swatches, a striped swatch for a pending colour, and the brand rows."""

from layouts.da_admin_page import TAB_UI, tab_content
from layouts.da_admin_ui_standards import swatch
from tests.test_da_admin_page import all_text, walk


def swatches(page):
    return [n for n in walk(page) if "adm-swatch" in str(getattr(n, "className", ""))]


def test_ui_tab_shows_brand_rows_and_swatches(published_rulebook):
    page = tab_content(TAB_UI, published_rulebook)
    text = all_text(page)
    for name in ("BLUE", "FONT_FAMILY", "FONT_BOLD", "SPACING", "TABLE_PAGE_SIZE"):
        assert name in text
    assert "CV-UI-001" in text and "Should fix" in text
    classes = [str(s.className) for s in swatches(page)]
    assert any("adm-swatch-pending" in c for c in classes)  # BRAND_RED is pending


def test_swatch_kinds():
    assert swatch("BLUE", "#1F6FE0").style["background"] == "#1F6FE0"
    assert "adm-swatch-pending" in swatch("BRAND_RED", "Pending brand guide").className
    assert swatch("FONT_FAMILY", "Segoe UI").style["fontFamily"] == "Segoe UI"
    assert "adm-swatch-none" in swatch("SPACING", "4, 8, 16, 24").className
