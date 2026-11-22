"""G5-23 (L4): the catalog edit view, the patterns panel and Browse modules, measured in a browser.

At 1366, 1536 and 1920 px: the actions of one row sit on one line (2 px), each action has the same
left in every row, and the inputs of one row are equally high. Pictures go to
logs/admin-screens/g5. Skipped when Playwright or its browser is missing."""

import pytest

from layouts.da_admin_common import TAB_CAPABILITY
from tests.test_da_admin_screens_browser import OUT, live  # noqa: F401  (the live server fixture)

pytestmark = pytest.mark.usefixtures("published_rulebook")

SIZES = (
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
)
# For each element the selector finds: the top and left of its visible buttons.
BUTTONS_JS = """(sel) => [...document.querySelectorAll(sel)].map(row =>
  [...row.querySelectorAll('button')].filter(b => b.offsetHeight > 0)
    .map(b => { const r = b.getBoundingClientRect(); return {top: r.top, left: r.left}; }))
  .filter(r => r.length)"""
INPUT_HEIGHTS_JS = """(sel) => [...document.querySelectorAll(sel)].map(row =>
  [...row.querySelectorAll('input:not([type=hidden]):not([type=checkbox]), textarea')]
    .filter(e => e.offsetHeight > 0).map(e => e.getBoundingClientRect().height))"""


def check_rows(page, selector: str) -> int:
    """One line per row, and the same lefts down each column. Returns the rows measured."""
    rows = page.evaluate(BUTTONS_JS, selector)
    assert rows, selector
    for buttons in rows:
        assert max(b["top"] for b in buttons) - min(b["top"] for b in buttons) <= 2
    for column in range(min(len(r) for r in rows)):
        lefts = [r[column]["left"] for r in rows]
        assert max(lefts) - min(lefts) <= 2
    return len(rows)


def open_edit_view(page, size):
    page.set_viewport_size(size)
    page.get_by_role("tab", name="Capability catalog", exact=True).click()
    body = page.locator(f"#adm-body-{TAB_CAPABILITY}")
    body.get_by_role("button", name="Edit", exact=True).click()
    page.get_by_text("Nothing changes for developers until you save.").wait_for(timeout=10000)
    page.wait_for_timeout(300)
    return body


def test_g5_23_catalog_rows_panel_and_browse_modules_line_up(make_live_page, live):  # noqa: F811
    folder = OUT / "g5"
    folder.mkdir(parents=True, exist_ok=True)
    rows_sel = f"#adm-body-{TAB_CAPABILITY} tbody tr"
    for size in SIZES:
        width = size["width"]
        page = make_live_page(live)
        body = open_edit_view(page, size)
        # The catalog table: the action column (arrows, Remove) of every row.
        assert check_rows(page, f"{rows_sel} td:last-child") >= 2
        for heights in page.evaluate(INPUT_HEIGHTS_JS, rows_sel):
            if len(heights) > 1:
                assert max(heights) - min(heights) <= 2
        page.screenshot(path=str(folder / f"catalog-edit-{width}.png"), full_page=True)
        # The patterns panel: Remove at one left, one line per row.
        body.get_by_role("button", name="pattern", exact=False).first.click()
        page.locator(".mantine-Drawer-body").wait_for(timeout=10000)
        page.wait_for_timeout(300)
        check_rows(page, ".mantine-Drawer-body div[style*='grid']")
        page.screenshot(path=str(folder / f"patterns-{width}.png"))
        page.get_by_role("button", name="Close", exact=True).click()
        page.locator(".mantine-Drawer-body").wait_for(state="detached", timeout=10000)
        # Browse modules: the pop-up table's rows are one line (no buttons is fine here).
        body.get_by_role("button", name="Browse modules...").first.click()
        page.locator(".mantine-Modal-body td code").first.wait_for(timeout=10000)
        page.wait_for_timeout(300)
        if page.evaluate(BUTTONS_JS, ".mantine-Modal-body tbody tr"):
            check_rows(page, ".mantine-Modal-body tbody tr")
        page.screenshot(path=str(folder / f"browse-{width}.png"))
    stems = ("catalog-edit", "patterns", "browse")
    assert all((folder / f"{s}-{z['width']}.png").exists() for s in stems for z in SIZES)
