"""Plain rules of the Build loop: contract, test file, Layer A, edit blocks, failure report."""

import pytest

from agents import da_build_checks as checks
from pydantic_classes.da_approach_models import TestCase
from pydantic_classes.da_build_models import (
    LABEL_NOT_PASSING,
    LABEL_WITH_WARNINGS,
    Contract,
    ContractFile,
    ContractItem,
    FileEdit,
    LayerAProblem,
    LayerAResult,
    LayerBResult,
    TestOutcome,
)

CREATE = "src/agents/excel_processor.py"
MODIFY = "src/agents/upload_validator.py"
PLANNED = [CREATE, MODIFY]
ORIGINAL = "def validate(path):\n    return True\n"


@pytest.fixture
def policy(seed_rulebook):
    return seed_rulebook.policy


def item(name="validate", kind="function", args=("path",)):
    return ContractItem(name=name, kind=kind, args=list(args), summary="does a thing")


def make_contract(**by_path):
    defaults = {CREATE: [item("read_sheets", args=("path",))], MODIFY: [item()]}
    defaults.update(by_path)
    return Contract(files=[ContractFile(path=p, items=i) for p, i in defaults.items()])


def case(number, criterion, source="tester"):
    return TestCase(
        test_id=f"T-{number}", criterion_id=f"AC-{criterion}", given="g", expect="e", source=source
    )


def context(policy, contract=None, modules=("agents", "web")):
    return checks.LayerAContext(
        planned_paths=PLANNED,
        policy=policy,
        contract=contract or make_contract(),
        codevision_modules=set(modules),
    )


def layer_a(policy, text, path=MODIFY, contract=None):
    return checks.check_layer_a({path: text}, context(policy, contract))


def codes(result):
    return [problem.code for problem in result.problems]


# --- small helpers ---


def test_module_of_path_drops_src():
    assert checks.module_of_path(MODIFY) == "agents.upload_validator"
    assert checks.module_of_path("src/da_x.py") == "da_x"


def test_public_items_lists_functions_and_classes_without_self():
    text = (
        "def run(a, b=1, *rest, key, **more):\n    pass\n"
        "def _hidden():\n    pass\n"
        "class Reader:\n    def __init__(self, path):\n        pass\n"
    )

    found = checks.public_items(text)

    assert set(found) == {"run", "Reader"}
    assert found["run"].args == ["a", "b", "rest", "key", "more"]
    assert found["Reader"].args == ["path"] and found["Reader"].kind == "class"


# --- the contract ---


def test_a_good_contract_has_no_problems():
    assert checks.find_contract_problems(make_contract(), PLANNED, {MODIFY: ORIGINAL}) == []


def test_contract_refuses_unplanned_missing_and_badly_named_items():
    contract = Contract(
        files=[
            ContractFile(path="src/agents/other.py", items=[item()]),
            ContractFile(
                path=CREATE, items=[item("class", args=("path",)), item("ok", args=("1x",))]
            ),
        ]
    )

    problems = " ".join(checks.find_contract_problems(contract, PLANNED, {}))

    assert "other.py is not a planned code file" in problems
    assert "upload_validator.py is planned but missing" in problems
    assert "'class' is not a valid Python name" in problems
    assert "argument '1x'" in problems


def test_a_modify_file_must_keep_every_existing_public_name():
    contract = make_contract(**{MODIFY: [item("other")]})

    problems = checks.find_contract_problems(contract, PLANNED, {MODIFY: ORIGINAL})

    assert any("already has 'validate'" in line for line in problems)


# --- the test file ---

CASES = [case(1, 1), case(2, 2, source="developer")]
GOOD_TESTS = '''
import unittest
from unittest import mock
from agents.upload_validator import validate


class Checks(unittest.TestCase):
    def test_t1_ac1_accepts_a_file(self):
        """A good file is accepted."""
        self.assertTrue(validate("a.xlsx"))

    def test_t2_ac2_rejects_empty(self):
        """An empty file is rejected."""
        with mock.patch("os.path.exists", return_value=False):
            self.assertTrue(validate("b.xlsx"))
'''


def test_a_good_test_file_has_no_problems(policy):
    assert checks.find_test_file_problems(GOOD_TESTS, CASES, make_contract(), policy) == []


def test_a_test_file_with_a_syntax_error_is_refused(policy):
    problems = checks.find_test_file_problems("def (:\n", CASES, make_contract(), policy)

    assert len(problems) == 1 and "syntax error" in problems[0]


