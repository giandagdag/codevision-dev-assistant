"""Phase 9 step 14a: what the Generator sees of a target file, and the frozen test set that holds
the safety net (tests 9-37 pure part, 9-38 pure part). The build loop calls these two helpers."""

import ast

from agents.da_build_checks import find_test_methods
from agents.da_enhance_build_checks import frozen_set_with_net, scoped_view
from pydantic_classes.da_enhance_models import SafetyCase, SafetyNet

SOURCE = '''import os
from datetime import date


def format_expiry(day, style):
    """Format a day."""
    return str(day) + style


def parse_date(text, strict=False):
    return text.strip()


class Report:
    def title(self):
        return "t"
'''

CRITERION_TESTS = '''import unittest


class Checks(unittest.TestCase):
    def test_t1_ac1_month_name(self):
        """Month shows as a name."""
        self.assertTrue(True)
'''

NET_CODE = '''import unittest

import limits as target


class SafetyNetChecks(unittest.TestCase):
    def test_s1_day_text(self):
        """The day is shown with two digits."""
        self.assertEqual(target.format_expiry(1, 2, 2026), "01/02/2026")

    def test_s2_days_left(self):
        """Days left never go below zero."""
        self.assertEqual(target.days_left(1, 9), 0)
'''


def net(expected_for_s2=None):
    return SafetyNet(
        cases=[
            SafetyCase(id="S-1", today_behaviour="Two digits.", function="format_expiry"),
            SafetyCase(
                id="S-2", today_behaviour="Never below zero.", function="days_left",
                expected_to_change=expected_for_s2,
            ),
        ],
        test_code=NET_CODE,
    )


# --- what the Generator sees ---


def test_the_view_holds_scope_bodies_imports_and_other_signatures_only():
    view = scoped_view("src/a.py", SOURCE, ["format_expiry"])

    assert "import os\nfrom datetime import date" in view
    assert "### format_expiry (lines 5 to 7)" in view
    body = 'def format_expiry(day, style):\n    """Format a day."""\n    return str(day) + style'
    assert body in view
    # The other function and the class method show a name and arguments, never a body.
    assert "def parse_date(text, strict)" in view and "def Report.title(self)" in view
    assert "return text.strip()" not in view and 'return "t"' not in view


def test_a_class_in_scope_is_shown_once_with_its_methods():
    view = scoped_view("src/a.py", SOURCE, ["Report"])

    assert view.count("### ") == 1 and "### Report (lines 14 to 16)" in view
    assert 'return "t"' in view


def test_a_view_of_a_file_that_does_not_parse_still_answers():
    view = scoped_view("src/a.py", "def broken(:\n", ["broken"])

    assert "## Functions in scope" in view


# --- the frozen set ---


def test_9_37_the_frozen_set_is_the_criterion_tests_then_the_whole_net_when_nothing_changes():
    text, net_methods, expected = frozen_set_with_net(CRITERION_TESTS, net())

    assert text.startswith(CRITERION_TESTS.rstrip("\n"))
    assert NET_CODE.rstrip("\n") in text  # the accepted net, byte for byte
    assert net_methods == ["test_s1_day_text", "test_s2_days_left"] and expected == []
    names = list(find_test_methods(ast.parse(text)))
    assert names == ["test_t1_ac1_month_name", *net_methods]


def test_9_38_a_test_expected_to_change_is_kept_by_name_but_left_out_of_the_set():
    text, net_methods, expected = frozen_set_with_net(CRITERION_TESTS, net("AC-1"))

    assert net_methods == ["test_s1_day_text"] and expected == ["test_s2_days_left"]
    assert "test_s2_days_left" not in text and "test_s1_day_text" in text
    ast.parse(text)  # one valid file the sandbox can run


def test_a_net_whose_every_test_is_expected_to_change_adds_nothing_to_the_set():
    only = SafetyNet(
        cases=[SafetyCase(id="S-1", today_behaviour="x", function="f", expected_to_change="AC-1")],
        test_code=NET_CODE.split("    def test_s2")[0],
    )

    text, net_methods, expected = frozen_set_with_net(CRITERION_TESTS, only)

    assert text == CRITERION_TESTS and net_methods == [] and expected == ["test_s1_day_text"]
