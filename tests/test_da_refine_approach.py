"""The approach lane (Phase 8 step 8): a new approach version with source `refine`, the plan kept or
rewritten by the design decisions, the criterion-change refusal and the switch.

Tests 8-20 and 8-21."""

import pytest

from agents import da_approach_flow as approach
from agents import da_build_agent as build_agent
from agents import da_refine_approach as lane
from agents import da_refine_lanes as lanes
from agents import da_workspace_flow as workspace
from agents.da_approach_agent import ScriptedApproachClient
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import (
    read_approach_state,
    read_approach_versions,
    read_latest_plan,
)
from db_table_functions.db_tbl_da_refine import RefineError, read_refines
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from db_table_functions.db_tbl_da_workspace import read_workspace_state
from pydantic_classes.da_models import (
    STATUS_APPROACH_PROPOSED,
    STATUS_READY_FOR_REVIEW,
    STATUS_READY_TO_BUILD,
    STATUS_REVISION,
)
from tests.da_approach_play import ChangedTester, Tweaked, events_of
from tests.da_build_play import chat, request_status
from tests.da_refine_play import lane_reply, records_of, rev, written_request
from tests.da_stub_client import StubClient
from tests.test_da_refine_lanes import CHANGE_AND_ADD

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def at_approach_lane(settings):
    """A built request whose Refine has the approach lane chosen."""
    request_id, folder = written_request(settings)
    lanes.suggest(settings, request_id, "Use a smaller design", rev(settings, request_id),
                  StubClient(lane_reply("approach")))
    lanes.choose_lane(settings, request_id, "approach", rev(settings, request_id))
    return request_id, folder


def no_choices(data):
    data["design_choices"] = []


def one_choice(data):
    data["design_choices"] = [
        {"question": "Where does the check live?", "impact": "file layout",
         "options": ["In the upload module", "In a new module"]}
    ]


def approach_versions(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_approach_versions(conn, request_id)


def newest_approach(settings, request_id) -> int:
    return approach_versions(settings, request_id)[-1].approach_version


def change_count(settings, request_id) -> int:
    with open_db(settings.db_path) as conn:
        return read_approach_state(conn, request_id).change_count


def silent_tester():
    """A Tester that would answer, so a test can prove it was never asked."""
    return ChangedTester("test_plan")


# --- 8-20: the new version, the plan, the gate ---


def test_8_20_a_good_reply_is_saved_as_a_refine_version(settings):
    request_id, _ = at_approach_lane(settings)
    before = len(approach_versions(settings, request_id))
    count = change_count(settings, request_id)

    state = lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change", no_choices)
    )

    assert state.step == "approach_plan"
    assert request_status(settings, request_id) == STATUS_APPROACH_PROPOSED
    versions = approach_versions(settings, request_id)
    assert len(versions) == before + 1
    assert versions[-1].source == "refine" and versions[-1].record_version == 1
    assert change_count(settings, request_id) == count  # G9 untouched
    assert events_of(settings, request_id, "approach_refined")


def test_the_feedback_goes_to_the_change_call_between_lines(settings):
    request_id, _ = at_approach_lane(settings)
    client = Tweaked("change", no_choices)

    lane.start_approach_change(settings, request_id, rev(settings, request_id), generator=client)

    assert "Task: change an approach" in client.prompts[0]
    assert "Use a smaller design" in client.prompts[0]


def test_8_20_same_decisions_keep_the_test_plan_and_the_tester_is_not_asked(settings):
    request_id, _ = at_approach_lane(settings)
    with open_db(settings.db_path) as conn:
        old_plan = read_latest_plan(conn, request_id)
    lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change", no_choices)
    )
    view = approach.get_approach_view(settings, request_id)
    assert view.step == "review"
    tester = silent_tester()

    view = approach.accept_approach(settings, request_id, view.revision, tester=tester)

    assert tester.prompts == []
    assert view.step == "tests"
    assert view.plan.plan_version == old_plan.plan_version + 1
    assert view.plan.source_of_change == "refine"
    assert view.plan.approach_version == newest_approach(settings, request_id)
    assert view.plan.cases == old_plan.cases  # byte for byte, Yours included
    assert any(not check.passed for check in view.gate)  # he must accept the plan again


def test_8_20_changed_decisions_make_the_tester_write_a_new_plan(settings):
    request_id, _ = at_approach_lane(settings)
    lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change", one_choice)
    )
    view = approach.get_approach_view(settings, request_id)
    assert view.step == "choices"
    view = approach.choose_design_option(
        settings, request_id, view.buttons[0][1], view.revision,
        generator=ScriptedApproachClient("settle"),
    )
    tester = silent_tester()

    view = approach.accept_approach(settings, request_id, view.revision, tester=tester)

    assert len(tester.prompts) == 1
    assert view.step == "tests"
    assert view.plan.source_of_change == "refine"


