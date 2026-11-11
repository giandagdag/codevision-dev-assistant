"""Phase 9 step 5: the plain rules for the safety net (tests 9-28, 9-33, 9-37, pure parts)."""

import pytest

from agents.da_safety_net_checks import (
    DROPPED_REASON,
    NO_CASE_REASON,
    case_id_of_method,
    complete_not_covered,
    drop_cases,
    failure_report_for_cases,
    must_pass_methods,
    proof_split,
    remove_methods,
    safety_net_problems,
    split_by_expected,
)
from pydantic_classes.da_build_models import LayerBResult, TestOutcome
from pydantic_classes.da_enhance_models import NotCovered, SafetyCase, SafetyNet
from pydantic_classes.da_request_record_models import (
    AcceptanceCriterion,
    MustNotChange,
    RequestRecord,
)

TEST_CODE = '''import unittest

from data.made_up import format_expiry


class TestNet(unittest.TestCase):
    def test_s1_plain_date(self):
        """A plain date is formatted."""
        self.assertEqual(format_expiry(1), "a")

    def test_s2_leap_day(self):
        """A leap day is kept."""
        self.assertEqual(format_expiry(2), "b")

    def test_s3_empty(self):
        """Empty gives nothing."""
        self.assertEqual(format_expiry(3), "c")
'''


@pytest.fixture
def policy(seed_rulebook):
    return seed_rulebook.policy.model_copy(update={"safety_net_max_tests": 5})


def record():
    return RequestRecord(
        request_id="CVDA-2026-0001",
        version=1,
        rulebook_version=1,
        functions_in_scope=["format_expiry", "parse_date"],
        must_not_change=[
            MustNotChange(id="NC-1", text="Dates stay"),
            MustNotChange(id="NC-2", text="Totals stay"),
        ],
        acceptance_criteria=[
            AcceptanceCriterion(id="AC-1", kind="success", given="a", when="b", then="c")
        ],
    )


def case(number, function="format_expiry", nc=(), expected=None):
    return SafetyCase(
        id=f"S-{number}",
        today_behaviour="It does a thing.",
        function=function,
        nc_ids=list(nc),
        expected_to_change=expected,
    )


def good_net():
    return SafetyNet(
        cases=[case(1, nc=["NC-1"]), case(2, expected="AC-1"), case(3)], test_code=TEST_CODE
    )


MODULES = {"data.made_up"}


# --- 9-28: reply checks ---


def test_9_28_a_good_reply_has_no_problems(policy):
    assert safety_net_problems(good_net(), record(), policy, MODULES) == []


def test_9_28_unknown_function_nc_and_ac_ids_are_named(policy):
    net = good_net()
    net.cases[0] = case(1, function="ghost", nc=["NC-9"])
    net.cases[1] = case(2, expected="AC-7")

    text = " ".join(safety_net_problems(net, record(), policy, MODULES))

    assert "ghost is not a function in scope" in text
    assert "NC-9 is not a must-not-change ID" in text
    assert "AC-7 is not a criterion ID" in text


def test_9_28_a_method_without_a_case_and_a_case_without_a_method(policy):
    net = good_net().model_copy(update={"cases": [case(1), case(2)]})
    problems = " ".join(safety_net_problems(net, record(), policy, MODULES))
    assert "test_s3_empty does not belong to any case" in problems

    net = good_net().model_copy(update={"cases": [*good_net().cases, case(4)]})
    assert "S-4 needs exactly one test method" in " ".join(
        safety_net_problems(net, record(), policy, MODULES)
    )


def test_9_28_too_many_cases_and_empty_net(policy):
    many = SafetyNet(cases=[case(n) for n in range(1, 7)], test_code=TEST_CODE)
    assert "At most 5 cases" in " ".join(safety_net_problems(many, record(), policy, MODULES))
    assert "no cases" in " ".join(safety_net_problems(SafetyNet(), record(), policy, MODULES))


def test_9_28_syntax_error_blocked_import_and_file_write(policy):
    bad = good_net().model_copy(update={"test_code": "def broken(:\n"})
    assert "syntax error" in " ".join(safety_net_problems(bad, record(), policy, MODULES))

    sneaky = TEST_CODE.replace("import unittest", "import unittest\nimport requests")
    net = good_net().model_copy(update={"test_code": sneaky})
    assert "requests" in " ".join(safety_net_problems(net, record(), policy, MODULES))

    writer = TEST_CODE.replace('self.assertEqual(format_expiry(3), "c")', 'open("x", "w")')
    net = good_net().model_copy(update={"test_code": writer})
    assert "touches files" in " ".join(safety_net_problems(net, record(), policy, MODULES))


def test_9_28_a_not_covered_item_must_be_real(policy):
    net = good_net().model_copy(update={"not_covered": [NotCovered(item="ghost", reason="x")]})
    assert "ghost" in " ".join(safety_net_problems(net, record(), policy, MODULES))


def test_method_names_map_to_case_ids():
    assert case_id_of_method("test_s12_some_words") == "S-12"
    assert case_id_of_method("test_t1_ac1_x") is None


# --- 9-33: not covered, plain code ---


