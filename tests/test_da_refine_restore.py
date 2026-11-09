"""Versions and Restore (Phase 8 step 11; tests 8-30, 8-31, 8-32, 8-40)."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_refine_flow as rflow
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import BuildError
from db_table_functions.db_tbl_da_refine import read_test_sets, read_tested
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from db_table_functions.db_tbl_da_workspace import read_file_versions
from tests.da_approach_play import events_of
from tests.da_build_play import (
    MODIFY,
    build_state,
    chat,
    ready_with_workspace,
    request_status,
)
from tests.da_workspace_play import facts_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def revision(settings, request_id):
    return flow.get_revision(settings, request_id)


def rescan(settings, request_id, folder):
    return rflow.rescan(
        settings, request_id, facts_of(settings, request_id, folder), revision(settings, request_id)
    )


@pytest.fixture
def two_builds(settings):
    """Build 1 written; then an edit, a re-scan and a check run (build 2). Returns the text that
    build 1 wrote to MODIFY."""
    request_id, folder = ready_with_workspace(settings)
    flow.start_build(settings, request_id, 0)
    assert loop.run_build(settings, request_id) == "done"
    job = flow.prepare_write(settings, request_id, revision(settings, request_id))
    flow.save_write(settings, request_id, folder.run_job(job), revision(settings, request_id))
    first = folder.files[MODIFY]
    folder.edit(MODIFY, "# my own note\n" + first)
    rescan(settings, request_id, folder)
    rflow.start_check(settings, request_id, revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    return request_id, folder, first


def restore(settings, request_id, folder, number, mode="restore"):
    job = rflow.prepare_restore(settings, request_id, number, revision(settings, request_id))
    report = folder.run_job(job)
    rflow.save_restore(settings, request_id, number, report, revision(settings, request_id), mode)
    return report


def test_the_versions_list_has_one_row_per_finished_run_and_marks_last_tested(settings, two_builds):
    request_id, _, _ = two_builds

    rows = rflow.list_versions(settings, request_id)

    assert [(r.build_number, r.kind) for r in rows] == [(1, "build"), (2, "check")]
    assert [r.is_last_tested for r in rows] == [False, True]
    assert MODIFY in rows[0].files
    assert all(r.label for r in rows)


def test_8_31_restore_writes_the_whole_old_set_and_keeps_tests_and_record(settings, two_builds):
    request_id, folder, first = two_builds
    tests_before = len(read_test_sets_of(settings, request_id))
    status = request_status(settings, request_id)
    rescan(settings, request_id, folder)

    restore(settings, request_id, folder, 1)

    assert folder.files[MODIFY] == first
    state = build_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_written", "written")
    assert request_status(settings, request_id) == status
    with open_db(settings.db_path) as conn:
        tested = read_tested(conn, request_id)
        newest = read_file_versions(conn, request_id, MODIFY)[-1]
    assert (tested["last_tested_build"], tested["last_tested_kind"]) == (1, "restore")
    assert (newest.kind, newest.mode) == ("written", "restore")
    assert len(read_test_sets_of(settings, request_id)) == tests_before
    event = events_of(settings, request_id, "version_restored")[0]
    assert event.details == {"from": 2, "to": 1}
    assert "Restored build 1" in chat(settings, request_id, "assistant")[-1]
    assert rflow.get_edit_view(settings, request_id).changed == []


def test_8_32_the_warning_names_the_file_and_says_the_edit_stays_saved(settings, two_builds):
    request_id, folder, _ = two_builds
    folder.edit(MODIFY, "# a second edit\n" + folder.files[MODIFY])
    rescan(settings, request_id, folder)

    preview = rflow.restore_preview(settings, request_id, 1)

    assert f"`{MODIFY}`" in preview.warning
    assert "stay saved on the server" in preview.warning
    assert preview.button_label == "Restore build 1"


def test_a_preview_without_edits_has_no_warning(settings, two_builds):
    request_id, _, _ = two_builds

    assert rflow.restore_preview(settings, request_id, 2).warning == ""


def test_8_30_an_edit_after_the_last_scan_stops_the_restore_and_changes_nothing(
    settings, two_builds
):
    request_id, folder, _ = two_builds
    folder.edit(MODIFY, "# edited after the scan\n")

    report = restore(settings, request_id, folder, 1)

    assert report.stopped is not None
    assert folder.files[MODIFY] == "# edited after the scan\n"
    with open_db(settings.db_path) as conn:
        assert read_tested(conn, request_id)["last_tested_build"] == 2
    assert events_of(settings, request_id, "version_restored") == []
    assert "Re-scan first" in chat(settings, request_id, "assistant")[-1]
    assert build_state(settings, request_id).step == "b_written"


def test_restore_is_refused_for_an_unknown_build_and_an_old_window(settings, two_builds):
    request_id, folder, _ = two_builds
    old = revision(settings, request_id)

    with pytest.raises(BuildError, match="no saved code"):
        rflow.prepare_restore(settings, request_id, 9, old)
    job = rflow.prepare_restore(settings, request_id, 1, old)
    rescan(settings, request_id, folder)
    with pytest.raises(StaleRevisionError):
        rflow.save_restore(settings, request_id, 1, folder.run_job(job), old)


def test_8_40_download_mode_says_upload_and_the_zip_holds_code_files_only(settings, two_builds):
    request_id, folder, first = two_builds
    rescan(settings, request_id, folder)

    job, readme = rflow.prepare_restore_download(
        settings, request_id, 1, revision(settings, request_id)
    )

    assert rflow.rescan_label("download") == "Upload folder to re-scan"
    assert rflow.rescan_label("picker") == "Re-scan"
    assert "Upload your folder before every new download" in rflow.UPLOAD_BEFORE_DOWNLOAD_LINE
    assert job.files and all(not f.path.startswith("tests/") for f in job.files)
    assert readme
    with open_db(settings.db_path) as conn:
        newest = read_file_versions(conn, request_id, MODIFY)[-1]
        assert (newest.kind, newest.mode, newest.text) == ("written", "download", first)


def read_test_sets_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_test_sets(conn, request_id)
