"""Phase 11c step 4: the Overview screen (11-1, 11-3, 11-40 on screen, 11-44)."""

import ast
from pathlib import Path

import pytest
from dash import html
from dash.exceptions import PreventUpdate

from callbacks.screen_callbacks.da_admin_page_callbacks import (
    admin_content,
    change_window,
    health_content,
    refresh_overview,
)
from layouts.da_admin_page import ADMIN_PATH, ADMIN_TABS, TAB_OVERVIEW, TAB_UI
from tests.test_da_admin_page import all_text, walk

SRC = Path(__file__).resolve().parents[1] / "src"


def admin_settings(make_settings):
    return make_settings(admin_ids=("admin-0001",), developer_id="admin-0001")


def test_overview_is_the_first_tab_and_shows_the_header_line(make_settings, published_rulebook):
    content = admin_content(admin_settings(make_settings), ADMIN_PATH)

    tabs = next(c for c in walk(content) if type(c).__name__ == "Tabs")
    assert tabs.value == TAB_OVERVIEW
    assert "Active rulebook v1" in all_text(content)


def test_areas_table_has_six_rows_with_a_status_badge(make_settings, published_rulebook):
    content = admin_content(admin_settings(make_settings), ADMIN_PATH)

    table = next(c for c in walk(content) if type(c).__name__ == "Table")
    body = next(c for c in walk(table) if type(c).__name__ == "TableTbody")
    assert len(body.children) == 6
    for row in body.children:
        assert any(type(c).__name__ == "Badge" for c in walk(row))


def test_an_empty_database_says_no_data_yet_on_every_number(make_settings, published_rulebook):
    text = all_text(admin_content(admin_settings(make_settings), ADMIN_PATH))

    assert text.count("No data yet") >= 10
    assert "Handoffs: No data yet" in text
    assert "Escalations: No data yet" in text
    assert "Phase 10" not in text  # Phase 10 is built: the "comes with Phase 10" notes are gone


def test_the_window_change_redraws_only_the_health_numbers(make_settings, published_rulebook):
    settings = admin_settings(make_settings)

    for window in ("30d", "all", "nonsense"):
        text = all_text(health_content(settings, window))
        assert "Requests: No data yet" in text
        assert "Rulebook areas" not in text


def test_non_admin_gets_prevent_update_from_the_new_callbacks(make_settings, published_rulebook):
    settings = make_settings(admin_ids=("admin-0001",), developer_id="dev-0002")

    with pytest.raises(PreventUpdate):
        refresh_overview(settings, TAB_OVERVIEW)
    with pytest.raises(PreventUpdate):
        change_window(settings, "30d")


def test_refresh_only_when_the_overview_tab_opens(make_settings, published_rulebook):
    settings = admin_settings(make_settings)

    with pytest.raises(PreventUpdate):
        refresh_overview(settings, TAB_UI)
    children = refresh_overview(settings, TAB_OVERVIEW)
    assert "Rulebook" in all_text(html.Div(children))


def test_overview_is_a_card_grid_rulebook_and_health_left_attention_right(
    make_settings, published_rulebook
):
    """Fix 3 step 8a: Rulebook, then Health numbers in the main column; Needs attention beside."""
    content = admin_content(admin_settings(make_settings), ADMIN_PATH)

    grid = next(
        c
        for c in walk(content)
        if isinstance(getattr(c, "style", None), dict)
        and c.style.get("display") == "grid"
        and "2fr" in c.style["gridTemplateColumns"]
        and "Needs attention" in all_text(c)
    )
    left, right = grid.children
    assert "Rulebook" in all_text(left) and "Needs attention" not in all_text(left)
    assert "Needs attention" in all_text(right)
    assert "Health numbers" in all_text(left) and "Health numbers" not in all_text(right)


def test_overview_no_longer_says_comes_in(make_settings, published_rulebook):
    text = all_text(admin_content(admin_settings(make_settings), ADMIN_PATH))

    assert "Needs attention" in text and "Comes in 11c" not in text
    assert [name for name, _, _ in ADMIN_TABS][0] == TAB_OVERVIEW


def test_no_console_module_imports_the_developer_callbacks():
    paths = list((SRC / "callbacks").rglob("da_admin*.py"))
    paths += list((SRC / "layouts").rglob("da_admin*.py"))
    paths += list((SRC / "agents").rglob("da_admin*.py"))
    assert any(p.name == "da_admin_overview.py" for p in paths)
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not [m for m in modules if "developer_assistant_page" in m], path
