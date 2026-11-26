"""Fix G9 T3 (G9-7, G9-8): a test may only expect text the requirement holds."""

import ast

from agents import da_test_expectations as ex

TEST_FILE = '''
import unittest
from da_evidence import evidence


class T(unittest.TestCase):
    def test_a(self):
        """Message shown."""
        evidence(self, "msg", "x", "Error message", "Error message")
        self.assertEqual("a", "a")

    def test_b(self):
        """Backed."""
        evidence(self, "msg", "x", "File  must be CSV", "y")
        evidence(self, "err", "x", "ValueError", "ValueError")
'''
WANTED = "the system shows: file must be csv"


def test_invented_message_is_found_and_names_are_not():
    bad = ex.invented_by_method(TEST_FILE, WANTED)

    assert bad == {"test_a": ["Error message"]}  # case and spacing blind; ValueError passes


def test_reason_names_the_method_and_the_text():
    reason = ex.reason_for_writer({"test_a": ["Error message"]})

    assert "test_a expects 'Error message'" in reason


def test_dropping_a_method_keeps_the_rest_valid():
    code = ex.drop_methods(TEST_FILE, {"test_a"})

    names = [n.name for n in ast.walk(ast.parse(code)) if isinstance(n, ast.FunctionDef)]
    assert names == ["test_b"]


def test_dropping_every_method_gives_no_file():
    assert ex.drop_methods(TEST_FILE, {"test_a", "test_b"}) == ""


def test_a_backed_file_has_nothing_invented():
    assert ex.invented_by_method(TEST_FILE, WANTED + " error message") == {}
