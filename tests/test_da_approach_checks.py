import pytest

from agents.da_approach_checks import (
    CHANGE,
    NO_CRITERION_MESSAGE,
    PROPOSE,
    SETTLE,
    case_text_problem,
    change_text_problem,
    compute_gate,
    compute_warnings,
    custom_answer_problem,
    find_approach_problems,
    find_test_case_problems,
    find_test_plan_problems,
    folder_for_tests,
    gate_problem_lines,
    limit_reason_problem,
)
from pydantic_classes.da_approach_models import (
    ApproachReply,
    ApproachState,
    ApproachVersion,
    TestCase,
    TestCaseReply,
    TestPlanReply,
    TestPlanVersion,
)
from pydantic_classes.da_discovery_models import DiscoveryResult, Finding, SearchHit
from pydantic_classes.da_request_record_models import AcceptanceCriterion, RequestRecord
from pydantic_classes.da_rulebook_models import Policy

REQUEST_ID = "CVDA-2026-0001"


@pytest.fixture
def policy(seed_rulebook) -> Policy:
    return seed_rulebook.policy


def hit(number, path="app/upload/validator.py", symbol="check"):
    return SearchHit(
        hit_id=number, source_path=path, symbol=symbol, kind="code", score=0.5, mode="exact"
    )


@pytest.fixture
def discovery():
    return DiscoveryResult(
        request_id=REQUEST_ID,
        round=1,
        record_version=1,
        rulebook_version=1,
        search_provider="fake",
        queries=[],
        hits=[hit(1), hit(2, symbol="other")],
        findings=[
            Finding(
                kind="existing_capability", title="t", explanation="e", hit_ids=[1],
                confidence="high",
            ),
            Finding(
                kind="similar_implementation", title="t", explanation="e", hit_ids=[2],
                confidence="low",
            ),
            Finding(
                kind="affected_area", title="t", explanation="e", hit_ids=[], confidence="low"
            ),
        ],
        limitations=[],
        summary_source="ai",
    )


def reply(**changes):
    values = {
        "summary": "Add Excel support",
        "files": [
            {"path": "src/agents/excel_processor.py", "action": "create", "purpose": "Read",
             "reuses": [1]}
        ],
        "reuse_decisions": [
            {"hit_id": 1, "decision": "reuse", "reason": "Same pattern"},
            {"hit_id": 2, "decision": "ignore", "reason": "Not needed"},
        ],
        "libraries": ["openpyxl", "json"],
    }
    values.update(changes)
    return ApproachReply.model_validate(values)


def file_entry(path, action="create"):
    return {"path": path, "action": action, "purpose": "p"}


def problems(policy, discovery, call=PROPOSE, answered=frozenset(), **changes):
    return find_approach_problems(reply(**changes), policy, discovery, set(answered), call)


def test_a_good_reply_has_no_problems(policy, discovery):
    assert problems(policy, discovery) == []


@pytest.mark.parametrize(
    ("path", "word"),
    [
        ("../x.py", "'..'"),
        ("src/agents/../../x.py", "'..'"),
        ("/etc/x.py", "relative"),
        ("C:/x/y.py", "relative"),
        ("C:\\x\\y.py", "relative"),
        ("src/other/x.py", "allowed folder"),
    ],
)
def test_4_3_bad_paths_each_get_their_own_note(policy, discovery, path, word):
    found = problems(policy, discovery, files=[file_entry(path)])

    assert len(found) == 1 and word in found[0]


def test_backslashes_become_slashes(policy, discovery):
    assert problems(policy, discovery, files=[file_entry("src\\agents\\excel_reader.py")]) == []


def test_4_4a_a_path_under_tests_is_the_testers(policy, discovery):
    found = problems(policy, discovery, files=[file_entry("tests/test_x.py")])

    assert found == ["tests/test_x.py: Tests are written by the Tester, not planned here. "
                     "Remove it."]


def test_4_4b_a_protected_file_is_refused_and_needs_people_is_allowed(policy, discovery):
    found = problems(policy, discovery, files=[file_entry("src/web/web_server.py", "modify")])
    assert found == [
        "src/web/web_server.py is protected. List it under needs_people with the reason instead."
    ]

    ok = problems(
        policy, discovery, needs_people=[{"path": "src/web/web_server.py", "reason": "Add route"}]
    )
    assert ok == []


