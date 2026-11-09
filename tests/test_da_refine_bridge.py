"""The browser buttons Re-scan and Restore build N through the four hops (Phase 8 step 16c).

The real clicks are checked by row 8-42 in a browser (`test_da_refine_e2e.py`). Here: the script
text and the server side of each hop, with the pretend folder."""

import pytest
from dash import no_update

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_refine_actions as actions
from agents import da_refine_flow as rflow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from callbacks.screen_callbacks import da_workspace_callbacks as wcb
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_refine import read_tested
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE
from db_table_functions.db_tbl_da_workspace import read_file_versions
from layouts import da_workspace_panel as panel
from tests.da_build_play import MODIFY, chat, ready_with_workspace
from tests.da_refine_play import rev
from tests.da_tree import by_id
from tests.da_workspace_play import facts_of
from web.da_workspace_bridge import workspace_script

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def two_builds(settings):
    """Build 1 written, then an edit, a re-scan and a check run (build 2): b_written again."""
    request_id, folder = ready_with_workspace(settings)
    flow.start_build(settings, request_id, 0)
    assert loop.run_build(settings, request_id) == "done"
    job = flow.prepare_write(settings, request_id, flow.get_revision(settings, request_id))
    revision = flow.get_revision(settings, request_id)
    flow.save_write(settings, request_id, folder.run_job(job), revision)
    first = folder.files[MODIFY]
    folder.edit(MODIFY, "# my own note\n" + first)
    scan(settings, request_id, folder)
    rflow.start_check(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    return request_id, folder, first


def ctx_of(request_id) -> dict:
    tree = cb.show_page(f"?request={request_id}", 0)
    return dict(by_id(tree, panel.WS_CTX_ID).data)


def scan(settings, request_id, folder, ctx=None):
    facts = facts_of(settings, request_id, folder).model_dump(mode="json")
    event = {"kind": "scan_facts", "facts": facts}
    return wcb.handle_workspace_event(settings, event, ctx or ctx_of(request_id), 4)


def test_the_script_knows_restore_go_and_picks_the_mode():
    script = workspace_script()

    assert 'key === "restore_go"' in script
    assert '"restore_download"' in script and '"restore_write"' in script
    assert 'key === "rescan"' in script  # Re-scan at b_written is the same script button


def test_a_rescan_at_b_written_is_the_refine_rescan_with_the_build_revision(settings, two_builds):
    request_id, folder, _ = two_builds
    folder.edit(MODIFY, "# a second edit\n" + folder.files[MODIFY])
    ctx = ctx_of(request_id)
    assert ctx["build_step"] == "b_written"

    result = scan(settings, request_id, folder, ctx)

    assert result == (5, None, no_update, "")
    with open_db(settings.db_path) as conn:
        assert read_file_versions(conn, request_id, MODIFY)[-1].kind == "scanned"
    assert rflow.get_edit_view(settings, request_id).changed == [MODIFY]
    assert "I found your edits" in chat(settings, request_id, "assistant")[-1]


def test_an_old_window_rescan_is_refused_with_the_message(settings, two_builds):
    request_id, folder, _ = two_builds
    ctx = ctx_of(request_id)
    scan(settings, request_id, folder, ctx)

    result = scan(settings, request_id, folder, ctx)  # the same old page again

    assert result[0] is no_update and result[3] == STALE_MESSAGE


def pick_build_one(settings, request_id):
    actions.perform_refine(settings, "restore", request_id, rev(settings, request_id),
                           build_revision=flow.get_revision(settings, request_id))
    actions.perform_refine(settings, "restore_pick:1", request_id, rev(settings, request_id))


def test_restore_runs_the_four_hops_and_the_old_set_is_back(settings, two_builds):
    request_id, folder, first = two_builds
    scan(settings, request_id, folder)  # the guard compares with what the server last scanned
    pick_build_one(settings, request_id)
    ctx = ctx_of(request_id)
    assert ctx["restore_build"] == 1

    refresh, job, pack, message = wcb.handle_workspace_event(
        settings, {"kind": "restore_write", "nonce": 7}, ctx, 2
    )  # hop 2: the server hands over the job
    assert (refresh, pack, message) == (no_update, no_update, "") and job["nonce"] == 7
    report = folder.run_job(rflow.prepare_restore(settings, request_id, 1, ctx["build_revision"]))
    done = wcb.finish_workspace_write(
        settings, report.model_dump(mode="json") | {"nonce": 7}, {"kind": "restore_write"}, ctx, 2
    )  # hop 4: one transaction saves it

    assert done == (3, "") and folder.files[MODIFY] == first
    with open_db(settings.db_path) as conn:
        assert read_tested(conn, request_id)["last_tested_build"] == 1
    assert actions.get_refine_bar(settings, request_id).restore_build == 0  # the choice is used up
    assert ctx_of(request_id)["restore_build"] == 0


def test_restore_in_download_mode_hands_back_a_zip_of_the_set_and_saves_it(settings, two_builds):
    request_id, folder, first = two_builds
    scan(settings, request_id, folder)
    pick_build_one(settings, request_id)
    ctx = ctx_of(request_id) | {"mode": "download"}

    refresh, job, pack, message = wcb.handle_workspace_event(
        settings, {"kind": "restore_download", "nonce": 9}, ctx, 2
    )

    assert (refresh, job, message) == (3, None, "") and pack["nonce"] == 9
    assert MODIFY in [item["path"] for item in pack["files"]]
    assert pack["readme_name"] and pack["readme"]
    with open_db(settings.db_path) as conn:
        assert read_tested(conn, request_id)["last_tested_kind"] == "restore"


def test_restore_without_a_chosen_build_says_so_and_saves_nothing(settings, two_builds):
    request_id, _, _ = two_builds

    result = wcb.handle_workspace_event(
        settings, {"kind": "restore_write", "nonce": 1}, ctx_of(request_id), 2
    )

    assert result[0] is no_update and "Pick the build to restore" in result[3]
    with open_db(settings.db_path) as conn:
        assert read_tested(conn, request_id)["last_tested_build"] == 2


def test_a_restore_that_is_not_connected_is_not_saved_as_a_stop(settings, two_builds):
    request_id, folder, _ = two_builds
    scan(settings, request_id, folder)
    pick_build_one(settings, request_id)
    ctx = ctx_of(request_id)

    result = wcb.finish_workspace_write(
        settings, {"written": [], "stopped": None, "not_connected": True, "nonce": 1},
        {"kind": "restore_write"}, ctx, 2,
    )

    assert result == (no_update, wcb.NOT_CONNECTED)
