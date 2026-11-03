"""The Tester's plan, the developer's own cases, and Change the approach (rows 4-18 to 4-24)."""

import pytest

from agents import da_approach_flow as flow
from agents.da_approach_agent import ScriptedApproachClient
from agents.da_approach_checks import NO_CRITERION_MESSAGE
from agents.da_tester_agent import ScriptedTesterClient
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import ApproachError, read_test_plans
from tests.da_approach_play import (
    ChangedTester,
    at_review,
    at_tests,
    discovery_confirmed_id,
    events_of,
    texts,
)
from tests.da_stub_client import FailingClient, StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return discovery_confirmed_id(settings)


def plans(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_test_plans(conn, request_id)


def add_case(settings, request_id, view, text="A workbook where every visible sheet is empty",
             tester=None):
    view = flow.request_case(settings, request_id, view.revision)
    return flow.submit_text(
        settings, request_id, text, view.revision,
        tester=tester or ScriptedTesterClient("test_case"),
    )


def test_accepting_the_approach_has_the_tester_write_plan_v1(settings, request_id):
    view = at_tests(settings, request_id)

    assert view.step == "tests" and view.request.status == "APPROACH_PROPOSED"
    plan = view.plan
    assert plan.plan_version == 1 and plan.approach_version == 2  # the settled version
    assert [c.test_id for c in plan.cases] == [f"T-{n}" for n in range(1, 10)]  # 4-21
    assert {c.source for c in plan.cases} == {"tester"}
    assert len({c.criterion_id for c in plan.cases}) == 7
    assert events_of(settings, request_id, "approach_accepted")
    assert events_of(settings, request_id, "test_plan_written")
    assert "9 test cases covering 7 of 7 criteria" in texts(view, "assistant")[-1]


def test_4_18_the_tester_prompt_has_no_file_plan_reuse_or_chat(settings, request_id):
    view = at_review(settings, request_id)
    tester = ChangedTester("test_plan")

    view = flow.accept_approach(settings, request_id, view.revision, tester=tester)

    prompt = tester.prompts[0]
    assert all(f"AC-{n}" in prompt for n in range(1, 8))
    assert "Where does Excel upload live? -> Existing upload screen" in prompt
    for forbidden in ("excel_processor", "upload_validator", "Reuse", "extend", "Discover"):
        assert forbidden not in prompt
    # No chat: none of the assistant lines of the conversation is in it.
    for line in texts(view, "assistant"):
        assert line not in prompt


def test_the_approach_stays_accepted_when_the_tester_fails_and_a_button_retries(
    settings, request_id
):
    view = at_review(settings, request_id)

    view = flow.accept_approach(
        settings, request_id, view.revision, tester=FailingClient("The Tester is down")
    )

    assert view.step == "tests_pending" and view.plan is None
    assert view.buttons == [("write_plan", "Write the test plan"), ("help", "Get help")]
    assert events_of(settings, request_id, "approach_accepted")
    assert "The Tester is down" in texts(view, "assistant")[-1]
    assert [c.name for c in view.gate if c.passed] == ["Request confirmed", "Discover done",
                                                       "Approach confirmed"]

    view = flow.write_test_plan_again(
        settings, request_id, view.revision, tester=ScriptedTesterClient("test_plan")
    )

    assert view.step == "tests" and view.plan.plan_version == 1
    assert len(events_of(settings, request_id, "approach_accepted")) == 1


def test_4_19_a_tester_plan_missing_a_criterion_is_retried_once(settings, request_id):
    view = at_review(settings, request_id)

    def drop_ac_4(data):
        data["cases"] = [c for c in data["cases"] if c["criterion_id"] != "AC-4"]

    tester = ChangedTester("test_plan")
    calls = []

    def first_bad(data):
        calls.append(1)
        if len(calls) == 1:
            drop_ac_4(data)

    tester.change = first_bad
    view = flow.accept_approach(settings, request_id, view.revision, tester=tester)

    assert view.step == "tests" and len(tester.prompts) == 2
    assert "AC-4 has no test case." in tester.prompts[1]


def test_4_20_two_vague_tester_plans_fail_and_leave_tests_pending(settings, request_id):
    view = at_review(settings, request_id)
    vague = {"cases": [{"criterion_id": "AC-1", "given": "g", "expect": "it works"}]}
    bad = StubClient(vague, vague)

    view = flow.accept_approach(settings, request_id, view.revision, tester=bad)

    assert view.step == "tests_pending"


def test_4_22_a_typed_case_becomes_a_draft_and_keep_saves_it_as_yours(settings, request_id):
    view = at_tests(settings, request_id)

    view = add_case(settings, request_id, view)

    assert view.step == "case_check" and view.draft_case.criterion_id == "AC-4"
    assert len(plans(settings, request_id)) == 1  # a draft saves nothing
    assert [label for _, label in view.buttons] == ["Keep this case", "Discard it"]
    assert events_of(settings, request_id, "test_case_drafted")

    view = flow.keep_case(settings, request_id, view.revision)

    assert view.step == "tests" and view.draft_case is None
    assert view.plan.plan_version == 2 and view.plan.approach_version == 2
    mine = view.plan.cases[-1]
    assert (mine.test_id, mine.source, mine.criterion_id) == ("T-10", "developer", "AC-4")
    assert view.developer_case_count == 1
    assert events_of(settings, request_id, "test_case_kept")[0].details["test_id"] == "T-10"


def test_discard_it_saves_nothing(settings, request_id):
    view = at_tests(settings, request_id)
    view = add_case(settings, request_id, view)

    view = flow.discard_case(settings, request_id, view.revision)

    assert view.step == "tests" and view.draft_case is None
    assert len(plans(settings, request_id)) == 1 and view.developer_case_count == 0
    assert events_of(settings, request_id, "test_case_discarded")


def test_4_23_a_case_that_fits_no_criterion_is_refused_with_the_spec_sentence(
    settings, request_id
):
    view = at_tests(settings, request_id)
    none = StubClient({"case": None, "note": "No match"})

    view = add_case(settings, request_id, view, "Check the colour of the button", tester=none)

    assert texts(view, "assistant")[-1] == NO_CRITERION_MESSAGE
    assert view.step == "tests" and view.draft_case is None
    assert len(plans(settings, request_id)) == 1


def test_4_23_a_sixth_developer_case_is_refused(settings, request_id):
    view = at_tests(settings, request_id)
    for _ in range(5):
        view = add_case(settings, request_id, view)
        view = flow.keep_case(settings, request_id, view.revision)
    assert view.developer_case_count == 5

    with pytest.raises(ApproachError) as refused:
        flow.request_case(settings, request_id, view.revision)

    assert str(refused.value) == "You already added 5 test cases of your own. That is the limit."
    assert [c.test_id for c in view.plan.cases][-1] == "T-14"


def test_a_failing_tester_call_for_a_case_saves_nothing(settings, request_id):
    view = at_tests(settings, request_id)
    view = flow.request_case(settings, request_id, view.revision)

    with pytest.raises(ApproachError, match="Nothing was saved"):
        flow.submit_text(settings, request_id, "an empty sheet", view.revision,
                         tester=FailingClient("down"))

    assert flow.get_approach_view(settings, request_id).step == "case_text"


def test_a_case_text_over_500_characters_is_refused(settings, request_id):
    view = at_tests(settings, request_id)
    view = flow.request_case(settings, request_id, view.revision)

    with pytest.raises(ApproachError, match="under 500 characters"):
        flow.submit_text(settings, request_id, "x" * 501, view.revision)


def test_4_24_changing_the_approach_gives_a_new_plan_and_keeps_the_developers_cases(
    settings, request_id
):
    view = at_tests(settings, request_id)
    view = add_case(settings, request_id, view)
    view = flow.keep_case(settings, request_id, view.revision)
    view = flow.request_plan_change(settings, request_id, view.revision)
    assert view.step == "change"

    view = flow.submit_text(settings, request_id, "Log skipped sheets", view.revision,
                            generator=ScriptedApproachClient("change"))

    assert view.step == "review" and view.approach.approach_version == 3
    assert view.change_count == 0  # Change the approach does not count toward the 3 (G4, G9)
    assert [c.passed for c in view.gate] == [True, True, False, False]

    view = flow.accept_approach(
        settings, request_id, view.revision, tester=ScriptedTesterClient("test_plan")
    )

    plan = view.plan
    assert plan.plan_version == 3 and plan.approach_version == 3
    assert [c.test_id for c in plan.cases if c.source == "developer"] == ["T-10"]
    assert [c.test_id for c in plan.cases if c.source == "tester"] == [
        f"T-{n}" for n in range(11, 20)
    ]
    assert not view.gate[3].passed  # the new plan must be accepted again
    assert view.gate[2].passed
    view = flow.accept_test_plan(settings, request_id, view.revision)
    assert view.request.status == "READY_TO_BUILD"


def test_text_and_buttons_at_the_wrong_tests_step_are_refused(settings, request_id):
    view = at_tests(settings, request_id)

    with pytest.raises(ApproachError, match="Please choose one of the options"):
        flow.submit_text(settings, request_id, "hello", view.revision)
    with pytest.raises(ApproachError):
        flow.keep_case(settings, request_id, view.revision)
    with pytest.raises(ApproachError):
        flow.accept_approach(settings, request_id, view.revision)


def test_5_28_get_help_is_offered_and_works_when_the_tester_stays_down(settings, request_id):
    view = at_review(settings, request_id)
    view = flow.accept_approach(
        settings, request_id, view.revision, tester=FailingClient("The Tester is down")
    )
    assert ("help", "Get help") in view.buttons

    view = flow.request_help(settings, request_id, view.revision)

    assert view.request.status == "ESCALATION_REQUIRED" and view.step == "escalated"
    assert view.open_item == "Escalated in Approach: tests_pending"
