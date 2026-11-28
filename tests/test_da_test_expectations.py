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


def test_a_single_message_word_is_checked_but_code_names_pass():
    """Finish review 1, Must 3: 'ERROR' is invented when the requirement says NO INPUT PROVIDED."""
    code = (
        "class T:\n"
        "    def test_x(self):\n"
        "        self.assertIn('ERROR', out)\n"
        "        self.assertIn('ValueError', out)\n"
        "        self.assertIn('items', out)\n"
    )

    # Finish review 3: a lower-case one-word value is checked too
    bad = {"test_x": ["ERROR", "items"]}
    assert ex.invented_by_method(code, "output NO INPUT PROVIDED") == bad
    half = ex.invented_by_method(code, "output NO INPUT PROVIDED and error")
    assert half == {"test_x": ["items"]}
    assert ex.invented_by_method(code, "error items") == {}


def test_contract_names_and_arguments_count_as_requirement_text():
    from types import SimpleNamespace

    from pydantic_classes.da_build_models import Contract, ContractFile, ContractItem

    item = ContractItem(name="summarise", kind="function", args=["totals"], summary="Adds up")
    contract = Contract(files=[ContractFile(path="src/a.py", items=[item])])
    record = SimpleNamespace(acceptance_criteria=[], exceptions=[])

    wanted = ex.requirement_text(record, [], contract)

    code = "class T:\n    def test_x(self):\n        self.assertIn('totals', out)\n"
    assert ex.invented_by_method(code, wanted) == {}
    assert ex.invented_by_method(code.replace("totals", "balance"), wanted) != {}


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


def test_assert_equal_checks_the_literal_on_either_side():
    code = "class T:\n    def test_x(self):\n        self.assertEqual('Error message', out)\n"

    assert ex.invented_by_method(code, "nothing") == {"test_x": ["Error message"]}


def test_replace_methods_swaps_only_the_named_ones():
    old = "class T:\n    def test_a(self):\n        x = 1\n\n    def test_b(self):\n        y = 2\n"
    new = "class T:\n    def test_a(self):\n        x = 9\n\n    def test_b(self):\n        y = 8\n"

    merged = ex.replace_methods(old, new, {"test_a"})

    assert "x = 9" in merged and "y = 2" in merged and "x = 1" not in merged
    ast.parse(merged)
