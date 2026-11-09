"""Re-scan and Check my edits (Phase 8 step 6; tests 8-3, 8-4, 8-5, 8-6, check-run Stop)."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_refine_flow as rflow
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import BuildError, read_build_runs
from db_table_functions.db_tbl_da_refine import read_tested
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from db_table_functions.db_tbl_da_workspace import read_file_versions
from tests.da_approach_play import events_of
from tests.da_build_play import (
    CREATE,
    MODIFY,
    RecordingFactory,
    build_state,
    chat,
    event_types,
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
def written(settings):
    """A request at b_written, READY_FOR_REVIEW: built and written to the pretend folder."""
    request_id, folder = ready_with_workspace(settings)
    flow.start_build(settings, request_id, 0)
    assert loop.run_build(settings, request_id) == "done"
    job = flow.prepare_write(settings, request_id, revision(settings, request_id))
    flow.save_write(settings, request_id, folder.run_job(job), revision(settings, request_id))
    assert build_state(settings, request_id).step == "b_written"
    return request_id, folder


def revision(settings, request_id):
    return flow.get_revision(settings, request_id)


def rescan(settings, request_id, folder):
    return rflow.rescan(
        settings, request_id, facts_of(settings, request_id, folder), revision(settings, request_id)
    )


def check_it(settings, request_id, factory=None):
    rflow.start_check(settings, request_id, revision(settings, request_id))
    return loop.run_build(settings, request_id, factory)


def edit_with_a_note(folder, path=MODIFY):
    folder.edit(path, "# my own note\n" + folder.files[path])


# --- Re-scan ---


def test_8_3_a_rescan_shows_the_edited_file_side_by_side_and_changes_no_status(settings, written):
    request_id, folder = written
    status = request_status(settings, request_id)
    edit_with_a_note(folder)

    state = rescan(settings, request_id, folder)

    assert request_status(settings, request_id) == status
    assert state.step == "b_written"
    with open_db(settings.db_path) as conn:
        assert read_file_versions(conn, request_id, MODIFY)[-1].kind == "scanned"
    view = rflow.get_edit_view(settings, request_id)
    assert view.changed == [MODIFY]
    assert view.not_tested_line == "Your edits are not tested yet. Press Check my edits."
    rows = view.diffs[0].rows
    assert rows[0] == ("", "# my own note", True)
    assert all(not changed for _, _, changed in rows[1:])
    assert "Your edits are not tested yet" in chat(settings, request_id, "assistant")[-1]
    assert events_of(settings, request_id, "rescan")[0].details == {"changed": 1}


def test_8_4_only_planned_files_are_read_and_the_fixed_line_is_shown(settings, written):
    request_id, folder = written
    folder.edit("src/web/da_page.py", "# not a planned file, and I changed it\n")
    folder.reads.clear()

    rescan(settings, request_id, folder)

    assert "src/web/da_page.py" not in folder.reads
    assert rflow.get_edit_view(settings, request_id).changed == []
    last = chat(settings, request_id, "assistant")[-1]
    assert rflow.ONLY_PLANNED_LINE in last
    assert rflow.get_edit_view(settings, request_id).only_planned_line == rflow.ONLY_PLANNED_LINE


def test_a_rescan_with_no_edits_says_so_and_offers_no_check(settings, written):
    request_id, folder = written

    rescan(settings, request_id, folder)

    assert rflow.NO_CHANGES_LINE in chat(settings, request_id, "assistant")[-1]
    with pytest.raises(BuildError, match="Nothing has changed"):
        rflow.start_check(settings, request_id, revision(settings, request_id))


def test_a_rescan_is_refused_while_a_build_runs_and_with_an_old_window(settings, written):
    request_id, folder = written
    old = revision(settings, request_id)
    edit_with_a_note(folder)
    rescan(settings, request_id, folder)

    with pytest.raises(StaleRevisionError):
        rflow.rescan(settings, request_id, facts_of(settings, request_id, folder), old)


# --- Check my edits ---


def test_8_5_an_edit_that_keeps_the_tests_passing_is_checked_without_the_generator(
    settings, written
):
    request_id, folder = written
    edit_with_a_note(folder)
    rescan(settings, request_id, folder)
    versions_before = len(open_versions(settings, request_id, MODIFY))
    factory = RecordingFactory()

    rflow.start_check(settings, request_id, revision(settings, request_id))
    assert request_status(settings, request_id) == "BUILDING"
    assert loop.run_build(settings, request_id, factory) == "done"

    assert factory.code_calls() == []  # no Generator call
    assert [role for role, _ in factory.calls if role == "generator"] == []
    run = run_row(settings, request_id, build=2)
    assert run.kind == "check"
    assert run.rounds_used == 0  # the budget was not touched
    assert run.label in ("Ready for your review", "Ready with warnings")
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    state = build_state(settings, request_id)
    assert (state.step, state.write_state, state.return_status) == ("b_written", "written", "")
    with open_db(settings.db_path) as conn:
        assert read_tested(conn, request_id)["last_tested_build"] == 2
        assert read_tested(conn, request_id)["last_tested_kind"] == "check"
    assert len(open_versions(settings, request_id, MODIFY)) == versions_before  # nothing written
    assert rflow.get_edit_view(settings, request_id).changed == []  # his files are now tested
    types = event_types(settings, request_id)
    assert "check_run_started" in types and "layer_b_result" in types
    assert "tester_review_done" in types


def test_8_6_an_edit_that_breaks_a_test_ends_not_passing_with_the_report(settings, written):
    request_id, folder = written
    folder.edit(MODIFY, "def validate(path):\n    return False\n")
    rescan(settings, request_id, folder)

    assert check_it(settings, request_id) == "done"

    assert request_status(settings, request_id) == "NOT_PASSING"
    assert run_row(settings, request_id, build=2).label == "Not passing"
    assert build_state(settings, request_id).step == "b_written"
    assert "Your edit breaks" in chat(settings, request_id, "assistant")[-1]
    with open_db(settings.db_path) as conn:
        assert read_tested(conn, request_id)["last_tested_build"] == 2


def test_8_7_ill_fix_it_myself_changes_no_status_and_says_what_to_do(settings, written):
    request_id, folder = written
    folder.edit(MODIFY, "def validate(path):\n    return False\n")
    rescan(settings, request_id, folder)
    check_it(settings, request_id)

    state = rflow.fix_myself(settings, request_id, revision(settings, request_id))

    assert request_status(settings, request_id) == "NOT_PASSING"
    assert state.step == "b_written"
    assert chat(settings, request_id, "assistant")[-1] == rflow.FIX_MYSELF_LINE
    assert "fix_myself" in event_types(settings, request_id)


def test_the_check_run_uses_a_new_build_number_and_the_old_builds_stay(settings, written):
    request_id, folder = written
    edit_with_a_note(folder)
    rescan(settings, request_id, folder)

    check_it(settings, request_id)

    with open_db(settings.db_path) as conn:
        runs = read_build_runs(conn, request_id)
    assert [(r.build_number, r.kind) for r in runs] == [(1, "build"), (2, "check")]


def test_a_check_run_on_a_file_he_renamed_a_function_in_fails_the_contract_check(settings, written):
    request_id, folder = written
    folder.edit(CREATE, folder.files[CREATE].replace("def read_sheets", "def read_all_sheets"))
    rescan(settings, request_id, folder)

    check_it(settings, request_id)

    assert request_status(settings, request_id) == "NOT_PASSING"
    last = chat(settings, request_id, "assistant")[-1]
    assert "code checks" in last or "Your edit breaks" in last


def test_stop_build_on_a_check_run_goes_back_to_where_it_was(settings, written):
    request_id, folder = written
    edit_with_a_note(folder)
    rescan(settings, request_id, folder)
    state = rflow.start_check(settings, request_id, revision(settings, request_id))
    assert state.return_status == "READY_FOR_REVIEW"

    flow.stop_build(settings, request_id, revision(settings, request_id))

    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    after = build_state(settings, request_id)
    assert (after.step, after.return_status) == ("b_written", "")
    assert "Your folder was not changed" in chat(settings, request_id, "assistant")[-1]


def test_a_check_is_refused_while_building_and_for_a_request_that_was_never_built(settings):
    request_id, folder = ready_with_workspace(settings)

    with pytest.raises(BuildError, match="no build"):
        rflow.start_check(settings, request_id, 0)
    flow.start_build(settings, request_id, 0)
    with pytest.raises(BuildError):
        rflow.start_check(settings, request_id, revision(settings, request_id))


def open_versions(settings, request_id, path):
    with open_db(settings.db_path) as conn:
        return read_file_versions(conn, request_id, path)
