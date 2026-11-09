"""His picks on conflicts and Apply my choices (Phase 8 step 10b): tests 8-28, 8-29, 8-30, 8-41."""

from datetime import UTC, datetime

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_refine_fixit as fixit
from agents import da_refine_picks as picks
from agents import da_tester_flow as tflow
from agents.da_workspace_checks import fingerprint
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import BuildError
from db_table_functions.db_tbl_da_refine import read_conflicts
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from tests.da_approach_play import events_of
from tests.da_build_play import build_state, event_types, files_of, run_row
from tests.da_refine_play import rev, written_request
from tests.test_da_refine_conflicts_loop import _factory, _he_edits

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def _at_conflicts(settings):
    """A rebuild that stopped at b_conflicts with one conflict (C-1) on the file he edited."""
    request_id, folder = written_request(settings)
    rows = tflow.get_tester_view(settings, request_id).rows
    finding = next(r.finding for r in rows if r.finding.severity == "should_fix")
    _he_edits(settings, request_id, finding.file)
    # His edit is in his folder too, or the write guard would (rightly) stop the write.
    his_text = "# my note\n" + folder.files[finding.file]
    folder.edit(finding.file, his_text)
    fixit.fix_it(settings, request_id, rev(settings, request_id), finding.finding_id)
    assert loop.run_build(settings, request_id, _factory("# ai note"), build_number=2) == "done"
    assert build_state(settings, request_id).step == "b_conflicts"
    return request_id, folder, finding.file


def _revision(settings, request_id):
    return flow.get_revision(settings, request_id)


def _write(settings, request_id, folder):
    job = flow.prepare_write(settings, request_id, _revision(settings, request_id))
    report = folder.run_job(job)
    flow.save_write(settings, request_id, report, _revision(settings, request_id))
    return job, report


def _pick(settings, request_id, path, choice):
    return picks.pick(settings, request_id, path, "C-1", choice, _revision(settings, request_id))


def test_8_26_the_rebuild_prompt_marks_his_lines(settings):
    request_id, folder = written_request(settings)
    rows = tflow.get_tester_view(settings, request_id).rows
    finding = next(r.finding for r in rows if r.finding.severity == "should_fix")
    _he_edits(settings, request_id, finding.file)
    fixit.fix_it(settings, request_id, rev(settings, request_id), finding.finding_id)
    seen = []

    def spy(settings_, role):
        client = _factory("# ai note")(settings_, role)

        class Spy:
            model = client.model

            def complete(self, prompt, system=None):
                seen.append(prompt)
                return client.complete(prompt, system)

        return Spy()

    loop.run_build(settings, request_id, spy, build_number=2)

    assert any("written by the developer" in p for p in seen)


def test_8_28_all_picks_take_the_ai_writes_the_tested_result_with_no_check_run(settings):
    request_id, folder, path = _at_conflicts(settings)
    _pick(settings, request_id, path, picks.TAKE_AI)

    picks.apply_choices(settings, request_id, _revision(settings, request_id))

    state = build_state(settings, request_id)
    assert state.step == "b_done" and state.build_number == 2  # no new build
    job, report = _write(settings, request_id, folder)
    assert report.stopped is None
    assert "# ai note" in folder.files[path] and "# my note" not in folder.files[path]
    assert [f.text for f in job.files if f.path == path] == [folder.files[path]]
    assert "merge_check_started" not in event_types(settings, request_id)
    assert events_of(settings, request_id, "conflicts_applied")[0].details == {"mine": 0, "ai": 1}


def test_8_29_keep_mine_runs_a_check_on_the_merged_files_then_writes(settings):
    request_id, folder, path = _at_conflicts(settings)
    _pick(settings, request_id, path, picks.KEEP_MINE)

    picks.apply_choices(settings, request_id, _revision(settings, request_id))

    state = build_state(settings, request_id)
    assert state.step == "b_running" and state.build_number == 3
    assert run_row(settings, request_id, 3).kind == "check"
    merged = [f for f in files_of(settings, request_id, 3, "code") if f.path == path]
    assert merged[0].made_by == "merge" and "# my note" in merged[0].text
    assert loop.run_build(settings, request_id, build_number=3) == "done"
    assert build_state(settings, request_id).step == "b_done"
    _write(settings, request_id, folder)
    assert "# my note" in folder.files[path] and "# ai note" not in folder.files[path]
    assert build_state(settings, request_id).step == "b_written"
    assert run_row(settings, request_id, 3).label  # the label comes from the check run
    assert events_of(settings, request_id, "conflicts_applied")[0].details == {"mine": 1, "ai": 0}


def test_8_29_every_pick_is_audited_and_he_can_change_his_mind(settings):
    request_id, _, path = _at_conflicts(settings)
    _pick(settings, request_id, path, picks.KEEP_MINE)
    _pick(settings, request_id, path, picks.TAKE_AI)

    events = events_of(settings, request_id, "conflict_resolved")
    assert [e.details["choice"] for e in events] == ["mine", "ai"]
    with open_db(settings.db_path) as conn:
        assert read_conflicts(conn, request_id, 2)[0].choice == "ai"  # the newest pick counts


def test_apply_needs_a_pick_for_every_conflict_and_a_real_choice(settings):
    request_id, _, path = _at_conflicts(settings)

    with pytest.raises(BuildError, match="every conflict"):
        picks.apply_choices(settings, request_id, _revision(settings, request_id))
    with pytest.raises(BuildError, match="Pick Keep mine"):
        _pick(settings, request_id, path, "both")
    with pytest.raises(BuildError, match="no conflict"):
        picks.pick(settings, request_id, path, "C-9", "ai", _revision(settings, request_id))
    assert build_state(settings, request_id).step == "b_conflicts"  # nothing moved


def test_a_pick_from_an_old_window_is_refused(settings):
    request_id, _, path = _at_conflicts(settings)
    old = _revision(settings, request_id)
    picks.pick(settings, request_id, path, "C-1", "ai", old)

    with pytest.raises(StaleRevisionError, match="another window"):
        picks.pick(settings, request_id, path, "C-1", "mine", old)


def test_8_30_a_file_edited_after_the_last_scan_stops_the_write(settings):
    request_id, folder, path = _at_conflicts(settings)
    _pick(settings, request_id, path, picks.TAKE_AI)
    picks.apply_choices(settings, request_id, _revision(settings, request_id))
    later = folder.files[path] + "# edited after the scan\n"
    folder.edit(path, later)

    _, report = _write(settings, request_id, folder)

    assert report.stopped is not None and "Re-scan first" in report.stopped.reason
    assert folder.files[path] == later  # his text was not touched
    assert fingerprint(folder.files[path]) == fingerprint(later)


def test_8_41_the_write_after_picks_holds_code_files_only(settings):
    request_id, folder, path = _at_conflicts(settings)
    before = set(folder.files)
    _pick(settings, request_id, path, picks.TAKE_AI)
    picks.apply_choices(settings, request_id, _revision(settings, request_id), datetime.now(UTC))

    job, _ = _write(settings, request_id, folder)

    assert not any(f.path.startswith("tests/") for f in job.files)
    assert not folder.folder_exists("tests")
    assert not (set(folder.files) - before) - {f.path for f in job.files}
