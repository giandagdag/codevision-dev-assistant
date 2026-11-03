"""Writing the built code files to the folder (rows 6-21 to 6-25, 6-40; rules D-E, B9)."""

import zipfile

import pytest

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_workspace_checks import ABSENT, fingerprint
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import BuildError
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE, StaleRevisionError
from db_table_functions.db_tbl_da_workspace import read_file_versions
from pydantic_classes.da_workspace_models import WriteReport
from tests.da_approach_play import events_of
from tests.da_build_play import (
    CREATE,
    MODIFY,
    ORIGINAL,
    RecordingFactory,
    build_state,
    chat,
    event_types,
    files_of,
    ready_with_workspace,
    request_status,
    run_row,
)
from tests.da_workspace_play import facts_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def built(settings):
    """A request whose build is finished (b_done, READY_FOR_REVIEW) but not yet written."""
    request_id, folder = ready_with_workspace(settings)
    flow.start_build(settings, request_id, 0)
    assert loop.run_build(settings, request_id) == "done"
    return request_id, folder


def revision(settings, request_id):
    return flow.get_revision(settings, request_id)


def write_it(settings, request_id, folder):
    job = flow.prepare_write(settings, request_id, revision(settings, request_id))
    report = folder.run_job(job)
    flow.save_write(settings, request_id, report, revision(settings, request_id))
    return job, report


def test_6_22_the_write_job_holds_the_code_files_only_with_the_right_expected_fingerprints(
    settings, built
):
    request_id, folder = built

    job = flow.prepare_write(settings, request_id, revision(settings, request_id))

    assert [f.path for f in job.files] == [CREATE, MODIFY]  # file-plan order, nothing else
    assert not any(f.path.startswith("tests/") for f in job.files)
    by_path = {f.path: f for f in job.files}
    assert by_path[CREATE].expected == ABSENT  # first write of this request
    assert by_path[MODIFY].expected == fingerprint(ORIGINAL)  # the baseline
    assert ".xlsx" in by_path[MODIFY].text  # the edit block was applied to his file
    assert build_state(settings, request_id).step == "b_done"  # preparing saves nothing


def test_6_22_the_write_puts_only_code_files_in_the_folder_and_saves_what_was_read_back(
    settings, built
):
    request_id, folder = built
    before = set(folder.files)

    job, report = write_it(settings, request_id, folder)

    assert report.stopped is None
    assert set(folder.files) - before == {CREATE}  # one new file; no tests, no new folder
    assert not folder.folder_exists("tests")
    state = build_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_written", "written")
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    with open_db(settings.db_path) as conn:
        written = {p: read_file_versions(conn, request_id, p)[-1] for p in (CREATE, MODIFY)}
    for path, row in written.items():
        assert row.kind == "written" and row.fingerprint == fingerprint(folder.files[path])
    assert events_of(settings, request_id, "workspace_written")[0].details["files"] == {
        CREATE: fingerprint(folder.files[CREATE]),
        MODIFY: fingerprint(folder.files[MODIFY]),
    }
    said = chat(settings, request_id, "assistant")[-1]
    assert "Wrote 2 code files" in said and "test the change by hand" in said
    assert "tests" not in said.lower().replace("test the change", "")


def test_6_21_a_not_passing_build_is_still_written_with_its_red_label_kept_in_the_app(
    settings, monkeypatch
):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"always_fail"}))
    request_id, folder = ready_with_workspace(settings)
    flow.start_build(settings, request_id, 0)
    loop.run_build(settings, request_id)
    assert request_status(settings, request_id) == "NOT_PASSING"

    write_it(settings, request_id, folder)

    assert CREATE in folder.files  # the code is there for him to see
    assert request_status(settings, request_id) == "NOT_PASSING"
    assert run_row(settings, request_id).label == "Not passing"
    assert "Not passing" not in folder.files[CREATE]  # the label never goes inside a file


def test_6_23_the_write_still_works_when_the_request_is_opened_later(settings, built):
    request_id, folder = built
    # The page was closed at b_done. Nothing happened since; opening it later asks for the job.
    assert build_state(settings, request_id).write_state == "not_written"

    write_it(settings, request_id, folder)

    assert build_state(settings, request_id).step == "b_written"


def test_6_24_an_edit_during_the_build_stops_the_write_at_that_file(settings, built):
    request_id, folder = built
    folder.edit(MODIFY, ORIGINAL + "# the developer changed this while I was building\n")

    job, report = write_it(settings, request_id, folder)

    assert [w.path for w in report.written] == [CREATE]  # the file before the stop stays written
    assert report.stopped.path == MODIFY and "Re-scan first" in report.stopped.reason
    assert folder.files[MODIFY].endswith("while I was building\n")  # his text was not touched
    state = build_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_write_stopped", "stopped")
    said = chat(settings, request_id, "assistant")[-1]
    assert f"Written: {CREATE}" in said and f"Not written: {MODIFY}" in said
    assert "workspace_write_stopped" in event_types(settings, request_id)


