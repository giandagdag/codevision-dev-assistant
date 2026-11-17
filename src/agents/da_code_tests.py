"""Code tests (Fix D1, E4): tests written AFTER the code passed its requirement tests, by an AI that
reads the code. They test the code against itself: branches, edge values, error paths.

Requirement tests (T-n) are frozen and written before the code. Code tests (C-n) are per build:
the code changed, so they are written again. The plain-code checks below are the Layer A of a
code test file; the call itself is `write_code_tests`.
"""

import ast
import re

from agents.da_approach_agent import fill_template
from agents.da_build_agent import (
    DATA_FOLDER,
    AIResult,
    BuildContext,
    _ask,
    format_cases,
    format_contract_lines,
)
from agents.da_build_checks import (
    _evidence_problems,
    _file_access_problems,
    _risky_call_problems,
    _test_import_problems,
    clean_code_reply,
    find_test_methods,
    module_of_path,
)
from agents.da_llm_client import LLMClient
from pydantic_classes.da_build_models import Contract
from pydantic_classes.da_rulebook_models import Policy

CODE_TEST_LIMIT = 15
CODE_TESTS_PROMPT = DATA_FOLDER / "da_build_code_tests_prompt.md"
CODE_TESTS_MARKER = "Task: write the code tests"
NO_CODE_NOTE = "The reply held no code. Reply with the complete test file as Python code."
_METHOD = re.compile(r"^test_c(\d+)_[a-z0-9]+(_[a-z0-9]+)*$")
_TARGETS = re.compile(r"^Targets: (\S+):(\w+) \S", re.MULTILINE)
_CONTRACT_LINE = re.compile(r"^- (src/\S+\.py): (?:function|class) (\w+)\(", re.MULTILINE)


def code_test_id(method_name: str) -> str:
    """test_c3_empty_name gives C-3; "" when the name is not a code test."""
    match = _METHOD.match(method_name)
    return f"C-{int(match.group(1))}" if match else ""


def build_code_tests_prompt(
    context: BuildContext, contract: Contract, code_files: dict[str, str]
) -> str:
    code = "\n\n".join(f"### {path}\n{text}" for path, text in code_files.items())
    values = {
        "cases": format_cases(context.cases),
        "contract": format_contract_lines(contract),
        "code": code or "(no code)",
        "limit": str(CODE_TEST_LIMIT),
    }
    return fill_template(CODE_TESTS_PROMPT, values)


def find_code_test_problems(text: str, contract: Contract, policy: Policy) -> list[str]:
    """Parses; 1 to 15 methods named test_c1_..., test_c2_... in order; each with a docstring
    `Targets: <contract file>:<name> <words>`; evidence in each; the same import, call and file
    rules as a requirement test file."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return [f"The test file has a syntax error on line {error.lineno}: {error.msg}."]
    return (
        _method_problems(tree, {entry.path for entry in contract.files})
        + _evidence_problems(tree)
        + _test_import_problems(tree, contract, policy)
        + _risky_call_problems(tree, "the test file")
        + _file_access_problems(tree)
    )


def _method_problems(tree: ast.AST, contract_paths: set[str]) -> list[str]:
    methods = find_test_methods(tree)
    if not methods:
        return ["The test file has no test method."]
    problems = []
    if len(methods) > CODE_TEST_LIMIT:
        problems.append(f"Write at most {CODE_TEST_LIMIT} code tests; found {len(methods)}.")
    numbers = []
    for name, method in methods.items():
        if not code_test_id(name):
            problems.append(f"{name}: name it test_c1_<short words>, test_c2_<short words>, ...")
            continue
        numbers.append(int(_METHOD.match(name).group(1)))
        target = _TARGETS.search(ast.get_docstring(method) or "")
        if target is None:
            problems.append(f"{name} needs a docstring line 'Targets: <file>:<function> <words>'.")
        elif target.group(1) not in contract_paths:
            problems.append(f"{name}: '{target.group(1)}' is not a file of the contract.")
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        problems.append("Number the code tests in order from 1 with no gaps and no repeats.")
    return problems


def targets_of(source: str) -> dict[str, str]:
    """{C-n: 'path:name words'} read from the Targets line of each test in a saved test file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    found = {}
    for name, method in find_test_methods(tree).items():
        target = re.search(r"^Targets: (\S.*)$", ast.get_docstring(method) or "", re.MULTILINE)
        if code_test_id(name) and target:
            found[code_test_id(name)] = target.group(1)
    return found