def test_9_33_unproven_function_and_nc_item_are_added(policy):
    net = SafetyNet(cases=[case(1, nc=["NC-1"])], test_code=TEST_CODE)

    done = complete_not_covered(net, record())

    assert {(i.item, i.reason) for i in done.not_covered} == {
        ("parse_date", NO_CASE_REASON),
        ("NC-2", NO_CASE_REASON),
    }


def test_9_33_the_testers_own_reason_stays_and_nothing_is_listed_twice():
    net = SafetyNet(
        cases=[case(1, nc=["NC-1", "NC-2"])],
        not_covered=[NotCovered(item="parse_date", reason="a Dash screen layout")],
    )

    done = complete_not_covered(net, record())

    assert [(i.item, i.reason) for i in done.not_covered] == [
        ("parse_date", "a Dash screen layout")
    ]


def test_9_33_a_covered_item_the_tester_listed_is_taken_off():
    net = SafetyNet(
        cases=[case(1, nc=["NC-1", "NC-2"]), case(2, function="parse_date")],
        not_covered=[NotCovered(item="NC-2", reason="unsure")],
    )

    assert complete_not_covered(net, record()).not_covered == []


# --- proof ---


def outcome(name, result="pass", tail=None):
    return TestOutcome(name=name, result=result, traceback_tail=tail or [])


def test_proof_split_marks_passing_and_failing_cases():
    result = LayerBResult(
        tests=[
            outcome("test_s1_plain_date"),
            outcome("test_s2_leap_day", "fail", ["AssertionError: 'x' != 'b'"]),
            outcome("test_s3_empty", "error"),
        ]
    )

    proven, failing = proof_split(good_net(), result)

    assert proven == ["S-1"]
    assert failing == ["S-2", "S-3"]
    report = failure_report_for_cases(good_net(), result, failing)
    assert "S-2: fail: AssertionError" in report


def test_proof_split_a_timeout_counts_the_unfinished_cases_as_failing():
    result = LayerBResult(
        timed_out=True, running_test="test_s2_leap_day", tests=[outcome("test_s1_plain_date")]
    )

    proven, failing = proof_split(good_net(), result)

    assert (proven, failing) == (["S-1"], ["S-2", "S-3"])
    assert "time limit while running test_s2_leap_day" in failure_report_for_cases(
        good_net(), result, failing
    )


def test_proof_split_a_run_that_never_started_proves_nothing():
    proven, failing = proof_split(good_net(), LayerBResult(ran=False, error="no sandbox"))

    assert proven == []
    assert failing == ["S-1", "S-2", "S-3"]


def test_9_32_a_dropped_case_goes_to_not_covered_and_the_rest_stays_byte_for_byte():
    net = good_net()

    dropped = drop_cases(net, ["S-2"])

    assert [c.id for c in dropped.cases] == ["S-1", "S-3"]
    assert [(i.item, i.reason) for i in dropped.not_covered] == [("format_expiry", DROPPED_REASON)]
    assert "test_s2_leap_day" not in dropped.test_code
    assert "test_s1_plain_date" in dropped.test_code
    # The kept methods are the accepted lines, unchanged.
    assert dropped.test_code == TEST_CODE.replace(
        '    def test_s2_leap_day(self):\n        """A leap day is kept."""\n'
        '        self.assertEqual(format_expiry(2), "b")\n',
        "",
    )


def test_a_dropped_nc_case_lists_its_nc_item_too():
    two_methods = TEST_CODE.split("    def test_s3")[0]
    net = SafetyNet(cases=[case(1, nc=["NC-1"]), case(2)], test_code=two_methods)

    dropped = drop_cases(net, ["S-1"])

    assert {i.item for i in dropped.not_covered} == {"format_expiry", "NC-1"}


# --- 9-37: the frozen file ---


def test_9_37_expected_to_change_methods_are_left_out_of_layer_b():
    net = good_net()

    must_text, expected_text = split_by_expected(net)

    assert "test_s2_leap_day" not in must_text
    assert "test_s1_plain_date" in must_text and "test_s3_empty" in must_text
    assert "test_s2_leap_day" in expected_text
    assert "test_s1_plain_date" not in expected_text
    assert must_pass_methods(net) == ["test_s1_plain_date", "test_s3_empty"]


def test_9_37_the_kept_methods_are_byte_for_byte_the_accepted_text():
    must_text, _ = split_by_expected(good_net())

    for name in ("test_s1_plain_date", "test_s3_empty"):
        block = TEST_CODE.split(f"    def {name}")[1].split("\n    def ")[0].rstrip("\n")
        assert block in must_text


def test_9_37_a_half_with_no_method_is_empty_text():
    only_must = SafetyNet(cases=[case(1)], test_code=TEST_CODE.split("    def test_s2")[0])
    all_expected = SafetyNet(
        cases=[case(1, expected="AC-1")], test_code=TEST_CODE.split("    def test_s2")[0]
    )

    assert split_by_expected(only_must)[1] == ""
    assert split_by_expected(all_expected)[0] == ""


def test_remove_methods_with_nothing_to_remove_returns_the_same_text():
    assert remove_methods(TEST_CODE, []) == TEST_CODE
