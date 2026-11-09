"""Fix it on a Should fix finding (Phase 8 step 9b-2): test 8-25."""

import pytest

from agents import da_build_loop as loop
from agents import da_refine_fixit as fixit
from agents import da_refine_lanes as lanes
from agents import da_tester_flow as tflow
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_refine import RefineError, read_refines, read_test_sets
from pydantic_classes.da_models import STATUS_BUILDING
from tests.da_approach_play import events_of
from tests.da_build_play import RecordingFactory, files_of, request_status, run_row
from tests.da_refine_play import rev, written_request

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def open_finding(settings, request_id):
    rows = tflow.get_tester_view(settings, request_id).rows
    return next(r.finding for r in rows if r.finding.severity == "should_fix")


def test_8_25_fix_it_runs_a_fix_round_on_the_cited_file_with_no_repro_test(settings):
    request_id, _ = written_request(settings)
    finding = open_finding(settings, request_id)

    state = fixit.fix_it(settings, request_id, rev(settings, request_id), finding.finding_id)

    assert state.step == "finding_fixing" and state.fix_finding == finding
    assert request_status(settings, request_id) == STATUS_BUILDING
    assert run_row(settings, request_id, 2).kind == "rebuild"
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []  # no repro test
        assert read_refines(conn, request_id)[0].source == "finding"
    factory = RecordingFactory()
    assert loop.run_build(settings, request_id, factory, build_number=2) == "done"

    rows = files_of(settings, request_id, 2, "code")
    before = {f.path: f.fingerprint for f in files_of(settings, request_id, 1, "code")}
    changed = {f.path for f in rows if before.get(f.path) != f.fingerprint}
    assert changed <= {finding.file}  # every other planned file is kept as it was
    assert len({f.path for f in rows}) > 1  # and they are still part of this build's code
    assert files_of(settings, request_id, 2, "test") == []  # tests not written again
    after = lanes.get_refine_state(settings, request_id)
    assert after.step == "start" and after.fix_finding is None
    with open_db(settings.db_path) as conn:
        assert read_refines(conn, request_id)[0].result in ("fixed", "not_fixed")
    assert events_of(settings, request_id, "finding_fixed") or events_of(
        settings, request_id, "finding_not_fixed"
    )


def test_fix_it_refuses_a_finding_that_is_not_a_should_fix(settings):
    request_id, _ = written_request(settings)
    rows = tflow.get_tester_view(settings, request_id).rows
    fyi = next(r.finding for r in rows if r.finding.severity == "fyi")

    with pytest.raises(RefineError):
        fixit.fix_it(settings, request_id, rev(settings, request_id), fyi.finding_id)
    with pytest.raises(RefineError):
        fixit.fix_it(settings, request_id, rev(settings, request_id), "F-99")
