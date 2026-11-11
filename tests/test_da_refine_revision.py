"""The requirement lane after Confirm v2 (Phase 8 step 7b): Discover, the revision approach, the
test plan with New cases, the gate and the workspace check.

Tests 8-16, 8-17, 8-19."""

import pytest

from agents import da_approach_flow as approach
from agents import da_refine_lanes as lanes
from agents import da_refine_revision as revision
from agents import da_workspace_flow as workspace
from agents.da_approach_agent import ScriptedApproachClient
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import (
    read_approach_state,
    read_approach_versions,
    read_latest_plan,
)
from db_table_functions.db_tbl_da_discovery import read_latest_result
from db_table_functions.db_tbl_da_refine import RefineError, read_refines
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from db_table_functions.db_tbl_da_workspace import read_workspace_state
from pydantic_classes.da_models import STATUS_APPROACH_PROPOSED, STATUS_READY_TO_BUILD
from tests.da_approach_play import ChangedTester, Tweaked, events_of
from tests.da_build_play import chat, request_status
from tests.da_refine_play import lane_reply, records_of, rev, written_request
from tests.da_stub_client import StubClient
from tests.test_da_refine_lanes import CHANGE_AND_ADD

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def at_v2(settings):
    """A built request whose requirement lane has Confirm v2 pressed (AC-2 changed, one added)."""
    request_id, folder = written_request(settings)
    lanes.suggest(settings, request_id, "Reject big files", rev(settings, request_id),
                  StubClient(lane_reply("requirement")))
    lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))
    lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(CHANGE_AND_ADD))
    lanes.confirm_revision(settings, request_id, rev(settings, request_id))
    return request_id, folder


def at_findings(settings):
    request_id, folder = at_v2(settings)
    revision.run_discover(settings, request_id, rev(settings, request_id))
    return request_id, folder


def at_revision_approach(settings, change=None):
    request_id, folder = at_findings(settings)
    revision.confirm_findings(settings, request_id, rev(settings, request_id))
    state = revision.start_revision_approach(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change", change)
    )
    return request_id, folder, state


def change_count(settings, request_id) -> int:
    with open_db(settings.db_path) as conn:
        return read_approach_state(conn, request_id).change_count


def scripted_tester(request_id, settings):
    """A Tester that answers for exactly the criteria in the prompt's record (new and changed)."""
    new_id = f"AC-{len(records_of(settings, request_id)[0].acceptance_criteria) + 1}"

    def only_needed(data):
        data["cases"] = [
            {
                "criterion_id": cid,
                "given": "a file is uploaded",
                "expect": "a message says the file is rejected",
            }
            for cid in ("AC-2", new_id)
        ]

    return ChangedTester("test_plan", only_needed), new_id


# --- 8-16: Discover by itself, then a revision approach ---


def test_8_16_discover_runs_on_v2_and_a_revision_approach_follows(settings):
    request_id, _ = at_v2(settings)

    state = revision.run_discover(settings, request_id, rev(settings, request_id))

    assert state.step == "req_findings"
    outcomes = ("SIMILAR_IMPLEMENTATION_FOUND", "NO_RELIABLE_MATCH")
    assert request_status(settings, request_id) in outcomes
    with open_db(settings.db_path) as conn:
        assert read_latest_result(conn, request_id).record_version == 2

    state = revision.confirm_findings(settings, request_id, rev(settings, request_id))
    assert state.step == "req_approach"
    assert request_status(settings, request_id) == "DISCOVERY_CONFIRMED"
    before = change_count(settings, request_id)

    state = revision.start_revision_approach(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change")
    )

    assert state.step == "req_plan"
    assert request_status(settings, request_id) == STATUS_APPROACH_PROPOSED
    with open_db(settings.db_path) as conn:
        versions = read_approach_versions(conn, request_id)
        assert versions[-1].source == "revision" and versions[-1].record_version == 2
    assert change_count(settings, request_id) == before  # G9 untouched
    assert events_of(settings, request_id, "approach_revised")


def test_the_generator_is_told_what_changed_in_plain_words(settings):
    request_id, _ = at_findings(settings)
    revision.confirm_findings(settings, request_id, rev(settings, request_id))
    client = Tweaked("change")

    revision.start_revision_approach(
        settings, request_id, rev(settings, request_id), generator=client
    )

    assert "AC-2 is changed" in client.prompts[0] and "is added" in client.prompts[0]


