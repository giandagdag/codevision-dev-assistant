"""Plain-code build rules for an enhance request (Phase 9, spec section 10): A8 scope, A9 locked
signature, and the safety-net wording in the failure report. No AI, no files.

A8 is like a change-control ticket that names the one routine you may touch: an edit outside it
is refused. A9 is like a locked parameter list on a program that other jobs CALL: the callers are
not in this change, so the list must stay the same.
"""

import ast

from agents.da_approach_checks import normalise_path
from agents.da_build_checks import find_test_methods
from agents.da_code_splitter import MODULE_SYMBOL, CodePiece, split_python_file
from agents.da_impact import locked_signatures
from agents.da_safety_net_checks import case_id_of_method, must_pass_methods, split_by_expected
from agents.da_workspace_checks import normalise
from pydantic_classes.da_build_models import FileEdit, LayerAProblem, LayerBResult
from pydantic_classes.da_enhance_models import ImpactRow, SafetyNet

# --- what the Generator sees of a target file (spec section 10, step 2) ---


def scoped_view(path: str, text: str, in_scope: list[str]) -> str:
    """The in-scope functions word for word with their line numbers, the file's import lines, and
    the names and arguments of the other functions (no bodies). The Generator edits with FIND and
    REPLACE blocks, so each body is copied exactly as it is in the file."""
    text = normalise(text)
    lines = text.split("\n")
    pieces = in_scope_pieces(path, text, in_scope)
    # A class in scope brings its methods along: show only the outermost pieces.
    outer = [
        p for p in pieces
        if not any(
            o is not p and o.line_start <= p.line_start and p.line_end <= o.line_end
            for o in pieces
        )
    ]
    shown = {p.symbol for p in pieces}
    parts = ["## Import lines of this file", "\n".join(_import_lines(text)) or "(none)", ""]
    parts.append("## Functions in scope (the only code you may change)")
    for piece in sorted(outer, key=lambda p: p.line_start):
        body = "\n".join(lines[piece.line_start - 1 : piece.line_end])
        parts += [f"### {piece.symbol} (lines {piece.line_start} to {piece.line_end})", body, ""]
    parts.append("## Other functions (names and arguments only, do not change)")
    others = [
        f"def {symbol}({', '.join(args)})"
        for symbol, args in signatures(text).items()
        if symbol not in shown
    ]
    parts.append("\n".join(others) or "(none)")
    return "\n".join(parts)


