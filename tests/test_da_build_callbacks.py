"""The browser-to-server events of the Build: start from a re-scan, the automatic write, the
rebuild and the ZIP (rows 6-2, 6-22, 6-23, 6-24, 6-25, 6-29, 6-40)."""

import pytest
from dash import no_update

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_build_runner as runner
from agents import da_workspace_flow as workspace_flow
from callbacks.screen_callbacks import da_workspace_callbacks as wcb
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE
from db_table_functions.db_tbl_da_workspace import read_file_versions
from layouts import da_workspace_panel as panel
from tests.da_build_play import CREATE, MODIFY, ORIGINAL, ready_with_workspace
from tests.da_workspace_play import facts_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def submitted(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "submit_build", lambda settings, rid, *a: calls.append(rid))
    return calls


def ctx_of(settings, request_id):
    return panel.workspace_context(
        workspace_workspace(settings, request_id), flow.get_build_view(settings, request_id)
    )


def workspace_workspace(settings, request_id):
    return workspace_flow.get_workspace_view(settings, request_id)


def event_with(settings, request_id, folder, kind, nonce=1):
    facts = facts_of(settings, request_id, folder).model_dump(mode="json")
    return {"kind": kind, "nonce": nonce, "facts": facts}


def built(settings):
    request_id, folder = ready_with_workspace(settings)
    flow.start_build(settings, request_id, 0)
    assert loop.run_build(settings, request_id) == "done"
    return request_id, folder


def test_6_2_a_build_event_takes_the_rescan_starts_the_build_and_hands_it_to_the_runner(
    settings, submitted
):
    request_id, folder = ready_with_workspace(settings)
    folder.edit(MODIFY, ORIGINAL + "# edited before Build\n")
    event = event_with(settings, request_id, folder, "build_facts")

    refresh, job, pack, message = wcb.handle_workspace_event(
        settings, event, ctx_of(settings, request_id), 4
    )

    assert (refresh, job, message) == (5, None, "")
    assert flow.get_state(settings, request_id).step == "b_running"
    assert submitted == [request_id]
    with open_db(settings.db_path) as conn:
        assert read_file_versions(conn, request_id, MODIFY)[-1].kind == "scanned"


def test_6_29_a_build_click_from_an_old_window_starts_nothing(settings, submitted):
    request_id, folder = ready_with_workspace(settings)
    ctx = ctx_of(settings, request_id)
    flow.start_build(settings, request_id, 0)  # another window pressed Build first
    event = event_with(settings, request_id, folder, "build_facts")

    *_, message = wcb.handle_workspace_event(settings, event, ctx, 0)

    assert message == STALE_MESSAGE
    assert submitted == []  # no second build was handed to the runner
    assert flow.get_state(settings, request_id).build_number == 1


def test_6_22_the_automatic_write_hands_the_browser_a_job_with_code_files_only(settings):
    request_id, folder = built(settings)

    refresh, job, pack, message = wcb.handle_workspace_event(
        settings, {"kind": "build_write", "nonce": 7}, ctx_of(settings, request_id), 2
    )

    assert refresh is no_update and pack is no_update and message == ""
    assert [f["path"] for f in job["files"]] == [CREATE, MODIFY] and job["nonce"] == 7
    assert not any(f["path"].startswith("tests/") for f in job["files"])


def test_6_22_the_report_of_the_write_is_saved_and_the_step_becomes_written(settings):
    request_id, folder = built(settings)
    ctx = ctx_of(settings, request_id)
    _, job, *_ = wcb.handle_workspace_event(settings, {"kind": "build_write", "nonce": 7}, ctx, 2)
    pretend_job = workspace_flow.WriteJob.model_validate(
        {k: v for k, v in job.items() if k != "nonce"}
    )
    report = folder.run_job(pretend_job).model_dump(mode="json") | {"nonce": 8}

    refresh, message = wcb.finish_workspace_write(
        settings, report, {"kind": "build_write", "nonce": 7}, ctx, 2
    )

    assert (refresh, message) == (3, "")
    state = flow.get_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_written", "written")


def test_6_23_with_no_folder_allowed_nothing_is_saved_and_the_page_says_reconnect(settings):
    request_id, folder = built(settings)
    ctx = ctx_of(settings, request_id)
    report = {"written": [], "stopped": None, "not_connected": True, "nonce": 9}

    refresh, message = wcb.finish_workspace_write(
        settings, report, {"kind": "build_write", "nonce": 7}, ctx, 2
    )

    assert refresh is no_update and "Reconnect" in message
    state = flow.get_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_done", "not_written")  # NOT a stopped write


def test_6_24_a_stopped_write_is_saved_as_stopped(settings):
    request_id, folder = built(settings)
    folder.edit(MODIFY, "# changed during the build\n")
    ctx = ctx_of(settings, request_id)
    _, job, *_ = wcb.handle_workspace_event(settings, {"kind": "build_write", "nonce": 1}, ctx, 0)
    pretend_job = workspace_flow.WriteJob.model_validate(
        {k: v for k, v in job.items() if k != "nonce"}
    )
    report = folder.run_job(pretend_job).model_dump(mode="json") | {"nonce": 2}

    wcb.finish_workspace_write(settings, report, {"kind": "build_write", "nonce": 1}, ctx, 0)

    assert flow.get_state(settings, request_id).step == "b_write_stopped"


def test_6_25_the_rebuild_event_starts_a_new_build_from_his_text(settings, submitted):
    request_id, folder = built(settings)
    folder.edit(MODIFY, ORIGINAL + "# changed during the build\n")
    ctx = ctx_of(settings, request_id)
    _, job, *_ = wcb.handle_workspace_event(settings, {"kind": "build_write", "nonce": 1}, ctx, 0)
    pretend_job = workspace_flow.WriteJob.model_validate(
        {k: v for k, v in job.items() if k != "nonce"}
    )
    report = folder.run_job(pretend_job).model_dump(mode="json") | {"nonce": 2}
    wcb.finish_workspace_write(settings, report, {"kind": "build_write", "nonce": 1}, ctx, 0)
    ctx = ctx_of(settings, request_id)
    event = event_with(settings, request_id, folder, "rebuild_facts")

    refresh, *_ = wcb.handle_workspace_event(settings, event, ctx, 5)

    assert refresh == 6 and submitted == [request_id]
    assert flow.get_state(settings, request_id).build_number == 2


def test_6_40_the_download_event_gives_the_zip_pieces_for_the_code_files_only(settings):
    request_id, folder = built(settings)

    refresh, job, pack, message = wcb.handle_workspace_event(
        settings, {"kind": "build_download", "nonce": 3}, ctx_of(settings, request_id), 0
    )

    assert refresh == 1 and job is None and message == ""
    assert [f["path"] for f in pack["files"]] == [CREATE, MODIFY]
    assert pack["readme_name"] == "READ_ME_FIRST.txt" and "Unzip" in pack["readme"]
    assert flow.get_state(settings, request_id).step == "b_written"


def test_the_auto_write_script_never_prompts_and_fires_once_per_build_revision():
    body = wcb.AUTO_WRITE_BODY

    assert "chip.permission !== 'granted'" in body  # no permission: wait for Reconnect
    assert "requestPermission" not in body
    assert "window.__daAutoWrite === ctx.build_revision" in body
    assert "ctx.mode === 'download'" in body  # in download mode the developer presses the button
