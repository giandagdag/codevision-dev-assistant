"""The write job, the edit guard and the stale window (rows 5-11, 5-12, 5-13, 5-25), plus the
Phase 6 rules: the check writes nothing and the writer creates no folder (rows 6-35, 6-36)."""

import pytest

from agents import da_workspace_checks as checks
from agents import da_workspace_flow as flow
from agents.da_workspace_checks import ABSENT, fingerprint
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from db_table_functions.db_tbl_da_workspace import WorkspaceError, read_workspace_revision
from pydantic_classes.da_workspace_models import (
    JobFile,
    WriteJob,
    WriteReport,
    WrittenFile,
)
from tests.da_approach_play import event_types
from tests.da_workspace_play import facts_of, good_folder, pick, ready_to_build_id, texts

pytestmark = pytest.mark.usefixtures("published_rulebook")

CODE = "src/web/da_page.py"  # a code file the good folder holds


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_to_build_id(settings)


def job_with(*items):
    return WriteJob(
        request_id="CVDA-2026-0001",
        folder_name="codevision",
        files=[JobFile(path=p, text=t, expected=e) for p, t, e in items],
    )


def test_5_11_the_pretend_browser_refuses_a_path_not_in_the_job_or_with_dots():
    folder = good_folder()
    report = folder.run_job(job_with(("../outside.py", "x\n", ABSENT)))

    assert report.written == [] and "not allowed" in report.stopped.reason
    assert "../outside.py" not in folder.files


def test_5_11_the_server_refuses_a_report_that_names_a_path_outside_the_job(settings, request_id):
    folder = good_folder()
    facts = facts_of(settings, request_id, folder)
    job = flow.judge_facts(settings, request_id, facts, 0).job
    report = folder.run_job(job)
    stray = WrittenFile(path="src/other.py", text="x\n", fingerprint=fingerprint("x\n"))
    report.written.append(stray)

    with pytest.raises(WorkspaceError, match="not in the write job"):
        flow.save_check(settings, request_id, facts, report, 0)

    assert flow.get_workspace_view(settings, request_id).revision == 0
    assert "workspace_written" not in event_types(settings, request_id)


def test_6_35_a_good_folder_passes_with_no_file_written_and_no_tests_folder(settings, request_id):
    folder = good_folder()
    before = dict(folder.files)

    view, _ = pick(settings, request_id, folder)

    assert view.step == "ws_ready"
    assert folder.files == before  # nothing was written
    assert not folder.folder_exists("tests")  # and no tests folder was made
    said = " ".join(texts(view, "assistant"))
    assert "passed the check" in said and "Tests folder" not in said
    assert "workspace_written" not in event_types(settings, request_id)
    assert "workspace_baseline_taken" in event_types(settings, request_id)


def test_5_12_an_edit_between_the_facts_and_the_write_stops_the_job():
    folder = good_folder(files={CODE: "original\n"})
    job = job_with((CODE, "new text\n", fingerprint("original\n")))
    folder.edit(CODE, "# the developer changed this\n")  # after the facts, before the write

    report = folder.run_job(job)

    assert report.stopped is not None and report.written == []
    assert report.stopped.path == CODE and "Re-scan first" in report.stopped.reason
    assert folder.files[CODE] == "# the developer changed this\n"  # not overwritten
    message = checks.stop_message(job, report)
    assert "Written: none" in message and f"Not written: {CODE}" in message


def test_5_12_files_before_the_stop_stay_written_in_a_longer_job():
    folder = good_folder(files={"src/web/b.py": "developer text\n"})
    job = job_with(
        ("src/web/a.py", "# a\n", ABSENT),
        ("src/web/b.py", "new text\n", fingerprint("original\n")),
        ("src/web/c.py", "# c\n", ABSENT),
    )

    report = folder.run_job(job)

    assert [item.path for item in report.written] == ["src/web/a.py"]
    assert report.stopped.path == "src/web/b.py"
    assert "Re-scan first" in report.stopped.reason
    assert folder.files["src/web/b.py"] == "developer text\n"
    assert "src/web/c.py" not in folder.files


def test_5_13_a_new_file_that_appeared_after_the_facts_stops_the_job():
    folder = good_folder()
    job = job_with(("src/web/new_file.py", "x\n", ABSENT))
    folder.edit("src/web/new_file.py", "")  # somebody created it in the meantime

    report = folder.run_job(job)

    assert report.stopped is not None and "already exists" in report.stopped.reason
    assert folder.files["src/web/new_file.py"] == ""


def test_6_36_the_writer_creates_no_folder_a_missing_parent_is_refused():
    folder = good_folder()
    job = job_with(("src/newfolder/x.py", "x\n", ABSENT))

    report = folder.run_job(job)

    assert report.written == [] and "does not exist, and the app does not create it" in (
        report.stopped.reason
    )
    assert not folder.folder_exists("src/newfolder")
    assert "src/newfolder/x.py" not in folder.files


def test_a_report_with_a_read_back_that_differs_from_what_was_sent_is_refused():
    job = job_with((CODE, "sent\n", ABSENT))
    other = "# something else entirely\n"
    report = WriteReport(
        written=[WrittenFile(path=CODE, text=other, fingerprint=fingerprint(other))]
    )

    with pytest.raises(checks.FactsProblem, match="read back differently"):
        checks.verify_report(job, report)


def test_5_25_every_workspace_action_with_an_old_revision_is_refused(settings, request_id):
    folder = good_folder()
    view, _ = pick(settings, request_id, folder)
    facts = facts_of(settings, request_id, folder)
    actions = [
        lambda: flow.judge_facts(settings, request_id, facts, 0),
        lambda: flow.save_check(settings, request_id, facts, WriteReport(), 0),
        lambda: flow.rescan(settings, request_id, facts, 0),
        lambda: flow.picker_cancelled(settings, request_id, 0),
        lambda: flow.use_fallback(settings, request_id, "refused", 0),
        lambda: flow.prepare_download(settings, request_id, 0),
        lambda: flow.check_uploaded(settings, request_id, facts, 0),
        lambda: flow.change_approach(settings, request_id, 0),
        lambda: flow.request_help(settings, request_id, 0),
    ]

    for action in actions:
        with pytest.raises(StaleRevisionError):
            action()

    with open_db(settings.db_path) as conn:
        assert read_workspace_revision(conn, request_id) == view.revision


def test_a_workspace_action_before_ready_to_build_is_refused(make_settings):
    from tests.da_approach_play import discovery_confirmed_id

    settings = make_settings()
    request_id = discovery_confirmed_id(settings)

    with pytest.raises(Exception, match="no approach|READY TO BUILD"):
        flow.picker_cancelled(settings, request_id, 0)


def test_a_second_check_on_the_same_folder_keeps_the_developers_edits(settings, request_id):
    folder = good_folder()
    view, _ = pick(settings, request_id, folder)
    folder.edit(CODE, "# my own notes\n")  # edited after the first check

    view, _ = pick(settings, request_id, folder, view.revision)

    assert folder.files[CODE] == "# my own notes\n"  # a check never writes