def test_every_case_needs_exactly_one_method(policy):
    missing = GOOD_TESTS.replace("test_t2_ac2_rejects_empty", "test_t3_ac2_rejects_empty")
    twice = GOOD_TESTS + (
        '\n    def test_t1_ac1_again(self):\n        """Again."""\n        self.assertTrue(1)\n'
    )

    gone = " ".join(checks.find_test_file_problems(missing, CASES, make_contract(), policy))
    double = " ".join(checks.find_test_file_problems(twice, CASES, make_contract(), policy))

    assert "Case T-2 (AC-2) needs exactly one test method named test_t2_ac2_" in gone
    assert "test_t3_ac2_rejects_empty does not belong to any accepted case" in gone
    assert "Case T-1 (AC-1) needs exactly one" in double and "found 2" in double


def test_a_test_without_a_docstring_is_refused(policy):
    bare = GOOD_TESTS.replace('        """A good file is accepted."""\n', "")

    problems = checks.find_test_file_problems(bare, CASES, make_contract(), policy)

    assert any("test_t1_ac1_accepts_a_file needs a one-sentence docstring" in p for p in problems)


def test_test_ids_do_not_confuse_t1_with_t10(policy):
    tens = [case(10, 1)]
    text = GOOD_TESTS.replace("test_t1_ac1_accepts", "test_t10_ac1_accepts")

    problems = checks.find_test_file_problems(text, tens, make_contract(), policy)

    assert any("test_t2_ac2" in line for line in problems)  # the old second test is now extra
    assert not any("Case T-10" in line for line in problems)


@pytest.mark.parametrize(
    ("import_line", "fragment"),
    [
        ("import subprocess", "imports 'subprocess', which is blocked"),
        ("import requests", "imports 'requests', which is blocked"),
        ("from urllib.request import urlopen", "imports 'urllib.request', which is blocked"),
        ("import pandas", "'pandas'. Tests may import only"),
        ("from agents.upload_validator import nothing_there", "agents.upload_validator"),
        ("from agents.other import x", "'agents.other'"),
    ],
)
def test_test_file_imports_are_limited(policy, import_line, fragment):
    text = GOOD_TESTS.replace("from unittest import mock", import_line)

    problems = " ".join(checks.find_test_file_problems(text, CASES, make_contract(), policy))

    assert fragment in problems


def test_a_test_may_not_touch_files_or_call_eval_unless_it_uses_tempfile(policy):
    risky = GOOD_TESTS.replace('self.assertTrue(validate("a.xlsx"))', 'open("x.txt"); eval("1")')

    problems = " ".join(checks.find_test_file_problems(risky, CASES, make_contract(), policy))
    with_temp = risky.replace("import unittest", "import unittest\nimport tempfile")
    after = " ".join(checks.find_test_file_problems(with_temp, CASES, make_contract(), policy))

    assert "open() touches files" in problems and "eval() is not allowed" in problems
    assert "touches files" not in after and "eval() is not allowed" in after  # eval stays banned


# --- Layer A ---


def test_clean_code_passes_layer_a(policy):
    result = layer_a(policy, "import os\nimport pandas\nfrom agents import x\n\n" + ORIGINAL)

    assert result.ok and result.rulebook_checks_applied == 0


def test_a1_syntax_error(policy):
    result = layer_a(policy, "def validate(path:\n")

    assert codes(result) == ["A1"] and "Syntax error on line" in result.problems[0].text


def test_a2_unplanned_files_and_anything_under_tests_are_refused(policy):
    other = layer_a(policy, "x = 1\n", path="src/agents/surprise.py")
    tests = layer_a(policy, "x = 1\n", path="tests/cvda_2026_0001/test_x.py")
    upper = layer_a(policy, "x = 1\n", path="Tests/test_x.py")
    dots = layer_a(policy, "x = 1\n", path="src/../etc/x.py")

    assert codes(other) == ["A2"] and "not in the accepted file plan" in other.problems[0].text
    assert codes(tests) == ["A2"] and "Tests are frozen" in tests.problems[0].text
    assert codes(upper) == ["A2"] and codes(dots) == ["A2"]


def test_a3_protected_files_are_refused_even_when_planned(policy):
    path = "src/configs/llm_config.py"
    ctx = checks.LayerAContext([path], policy, make_contract(), {"agents"})

    result = checks.check_layer_a({path: "x = 1\n"}, ctx)

    assert codes(result) == ["A3"]


