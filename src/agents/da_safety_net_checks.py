"""Plain-code rules for the safety net (Phase 9, spec section 8). No AI, no database, no sandbox:
the flow calls these with made-up values in tests.

AS400 picture: the regression test pack you run before touching a production program. Plain code
checks the Tester's pack, adds what it did not cover, and cuts the pack into two halves: tests
that must still pass, and tests that are expected to change.
"""

import ast
import re
import sys

from agents.da_build_checks import (
    _file_access_problems,
    _risky_call_problems,
    find_test_methods,
    imported_modules,
    module_of_path,
)
from pydantic_classes.da_build_models import LayerBResult
from pydantic_classes.da_enhance_models import NotCovered, SafetyCase, SafetyNet
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Policy

DROPPED_REASON = "Test could not be made to pass on today's code"
NO_CASE_REASON = "No test of today's behaviour passed for this."
UNABLE_TEXT = "The safety net could not be written."
_METHOD_NAME = re.compile(r"^test_s(\d+)_[a-z0-9]+(_[a-z0-9]+)*$")


def method_prefix(case_id: str) -> str:
    """S-3 gives test_s3_ (spec section 8, step 2)."""
    return f"test_s{case_id.split('-')[1]}_"


def case_id_of_method(name: str) -> str | None:
    """test_s3_empty_input gives S-3; None when the name has no case in it."""
    match = _METHOD_NAME.match(name)
    return f"S-{match.group(1)}" if match else None


# --- reply checks (spec section 8, step 3) ---


def safety_net_problems(
    net: SafetyNet,
    record: RequestRecord,
    policy: Policy,
    code_modules: set[str] | None = None,
) -> list[str]:
    """Every reason the Tester's reply cannot be used. Empty list = fine. The problems are
    sent back to the Tester as a retry note. `code_modules` are the dotted modules of the
    target files, which the tests may import."""
    problems = _case_problems(net, record, policy)
    if not net.test_code.strip():
        return [*problems, "test_code is empty."]
    try:
        tree = ast.parse(net.test_code)
    except SyntaxError as error:
        return [*problems, f"The test file has a syntax error on line {error.lineno}: {error.msg}."]
    return (
        problems
        + _method_problems(tree, net.cases)
        + _import_problems(tree, code_modules or set(), policy)
        + _risky_call_problems(tree, "the test file")
        + _file_access_problems(tree)
    )


def _case_problems(net: SafetyNet, record: RequestRecord, policy: Policy) -> list[str]:
    problems: list[str] = []
    if not net.cases:
        problems.append("The safety net has no cases.")
    if len(net.cases) > policy.safety_net_max_tests:
        problems.append(f"At most {policy.safety_net_max_tests} cases. You wrote {len(net.cases)}.")
    real_nc = {item.id for item in record.must_not_change}
    real_ac = {item.id for item in record.acceptance_criteria}
    seen: set[str] = set()
    for case in net.cases:
        if case.id in seen:
            problems.append(f"{case.id} is used twice.")
        seen.add(case.id)
        if case.function not in record.functions_in_scope:
            problems.append(f"{case.id}: {case.function} is not a function in scope.")
        problems += [
            f"{case.id}: {nc} is not a must-not-change ID."
            for nc in case.nc_ids
            if nc not in real_nc
        ]
        if case.expected_to_change is not None and case.expected_to_change not in real_ac:
            problems.append(f"{case.id}: {case.expected_to_change} is not a criterion ID.")
    for item in net.not_covered:
        if item.item not in record.functions_in_scope and item.item not in real_nc:
            problems.append(f"not_covered: {item.item} is not a function in scope or an NC ID.")
    return problems


def _method_problems(tree: ast.AST, cases: list[SafetyCase]) -> list[str]:
    """One method per case and one case per method (9-28)."""
    methods = find_test_methods(tree)
    problems: list[str] = []
    claimed: set[str] = set()
    for case in cases:
        found = [name for name in methods if name.startswith(method_prefix(case.id))]
        claimed.update(found)
        if len(found) != 1:
            problems.append(
                f"{case.id} needs exactly one test method named "
                f"{method_prefix(case.id)}<short words>; found {len(found)}."
            )
        elif case_id_of_method(found[0]) != case.id:
            problems.append(f"{found[0]}: use lower case words joined with underscores.")
        elif not ast.get_docstring(methods[found[0]]):
            problems.append(f"{found[0]} needs a one-sentence docstring saying what is expected.")
    problems += [
        f"{name} does not belong to any case. Remove it." for name in methods if name not in claimed
    ]
    return problems


def _import_problems(tree: ast.AST, code_modules: set[str], policy: Policy) -> list[str]:
    blocked = {name.lower() for name in policy.build_blocked_imports}
    problems: list[str] = []
    for module, _names, _line in imported_modules(tree):
        top = module.split(".")[0]
        if top.lower() in blocked:
            problems.append(f"The test file imports '{module}', which is blocked.")
        elif top in sys.stdlib_module_names or module in code_modules or top in code_modules:
            continue
        else:
            problems.append(
                f"The test file imports '{module}'. Tests may import only unittest, the standard "
                "library and the programs being changed."
            )
    return problems