def test_a_failed_approach_call_saves_nothing_and_can_be_tried_again(settings):
    request_id, _ = at_findings(settings)
    revision.confirm_findings(settings, request_id, rev(settings, request_id))

    state = revision.start_revision_approach(
        settings, request_id, rev(settings, request_id), generator=StubClient("not json", "no")
    )

    assert state.step == "req_approach"
    assert request_status(settings, request_id) == "DISCOVERY_CONFIRMED"
    assert "Try again" in chat(settings, request_id, "assistant")[-1]
    state = revision.start_revision_approach(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change")
    )
    assert state.step == "req_plan"


def test_the_steps_run_in_order_only(settings):
    request_id, _ = at_v2(settings)

    with pytest.raises(RefineError):
        revision.confirm_findings(settings, request_id, rev(settings, request_id))
    with pytest.raises(RefineError):
        revision.start_revision_approach(settings, request_id, rev(settings, request_id))


# --- 8-17: the test plan ---


def accept_approach_and_plan(settings, request_id):
    view = approach.get_approach_view(settings, request_id)
    if view.step == "choices":
        view = approach.choose_design_option(
            settings, request_id, view.buttons[0][1], view.revision,
            generator=ScriptedApproachClient("settle"),
        )
    tester, new_id = scripted_tester(request_id, settings)
    view = approach.accept_approach(settings, request_id, view.revision, tester=tester)
    return view, tester, new_id


def test_8_17_only_new_and_changed_criteria_get_new_cases(settings):
    request_id, _, _ = at_revision_approach(settings)
    with open_db(settings.db_path) as conn:
        old_plan = read_latest_plan(conn, request_id)
    unchanged = [c for c in old_plan.cases if c.criterion_id not in ("AC-2",)]

    view, tester, new_id = accept_approach_and_plan(settings, request_id)

    assert view.step == "tests"
    plan = view.plan
    assert plan.source_of_change == "revision" and plan.plan_version == old_plan.plan_version + 1
    for kept in unchanged:  # byte for byte, Yours included
        assert kept in plan.cases
    assert all(c.criterion_id != "AC-2" or c.new for c in plan.cases)
    fresh = [c for c in plan.cases if c.new]
    assert {c.criterion_id for c in fresh} == {"AC-2", new_id}
    assert all(c.source == "tester" for c in fresh)
    # acceptance is required again
    assert any(not check.passed for check in view.gate)


def test_the_tester_is_asked_only_about_the_new_and_changed_criteria(settings):
    request_id, _, _ = at_revision_approach(settings)

    _, tester, new_id = accept_approach_and_plan(settings, request_id)

    prompt = tester.prompts[0]
    assert "AC-2" in prompt and new_id in prompt and "AC-1:" not in prompt and "AC-3:" not in prompt


# --- the gate, the workspace check, 8-19 ---


def test_accepting_the_plan_runs_the_gate_closes_the_refine_and_resets_the_workspace(settings):
    request_id, _, _ = at_revision_approach(settings)
    view, _, _ = accept_approach_and_plan(settings, request_id)

    view = approach.accept_test_plan(settings, request_id, view.revision)

    assert request_status(settings, request_id) == STATUS_READY_TO_BUILD
    assert all(check.passed for check in view.gate)
    with open_db(settings.db_path) as conn:
        row = read_refines(conn, request_id)[0]
        assert row.result == "requirement" and row.record_version_after == 2
        newest = read_approach_versions(conn, request_id)[-1]
        assert row.approach_version_after == newest.approach_version
        assert read_workspace_state(conn, request_id).step == "start"  # the folder check runs again
    assert lanes.get_refine_state(settings, request_id).step == "start"
    assert events_of(settings, request_id, "refine_requirement_ready")
    assert workspace.get_workspace_view(settings, request_id).step == "start"


def test_8_19_a_file_the_old_plan_had_is_listed_and_not_deleted(settings):
    def drop_first_file(data):
        data["files"] = data["files"][1:] or data["files"]

    request_id, folder, _ = at_revision_approach(settings, drop_first_file)
    with open_db(settings.db_path) as conn:
        old, new = read_approach_versions(conn, request_id)[-2:]
    gone = [f.path for f in old.plan.files if f.path not in {n.path for n in new.plan.files}]
    assert gone, "the test needs the new plan to drop a file"
    view, _, _ = accept_approach_and_plan(settings, request_id)

    approach.accept_test_plan(settings, request_id, view.revision)

    line = chat(settings, request_id, "assistant")[-1]
    assert "no longer in the plan" in line and gone[0] in line
    assert events_of(settings, request_id, "files_dropped_from_plan")[0].details["paths"] == gone


