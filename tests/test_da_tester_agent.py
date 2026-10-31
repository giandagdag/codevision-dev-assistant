import json
from datetime import UTC, datetime

from agents.da_tester_agent import (
    CASE_MARKER,
    PLAN_MARKER,
    ScriptedTesterClient,
    build_case_prompt,
    build_plan_prompt,
    draft_test_case,
    write_test_plan,
)
from pydantic_classes.da_approach_models import ApproachDecision, TestCase
from tests.da_approach_samples import good_test_plan, sample_record
from tests.da_stub_client import FailingClient, StubClient

DECISIONS = [
    ApproachDecision(
        question="Where does Excel upload live?", choice="Existing screen", custom=False,
        decided_at=datetime(2026, 10, 31, tzinfo=UTC),
    )
]


def test_4_18_the_tester_prompt_has_the_criteria_and_decisions_only():
    record = sample_record()

    prompt = build_plan_prompt(record, DECISIONS)

    assert PLAN_MARKER in prompt
    for criterion in record.acceptance_criteria:
        assert criterion.id in prompt
    assert "Where does Excel upload live? -> Existing screen" in prompt
    # No file plan, no reuse decisions, no code, no chat (decision D-B).
    for forbidden in ("excel_processor", "upload_validator", "reuse", "extend", "Discover",
                      "needs_people", "Generator"):
        assert forbidden not in prompt, forbidden


def test_the_case_prompt_has_the_plan_so_far_and_the_typed_case_between_lines():
    plan = [TestCase(test_id="T-1", criterion_id="AC-1", given="g1", expect="e1", source="tester")]

    prompt = build_case_prompt(sample_record(), DECISIONS, plan, "an empty sheet is rejected")

    assert CASE_MARKER in prompt and PLAN_MARKER not in prompt
    assert "- T-1 (AC-1): given g1; expect e1" in prompt
    assert "----------\nan empty sheet is rejected\n----------" in prompt
    assert "information only" in prompt


def test_a_good_test_plan_is_accepted():
    client = StubClient(good_test_plan())

    result = write_test_plan(client, sample_record(), DECISIONS, "")

    assert result.ok and len(result.reply.cases) == 3 and result.attempts == 1


def test_4_19_a_plan_missing_a_criterion_is_retried_once_then_accepted():
    missing = good_test_plan()
    missing["cases"].pop(1)
    client = StubClient(missing, good_test_plan())

    result = write_test_plan(client, sample_record(), DECISIONS, "")

    assert result.ok and result.attempts == 2
    assert "AC-2 has no test case." in client.prompts[1]


def test_two_bad_plans_fail():
    bad = good_test_plan()
    bad["cases"][0]["expect"] = "it works"

    result = write_test_plan(StubClient(bad, bad), sample_record(), DECISIONS, "")

    assert not result.ok and result.attempts == 2
    assert "'expect' must say something" in result.problems[0]


def test_an_unreachable_tester_is_reported():
    result = write_test_plan(FailingClient("down"), sample_record(), DECISIONS, "")

    assert not result.ok and result.message == "down"


def test_a_draft_case_is_returned_when_it_fits():
    case = {"case": {"criterion_id": "AC-2", "given": "a blank workbook",
                     "expect": "the file is rejected as empty"}}

    result = draft_test_case(StubClient(case), sample_record(), DECISIONS, [], "blank", "")

    assert result.ok and result.case.criterion_id == "AC-2"


def test_a_case_that_fits_no_criterion_comes_back_as_none_with_a_note():
    result = draft_test_case(
        StubClient({"case": None, "note": "Not about this request"}),
        sample_record(), DECISIONS, [], "something else", "",
    )

    assert result.ok and result.case is None and result.note == "Not about this request"


def test_a_draft_for_an_unknown_criterion_is_retried_then_fails():
    wrong = {"case": {"criterion_id": "AC-9", "given": "g", "expect": "a visible message appears"}}

    result = draft_test_case(StubClient(wrong, wrong), sample_record(), DECISIONS, [], "x", "")

    assert not result.ok and result.attempts == 2


def test_the_scripted_tester_covers_all_seven_example_criteria():
    plan = json.loads(ScriptedTesterClient("test_plan").complete("x").text)

    assert {case["criterion_id"] for case in plan["cases"]} == {f"AC-{n}" for n in range(1, 8)}
    assert len(plan["cases"]) == 9
    one = json.loads(ScriptedTesterClient("test_case").complete("x").text)
    assert one["case"]["criterion_id"] == "AC-4"
