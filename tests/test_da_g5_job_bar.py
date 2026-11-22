"""Fix G5 step 8b (N2): one progress bar on the Index card, the catalog and the Review queue."""

from datetime import datetime

import pytest
from dash.exceptions import PreventUpdate

from agents import da_admin_job as job
from callbacks.screen_callbacks import da_admin_page_callbacks as page
from layouts import da_admin_index_panels as panels
from layouts.da_admin_job_bar import BAR_CATALOG, BAR_QUEUE, JOB_STOP_TYPE, job_bar
from tests.test_da_admin_page import all_text, walk

RUNNING = {"step": 1, "done": 12, "total": 40, "started_by": "admin-0001", "mode": "full"}


@pytest.mark.parametrize(
    ("status", "name"),
    [
        ({**RUNNING, "step": 1}, "Reading code"),
        ({**RUNNING, "step": 2}, "Linking code"),
        ({**RUNNING, "step": 3}, "Tagging programs"),
        ({**RUNNING, "step": 3, "mode": "recheck"}, "Re-checking programs"),
    ],
)
def test_the_bar_names_its_step(status, name):
    shown = all_text(panels.html.Div(job_bar(status, datetime.now(), "catalog")))
    assert name in shown and "12 of 40" in shown and "(30%)" in shown


def test_nothing_shows_when_no_job_runs():
    assert job_bar(RUNNING, None, "catalog") == []


def test_catalog_and_queue_get_a_stop_button_each_the_index_card_keeps_its_own():
    stops = lambda where: [  # noqa: E731
        c for c in walk(panels.html.Div(job_bar(RUNNING, datetime.now(), where)))
        if isinstance(getattr(c, "id", None), dict) and c.id["type"] == JOB_STOP_TYPE
    ]
    assert len(stops("catalog")) == 1 and len(stops("queue")) == 1
    assert stops("catalog")[0].id != stops("queue")[0].id
    assert stops("index") == []


def test_the_index_card_uses_the_same_bar():
    parts = panels.job_panel(RUNNING, datetime.now())
    assert "Reading code" in str(parts) and "Step 1 of 3" in str(parts)


def test_the_watcher_fills_both_bars_and_stop_asks_the_job_to_end(
    make_settings, tmp_path, monkeypatch
):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    assert page.bars_now() == ([], [])  # idle: both empty
    assert BAR_CATALOG != BAR_QUEUE
    job.begin(tmp_path, datetime.now(), "admin-0001", "full", "Manual")
    monkeypatch.setattr(page, "running_since", lambda: datetime.now())
    caps, queue = page.bars_now()
    assert "Reading code" in str(caps) and "Reading code" in str(queue)

    page.stop_from_bar(make_settings(admin_ids=("admin-0001",), developer_id="admin-0001"))
    assert job.stop_requested(tmp_path)
    with pytest.raises(PreventUpdate):  # someone who is not an admin cannot stop it
        page.stop_from_bar(make_settings(admin_ids=("admin-0001",), developer_id="dev-0002"))
