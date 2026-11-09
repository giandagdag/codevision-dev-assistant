"""The requirement lane from the screen's buttons to a new build (Phase 8 step 16a/16d): Send, the
lane, Confirm v2, Findings look right, Accept approach, Accept test plan, the folder check on the
new file plan, Build, READY_FOR_REVIEW. The fake provider answers every AI call."""

import pytest

from agents import da_approach_flow as approach
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_refine_actions as actions
from agents import da_refine_lanes as lanes
from agents import da_tester_flow as tester_flow
from agents import da_workspace_flow as workspace
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import read_build_runs, read_rounds
from db_table_functions.db_tbl_da_refine import read_refines
from tests.da_build_play import request_status
from tests.da_refine_play import rev, written_request

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def go(settings, request_id, key, text=""):
    return actions.perform_refine(
        settings, key, request_id, rev(settings, request_id), text,
        build_revision=flow.get_revision(settings, request_id),
    )


def refine_to_the_test_plan(settings, request_id):
    go(settings, request_id, "send", "Reject files over 5 MB")
    assert lanes.get_refine_state(settings, request_id).suggested_lane == "requirement"
    outcome = go(settings, request_id, "lane_requirement")  # the revision runs by itself
    assert outcome.message == "" and lanes.get_refine_state(settings, request_id).step == (
        "req_checkpoint"
    )
    go(settings, request_id, "confirm_v2")  # Discover runs by itself
    assert lanes.get_refine_state(settings, request_id).step == "req_findings"
    go(settings, request_id, "findings_ok")  # the revision approach starts by itself
    assert lanes.get_refine_state(settings, request_id).step == "req_plan"
    view = approach.get_approach_view(settings, request_id)
    if view.step == "choices":
        label = view.buttons[0][1]
        view = approach.choose_design_option(settings, request_id, label, view.revision)
    view = approach.accept_approach(settings, request_id, view.revision)
    return approach.accept_test_plan(settings, request_id, view.revision)


def test_the_requirement_lane_ends_in_a_new_build_that_is_ready_for_review(settings):
    request_id, folder = written_request(settings)

    view = refine_to_the_test_plan(settings, request_id)

    assert view.request.status == "READY_TO_BUILD"
    assert lanes.get_refine_state(settings, request_id).step == "start"
    with open_db(settings.db_path) as conn:
        row = read_refines(conn, request_id)[-1]
    assert row.chosen_lane == "requirement" and row.result == "requirement"
    assert row.record_version_after == 2
    # The workspace check runs again on the new file plan; then Build is pressed by him.
    ws = workspace.get_workspace_view(settings, request_id)
    assert ws.step == "start"
    facts = folder.facts(ws.planned_paths, ws.markers, request_id, ws.max_file_kb)
    judged = workspace.judge_facts(settings, request_id, facts, ws.revision)
    assert judged.job is not None, judged.view.check.blockers
    ws = workspace.save_check(settings, request_id, facts, folder.run_job(judged.job), ws.revision)
    assert ws.step == "ws_ready"
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id), facts=facts)
    outcome = loop.run_build(settings, request_id)

    shown = tester_flow.get_build_view(settings, request_id)
    rows = shown.tester.rows if shown.tester else []
    found = [(r.finding.finding_id, r.finding.severity, r.finding.message) for r in rows]
    with open_db(settings.db_path) as conn:
        for item in read_rounds(conn, request_id, 2):
            report = item.failure_report
            if report is not None:  # say why a round failed, in the failure of this test
                found.append((item.round, [i.test_id for i in report.items],
                              [(p.path, p.text) for p in report.layer_a]))
    assert outcome == "done", (shown.banner_text, found)
    assert request_status(settings, request_id) == "READY_FOR_REVIEW", (shown.banner_text, found)
    with open_db(settings.db_path) as conn:
        assert [run.build_number for run in read_build_runs(conn, request_id)] == [1, 2]