def test_8_20_accepting_the_plan_runs_the_gate_and_closes_the_refine(settings):
    request_id, _ = at_approach_lane(settings)
    lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change", no_choices)
    )
    view = approach.get_approach_view(settings, request_id)
    view = approach.accept_approach(settings, request_id, view.revision, tester=silent_tester())

    view = approach.accept_test_plan(settings, request_id, view.revision)

    assert request_status(settings, request_id) == STATUS_READY_TO_BUILD
    assert all(check.passed for check in view.gate)
    assert len(records_of(settings, request_id)) == 1  # the record version did not change
    with open_db(settings.db_path) as conn:
        row = read_refines(conn, request_id)[0]
        assert row.result == "approach" and row.record_version_after == 1
        assert row.approach_version_after == newest_approach(settings, request_id)
        assert read_workspace_state(conn, request_id).step == "start"  # folder check runs again
    assert lanes.get_refine_state(settings, request_id).step == "start"
    assert events_of(settings, request_id, "refine_approach_ready")
    assert workspace.get_workspace_view(settings, request_id).step == "start"


def test_a_failed_call_saves_nothing_and_can_be_tried_again(settings):
    request_id, _ = at_approach_lane(settings)
    before = len(approach_versions(settings, request_id))

    state = lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=StubClient("not json", "no")
    )

    assert state.step == "approach_start"
    assert request_status(settings, request_id) == STATUS_REVISION
    assert len(approach_versions(settings, request_id)) == before
    assert "Try again" in chat(settings, request_id, "assistant")[-1]
    state = lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change", no_choices)
    )
    assert state.step == "approach_plan"


def test_the_steps_run_in_order_only(settings):
    request_id, _ = written_request(settings)

    with pytest.raises(RefineError):
        lane.start_approach_change(settings, request_id, rev(settings, request_id))
    with pytest.raises(RefineError):
        lane.switch_to_requirement(settings, request_id, rev(settings, request_id))


def test_a_stale_window_is_refused(settings):
    request_id, _ = at_approach_lane(settings)
    old = rev(settings, request_id)
    lane.start_approach_change(
        settings, request_id, old, generator=Tweaked("change", no_choices)
    )

    with pytest.raises(StaleRevisionError):
        lane.start_approach_change(settings, request_id, old, generator=Tweaked("change"))


# --- 8-21: a reply that changes a criterion ---


def refuse_with_switch(settings, monkeypatch):
    request_id, _ = at_approach_lane(settings)
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"approach_changes_criterion"}))
    before = len(approach_versions(settings, request_id))
    state = lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=ScriptedApproachClient("change")
    )
    return request_id, state, before


def test_8_21_a_reply_that_changes_a_criterion_is_refused(settings, monkeypatch):
    request_id, state, before = refuse_with_switch(settings, monkeypatch)

    assert state.step == "approach_refused"
    assert request_status(settings, request_id) == STATUS_REVISION
    assert len(approach_versions(settings, request_id)) == before  # nothing saved
    line = chat(settings, request_id, "assistant")[-1]
    assert "Use the requirement lane" in line and lane.SWITCH_LABEL in line
    assert events_of(settings, request_id, "approach_refused_criterion")


def test_the_switch_is_off_unless_a_test_turns_it_on(settings):
    request_id, _ = at_approach_lane(settings)

    state = lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=ScriptedApproachClient("change")
    )

    assert state.step in ("approach_plan",)


def test_8_21_switch_to_requirement_goes_on_in_the_same_refine(settings, monkeypatch):
    request_id, state, _ = refuse_with_switch(settings, monkeypatch)
    count = state.refine_count

    state = lane.switch_to_requirement(settings, request_id, rev(settings, request_id))

    assert state.step == "req_revise" and state.chosen_lane == "requirement"
    assert state.refine_count == count and len(read_all(settings, request_id)) == 1
    assert events_of(settings, request_id, "lane_switched")
    state = lanes.revise(
        settings, request_id, rev(settings, request_id), client=StubClient(CHANGE_AND_ADD)
    )
    assert state.step == "req_checkpoint"


def read_all(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_refines(conn, request_id)


def test_8_21_cancel_after_a_refusal_gives_everything_back(settings, monkeypatch):
    request_id, _, before = refuse_with_switch(settings, monkeypatch)

    state = lanes.cancel(settings, request_id, rev(settings, request_id))

    assert state.step == "start"
    assert request_status(settings, request_id) == STATUS_READY_FOR_REVIEW
    assert len(approach_versions(settings, request_id)) == before


def test_a_reply_flagged_by_the_generator_itself_is_refused_too(settings):
    request_id, _ = at_approach_lane(settings)

    def flag(data):
        data["changes_criteria"] = True

    state = lane.start_approach_change(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change", flag)
    )

    assert state.step == "approach_refused"
