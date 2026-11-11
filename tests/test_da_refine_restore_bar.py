"""FX-8, FX-9 and FX-13 (Phase 8 fix 1, F5 and F8): the Refine bar order, the greyed Restore and
Undo my edits. No browser: the bar is read as data and as a component tree."""

import pytest

from agents import da_build_flow as flow
from agents import da_refine_actions as actions
from agents import da_refine_edit as edit
from agents import da_refine_flow as rflow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests.da_build_play import MODIFY
from tests.da_refine_play import written_request
from tests.da_tree import all_text, components
from tests.da_workspace_play import facts_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def rescan_after_edit(settings, request_id, folder):
    folder.edit(MODIFY, "# my own note\n" + folder.files[MODIFY])
    rflow.rescan(
        settings,
        request_id,
        facts_of(settings, request_id, folder),
        flow.get_revision(settings, request_id),
    )


def bar_buttons(tree) -> list:
    """(label, disabled) of every button in the chat bar, left to right."""
    found = []
    for button in components(tree, "Button"):
        bar_id = getattr(button, "id", None)
        if isinstance(bar_id, dict) or (isinstance(bar_id, str) and bar_id.startswith("ws-")):
            found.append((all_text(button), bool(getattr(button, "disabled", False))))
    return found


def test_fx_13_the_bar_order_is_rescan_check_restore_then_help_last(settings):
    request_id, folder = written_request(settings)
    rescan_after_edit(settings, request_id, folder)

    labels = [label for label, _ in bar_buttons(draw(request_id))]

    wanted = ["Re-scan", "Check my edits", "Undo my edits (back to build 1)", "Get help"]
    positions = [labels.index(name) for name in wanted]
    assert positions == sorted(positions)


def test_fx_8_restore_is_greyed_with_the_line_when_there_is_nothing_to_restore(settings):
    request_id, _ = written_request(settings)

    tree = draw(request_id)

    assert ("Restore an earlier version", True) in bar_buttons(tree)
    assert rflow.NOTHING_TO_RESTORE_LINE in all_text(tree)
    assert actions.get_refine_bar(settings, request_id).disabled_keys == ["restore"]


def test_fx_9_undo_my_edits_names_the_file_and_puts_back_build_one(settings):
    request_id, folder = written_request(settings)
    first = folder.files[MODIFY]
    rescan_after_edit(settings, request_id, folder)
    bar = actions.get_refine_bar(settings, request_id)
    assert ("restore_pick:1", "Undo my edits (back to build 1)") in bar.buttons
    assert bar.disabled_keys == []

    edit.pick_restore(settings, request_id, 1, bar.refine_revision)
    preview = rflow.restore_preview(settings, request_id, 1)
    assert f"`{MODIFY}`" in preview.warning and "stay saved on the server" in preview.warning
    job = rflow.prepare_restore(settings, request_id, 1, flow.get_revision(settings, request_id))
    report = folder.run_job(job)
    rflow.save_restore(
        settings, request_id, 1, report, flow.get_revision(settings, request_id), "restore"
    )

    assert folder.files[MODIFY] == first  # the folder has build 1's text again
    assert rflow.get_edit_view(settings, request_id).changed == []
    texts = [v.text for v in _versions(settings, request_id)]
    assert any(text.startswith("# my own note") for text in texts)  # his edit is still saved


def _versions(settings, request_id):
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_workspace import read_file_versions

    with open_db(settings.db_path) as conn:
        return read_file_versions(conn, request_id, MODIFY)