def test_6_25_re_scan_and_build_again_starts_from_his_text_with_a_fresh_budget(settings, built):
    request_id, folder = built
    his_text = ORIGINAL + "# the developer changed this while I was building\n"
    folder.edit(MODIFY, his_text)
    write_it(settings, request_id, folder)  # stops at MODIFY
    facts = facts_of(settings, request_id, folder)
    factory = RecordingFactory()

    state = flow.rebuild_after_stop(settings, request_id, facts, revision(settings, request_id))

    assert (state.build_number, state.step) == (2, "b_running")  # a new build, a new budget
    assert request_status(settings, request_id) == "BUILDING"
    with open_db(settings.db_path) as conn:
        assert read_file_versions(conn, request_id, MODIFY)[-1].kind == "scanned"
    assert loop.run_build(settings, request_id, factory) == "done"
    assert factory.prompts("tester") == []  # the same frozen tests: the Tester is not asked again
    modify_prompt = [p for p in factory.code_calls() if f"File: {MODIFY}" in p][0]
    assert his_text in modify_prompt  # round 1 starts from HIS text, not the old baseline
    job = flow.prepare_write(settings, request_id, revision(settings, request_id))
    assert {f.path: f.expected for f in job.files}[MODIFY] == fingerprint(his_text)
    report = folder.run_job(job)
    assert report.stopped is None
    assert "while I was building" in folder.files[MODIFY]  # his edit survived the AI's change
    assert ".xlsx" in folder.files[MODIFY]
    assert run_row(settings, request_id, 2).rounds_used >= 1


def test_6_25_a_new_file_the_developer_changed_is_patched_not_overwritten(settings, built):
    request_id, folder = built
    first_write = flow.prepare_write(settings, request_id, revision(settings, request_id))
    folder.edit(CREATE, "# he made this file himself first\n" + first_write.files[0].text)
    job = first_write
    flow.save_write(settings, request_id, folder.run_job(job), revision(settings, request_id))
    facts = facts_of(settings, request_id, folder)

    flow.rebuild_after_stop(settings, request_id, facts, revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"

    job = flow.prepare_write(settings, request_id, revision(settings, request_id))
    folder_report = folder.run_job(job)
    assert folder_report.stopped is None
    assert folder.files[CREATE].startswith("# he made this file himself first\n")


def test_the_server_refuses_a_report_that_names_a_file_outside_the_job(settings, built):
    request_id, folder = built
    job = flow.prepare_write(settings, request_id, revision(settings, request_id))
    report = folder.run_job(job)
    from pydantic_classes.da_workspace_models import WrittenFile

    report.written.append(
        WrittenFile(path="src/other.py", text="x\n", fingerprint=fingerprint("x\n"))
    )

    with pytest.raises(BuildError, match="not in the write job"):
        flow.save_write(settings, request_id, report, revision(settings, request_id))

    assert build_state(settings, request_id).step == "b_done"  # nothing was saved


def test_a_stale_window_cannot_prepare_or_save_a_write(settings, built):
    request_id, folder = built
    old = revision(settings, request_id) - 1

    with pytest.raises(StaleRevisionError, match=STALE_MESSAGE):
        flow.prepare_write(settings, request_id, old)
    with pytest.raises(StaleRevisionError, match=STALE_MESSAGE):
        flow.save_write(settings, request_id, WriteReport(), old)


def test_the_write_is_refused_while_the_build_is_still_running(settings):
    request_id, _ = ready_with_workspace(settings)
    flow.start_build(settings, request_id, 0)

    with pytest.raises(BuildError, match="running"):
        flow.prepare_write(settings, request_id, revision(settings, request_id))


def test_a_write_cannot_be_saved_twice(settings, built):
    request_id, folder = built
    job = flow.prepare_write(settings, request_id, revision(settings, request_id))
    report = folder.run_job(job)
    base = revision(settings, request_id)
    flow.save_write(settings, request_id, report, base)

    with pytest.raises(StaleRevisionError):
        flow.save_write(settings, request_id, report, base)


def test_re_scan_and_build_again_is_only_possible_after_a_stopped_write(settings, built):
    request_id, folder = built

    with pytest.raises(BuildError, match="being written|finished"):
        flow.rebuild_after_stop(
            settings,
            request_id,
            facts_of(settings, request_id, folder),
            revision(settings, request_id),
        )


def test_6_40_download_mode_gives_a_zip_of_the_code_files_only(settings, built, tmp_path):
    request_id, folder = built

    job, readme = flow.prepare_build_download(settings, request_id, revision(settings, request_id))

    archive = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for item in job.files:
            zf.writestr(item.path, item.text)
        zf.writestr("READ_ME_FIRST.txt", readme)
    with zipfile.ZipFile(archive) as zf:
        assert sorted(zf.namelist()) == sorted([CREATE, MODIFY, "READ_ME_FIRST.txt"])
        assert not any(name.startswith("tests/") for name in zf.namelist())
    assert "Unzip this file" in readme and "tests" not in readme
    state = build_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_written", "written")
    with open_db(settings.db_path) as conn:
        assert read_file_versions(conn, request_id, CREATE)[-1].mode == "download"
    assert "into the ZIP" in chat(settings, request_id, "assistant")[-1]
    assert files_of(settings, request_id, kind="test")  # the tests stay in the app
