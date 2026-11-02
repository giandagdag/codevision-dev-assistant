"""Re-scan through the flow (rows 5-17 and 5-18)."""

import pytest

from agents import da_workspace_flow as flow
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_workspace import WorkspaceError, read_file_versions
from tests.da_approach_play import event_types, events_of
from tests.da_workspace_play import MODIFY, facts_of, good_folder, pick, ready_to_build_id, texts

pytestmark = pytest.mark.usefixtures("published_rulebook")

TESTS = "tests/cvda_2026_0001"


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_to_build_id(settings)


@pytest.fixture
def ready(settings, request_id):
    folder = good_folder()
    view, _ = pick(settings, request_id, folder)
    return folder, view


def do_rescan(settings, request_id, folder, revision):
    return flow.rescan(settings, request_id, facts_of(settings, request_id, folder), revision)


def test_5_17_an_edited_planned_file_is_changed_by_you_and_saved_as_scanned(
    settings, request_id, ready
):
    folder, view = ready
    folder.edit(MODIFY, "def validate(path):\n    return False\n")

    after = do_rescan(settings, request_id, folder, view.revision)

    assert after.step == "ws_ready" and after.request.status == "READY_TO_BUILD"
    rows = {row.path: row.status for row in after.rows}
    assert rows[MODIFY] == "Changed by you"
    with open_db(settings.db_path) as conn:
        kinds = [v.kind for v in read_file_versions(conn, request_id, MODIFY)]
    assert kinds == ["baseline", "scanned"]
    assert texts(after, "assistant")[-1] == (
        "1 file changed by you. It will be checked when the build runs (Phase 6 onwards)."
    )
    assert events_of(settings, request_id, "workspace_rescanned")[0].details["changed"] == 1


def test_a_second_rescan_still_compares_with_the_last_write_not_the_scan(
    settings, request_id, ready
):
    folder, view = ready
    folder.edit(MODIFY, "changed\n")
    view = do_rescan(settings, request_id, folder, view.revision)

    again = do_rescan(settings, request_id, folder, view.revision)

    assert {row.path: row.status for row in again.rows}[MODIFY] == "Changed by you"


def test_a_rescan_with_nothing_changed_says_so(settings, request_id, ready):
    folder, view = ready

    after = do_rescan(settings, request_id, folder, view.revision)

    assert texts(after, "assistant")[-1] == "No changes found since the last check."
    assert {row.path: row.status for row in after.rows}[MODIFY] == "Not written yet"
    assert after.last_scan.count("unchanged") >= 1


def test_5_18_an_extra_file_in_the_tests_folder_is_listed_and_nothing_else_is_read(
    settings, request_id, ready
):
    folder, view = ready
    folder.edit("src/agents/secret_notes.py", "never read\n")
    folder.edit(f"{TESTS}/test_mine.py", "def test_x():\n    pass\n")
    folder.reads.clear()

    after = do_rescan(settings, request_id, folder, view.revision)

    outcomes = {item.path: item.outcome for item in after.last_scan.items}
    assert outcomes[f"{TESTS}/test_mine.py"] == "new_in_tests"
    allowed = set(after.planned_paths) | {f"{TESTS}/__init__.py", f"{TESTS}/test_mine.py"}
    assert set(folder.reads) <= allowed
    assert "src/agents/secret_notes.py" not in folder.reads
    with open_db(settings.db_path) as conn:
        assert [v.kind for v in read_file_versions(conn, request_id, f"{TESTS}/test_mine.py")] == [
            "scanned"
        ]


def test_a_missing_planned_file_is_listed_as_missing(settings, request_id, ready):
    folder, view = ready
    del folder.files[MODIFY]
    folder.edit("src/agents/keeps_folder.py", "x\n")

    after = do_rescan(settings, request_id, folder, view.revision)

    assert {row.path: row.status for row in after.rows}[MODIFY] == "Missing"


def test_a_rescan_is_refused_before_the_workspace_is_ready(settings, request_id):
    folder = good_folder()

    with pytest.raises(WorkspaceError, match="Please press Choose workspace folder"):
        do_rescan(settings, request_id, folder, 0)

    assert "workspace_rescanned" not in event_types(settings, request_id)