def test_protected_pattern_with_a_folder_matches_any_depth_and_case(policy, discovery):
    found = problems(policy, discovery, files=[file_entry("src/agents/.ENV.local", "modify")])

    assert "protected" in found[0]


def test_4_5_new_file_naming(policy, discovery):
    bad = problems(policy, discovery, files=[file_entry("src/agents/Upload Excel.py")])
    good = problems(policy, discovery, files=[file_entry("src/agents/excel_processor.py")])

    assert len(bad) == 1 and "must match" in bad[0]
    assert good == []


def test_naming_is_not_checked_for_modify(policy, discovery):
    assert problems(policy, discovery, files=[file_entry("src/agents/Old Name.py", "modify")]) == []


def test_duplicate_paths_are_refused(policy, discovery):
    found = problems(
        policy, discovery,
        files=[file_entry("src/agents/a.py"), file_entry("src/agents/A.py", "modify")],
    )

    assert found == ["src/agents/A.py is listed more than once."]


def test_4_6_a_hit_that_does_not_exist_is_refused(policy, discovery):
    files = [{**file_entry("src/agents/a.py"), "reuses": [9]}]
    found = problems(policy, discovery, files=files)
    assert any("hit 9" in p for p in found)

    decisions = [
        {"hit_id": 1, "decision": "reuse", "reason": "r"},
        {"hit_id": 2, "decision": "reuse", "reason": "r"},
        {"hit_id": 9, "decision": "reuse", "reason": "r"},
    ]
    assert any("hit 9" in p for p in problems(policy, discovery, reuse_decisions=decisions))


def test_4_7_every_cited_match_hit_needs_exactly_one_decision(policy, discovery):
    only_one = [{"hit_id": 1, "decision": "reuse", "reason": "r"}]
    found = problems(policy, discovery, reuse_decisions=only_one)
    assert found == ["Discover hit 2 needs a reuse decision (reuse, extend or ignore)."]

    twice = [{"hit_id": h, "decision": "reuse", "reason": "r"} for h in (1, 1, 2)]
    assert any("hit 1 has 2" in p for p in problems(policy, discovery, reuse_decisions=twice))


def test_4_8_libraries(policy, discovery):
    ok = problems(policy, discovery, libraries=["openpyxl", "json", "Dash-Mantine-Components"])
    bad = problems(policy, discovery, libraries=["openpyxl", "json", "evilkit"])

    assert ok == []
    assert len(bad) == 1 and "evilkit" in bad[0]


def choice(question, options=("A", "B")):
    return {"question": question, "impact": "i", "options": list(options)}


def test_design_choice_rules(policy, discovery):
    four = [choice(f"Q{n}") for n in range(4)]
    # The model allows 3 by shape; the policy limit is checked here, so lower it to prove it.
    low = policy.model_copy(update={"max_design_choices": 1})
    assert any("limit is 1" in p for p in problems(low, discovery, design_choices=four[:2]))
    assert problems(policy, discovery, design_choices=four[:3]) == []

    twice = problems(policy, discovery, design_choices=[choice("Where?"), choice("where?")])
    assert any("asked twice" in p for p in twice)

    again = problems(policy, discovery, answered={"where?"}, design_choices=[choice("Where?")])
    assert any("already answered" in p for p in again)


def test_4_14_a_settle_reply_with_a_choice_is_refused(policy, discovery):
    found = problems(policy, discovery, call=SETTLE, design_choices=[choice("Where?")])

    assert found == [
        "The settled plan must have no design choices. Decide them from the answers."
    ]
    assert problems(policy, discovery, call=CHANGE, design_choices=[choice("Where?")]) == []


def test_code_in_any_text_field_is_refused(policy, discovery):
    found = problems(policy, discovery, summary="import os\nprint(1)")

    assert len(found) == 1 and "contains code" in found[0]
    files = [{**file_entry("src/agents/a.py"), "purpose": "```x```"}]
    assert any("contains code" in p for p in problems(policy, discovery, files=files))


# --- warnings and zones ---


def test_4_9_modify_of_a_path_no_hit_has_is_a_warning(policy, discovery):
    plan = reply(files=[file_entry("src/agents/upload_check.py", "modify")])

    warnings, zones = compute_warnings(plan, policy, discovery)

    assert warnings == [
        "src/agents/upload_check.py: Not found in Discover. It will be checked against your "
        "workspace in Phase 5."
    ]
    assert zones == []