def code_modules_of(paths: list[str]) -> set[str]:
    """Dotted module names of the target files."""
    return {module_of_path(path) for path in paths}


# --- proof (spec section 8, step 4) ---


def proof_split(net: SafetyNet, result: LayerBResult) -> tuple[list[str], list[str]]:
    """(proven case IDs, failing case IDs) from one sandbox run on today's code.

    A case with no result (the run timed out before it, or never ran) counts as failing."""
    outcome = {item.name: item.result for item in result.tests}
    proven: list[str] = []
    failing: list[str] = []
    methods = _method_names(net.test_code)
    for case in net.cases:
        names = [name for name in methods if name.startswith(method_prefix(case.id))]
        if result.ran and names and all(outcome.get(name) == "pass" for name in names):
            proven.append(case.id)
        else:
            failing.append(case.id)
    return proven, failing


def failure_report_for_cases(net: SafetyNet, result: LayerBResult, failing: list[str]) -> str:
    """The plain note sent to the Tester: which cases failed on today's code and why."""
    by_name = {item.name: item for item in result.tests}
    lines = ["These cases failed on today's unchanged code, so the test is wrong:"]
    for case_id in failing:
        lines.append(f"- {case_id}: {_failure_text(net, result, case_id, by_name)}")
    if result.timed_out:
        lines.append(f"The run hit the time limit while running {result.running_test or 'a test'}.")
    return "\n".join(lines)


def _failure_text(net: SafetyNet, result: LayerBResult, case_id: str, by_name: dict) -> str:
    for name in _method_names(net.test_code):
        if name.startswith(method_prefix(case_id)) and name in by_name:
            item = by_name[name]
            tail = item.traceback_tail[-1] if item.traceback_tail else item.message
            return f"{item.result}: {tail}".strip()
    return result.error or "the test did not run"


def drop_cases(net: SafetyNet, case_ids: list[str], reason: str = DROPPED_REASON) -> SafetyNet:
    """The net without these cases: their methods are cut from the file (the other methods stay
    byte for byte) and each case's function and NC items go to not covered (D-I)."""
    gone = [case for case in net.cases if case.id in case_ids]
    kept = [case for case in net.cases if case.id not in case_ids]
    names = [
        name
        for name in _method_names(net.test_code)
        if case_id_of_method(name) in case_ids
    ]
    extra = [NotCovered(item=item, reason=reason) for case in gone for item in _items_of(case)]
    return SafetyNet(
        cases=kept,
        test_code=remove_methods(net.test_code, names),
        not_covered=[*net.not_covered, *extra],
    )


def _items_of(case: SafetyCase) -> list[str]:
    return [case.function, *case.nc_ids]


# --- not covered, plain code (spec section 8, step 5) ---


def complete_not_covered(net: SafetyNet, record: RequestRecord) -> SafetyNet:
    """Add every in-scope function and NC item with no case, even if the Tester did not say so.
    The Tester's own reasons stay; an item is listed once."""
    covered = {item for case in net.cases for item in _items_of(case)}
    listed = {item.item for item in net.not_covered}
    # A dropped case already put its items in the list; a case that is kept covers them.
    still_listed = [item for item in net.not_covered if item.item not in covered]
    extra: list[NotCovered] = []
    for name in [*record.functions_in_scope, *(i.id for i in record.must_not_change)]:
        if name not in covered and name not in listed and name not in {e.item for e in extra}:
            extra.append(NotCovered(item=name, reason=NO_CASE_REASON))
    return net.model_copy(update={"not_covered": [*still_listed, *extra]})


# --- the frozen test file (spec section 8, step 7; section 10) ---


def remove_methods(text: str, names: list[str]) -> str:
    """The file without these test methods. Every other line stays as it was."""
    if not names:
        return text
    tree = ast.parse(text)
    cut: list[tuple[int, int]] = []
    for name, node in find_test_methods(tree).items():
        if name in names:
            first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            cut.append((first, node.end_lineno or node.lineno))
    lines = text.splitlines(keepends=True)
    for first, last in sorted(cut, reverse=True):
        del lines[first - 1 : last]
    return "".join(lines)


def split_by_expected(net: SafetyNet) -> tuple[str, str]:
    """(must-still-pass file, expected-to-change file). The first goes into Layer B; the second is
    run once for information after Layer B passes (spec section 10). Both keep the accepted text
    of each method byte for byte."""
    expected = {case.id for case in net.cases if case.expected_to_change is not None}
    names = _method_names(net.test_code)
    expected_names = [n for n in names if case_id_of_method(n) in expected]
    must_names = [n for n in names if case_id_of_method(n) not in expected]
    # A half with no method left is "" (an empty class would not parse).
    must_text = remove_methods(net.test_code, expected_names) if must_names else ""
    expected_text = remove_methods(net.test_code, must_names) if expected_names else ""
    return must_text, expected_text


def must_pass_methods(net: SafetyNet) -> list[str]:
    """Names of the methods that go into Layer B."""
    expected = {case.id for case in net.cases if case.expected_to_change is not None}
    return [n for n in _method_names(net.test_code) if case_id_of_method(n) not in expected]


def _method_names(text: str) -> list[str]:
    try:
        return list(find_test_methods(ast.parse(text)))
    except SyntaxError:
        return []
