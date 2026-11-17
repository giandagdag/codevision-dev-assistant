"""Phase 11 fix 2, step 6: the catalog search modes on screen (AG-1 to AG-3). Made-up only."""

import pytest
from dash.exceptions import PreventUpdate

from agents.da_admin_meaning import FROM_SUMMARY, NEEDS_BUILDING, ModuleHit
from callbacks.screen_callbacks import da_admin_page_callbacks as page
from layouts.da_admin_catalog_meaning import (
    MODE_MEANING,
    MODE_NAMES,
    meaning_results,
    mode_switch,
    no_hits_line,
)
from layouts.da_admin_catalog_tab import catalog_view

HIT = ModuleHit("src/x/uploads_batch.py", ("run_upload", "check"), "Uploads", "Takes uploads.",
                "from code", 0.9)  # fmt: skip


def _admin(make_settings):
    return make_settings(admin_ids=("admin-0001",), developer_id="admin-0001")


def test_both_modes_are_on_the_switch():
    shown = str(mode_switch())
    assert "Names and people" in shown and "What the code does" in shown


def test_the_read_view_has_the_switch_and_a_results_area(published_rulebook):
    shown = str(catalog_view(published_rulebook))
    assert "adm-cat-mode" in shown and "adm-cat-meaning" in shown


def test_ag3_names_mode_gives_the_same_table_as_before(
    make_settings, published_rulebook, monkeypatch
):
    monkeypatch.setattr(page, "meaning_search", lambda *a: pytest.fail("no meaning search"))
    settings = _admin(make_settings)

    table, results = page.catalog_search(settings, "upload", False, MODE_NAMES)

    assert results is None
    assert str(table) == str(page.filtered_catalog(settings, "upload", False))


def test_meaning_mode_keeps_the_table_and_lists_the_programs(
    make_settings, published_rulebook, monkeypatch
):
    monkeypatch.setattr(page, "meaning_search", lambda q, s, c, t: ([HIT], ""))
    settings = _admin(make_settings)

    table, results = page.catalog_search(settings, "upload", False, MODE_MEANING)

    assert str(table) == str(page.filtered_catalog(settings, "", False))  # whole table
    shown = str(results)
    assert "src/x/uploads_batch.py" in shown and "Uploads" in shown and "run_upload, check" in shown
    assert "Takes uploads." in shown


def test_ag2_no_index_shows_one_plain_line(make_settings, published_rulebook, monkeypatch):
    monkeypatch.setattr(page, "meaning_search", lambda *a: ([], NEEDS_BUILDING))

    _table, results = page.catalog_search(_admin(make_settings), "upload", False, MODE_MEANING)

    assert NEEDS_BUILDING in str(results)


def test_nothing_found_and_nothing_typed(make_settings, published_rulebook, monkeypatch):
    monkeypatch.setattr(page, "meaning_search", lambda *a: ([], ""))
    settings = _admin(make_settings)

    assert page.catalog_search(settings, "zzz", False, MODE_MEANING)[1] is not None
    assert str(no_hits_line()) in str(page.catalog_search(settings, "zzz", False, MODE_MEANING)[1])
    assert page.catalog_search(settings, "", False, MODE_MEANING)[1] is None


def test_a_summary_only_hit_is_labelled():
    hit = ModuleHit("a.py", (), "Unassigned", "S.", FROM_SUMMARY, 0.5)
    assert "from summary" in str(meaning_results([hit]))


def test_a_click_filters_the_table_to_the_capability_that_holds_it(
    make_settings, published_rulebook, monkeypatch
):
    monkeypatch.setattr(page, "module_paths", lambda scope="": ["src/x/zzz_upload.py"])
    settings = _admin(make_settings)

    shown = str(page.catalog_for_module(settings, "src/x/zzz_upload.py"))

    # the header row plus exactly the capability that holds the module
    assert "zzz_upload.py" in shown and shown.count("TableTr(") == 2


def test_a_non_admin_click_does_nothing(make_settings, published_rulebook):
    with pytest.raises(PreventUpdate):
        page.catalog_for_module(make_settings(developer_id="nobody-9"), "a.py")
