"""Fix G5 step 8c (N3): job-starting buttons are greyed, not hidden, while a job runs."""

from datetime import datetime

from callbacks.screen_callbacks import da_admin_page_callbacks as page
from layouts import da_admin_index_panels as panels
from layouts.da_admin_builds_panel import builds_panel
from layouts.da_admin_catalog_tab import suggest_button
from layouts.da_admin_job_bar import LOCK_NAMES, lock_id, lock_state, locked
from layouts.da_tagger_try_panel import tagger_try_panel
from tests.test_da_admin_page import walk

RUNNING = {"step": 3, "done": 5, "total": 20, "mode": "full"}


def _ids(tree):
    return [getattr(c, "id", None) for c in walk(tree)]


def test_the_tooltip_is_the_jobs_short_status():
    disabled, title = lock_state(RUNNING, datetime.now(), "")
    assert disabled and "Tagging programs, 5 of 20" in title


def test_when_idle_the_screens_own_reason_stays():
    assert lock_state({}, None, "") == (False, "")
    assert lock_state({}, None, "1") == (True, "")  # e.g. the catalog is being edited


def test_every_job_button_sits_in_its_own_tooltip_wrapper():
    tree = panels.html.Div(
        [
            panels.rebuild_controls(None, []),
            tagger_try_panel(["src/x/a.py"]),
            builds_panel(),
            locked("recheck", panels.dmc.Button("x")),
            *suggest_button({"offer_suggest": True}),
        ]
    )
    ids = _ids(tree)
    for name in LOCK_NAMES:
        assert lock_id(name) in ids


def test_all_six_buttons_lock_together_and_free_together(tmp_path, monkeypatch):
    own = ("",) * 6
    monkeypatch.setattr(page, "running_since", lambda: None)
    monkeypatch.setattr(page.job, "read_status", lambda: {})
    assert page.locks_now(own) == [False] * 6 + [""] * 6

    monkeypatch.setattr(page, "running_since", lambda: datetime.now())
    monkeypatch.setattr(page.job, "read_status", lambda: RUNNING)
    out = page.locks_now(own)
    assert out[:6] == [True] * 6 and all("Tagging programs" in t for t in out[6:])


def test_n4_the_recheck_leaves_one_end_line_and_no_open_this_tab_text(tmp_path, make_settings):
    import json

    from agents import da_admin_job as job
    from agents.da_admin_recheck import start_recheck
    from layouts.da_admin_job_bar import job_bar
    from tests.test_da_admin_tagger_job import GOOD, _job, _setup

    policy, _, _ = _setup(tmp_path)
    out = tmp_path / "idx"

    class Down:
        def complete(self, prompt, system=None):
            raise RuntimeError("down")

    class Reply:
        text = json.dumps(GOOD)

    class Up:
        def complete(self, prompt, system=None):
            return Reply()

    _job(policy, out, Down(), make_settings())
    started, message = start_recheck(
        policy, make_settings(), "admin1", directory=out, wait=True, client=Up()
    )

    line = job.read_status(out)["end_line"]
    assert started and "Open this tab again" not in message
    assert line.startswith("Re-check done: ") and "still with no fit" in line
    assert line.endswith("0 could not be read.")
    assert line in str(job_bar(job.read_status(out), None, "catalog"))  # shown when idle
    assert job_bar(job.read_status(out), None, "index") == []  # the Index card has its own text


def test_the_end_of_a_job_does_not_enable_a_button_the_screen_disabled(monkeypatch):
    monkeypatch.setattr(page, "running_since", lambda: None)
    monkeypatch.setattr(page.job, "read_status", lambda: {})
    own = ("", "", "1", "", "", "")  # Re-check disabled because the catalog is being edited
    assert page.locks_now(own)[:6] == [False, False, True, False, False, False]