def test_a_modify_of_a_discover_hit_path_has_no_warning(policy):
    found = DiscoveryResult(
        request_id=REQUEST_ID, round=1, record_version=1, rulebook_version=1,
        search_provider="fake", queries=[], hits=[hit(1, path="src/agents/known.py")],
        findings=[], limitations=[], summary_source="ai",
    )

    assert compute_warnings(reply(files=[file_entry("src/agents/KNOWN.py", "modify")]), policy,
                            found) == ([], [])


def test_4_10_a_login_file_touches_the_login_zone(policy, discovery):
    plan = reply(files=[file_entry("src/layouts/login_page.py")])

    warnings, zones = compute_warnings(plan, policy, discovery)

    assert zones == ["Login"]
    assert (
        "Touches Login. A named senior becomes a required reviewer at the pull request."
        in warnings
    )


def test_4_11_needs_people_is_a_warning(policy, discovery):
    plan = reply(needs_people=[{"path": "src/web/web_server.py", "reason": "Add a route"}])

    warnings, _ = compute_warnings(plan, policy, discovery)

    assert "A person must change src/web/web_server.py: Add a route." in warnings


def test_too_many_files_is_a_warning(policy, discovery):
    files = [file_entry(f"src/agents/f{n}.py") for n in range(6)]

    warnings, _ = compute_warnings(reply(files=files), policy, discovery)

    assert "6 code files; the limit is 5. Splitting the request is safer." in warnings


def test_tests_folder_line():
    assert folder_for_tests("CVDA-2026-0001") == "tests/cvda_2026_0001/"


# --- the Tester ---


def make_record(count=3):
    criteria = [
        AcceptanceCriterion(
            id=f"AC-{n}", kind="failure" if n == 3 else "success", given="g", when="w",
            then="something visible happens",
        )
        for n in range(1, count + 1)
    ]
    return RequestRecord(
        request_id=REQUEST_ID, rulebook_version=1, acceptance_criteria=criteria
    )


def case(criterion="AC-1", given="a workbook with one sheet", expect="the rows reach ingestion"):
    return {"criterion_id": criterion, "given": given, "expect": expect}


def plan_reply(*cases):
    return TestPlanReply.model_validate({"cases": list(cases)})


def test_a_good_test_plan_has_no_problems():
    reply_ = plan_reply(case("AC-1"), case("AC-2"), case("AC-3"))

    assert find_test_plan_problems(reply_, make_record(), "") == []


def test_4_19_a_criterion_without_a_case_is_refused():
    found = find_test_plan_problems(plan_reply(case("AC-1"), case("AC-3")), make_record(), "")

    assert found == ["AC-2 has no test case."]


def test_more_than_three_cases_per_criterion_is_refused():
    cases = [case("AC-1")] * 4 + [case("AC-2"), case("AC-3")]

    found = find_test_plan_problems(plan_reply(*cases), make_record(), "")

    assert found == ["AC-1 has 4 test cases. The limit is 3."]


def test_a_case_for_an_unknown_criterion_is_refused():
    found = find_test_plan_problems(
        plan_reply(case("AC-1"), case("AC-2"), case("AC-3"), case("AC-9")), make_record(), ""
    )

    assert found == ["Case 4 (AC-9): AC-9 is not a criterion of this request."]


@pytest.mark.parametrize("expect", ["it works", "ok", "works as expected", "fine"])
def test_4_20_a_vague_expect_is_refused(expect):
    found = find_test_plan_problems(
        plan_reply(case("AC-1", expect=expect), case("AC-2"), case("AC-3")), make_record(), ""
    )

    assert len(found) == 1 and "'expect' must say something" in found[0]


def test_code_and_invented_names_in_a_case_are_refused():
    bad = case("AC-1", given="import os", expect="check_type(file) returns false")
    found = find_test_plan_problems(
        plan_reply(bad, case("AC-2"), case("AC-3")), make_record(), "check the type"
    )

    assert any("contains code" in p for p in found)
    assert any("check_type(file)" in p for p in found)


def test_a_name_the_developer_typed_is_allowed():
    named = case("AC-1", expect="upload.check_type rejects the file")

    found = find_test_plan_problems(
        plan_reply(named, case("AC-2"), case("AC-3")), make_record(), "use upload.check_type"
    )

    assert found == []