def _import_lines(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    return [
        ast.get_source_segment(text, node) or ""
        for node in tree.body
        if isinstance(node, ast.Import | ast.ImportFrom)
    ]


# --- the frozen test set with the safety net (spec section 10, step 1) ---


def frozen_set_with_net(criterion_text: str, net: SafetyNet) -> tuple[str, list[str], list[str]]:
    """(the frozen test text, the net methods that run in Layer B, the expected-to-change methods
    that are kept but not run there). The criterion tests come first and are not touched; the
    must-still-pass half of the net follows byte for byte as it was accepted."""
    must_text, _expected_text = split_by_expected(net)
    expected = {case.id for case in net.cases if case.expected_to_change is not None}
    names = [n for n in _net_method_names(net) if case_id_of_method(n) in expected]
    text = criterion_text
    if must_text:
        text = criterion_text.rstrip("\n") + "\n\n\n" + must_text
    return text, must_pass_methods(net), names


def _net_method_names(net: SafetyNet) -> list[str]:
    try:
        return list(find_test_methods(ast.parse(net.test_code)))
    except SyntaxError:
        return []


# --- A8: scope (spec section 10, step 3) ---


def in_scope_pieces(path: str, text: str, in_scope: list[str]) -> list[CodePiece]:
    """The pieces of this file that the change may touch. A class in scope covers its methods."""
    wanted = set(in_scope)
    return [
        piece
        for piece in split_python_file(path, text)
        if piece.symbol != MODULE_SYMBOL
        and any(piece.symbol == name or piece.symbol.startswith(name + ".") for name in wanted)
    ]


def scope_problems(
    path: str, start_text: str, edits: list[FileEdit], in_scope: list[str]
) -> list[LayerAProblem]:
    """A8. Every edit block's "find" text must lie inside an in-scope function of the text as it is
    at that moment. The "insert after a function" form is allowed too: a find that starts on the
    last line of an in-scope function, or on the blank lines right after it.

    A block whose find text is not found exactly once is left to the edit step (E1)."""
    text = normalise(start_text)
    problems: list[LayerAProblem] = []
    for number, edit in enumerate(edits, start=1):
        find = normalise(edit.find)
        if text.count(find) != 1:
            continue
        first, last = _line_range(text, find)
        if not _inside_scope(path, text, in_scope, first, last):
            symbol = _symbol_at(path, text, first)
            message = f"Edit block {number} changes `{symbol}`, which is not in scope."
            problems.append(LayerAProblem(code="A8", path=path, text=message))
        text = text.replace(find, normalise(edit.replace), 1)
    return problems


def _line_range(text: str, find: str) -> tuple[int, int]:
    start = text.index(find)
    first = text.count("\n", 0, start) + 1
    last = first + find.rstrip("\n").count("\n")
    return first, last


def _inside_scope(path: str, text: str, in_scope: list[str], first: int, last: int) -> bool:
    pieces = in_scope_pieces(path, text, in_scope)
    if any(piece.line_start <= first and last <= piece.line_end for piece in pieces):
        return True
    # Insert-after: the find starts on the blank lines right below an in-scope function.
    lines = text.splitlines()
    for piece in pieces:
        gap_end = piece.line_end
        while gap_end < len(lines) and not lines[gap_end].strip():
            gap_end += 1
        if piece.line_end < first <= gap_end and last <= gap_end:
            return True
    return False


def _symbol_at(path: str, text: str, line: int) -> str:
    """The innermost function or class holding this line, else the module-level code."""
    holding = [
        piece
        for piece in split_python_file(path, text)
        if piece.symbol != MODULE_SYMBOL and piece.line_start <= line <= piece.line_end
    ]
    if not holding:
        return "module-level code"
    return min(holding, key=lambda piece: piece.line_end - piece.line_start).symbol


# --- A9: locked signature (spec section 10, step 3) ---


def signatures(text: str) -> dict[str, list[str]]:
    """Symbol -> argument names (positional, then `*name`, keyword-only, `**name`) for every
    function and method. Types and default values do not count."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    found: dict[str, list[str]] = {}
    _collect(tree.body, "", found)
    return found


def _collect(body: list[ast.stmt], prefix: str, found: dict[str, list[str]]) -> None:
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found[f"{prefix}{node.name}"] = _argument_names(node.args)
        elif isinstance(node, ast.ClassDef):
            _collect(node.body, f"{prefix}{node.name}.", found)


def _argument_names(args: ast.arguments) -> list[str]:
    names = [a.arg for a in [*args.posonlyargs, *args.args]]
    if args.vararg:
        names.append("*" + args.vararg.arg)
    names += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        names.append("**" + args.kwarg.arg)
    return names


def signature_problems(
    path: str,
    start_text: str,
    new_text: str,
    rows: list[ImpactRow],
    planned_paths: list[str],
) -> list[LayerAProblem]:
    """A9. A function in scope with a Direct caller in a file that is NOT in the plan keeps its
    name and arguments. With the caller's file in the plan, it may change."""
    planned = {normalise_path(p) for p in planned_paths}
    locked = locked_signatures(rows, planned)
    before = signatures(start_text)
    after = signatures(new_text)
    callers = {
        row.function_in_scope: row.caller_path
        for row in rows
        if row.kind == "direct" and normalise_path(row.caller_path) not in planned
    }
    problems: list[LayerAProblem] = []
    for symbol in locked:
        if symbol not in before or before[symbol] == after.get(symbol):
            continue
        message = (
            f"`{symbol}` is called by `{callers[symbol]}`; its arguments cannot change "
            "unless that file is in the plan."
        )
        problems.append(LayerAProblem(code="A9", path=path, text=message))
    return problems


# --- Layer B failure report wording (spec section 10, step 4) ---


def safety_notes(net: SafetyNet) -> dict[str, str]:
    """Case ID -> the sentence for the failure report, in the net's own words (9-41)."""
    notes: dict[str, str] = {}
    for case in net.cases:
        text = f"Safety-net test {case.id} (today: {case.today_behaviour.rstrip('.')}) now fails."
        if case.nc_ids:
            keep = ", ".join(case.nc_ids)
            text += f" You said this must not change ({keep})."
        else:
            text += f" It captures how {case.function} worked before the change."
        notes[case.id] = text
    return notes


def failing_safety_cases(result: LayerBResult) -> list[str]:
    """The safety-net case IDs that failed or errored in a Layer B run, in order."""
    found: list[str] = []
    for item in result.tests:
        case_id = case_id_of_method(item.name)
        if case_id and item.result in ("fail", "error") and case_id not in found:
            found.append(case_id)
    return found
