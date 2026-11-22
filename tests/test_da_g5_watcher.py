"""Fix G5 step 8a (N1): one job watcher and the shared version number. Made-up data; no AI."""

import pytest
from dash import no_update
from dash.exceptions import PreventUpdate

from agents.da_admin_watch import IDLE_MS, RUNNING_MS, START_STATE, watch_step
from callbacks.screen_callbacks import da_admin_page_callbacks as page
from layouts.da_admin_catalog_tab import view_options
from layouts.da_admin_page import DATA_VERSION_ID, WATCH_ID, admin_page
from tests.test_da_admin_page import walk


def test_the_number_goes_up_only_when_a_running_job_ends():
    data, interval = watch_step(START_STATE, True)  # a job starts
    assert data == {"n": 0, "running": True} and interval == RUNNING_MS
    data, interval = watch_step(data, True)  # still running
    assert data["n"] == 0
    data, interval = watch_step(data, False)  # it ended (done or failed)
    assert data == {"n": 1, "running": False} and interval == IDLE_MS
    data, _ = watch_step(data, False)  # idle ticks change nothing
    assert data["n"] == 1


def test_a_first_tick_with_an_empty_store_is_safe():
    assert watch_step(None, False)[0] == START_STATE


def test_the_store_is_left_alone_when_nothing_changed(monkeypatch):
    monkeypatch.setattr(page, "running_since", lambda: None)
    store, interval = page.watch_job(START_STATE)
    assert store is no_update and interval == IDLE_MS


def test_the_watch_pieces_sit_in_the_page_shell(published_rulebook):
    ids = [getattr(c, "id", None) for c in walk(admin_page(published_rulebook))]
    assert DATA_VERSION_ID in ids and WATCH_ID in ids


def test_the_review_queue_button_carries_the_open_count():
    queue = {"rows": [1], "ai_cards": [1, 2], "suggestions": []}
    assert view_options(queue)[1]["label"] == "Review queue (3)"
    assert view_options({})[1]["label"] == "Review queue (0)"


@pytest.mark.parametrize("data", [None, START_STATE, {"n": 1, "running": True}])
def test_no_redraw_before_a_job_has_ended(make_settings, data):
    settings = make_settings(admin_ids=("admin-0001",), developer_id="admin-0001")
    with pytest.raises(PreventUpdate):
        page.redraw_after_job(settings, data, "", False, (None,) * 6)


def test_after_a_job_the_lists_redraw_and_keep_the_search(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    from agents.da_admin_tag_store import save_store

    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    proposed = {
        "state": "proposed", "proposed_capability": "Documents", "confidence": "high",
        "summary": "Writes markdown.", "reason": "fits", "file_hash": "h",
    }  # fmt: skip
    save_store({"modules": {"src/x/odd_a.py": proposed}, "runs": []}, tmp_path)
    settings = make_settings(admin_ids=("admin-0001",), developer_id="admin-0001")
    name = published_rulebook.rulebook.policy.capabilities[0].name

    overview, caps, items, count, options = page.redraw_after_job(
        settings, {"n": 1, "running": False}, name, False, (None,) * 6
    )

    assert name in str(caps)  # the typed search was applied again, not reset
    assert "odd_a.py" in str(items)
    assert options[1]["label"].startswith("Review queue (")
    assert overview and count
