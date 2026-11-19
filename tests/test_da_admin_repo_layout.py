"""Fix 3 step 7: Repository and index as cards with the Index job card (G3, G5; AH-7 UI)."""

from datetime import datetime

import pytest
from dash import html

from agents import da_admin_job as job
from callbacks.screen_callbacks import da_admin_page_callbacks as cb
from layouts import da_admin_index_panels as panels
from layouts.da_admin_card import is_card
from layouts.da_admin_page import TAB_REPO, tab_content
from tests.test_da_admin_page import all_text, walk


@pytest.fixture(autouse=True)
def own_index_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))


def _grid(published_rulebook):
    body = tab_content(TAB_REPO, published_rulebook, server=[("DA_SEARCH_TOP_K", "20")])
    return next(c for c in walk(body) if "gridTemplateColumns" in (getattr(c, "style", None) or {}))


def test_main_column_has_the_cards_and_side_column_one_index_job_card(published_rulebook):
    main, side = _grid(published_rulebook).children
    titles = [all_text(c.children[0]) for c in main.children]
    assert [t for t in ("Connection", "Refresh", "Exclusions") if t in " ".join(titles)] == [
        "Connection", "Refresh", "Exclusions"
    ]
    assert "Connection" in titles[0] and "Refresh" in titles[1] and "Exclusions" in titles[2]
    assert all(is_card(c) for c in main.children + side.children)
    assert len(side.children) == 1 and "Index job" in all_text(side.children[0].children[0])


def test_server_settings_card_is_collapsed(published_rulebook):
    main, _ = _grid(published_rulebook).children
    accordion = next(c for c in walk(main) if type(c).__name__ == "Accordion")
    assert accordion.value is None


def test_index_job_card_has_two_buttons_stop_and_a_5_second_poll(published_rulebook):
    _, side = _grid(published_rulebook).children
    ids = {getattr(c, "id", None): c for c in walk(side)}
    assert ids[panels.REBUILD_BTN].children == "Delta rebuild"
    assert ids[panels.REBUILD_FULL_BTN].children == "Full rebuild"
    assert ids[panels.REBUILD_STOP].disabled is True  # nothing is running
    assert ids[panels.REBUILD_POLL].interval == 5000


def test_running_job_shows_step_count_percent_and_a_stop_button():
    started = datetime(2026, 11, 18, 2, 0)
    status = {
        "started_by": "admin", "step": 1, "done": 340, "total": 1200,
        "step_started": started.isoformat(),
    }
    controls = panels.rebuild_controls(started, [], status=status, now=started)
    text = all_text(controls)
    assert "Step 1 of 3: reading the code, 340 of 1,200 pieces (28%)" in text
    assert "Started by admin at 02:00" in text
    ids = {getattr(c, "id", None): c for c in walk(controls)}
    assert ids[panels.REBUILD_STOP].disabled is False
    assert ids[panels.REBUILD_BTN].disabled and ids[panels.REBUILD_FULL_BTN].disabled


def test_last_error_shows_in_a_red_box_with_a_fix_hint():
    panel = panels.job_panel({"error": "CodeVision's code folder is not set"}, None)
    text = all_text(html.Div(panel))
    assert "CodeVision's code folder is not set" in text and panels.FIX_HINT in text
    assert panel[0].color == "red"
    running = {"error": "boom-error", "step_started": datetime.now().isoformat()}
    assert "boom-error" not in all_text(html.Div(panels.job_panel(running, datetime.now())))


def test_confirm_boxes_say_what_they_do_and_the_last_duration():
    runs = [{"saved": True, "mode": "full", "seconds": 11400}, {"saved": True, "mode": "delta"}]
    text = all_text(panels.rebuild_controls(None, runs))
    assert "Last full rebuild took about 3 h 10 min." in text
    assert "Reads only the new or changed programs" in text
    assert "re-tags every program" in text


def test_recent_refreshes_rows_show_mode_trigger_and_counts():
    run = {
        "started_by": "admin", "started_at": "2026-11-18T02:00:00", "saved": True, "count": 9,
        "mode": "delta", "trigger": "Nightly", "reread": 4, "tagged": 2, "seconds": 600,
    }
    expected = "Delta · Nightly · 4 pieces re-read · 2 programs tagged · 10 min"
    assert panels.run_detail(run) == expected


def test_stop_click_writes_the_stop_file(make_settings, tmp_path):
    from tests.test_da_admin_edit import settings_for

    cb.rebuild_action(settings_for(make_settings), panels.REBUILD_STOP)
    assert job.stop_requested(tmp_path)


def test_full_confirm_starts_a_full_job(make_settings, published_rulebook, monkeypatch):
    from tests.test_da_admin_edit import settings_for

    seen = []
    monkeypatch.setattr(
        cb, "start_rebuild", lambda *a, mode, **k: seen.append(mode) or (True, "ok")
    )
    settings = settings_for(make_settings)
    cb.rebuild_action(settings, panels.REBUILD_FULL_CONFIRM)
    cb.rebuild_action(settings, panels.REBUILD_CONFIRM)
    assert seen == ["full", "delta"]
