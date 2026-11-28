"""Fix G9 T3: a test may only expect text the requirement holds (plain code, no AI).

The test writer sometimes invents message text. Before the tests freeze, every expected string
with words in it must appear (case and spacing blind) in a criterion, a decision, an exception or
the contract. Phase 9 safety-net tests never come through here."""

import ast
import re

from pydantic_classes.da_build_models import Contract
from pydantic_classes.da_request_record_models import RequestRecord

NOT_COVERED_NOTE = "Not covered: the test could not be written from the requirement"
_MIN_LENGTH = 4
# Positions that may hold an expected literal. assertEqual takes both sides: the writer may put
# the literal first. A single word is checked too, unless it is a code name (_is_message).
_CODE_WORDS = frozenset({"true", "false", "none"})
_ASSERTS = {"assertEqual": (0, 1), "assertIn": (0,), "assertIs": (1,)}


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def requirement_text(record: RequestRecord, decisions: list[str], contract: Contract) -> str:
    parts = [f"{c.given} {c.when} {c.then}" for c in record.acceptance_criteria]
    parts += decisions + list(record.exceptions)
    for item in (item for entry in contract.files for item in entry.items):
        parts += [item.summary, item.name, *item.args]  # the contract's own names count too
    return _plain(" ".join(parts))


def _literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def expected_strings(method: ast.FunctionDef) -> list[str]:
    """The string literals this method expects: evidence(...) 4th argument, assert expected side."""
    found = []
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        if name == "evidence" and len(node.args) >= 4:
            found.append(_literal(node.args[3]))
        elif name in _ASSERTS:
            found += [_literal(node.args[i]) for i in _ASSERTS[name] if i < len(node.args)]
    return [text for text in found if text]


def _is_message(text: str) -> bool:
    """Words with a space: a message. Any single alphabetic word of 4+ letters counts too (ERROR,
    items); only True, False, None and names ending in Error, Exception or Warning pass."""
    text = text.strip()
    if len(text) < _MIN_LENGTH:
        return False
    if " " in text:
        return True
    code_like = text.endswith(("Error", "Exception", "Warning")) or text.casefold() in _CODE_WORDS
    return text.isalpha() and not code_like  # any case: "invalid" is a message like "Invalid"


def invented_by_method(code: str, wanted: str) -> dict[str, list[str]]:
    """Method name -> the expected strings the requirement does not hold."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    wanted = _plain(wanted)
    bad: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            texts = [t for t in expected_strings(node) if _is_message(t)]
            missing = [t for t in texts if _plain(t) not in wanted]
            if missing:
                bad[node.name] = missing
    return bad


def reason_for_writer(bad: dict[str, list[str]]) -> str:
    lines = [f"- {name} expects '{text}'" for name, texts in bad.items() for text in texts]
    return (
        "These expected texts are not written in the requirement. Copy the exact text from a "
        "criterion, or expect only what the requirement says:\n" + "\n".join(lines)
    )


def same_failures(older, newer) -> dict[str, str]:
    """Fix G9 T4: test method -> actual message, for each test that failed with the very same
    message in both runs (a different actual value is progress, not a stuck test)."""
    if older is None or newer is None:
        return {}
    before = {t.name.rsplit(".", 1)[-1]: t for t in older.tests if t.result in ("fail", "error")}
    stuck = {}
    for item in newer.tests:
        name = item.name.rsplit(".", 1)[-1]
        if item.result in ("fail", "error") and item.message and name in before:
            if before[name].message == item.message:
                stuck[name] = item.message
    return stuck


def expected_of(code: str, names: set[str]) -> dict[str, list[str]]:
    """Method -> every expected string it holds (for the audit and the repair note)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    return {
        node.name: expected_strings(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in names
    }


def criterion_of(text: str, record: RequestRecord) -> str:
    """The criterion that holds this expected text, or ''."""
    for item in record.acceptance_criteria:
        if _plain(text) in _plain(f"{item.given} {item.when} {item.then}"):
            return item.id
    return ""


def repair_note(code: str, names: set[str], record: RequestRecord) -> str:
    """The requirement backs the test: tell the Generator the exact expected value."""
    lines = []
    for method, texts in expected_of(code, names).items():
        for text in [t for t in texts if _is_message(t)] or [""]:
            where = criterion_of(text, record) if text else ""
            what = f"{where} says the result must be exactly '{text}'" if where else (
                f"The requirement backs {method}"
            )
            lines.append(f"- {what}. Change the code, not the test.")
    return "\n".join(lines)


def replace_methods(code: str, new_code: str, names: set[str]) -> str:
    """`code` with only the named test methods swapped for the same-named ones in `new_code`.
    Every other method stays as it is, so the frozen rule is bent for the stuck tests only. A
    name the new code lacks is dropped from the result."""
    new_lines = new_code.splitlines()
    parts: dict[str, list[str]] = {}
    for node in ast.walk(ast.parse(new_code)):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            parts[node.name] = new_lines[first - 1 : node.end_lineno]
    lines = code.splitlines()
    out: list[str] = []
    skip_to = 0
    spans = {}
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            spans[first] = (node.end_lineno, node.name)
    for number, line in enumerate(lines, 1):
        if number in spans:
            skip_to, name = spans[number]
            out += parts.get(name, [])
        if number > skip_to:
            out.append(line)
    return "\n".join(out) + "\n"


def drop_methods(code: str, names: set[str]) -> str:
    """The test file without these methods (whole lines, decorators included)."""
    tree = ast.parse(code)
    lines = code.splitlines()
    cut: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            cut.update(range(first, node.end_lineno + 1))
    every = {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name[:4] == "test"
    }
    if every <= names:
        return ""  # nothing is left: an empty class would not even parse
    return "\n".join(line for number, line in enumerate(lines, 1) if number not in cut) + "\n"