def test_a_removed_criterion_loses_its_cases(settings):
    request_id, _ = written_request(settings)
    top = len(records_of(settings, request_id)[-1].acceptance_criteria)
    lanes.suggest(settings, request_id, "Drop the last rule", rev(settings, request_id),
                  StubClient(lane_reply("requirement")))
    lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))
    remove_last = {"criteria_ops": [{"op": "remove", "id": f"AC-{top}"}], "field_updates": {}}
    lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(remove_last))
    lanes.confirm_revision(settings, request_id, rev(settings, request_id))
    revision.run_discover(settings, request_id, rev(settings, request_id))
    revision.confirm_findings(settings, request_id, rev(settings, request_id))
    revision.start_revision_approach(
        settings, request_id, rev(settings, request_id), generator=Tweaked("change")
    )
    view = approach.get_approach_view(settings, request_id)
    if view.step == "choices":
        view = approach.choose_design_option(
            settings, request_id, view.buttons[0][1], view.revision,
            generator=ScriptedApproachClient("settle"),
        )

    # nothing is new or changed, so the Tester is not asked at all
    tester = ChangedTester("test_plan")
    with open_db(settings.db_path) as conn:
        before = read_latest_plan(conn, request_id)
    view = approach.accept_approach(settings, request_id, view.revision, tester=tester)

    assert tester.prompts == [] and view.step == "tests"
    assert view.plan.plan_version == before.plan_version + 1
    assert view.plan.cases == [c for c in before.cases if c.criterion_id != f"AC-{top}"]
    assert not any(c.new for c in view.plan.cases)


def test_a_stale_window_is_refused(settings):
    request_id, _ = at_v2(settings)
    old = rev(settings, request_id) - 1

    with pytest.raises(StaleRevisionError):
        revision.run_discover(settings, request_id, old)


# --- FX-7: the three Phase 3 buttons at the findings step (F4) ---


def test_fx_7_something_is_missing_runs_the_next_round_within_the_cap(settings):
    from agents import da_refine_actions as actions
    from agents.da_discover_flow import get_discovery_view

    request_id, _ = at_findings(settings)
    # Rounds count for the whole request: round 1 was the first Discover, round 2 the revision's.
    assert get_discovery_view(settings, request_id).rounds_used == 2
    bar = actions.get_refine_bar(settings, request_id)
    assert [key for key, _ in bar.buttons] == ["findings_ok", "findings_escalate"]
    assert bar.text_open and "Round 2 of 3" in bar.note

    now_rev = rev(settings, request_id)
    state = revision.add_findings_hint(settings, request_id, now_rev, "csv export")

    assert state.step == "req_findings"
    view = get_discovery_view(settings, request_id)
    assert view.rounds_used == 3 and view.result.hint == "csv export"
    capped = actions.get_refine_bar(settings, request_id)  # round 3 of 3 used: no more hints
    assert not capped.text_open and "all 3 search rounds" in capped.note
    with pytest.raises(Exception, match="limit of 3"):
        revision.add_findings_hint(settings, request_id, rev(settings, request_id), "one more")
    revision.confirm_findings(settings, request_id, rev(settings, request_id))  # still allowed


def test_fx_7_escalate_ends_in_escalation_required_with_the_open_item(settings):
    from agents import da_refine_help as help_

    request_id, _ = at_findings(settings)

    state = help_.escalate_findings(settings, request_id, rev(settings, request_id))

    assert state.step == "escalated"
    assert request_status(settings, request_id) == "ESCALATION_REQUIRED"
    with open_db(settings.db_path) as conn:
        assert read_approach_state(conn, request_id).open_item == "Escalated in Refine: Discover"
        assert [r.result for r in read_refines(conn, request_id)][-1] == "escalated"
    event = events_of(settings, request_id, "discovery_escalated")[-1]
    assert event.details["open_item"] == "Escalated in Refine: Discover"
    assert event.details["round"] == 2
    assert "🙋 Escalate to a senior developer" in chat(settings, request_id, "developer")


def test_fx_7_the_send_and_escalate_keys_reach_the_engine(settings):
    from agents import da_refine_actions as actions
    from agents.da_discover_flow import get_discovery_view

    request_id, _ = at_findings(settings)
    actions.perform_refine(settings, "send", request_id, rev(settings, request_id), "csv export")
    assert get_discovery_view(settings, request_id).rounds_used == 3

    actions.perform_refine(settings, "findings_escalate", request_id, rev(settings, request_id))
    assert request_status(settings, request_id) == "ESCALATION_REQUIRED"


def test_fx_7_escalate_is_refused_outside_the_findings_step(settings):
    from agents import da_refine_help as help_

    request_id, _ = at_v2(settings)  # Discover has not run yet

    with pytest.raises(RefineError):
        help_.escalate_findings(settings, request_id, rev(settings, request_id))
