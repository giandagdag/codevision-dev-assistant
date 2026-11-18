"""Rebuild index button, confirm box and the "Rebuild now?" ask after a save (AF-7, AF-8)."""

import json
from datetime import datetime

import pytest
from dash.exceptions import PreventUpdate

from agents import da_admin_rebuild as rebuild
from callbacks.screen_callbacks import da_admin_page_callbacks as cb
from layouts.da_admin_index_panels import (
    REBUILD_BTN,
    REBUILD_CONFIRM,
    rebuild_controls,
    rebuild_status,
)
from tests.test_da_admin_edit import field, settings_for
from tests.test_da_admin_page import walk

REPO_SAVE = {"type": "adm-act", "tab": "repo", "action": "save"}


@pytest.fixture(autouse=True)
def own_index_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path / "idx"))


def _modal(content):
    return next(c for c in walk(content) if type(c).__name__ == "Modal")


def _repo_form(scope: str):
    return cb.form_from_cells(
        "repo",
        [],
        [field("repo", "index_folder_scope", scope), field("repo", "note", "New scope")],
        [],
    )


def test_button_is_disabled_and_status_says_running_while_a_build_runs():
    started = datetime(2026, 11, 15, 14, 2)
    controls = rebuild_controls(started, [])
    button = next(c for c in walk(controls) if getattr(c, "id", None) == REBUILD_BTN)
    assert button.disabled is True
    assert rebuild_status(started, []) == "Rebuilding… started 14:02"
    assert _modal(controls).opened is False


def test_saving_a_new_folder_scope_asks_to_rebuild(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    form, note = _repo_form("src/data/da_fake_main")
    content, editing = cb.run_action(settings, "repo", REPO_SAVE, form, note, 1)
    assert editing is False
    modal = _modal(content)
    assert modal.opened is True and modal.title == "Rebuild the index now?"


def test_an_unchanged_scope_and_exclusions_do_not_ask(published_rulebook):
    assert cb._index_source_changed(published_rulebook, published_rulebook) is False


def test_confirm_starts_a_build(make_settings, published_rulebook, monkeypatch):
    settings = settings_for(make_settings)
    started = []
    monkeypatch.setattr(
        cb, "start_rebuild", lambda policy, who, **_: started.append(who) or (True, "ok")
    )
    cb.rebuild_action(settings, REBUILD_CONFIRM)
    assert started == [settings.developer_id]


def test_a_second_confirm_is_refused_while_running(make_settings, published_rulebook, tmp_path):
    settings = settings_for(make_settings)
    out = tmp_path / "idx"
    out.mkdir(parents=True, exist_ok=True)
    (out / rebuild.LOCK_NAME).write_text(json.dumps({"started": datetime.now().isoformat()}))
    opened, status = cb.rebuild_action(settings, REBUILD_CONFIRM)
    assert opened is False and status == rebuild.ALREADY_RUNNING


def test_non_admin_cannot_rebuild(make_settings, published_rulebook):
    with pytest.raises(PreventUpdate):
        cb.rebuild_action(make_settings(admin_ids=("someone-else",)), REBUILD_CONFIRM)
