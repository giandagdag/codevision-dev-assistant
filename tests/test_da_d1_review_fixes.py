"""Fix D1 code review round 1: kept code bugs, Targets in the report, secrets in messages,
dropped tests are not handoff zones. No AI, no internet."""

import ast

from agents.da_code_tests import keep_code_tests, targets_of
from agents.da_test_report import _row
from pydantic_classes.da_build_models import TestOutcome

OLD = '''
import unittest
from da_evidence import evidence


class Checks(unittest.TestCase):
    def test_c1_fine(self):
        """Targets: src/a.py:f fine."""
        evidence(self, "x", 1, 1, 1)

    def test_c2_empty_input_fails_code_bug(self):
        """Targets: src/a.py:f empty input."""
        evidence(self, "x", 1, 1, 2)
        self.assertEqual(1, 2)
'''
NEW = '''
import unittest
from da_evidence import evidence


class Checks(unittest.TestCase):
    def test_c1_other(self):
        """Targets: src/a.py:g other."""
        evidence(self, "x", 1, 1, 1)
'''


def test_targets_of_reads_the_targets_line():
    assert targets_of(OLD)["C-2"] == "src/a.py:f empty input."
    assert targets_of("not python (") == {}


def test_a_kept_code_bug_runs_again_numbered_after_the_new_tests():
    merged = keep_code_tests(NEW, OLD, {"C-2"})
    names = [n.name for n in ast.walk(ast.parse(merged)) if isinstance(n, ast.FunctionDef)]
    assert names == ["test_c1_other", "test_c2_empty_input_fails_code_bug"]
    assert targets_of(merged)["C-2"].startswith("src/a.py:f")


def test_nothing_kept_leaves_the_new_file_alone():
    assert keep_code_tests(NEW, OLD, set()) == NEW
    assert keep_code_tests(NEW, "", {"C-2"}) == NEW


def test_a_secret_in_a_failure_message_is_hidden_in_the_report_row():
    outcome = TestOutcome(name="test_c1_x", result="fail", message="'token=abc123' != 'x'")
    assert _row(outcome, None, "")["message"] == "[hidden]"


def test_a_code_row_shows_its_targets_line_as_the_criterion():
    from agents.da_test_report import build_report

    outcome = TestOutcome(name="test_c2_x", result="pass")
    targets = {"C-2": "src/a.py:f"}
    report = build_report({}, [], [outcome], [], {}, "", False, [], [], targets=targets)
    code = next(s for s in report["sections"] if s["key"] == "code")
    assert code["rows"][0]["criterion"] == "src/a.py:f"


def test_a_dropped_test_line_is_not_a_handoff_zone():
    from agents.da_tester_review import DROPPED_TEST_PREFIX

    warnings = [DROPPED_TEST_PREFIX + ", C-1: x", "Touches the money zone: ..."]
    kept = [w for w in warnings if not w.startswith(DROPPED_TEST_PREFIX)]
    assert kept == [warnings[1]]