def test_a_single_case_is_checked_without_coverage_rules():
    one = TestCaseReply.model_validate(case("AC-2"))

    assert find_test_case_problems(one, make_record(), "") == []
    bad = TestCaseReply.model_validate(case("AC-8", expect="ok"))
    assert len(find_test_case_problems(bad, make_record(), "")) == 2
    assert "does not match any acceptance criterion" in NO_CRITERION_MESSAGE


# --- typed text ---


def test_custom_answer_limit():
    assert custom_answer_problem("x" * 300) is None
    assert custom_answer_problem("x" * 301) == (
        "Please keep your own answer under 300 characters, or choose a button."
    )
    assert custom_answer_problem("  ") == "Please type a message first."
    assert "looks like it contains" in custom_answer_problem("password: hunter2")


def test_change_case_and_reason_limits():
    assert change_text_problem("x" * 1000) is None
    assert "under 1,000" in change_text_problem("x" * 1001)
    assert case_text_problem("x" * 500) is None
    assert "under 500" in case_text_problem("x" * 501)
    assert "10 to 300" in limit_reason_problem("short")
    assert limit_reason_problem("a" * 12) is None
    assert "10 to 300" in limit_reason_problem("a" * 301)


# --- the gate ---


def make_version(**changes):
    values = {
        "request_id": REQUEST_ID, "approach_version": 2, "source": "settled",
        "record_version": 1, "rulebook_version": 1, "discovery_round": 2,
        "plan": ApproachReply(summary="s"),
    }
    values.update(changes)
    return ApproachVersion(**values)


def make_test_plan(approach=2, ids=("AC-1", "AC-2", "AC-3"), number=1):
    cases = [
        TestCase(test_id=f"T-{n}", criterion_id=c, given="g", expect="e", source="tester")
        for n, c in enumerate(ids, start=1)
    ]
    return TestPlanVersion(
        request_id=REQUEST_ID, plan_version=number, approach_version=approach, cases=cases,
        source_of_change="tester_plan",
    )


def gate(**changes):
    values = {
        "record": make_record(), "request_version": 1, "approach": make_version(),
        "saved_rounds": 2, "confirmed_round": 2,
        "state": ApproachState(
            request_id=REQUEST_ID, accepted_approach_version=2, accepted_plan_version=1
        ),
        "plan": make_test_plan(),
    }
    values.update(changes)
    return compute_gate(**values)


def test_4_25_all_four_checks_true():
    checks = gate()

    assert [c.passed for c in checks] == [True] * 4
    assert gate_problem_lines(checks) == []


def test_4_26_a_plan_for_an_older_approach_names_the_false_check():
    checks = gate(plan=make_test_plan(approach=1))

    assert [c.passed for c in checks] == [True, True, True, False]
    assert gate_problem_lines(checks) == [
        "Test plan accepted: The accepted test plan was written for an older approach."
    ]


def test_each_gate_check_can_fail_alone():
    assert not gate(approach=make_version(record_version=2))[0].passed
    assert not gate(confirmed_round=1)[1].passed
    assert not gate(saved_rounds=3)[1].passed
    older = ApproachState(request_id=REQUEST_ID, accepted_approach_version=1,
                          accepted_plan_version=1)
    assert not gate(state=older)[2].passed
    unaccepted = ApproachState(request_id=REQUEST_ID, accepted_approach_version=2)
    assert gate(state=unaccepted)[3].detail == "The latest test plan has not been accepted."
    assert gate(plan=make_test_plan(ids=("AC-1", "AC-2")))[3].detail == "AC-3 has no test case."
    assert gate(plan=None)[3].detail == "There is no test plan yet."
    assert [c.passed for c in gate(approach=None, state=None, plan=None)] == [False] * 4


def test_5_30_a_round_built_from_an_older_record_version_fails_check_2_in_plain_words():
    # The approach is for v2 and the round is the confirmed one, but the round was built from v1.
    checks = gate(
        request_version=2,
        approach=make_version(record_version=2),
        confirmed_round_record_version=1,
    )

    assert [c.passed for c in checks] == [True, False, True, True]
    assert checks[1].detail == (
        "The confirmed Discover round was built from an older version of the request."
    )


def test_5_30_a_round_built_from_the_current_record_version_passes_check_2():
    checks = gate(confirmed_round_record_version=1)

    assert checks[1].passed and checks[1].detail == "Round 2 confirmed"
