"""Writing through the flow: the write job, the edit guard and the stale window
(rows 5-11, 5-12, 5-13, 5-25)."""

import pytest

from agents import da_workspace_flow as flow
from agents.da_workspace_checks import ABSENT, fingerprint
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from db_table_functions.db_tbl_da_workspace import (
    WorkspaceError,
    read_file_versions,
    read_workspace_revision,
)
from pydantic_classes.da_workspace_models import (
    JobFile,
    WriteJob,
    WriteReport,
    WrittenFile,
)
from tests.da_approach_play import event_types, events_of
from tests.da_workspace_play import facts_of, good_folder, pick, ready_to_build_id, texts

pytestmark = pytest.mark.usefixtures("published_rulebook")

INIT = "tests/cvda_2026_0001/__init__.py"


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
        creatable_folders=["tests", "tests/cvda_2026_0001"],
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


def test_5_12_an_edit_between_the_job_and_the_write_stops_the_job(settings, request_id):
    folder = good_folder()
    view, _ = pick(settings, request_id, folder)  # the tests folder now exists
    facts = facts_of(settings, request_id, folder)
    job = flow.judge_facts(settings, request_id, facts, view.revision).job
    folder.edit(INIT, "# the developer changed this\n")  # after the facts, before the write
    report = folder.run_job(job)

    after = flow.save_check(settings, request_id, facts, report, view.revision)

    assert report.stopped is not None and report.written == []
    stopped = events_of(settings, request_id, "workspace_write_stopped")
    assert stopped[0].details["path"] == INIT
    message = texts(after, "assistant")[-1]
    assert "Written: none" in message and f"Not written: {INIT}" in message
    assert folder.files[INIT] == "# the developer changed this\n"  # not overwritten
    assert after.revision == view.revision  # the stop saves no state change


def test_5_12_files_before_the_stop_stay_written_in_a_longer_job():
    folder = good_folder()
    folder.edit("src/web/b.py", "developer text\n")
    job = job_with(
        ("tests/cvda_2026_0001/__init__.py", "# a\n", ABSENT),
        ("src/web/b.py", "new text\n", fingerprint("original\n")),
        ("tests/cvda_2026_0001/test_c.py", "# c\n", ABSENT),
    )

    report = folder.run_job(job)

    assert [item.path for item in report.written] == ["tests/cvda_2026_0001/__init__.py"]
    assert report.stopped.path == "src/web/b.py"
    assert "Re-scan first" in report.stopped.reason
    assert folder.files["src/web/b.py"] == "developer text\n"
    assert "tests/cvda_2026_0001/test_c.py" not in folder.files


def test_5_13_a_new_file_that_appeared_after_the_facts_stops_the_job(settings, request_id):
    folder = good_folder()
    facts = facts_of(settings, request_id, folder)
    job = flow.judge_facts(settings, request_id, facts, 0).job
    folder.edit(INIT, "")  # somebody created it in the meantime

    report = folder.run_job(job)

    assert report.stopped is not None and "already exists" in report.stopped.reason
    assert folder.files[INIT] == ""


def test_the_written_file_keeps_its_text_and_fingerprint_on_the_server(settings, request_id):
    folder = good_folder()
    pick(settings, request_id, folder)

    with open_db(settings.db_path) as conn:
        versions = read_file_versions(conn, request_id, INIT)

    assert [(v.kind, v.mode) for v in versions] == [("written", "picker")]
    assert versions[0].fingerprint == fingerprint(folder.files[INIT])
    assert versions[0].text == folder.files[INIT]


def test_the_job_keeps_the_line_ending_of_an_existing_file():
    # Row 5-16 on the Python side: the browser is told to write the file's own style.
    from agents.da_workspace_checks import build_write_job

    job = build_write_job(
        "CVDA-2026-0001", "codevision", [("src/a.py", "x = 2\n")],
        {"src/a.py": (fingerprint("x = 1\r\n"), "\r\n")},
    )

    assert job.files[0].text == "x = 2\r\n"
    folder = good_folder(files={"src/a.py": "x = 1\r\n"})
    report = folder.run_job(job)
    assert folder.files["src/a.py"] == "x = 2\r\n" and report.stopped is None


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