def keep_code_tests(new_text: str, old_source: str, keep_ids: set[str]) -> str:
    """Fix D1 (D1-6): a code test judged a code bug is kept. Its method is copied from last
    round's file into this round's file, numbered after the new ones, so the same check runs
    again on the fixed code. Anything unreadable is skipped (the new set still stands)."""
    try:
        old_tree, new_tree = ast.parse(old_source), ast.parse(new_text)
    except SyntaxError:
        return new_text
    old_methods = find_test_methods(old_tree)
    kept = [(n, m) for n, m in old_methods.items() if code_test_id(n) in keep_ids]
    if not kept:
        return new_text
    number = len(find_test_methods(new_tree))
    imports = [ast.get_source_segment(old_source, n) for n in old_tree.body
               if isinstance(n, ast.Import | ast.ImportFrom)]  # fmt: skip
    lines = ["\n\nclass KeptCodeChecks(unittest.TestCase):"]
    for _name, method in kept:
        number += 1
        body = ast.get_source_segment(old_source, method, padded=True) or ""
        lines.append(re.sub(r"def test_c\d+_", f"def test_c{number}_", body, count=1))
    # imports go first: a kept method may call a name the new file does not import
    head = "\n".join(i for i in imports if i) + "\nimport unittest\n"
    return head + new_text + "\n".join(lines) + "\n"


def write_code_tests(
    client: LLMClient, context: BuildContext, contract: Contract, code_files: dict[str, str]
) -> AIResult:
    """One call. The value is the test file text (checked), or None with the reasons."""
    prompt = build_code_tests_prompt(context, contract, code_files)

    def check(text: str):
        code = clean_code_reply(text)
        if not code.strip():
            return None, [NO_CODE_NOTE]
        return code, find_code_test_problems(code, contract, context.policy)

    return _ask(client, prompt, check, context, "build_code_tests")


# --- the fake provider (E13) ---


def is_code_tests_prompt(prompt: str) -> bool:
    return bool(re.search(rf"^{re.escape(CODE_TESTS_MARKER)}$", prompt, re.MULTILINE))


def scripted_code_tests_reply(prompt: str, switches: frozenset[str]) -> str:
    """A test file built from the contract lines in the prompt, so it fits Build new and Enhance:
    one 'can be imported and called' test per public name (at most 15). Switches add one failing
    test: code_test_bug (the code is wrong) or code_test_wrong (the test is wrong). The fake
    Tester's judgement reads the suffix of the failing test's name (Fix D1 step 3c)."""
    names = _CONTRACT_LINE.findall(prompt)[:CODE_TEST_LIMIT]
    imports = [f"from {module_of_path(path)} import {name}" for path, name in names]
    lines = ["import unittest", "", *imports, "from da_evidence import evidence", "", ""]
    lines.append("class ScriptedCodeChecks(unittest.TestCase):")
    tests = [
        (f"{name.lower()}_can_be_called", path, name, "True", f"callable({name})")
        for path, name in names
    ]
    fail_path, fail_name = names[0] if names else ("", "")
    if not names:
        switches = frozenset()  # nothing to point a failing test at
    if "code_test_bug" in switches:
        tests = tests[: CODE_TEST_LIMIT - 1] + [
            ("empty_input_fails_code_bug", fail_path, fail_name, "True", "False")
        ]
    elif "code_test_wrong" in switches:
        tests = tests[: CODE_TEST_LIMIT - 1] + [
            ("odd_expectation_fails_wrong_test", fail_path, fail_name, "True", "False")
        ]
    for number, (words, path, name, expected, actual) in enumerate(tests, start=1):
        lines += [
            f"    def test_c{number}_{words}(self):",
            f'        """Targets: {path}:{name} {words.replace("_", " ")}."""',
            f'        evidence(self, "{words}", "{name}", {expected}, {actual})',
            f"        self.assertEqual({expected}, {actual})",
            "",
        ]
    return "\n".join(lines) + "\n"