@pytest.mark.parametrize(
    ("line", "ok"),
    [
        ("import json", True),
        ("from pathlib import Path", True),
        ("import pandas as pd", True),
        ("import dash_mantine_components as dmc", True),
        ("from agents.helpers import go", True),
        ("from . import sibling", True),
        ("import subprocess", False),
        ("import socket", False),
        ("from http.client import HTTPConnection", False),
        ("import urllib.request", False),
        ("import some_unknown_library", False),
        ("import requests", False),  # approved in Phase 4, blocked in Phase 6: blocked wins
        ("import flask", True),  # approved, not blocked
    ],
)
def test_a4_imports(policy, line, ok):
    result = layer_a(policy, f"{line}\n\n{ORIGINAL}", contract=make_contract())
    imports = [p for p in result.problems if p.code == "A4"]

    assert (imports == []) is ok
    if not ok and "requests" in line:
        assert "blocked" in imports[0].text


@pytest.mark.parametrize(
    "call",
    [
        "eval('1')",
        "exec('x=1')",
        "compile('1','f','eval')",
        "__import__('os')",
        "os.system('ls')",
        "os.popen('ls')",
        "os.execv('/bin/ls', [])",
        "os.spawnl(0, 'x')",
    ],
)
def test_a5_risky_calls(policy, call):
    result = layer_a(policy, f"import os\n\n{ORIGINAL}\ndef extra():\n    {call}\n")

    assert "A5" in codes(result)


def test_a5_risky_names_imported_from_os_are_caught_too(policy):
    result = layer_a(policy, f"from os import system\n\n{ORIGINAL}")

    assert "A5" in codes(result)


def test_a6_contract_names_and_arguments(policy):
    wrong_args = layer_a(policy, "def validate(path, extra):\n    return 1\n")
    missing = layer_a(policy, "def other():\n    return 1\n")
    as_class = layer_a(policy, "class validate:\n    pass\n")
    right = layer_a(policy, "async def validate(path):\n    return 1\n")

    assert "must take (path) as agreed, but takes (path, extra)" in wrong_args.problems[0].text
    assert "promises function validate, but it is missing" in missing.problems[0].text
    assert codes(as_class) == ["A6"]
    assert right.ok


def test_a6_class_arguments_come_from_init(policy):
    contract = make_contract(**{MODIFY: [item("Reader", "class", ("path",))]})

    good = layer_a(
        policy, "class Reader:\n    def __init__(self, path):\n        pass\n", contract=contract
    )
    bad = layer_a(policy, "class Reader:\n    pass\n", contract=contract)

    assert good.ok and codes(bad) == ["A6"]


def test_b1_5_class_arguments_come_from_model_and_dataclass_fields(policy):
    contract = make_contract(**{MODIFY: [item("Loan", "class", ("amount", "rate"))]})
    model = (
        "from typing import ClassVar\nfrom pydantic import BaseModel\n\n"
        "class Loan(BaseModel):\n    amount: float\n    rate: float\n"
        "    _cache: int = 0\n    kind: ClassVar[str] = 'x'\n"
    )
    data = (
        "import dataclasses\n\n@dataclasses.dataclass(frozen=True)\n"
        "class Loan:\n    amount: float\n    rate: float\n"
    )
    plain = "class Loan:\n    amount: float\n    rate: float\n"

    assert layer_a(policy, model, contract=contract).ok
    assert layer_a(policy, data, contract=contract).ok
    assert codes(layer_a(policy, plain, contract=contract)) == ["A6"]


def test_every_problem_is_listed_not_just_the_first(policy):
    text = "import subprocess\n\ndef validate(path):\n    eval('1')\n"

    assert codes(layer_a(policy, text)) == ["A4", "A5"]


# --- edit blocks ---


def test_edit_blocks_that_match_once_are_applied_in_order():
    text, problems = checks.apply_edits(
        ORIGINAL,
        [
            FileEdit(find="return True", replace="return False"),
            FileEdit(find="return False", replace="return None"),
        ],
        MODIFY,
    )

    assert problems == [] and text == "def validate(path):\n    return None\n"


def test_edit_blocks_keep_crlf_line_endings():
    crlf = "def validate(path):\r\n    return True\r\n"

    text, problems = checks.apply_edits(
        crlf, [FileEdit(find="    return True\n", replace="    return 1\n    # done\n")], MODIFY
    )

    assert problems == []
    assert text == "def validate(path):\r\n    return 1\r\n    # done\r\n"
    assert "\n" not in text.replace("\r\n", "")


def test_an_edit_block_that_matches_no_place_fails_and_names_its_number():
    source = "a\nb\n"

    text, problems = checks.apply_edits(
        source,
        [FileEdit(find="a", replace="z"), FileEdit(find="nowhere", replace="q")],
        MODIFY,
    )

    assert [p.code for p in problems] == ["E1"]
    assert "Edit block 2 did not match the file" in problems[0].text
    assert "appears 0 times" in problems[0].text
    assert text == "z\nb\n"  # block 1 was applied, block 2 was not


