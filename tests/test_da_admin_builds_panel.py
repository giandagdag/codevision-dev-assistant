"""Upgrade G step 3: the builds panel on Repository and index (G5c, G5d)."""

import pytest
from dash.exceptions import PreventUpdate

from agents import da_admin_rebuild as rebuild
from agents.da_admin_audit import read_admin_events
from agents.da_code_index import FakeEmbedder
from callbacks.screen_callbacks import da_admin_builds_callbacks as cb
from layouts import da_admin_builds_panel as panel
from layouts.da_admin_index_panels import rebuild_controls
from tests.test_da_admin_edit import ADMIN, settings_for
from tests.test_da_admin_page import walk
from tests.test_da_index_rollback import _policy


@pytest.fixture
def two_builds(tmp_path, monkeypatch):
    out, source = tmp_path / "idx", tmp_path / "code"
    source.mkdir()
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(out))
    for n in range(2):
        (source / "a.py").write_text(f"def f():\n    return {n}\n", encoding="utf-8")
        rebuild.start_rebuild(
            _policy(source), "Admin", embedder=FakeEmbedder(), directory=out, wait=True
        )
    return out


def test_panel_lists_builds_newest_first_and_sits_in_the_rebuild_controls(two_builds):
    everything, with_copy = panel.build_options()
    assert [o["value"] for o in everything] == ["2", "1"] == [o["value"] for o in with_copy]
    ids = {getattr(c, "id", None) for c in walk(rebuild_controls(None, []))}
    assert {panel.BUILD_A, panel.BUILD_COMPARE_BTN, panel.BUILD_USE_MODAL} <= ids


def test_compare_action_words(two_builds):
    assert cb.compare_action(None, "2") == "Pick two builds to compare."
    assert "Build 1 to build 2: 0 added" in cb.compare_action("1", "2")


def test_use_build_rolls_back_for_admin_and_refuses_others(make_settings, two_builds):
    text = cb.use_build(settings_for(make_settings), "1")
    assert text == "Rolled back to build 1"
    assert [e["who"] for e in read_admin_events(two_builds)] == [ADMIN]
    with pytest.raises(PreventUpdate):
        cb.use_build(make_settings(admin_ids=(ADMIN,), developer_id="someone"), "1")
    assert cb.use_build(settings_for(make_settings), None) == "Pick a build first."
