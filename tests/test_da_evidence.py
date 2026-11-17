"""Fix D1 step 1: the evidence helper, the runner that collects it, the model (D1-1, 3, 15).

No AI and no internet. The sandbox tests use a real subprocess on the made-up reference folder."""

from pathlib import Path

import pytest

from agents import da_evidence_helper as helper
from agents.da_sandbox import run_tests
from agents.da_understand_checks import _SECRET_PATTERNS
from pydantic_classes.da_build_models import TestOutcome

REFERENCE = Path(__file__).parent / "fixtures" / "da_reference_codevision"
EXCLUDE = [".env", "*.db", ".git", "*.key", "*.pem"]


@pytest.fixture(autouse=True)
def clean_lines():
    helper.lines.clear()
    yield
    helper.lines.clear()


def record(*values):
    helper.evidence(None, "total", *values)
    return helper.lines[-1]


def sandbox(test_body: str, extra_tests: str = ""):
    text = (
        "import unittest\nfrom da_evidence import evidence\n\n\n"
        "class Checks(unittest.TestCase):\n" + test_body + extra_tests
    )
    return run_tests(
        REFERENCE, {}, "cvda_2026_0001", text, exclude=EXCLUDE, timeout_seconds=30
    )


def test_d1_1_helper_stores_given_expected_actual_and_match():
    line = record((2, 3), 5, 5)
    assert line == {
        "label": "total",
        "given": "(2, 3)",
        "expected": "5",
        "actual": "5",
        "match": True,
        "cut": False,
    }


def test_mismatch_is_recorded_as_no_match():
    assert record((2, 3), 5, 6)["match"] is False


def test_compare_that_raises_is_no_match_not_an_error():
    class Odd:
        def __eq__(self, other):
            raise RuntimeError("no compare")

    assert record(1, Odd(), 1)["match"] is False


def test_d1_3_value_of_2000_characters_is_cut_at_500_and_marked():
    line = record("x", "y", "z" * 2000)
    assert len(line["actual"]) == 500
    assert line["cut"] is True


def test_d1_15_secret_looking_value_is_hidden():
    line = record("password=hunter2", "ok", "ok")
    assert line["given"] == "[hidden]"
    assert line["expected"] == "'ok'"


def test_broken_repr_does_not_fail_the_test():
    class Broken:
        def __repr__(self):
            raise ValueError("bad")

    assert record(Broken(), 1, 1)["given"] == "<repr failed>"


def test_secret_patterns_match_the_understand_checks_list():
    # The helper stands alone in the sandbox, so its copy must never drift.
    assert helper.SECRET_PATTERNS == tuple(pattern.pattern for pattern, _what in _SECRET_PATTERNS)


def test_old_outcome_without_evidence_still_loads():
    outcome = TestOutcome.model_validate({"name": "test_x", "result": "pass"})
    assert outcome.evidence == []


def test_d1_1_sandbox_run_puts_the_evidence_line_in_the_outcome():
    result = sandbox(
        "    def test_t1_ac1_total(self):\n"
        '        """Adds."""\n'
        '        evidence(self, "total", (2, 3), 5, 2 + 3)\n'
        "        self.assertEqual(2 + 3, 5)\n"
    )
    line = result.tests[0].evidence[0]
    assert (line.given, line.expected, line.actual, line.match) == ("(2, 3)", "5", "5", True)


def test_evidence_does_not_leak_into_the_next_test():
    result = sandbox(
        "    def test_t1_ac1_a(self):\n"
        '        """A."""\n'
        '        evidence(self, "a", 1, 1, 1)\n'
        "        with self.subTest(i=1):\n"
        "            self.fail('first')\n"
        "        with self.subTest(i=2):\n"
        "            self.fail('second')\n",
        "    def test_t2_ac1_b(self):\n"
        '        """B."""\n'
        "        self.assertTrue(True)\n",
    )
    rows = {item.name: item for item in result.tests}
    assert len(rows["test_t1_ac1_a"].evidence) == 1
    assert rows["test_t2_ac1_b"].evidence == []


def test_a_test_that_never_imports_the_helper_records_no_lines():
    result = run_tests(
        REFERENCE,
        {},
        "cvda_2026_0001",
        "import unittest\n\n\nclass C(unittest.TestCase):\n"
        "    def test_t1_ac1_x(self):\n        self.assertTrue(True)\n",
        exclude=EXCLUDE,
        timeout_seconds=30,
    )
    assert result.tests[0].result == "pass"
    assert result.tests[0].evidence == []
