"""Fix G5 step 7b (R7, G5-10): Try the tagger on one program. Scripted client, saves nothing."""

import json
from dataclasses import replace

import pytest
from dash.exceptions import PreventUpdate

from agents.da_admin_rebuild import _lock_path
from agents.da_admin_tag_store import read_tags
from agents.da_tagger_try import RAW_MAX, try_tagger, try_text
from callbacks.screen_callbacks.da_admin_tag_history_callbacks import try_action
from layouts.da_admin_catalog_tab import queue_block
from tests.test_da_admin_tagger_job import GOOD, _job, _setup


def _built(tmp_path, make_settings):
    policy, client, _ = _setup(tmp_path)
    out = tmp_path / "idx"
    _job(policy, out, client, make_settings())
    return policy, out


class _Reply:
    def __init__(self, text):
        self.text = text


class _Says:
    def __init__(self, text):
        self.text = text

    def complete(self, prompt, system=None):
        return _Reply(self.text)


def test_shows_raw_reply_and_reader_result_and_saves_nothing(tmp_path, make_settings):
    policy, out = _built(tmp_path, make_settings)
    before = (out / "da_tags.json").read_bytes() if (out / "da_tags.json").exists() else None
    tags_before = read_tags(out)

    r = try_tagger(policy, make_settings(), "m0.py", out, _Says(json.dumps(GOOD)))

    assert r.result["summary"] == "Does a thing." and r.raw.startswith("{") and not r.reason
    assert "Read:" in try_text(r)
    assert read_tags(out) == tags_before
    if before is not None:
        assert (out / "da_tags.json").read_bytes() == before
    assert not _lock_path(out).exists()  # the lock is free again


def test_raw_is_cut_and_a_bad_reply_gives_its_reason(tmp_path, make_settings):
    policy, out = _built(tmp_path, make_settings)

    r = try_tagger(policy, make_settings(), "m0.py", out, _Says("not json " * 1000))

    assert len(r.raw) == RAW_MAX and r.result is None and r.reason == "no_json"
    assert "no_json" in try_text(r)


def test_a_failing_call_is_one_line_and_frees_the_lock(tmp_path, make_settings):
    policy, out = _built(tmp_path, make_settings)

    class Down:
        def complete(self, prompt, system=None):
            raise RuntimeError("secret")

    r = try_tagger(policy, make_settings(), "m0.py", out, Down())

    assert "RuntimeError" in r.message and "secret" not in r.message
    assert not _lock_path(out).exists()


def test_unknown_path_and_busy_job_are_refused(tmp_path, make_settings):
    policy, out = _built(tmp_path, make_settings)

    assert try_tagger(policy, make_settings(), "../x.py", out, _Says("{}")).message
    _lock_path(out).write_text(json.dumps({"started": "2999-01-01T00:00:00"}), encoding="utf-8")
    busy = try_tagger(policy, make_settings(), "m0.py", out, _Says("{}"))
    assert "running" in busy.message.lower()


def test_only_admin_can_try(make_settings):
    settings = make_settings()
    with pytest.raises(PreventUpdate):
        try_action(replace(settings, developer_id="nobody"), "m0.py")


def test_the_panel_is_on_the_review_queue_view():
    text = json.dumps(queue_block(None, []).to_plotly_json(), default=str)
    assert "Try the tagger on one program" in text and "adm-trytag-btn" in text
