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
_ASSERTS = {"assertEqual": 1, "assertIn": 0, "assertIs": 1}  # position of the expected side


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def requirement_text(record: RequestRecord, decisions: list[str], contract: Contract) -> str:
    parts = [f"{c.given} {c.when} {c.then}" for c in record.acceptance_criteria]
    parts += decisions + list(record.exceptions)
    parts += [item.summary for entry in contract.files for item in entry.items]
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
        elif name in _ASSERTS and len(node.args) > _ASSERTS[name]:
            found.append(_literal(node.args[_ASSERTS[name]]))
    return [text for text in found if text]


def _is_message(text: str) -> bool:
    """Words with a space: a message. Single names (ValueError, True, a file name) pass."""
    return len(text.strip()) >= _MIN_LENGTH and " " in text.strip()


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