def test_an_edit_block_that_matches_two_places_fails():
    text, problems = checks.apply_edits("a\nb\na\n", [FileEdit(find="a", replace="q")], MODIFY)

    assert "Edit block 1 did not match the file" in problems[0].text
    assert "appears 2 times" in problems[0].text
    assert text == "a\nb\na\n"  # nothing changed


# --- which files to fix, and the failure report ---

TEST_SOURCE = '''
import unittest
from agents.upload_validator import validate

class Checks(unittest.TestCase):
    def test_t1_ac1_accepts_a_file(self):
        """A good file is accepted."""
        self.assertTrue(validate("a"))

    def test_t2_ac2_rejects_empty(self):
        """An empty file is rejected.

        More detail here.
        """
        self.assertFalse(validate(""))
'''


def outcome(name, result="fail", message="False is not true", tail=()):
    return TestOutcome(name=name, result=result, message=message, traceback_tail=list(tail))


def test_files_to_fix_come_from_the_traceback_first():
    result = LayerBResult(
        tests=[
            outcome(
                "test_t1_ac1_accepts_a_file",
                tail=[
                    '  File "/tmp/sbx/src/agents/upload_validator.py", line 3, in validate',
                    "AssertionError",
                ],
            ),
            outcome("test_t2_ac2_rejects_empty", "pass"),
        ]
    )

    chosen = checks.choose_files_to_fix(
        LayerAResult(), result, PLANNED, make_contract(), TEST_SOURCE
    )

    assert chosen == [MODIFY]


def test_files_to_fix_fall_back_to_the_contract_names_the_test_uses():
    result = LayerBResult(tests=[outcome("test_t1_ac1_accepts_a_file", tail=["AssertionError"])])

    chosen = checks.choose_files_to_fix(
        LayerAResult(), result, PLANNED, make_contract(), TEST_SOURCE
    )

    assert chosen == [MODIFY]  # the test calls validate, which the contract puts in MODIFY


def test_files_to_fix_fall_back_to_every_file_and_never_a_test():
    result = LayerBResult(tests=[outcome("test_t9_ac9_unknown")])

    chosen = checks.choose_files_to_fix(
        LayerAResult(), result, PLANNED, make_contract(), TEST_SOURCE
    )

    assert chosen == PLANNED


def test_layer_a_problems_name_the_files_to_fix():
    a = LayerAResult(problems=[LayerAProblem(code="A5", path=CREATE, text="eval")])

    chosen = checks.choose_files_to_fix(a, None, PLANNED, make_contract(), TEST_SOURCE)

    assert chosen == [CREATE]


def test_failure_report_for_the_developer_has_ids_tag_expected_and_message():
    cases = [case(1, 1), case(2, 2, source="developer")]
    result = LayerBResult(
        tests=[
            outcome("test_t1_ac1_accepts_a_file", "pass"),
            outcome("test_t2_ac2_rejects_empty", message="True is not false", tail=["line a"]),
        ]
    )

    report = checks.build_failure_report(LayerAResult(), result, cases, TEST_SOURCE, [MODIFY])

    assert [i.test_id for i in report.items] == ["T-2"]
    first = report.items[0]
    assert (first.criterion_id, first.yours) == ("AC-2", True)
    assert first.expected == "An empty file is rejected."  # first docstring line only
    developer = checks.report_for_developer(report)
    assert (
        "T-2 (Yours), AC-2: expected An empty file is rejected. Got: True is not false" in developer
    )
    assert "line a" not in developer
    generator = checks.report_for_generator(report)
    assert "Traceback for T-2:" in generator and "  line a" in generator


def test_a_skipped_or_unexpected_success_test_is_a_failure_in_the_report_and_counts():
    result = LayerBResult(
        tests=[
            outcome("test_t1_ac1_accepts_a_file", "pass"),
            outcome("test_t2_ac2_rejects_empty", "skipped"),
        ],
        strict=True,
    )

    report = checks.build_failure_report(LayerAResult(), result, [], TEST_SOURCE, [MODIFY])

    assert [i.test_id for i in report.items] == ["T-2"] and result.failed == 1
    assert checks.failing_tests(result) == ["test_t2_ac2_rejects_empty"]


