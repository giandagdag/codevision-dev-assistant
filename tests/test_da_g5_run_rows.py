"""Fix G5 step 7a (R6, G5-9): the run row shows the Index result and the Tags result apart."""

import json

from agents import da_admin_tagger_job as tagjob
from agents.da_admin_index import recent_runs, run_line, tag_line
from layouts.da_admin_index_panels import rebuild_status, recent_refreshes
from tests.test_da_admin_tagger_job import _job, _setup


def test_all_tagged_is_green(tmp_path, make_settings):
    policy, client, _ = _setup(tmp_path)
    out = tmp_path / "idx"
    _job(policy, out, client, make_settings())

    row = recent_runs(out)[0]

    assert tag_line(row) == ("Tags: all 3 programs tagged", "green")
    assert "✅ Done" in run_line(row)  # the Index line is separate
    assert "Tags: all 3" in rebuild_status(None, [row])  # the job card's last line


def test_some_unreadable_is_amber_and_counted(tmp_path, make_settings):
    policy, _, _ = _setup(tmp_path)
    out = tmp_path / "idx"

    class Broken:
        def complete(self, prompt, system=None):
            raise RuntimeError("down")

    _job(policy, out, Broken(), make_settings())
    row = recent_runs(out)[0]

    assert row["unreadable"] == 3 and row["tag_total"] == 3 and row["tag_reasons"]
    assert tag_line(row) == ("Tags: 0 of 3 tagged, 3 could not be read", "orange")
    text = json.dumps(recent_refreshes([row]).to_plotly_json(), default=str)
    assert "3 could not be read" in text and "orange" in text


def test_a_crashed_tag_step_is_red_with_its_message(tmp_path, make_settings, monkeypatch):
    policy, client, _ = _setup(tmp_path)
    out = tmp_path / "idx"

    def boom(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(tagjob, "tag_programs", boom)
    _job(policy, out, client, make_settings())
    row = recent_runs(out)[0]

    text, colour = tag_line(row)
    assert colour == "red" and tagjob.TAGS_NOT_SAVED in text and "RuntimeError" in text
    assert "secret detail" not in text
    assert row["saved"]  # the index stays saved


def test_a_run_without_a_tag_step_has_no_tag_line():
    assert tag_line({"saved": True, "count": 4}) is None