def test_failure_report_names_a_timeout_and_layer_a_problems():
    a = LayerAResult(problems=[LayerAProblem(code="A4", path=CREATE, text="Line 1: bad import")])
    b = LayerBResult(timed_out=True, running_test="test_t1_ac1_x")

    text = checks.report_for_developer(checks.build_failure_report(a, b, [], "", []))

    assert "Timed out. The test running was test_t1_ac1_x." in text
    assert f"{CREATE}: Line 1: bad import" in text


# --- results, size guard, tests/ paths ---


def test_result_and_label_for_a_pass_and_for_a_used_up_budget():
    assert checks.result_for(True, LABEL_WITH_WARNINGS) == ("READY_FOR_REVIEW", LABEL_WITH_WARNINGS)
    assert checks.result_for(True, "Ready for your review")[1] == "Ready for your review"
    assert checks.result_for(False, "ignored") == ("NOT_PASSING", LABEL_NOT_PASSING)
    assert LABEL_WITH_WARNINGS == "Ready with warnings" and "Approved" not in LABEL_NOT_PASSING


def test_prompt_size_guard():
    assert not checks.prompt_too_big("x" * 100, 100)
    assert checks.prompt_too_big("x" * 101, 100)


def test_paths_under_tests_are_found():
    refused = checks.code_paths_refused([MODIFY, "tests/cvda_2026_0001/test_x.py", "Tests\\a.py"])

    assert refused == ["tests/cvda_2026_0001/test_x.py", "Tests\\a.py"]


def test_codevision_modules_are_read_from_a_src_folder(tmp_path):
    (tmp_path / "agents").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "da_main.py").write_text("x = 1\n")
    (tmp_path / "notes.txt").write_text("x\n")

    assert checks.list_codevision_modules(tmp_path) == {"agents", "da_main"}


# --- reading the Generator's replies ---


def test_clean_code_reply_removes_think_blocks_and_one_whole_fence():
    assert checks.clean_code_reply("<think>x</think>\n```python\nx = 1\n```") == "x = 1\n"
    assert checks.clean_code_reply("```\na = 1\nb = 2\n```\n") == "a = 1\nb = 2\n"
    assert checks.clean_code_reply("plain = 1") == "plain = 1\n"
    assert checks.clean_code_reply("  \n ") == ""


def test_parse_edit_blocks_reads_every_block_and_allows_an_empty_replacement():
    reply = (
        "Here you go:\n"
        "<<<<<<< FIND\n    return True\n=======\n    return 1\n    # done\n>>>>>>> REPLACE\n"
        "<<<<<<< FIND\nold_line\n=======\n>>>>>>> REPLACE\n"
    )

    edits = checks.parse_edit_blocks(reply)

    assert [(e.find, e.replace) for e in edits] == [
        ("    return True", "    return 1\n    # done"),
        ("old_line", ""),
    ]


def test_parse_edit_blocks_returns_nothing_for_a_reply_without_blocks():
    assert checks.parse_edit_blocks("def validate(path):\n    return 1\n") == []
    assert checks.parse_edit_blocks("<<<<<<< FIND\n\n=======\nx\n>>>>>>> REPLACE") == []


def test_blocks_from_a_reply_apply_to_a_file(policy):
    edits = checks.parse_edit_blocks(
        "<<<<<<< FIND\n    return True\n=======\n    return False\n>>>>>>> REPLACE"
    )

    text, problems = checks.apply_edits(ORIGINAL, edits, MODIFY)

    assert problems == [] and text == "def validate(path):\n    return False\n"


@pytest.mark.parametrize(
    "code",
    [
        "import os as o\n\ndef extra():\n    o.system('ls')\n",
        "import importlib\n\ndef extra():\n    importlib.import_module('subprocess')\n",
        "import builtins\n\ndef extra():\n    builtins.eval('1')\n",
        "import os\n\ndef extra():\n    os.fork()\n",
        "import os\n\ndef extra():\n    os.posix_spawn('/bin/ls', [], {})\n",
        "import asyncio\n\ndef extra():\n    asyncio.create_subprocess_exec('ls')\n",
        "from importlib import import_module\n",
        "from builtins import eval\n",
    ],
)
def test_a5_closes_the_cheap_ways_round_the_risky_call_rule(policy, code):
    """Code review round 1: an alias, importlib, builtins, fork, posix_spawn and asyncio
    subprocess calls are refused like os.system."""
    result = layer_a(policy, ORIGINAL + "\n" + code)

    assert "A5" in codes(result)


def test_a5_still_allows_ordinary_os_and_asyncio_use(policy):
    code = "import os\nimport asyncio\n\ndef extra(p):\n    return os.path.join(p, 'x')\n"

    assert layer_a(policy, ORIGINAL + "\n" + code).ok
