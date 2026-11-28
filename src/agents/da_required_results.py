"""Fix G9 B1/B2: the exact `given -> output` pairs a criterion states (plain code, no AI).

The Builder is shown these as required results. A pair is only made when the criterion gives
literal arguments and a literal result: a function call `check('abc')` that returns a value, or a
command line in backticks with an output and/or an exit code. Anything vaguer gives no pair."""

import ast
import re
import shlex
from dataclasses import dataclass

from pydantic_classes.da_request_record_models import RequestRecord

HEAD = (
    "\n## Required results\n\nThese results are required. They beat coding habits and every rule "
    "except an exception RX-n.\n\n"
)
RETURN_RULE = (
    "\nWhen a criterion says the function returns a value, return it. Never raise instead. "
    "Raise only where a criterion or decision says an error is raised.\n"
)
_QUOTE = r"""(['"`])(.*?)\1"""
_CALL = re.compile(r"\b([A-Za-z_]\w*)\(([^()]*)\)")
_RETURNS_TEXT = re.compile(rf"\b(?:returns?|outputs?|prints?|shows?|says?)\s+{_QUOTE}", re.I)
_RETURNS_VALUE = re.compile(r"\breturns?\s+(-?\d+(?:\.\d+)?|True|False|None)\b")
_CLI = re.compile(r"`(?:python\s+)?([\w./-]+\.py)((?:\s[^`]*)?)`")
_EXIT = re.compile(r"\bexit code\s+(non-zero|\d+)", re.I)


@dataclass(frozen=True)
class RequiredResult:
    criterion_id: str
    kind: str  # "function" or "cli"
    name: str  # function name, or the script path
    args: tuple
    has_value: bool = False
    value: object = None  # the expected return value, or the expected output text
    exit_code: str = ""  # "non-zero", "0", ... (cli only)

    @property
    def given(self) -> str:
        shown = ", ".join(repr(a) for a in self.args)
        if self.kind == "function":
            return f"{self.name}({shown})"
        return f"{self.name} {shown}".strip()

    def line(self) -> str:
        parts = []
        if self.has_value:
            parts.append(f"{'returns' if self.kind == 'function' else 'output'} {self.value!r}")
        if self.exit_code:
            parts.append(f"exit code {self.exit_code}")
        return f"- {self.criterion_id}: {self.given} -> {', '.join(parts)}"


def _literals(text: str) -> tuple | None:
    if not text.strip():
        return ()
    try:
        value = ast.literal_eval(f"({text},)")
    except (ValueError, SyntaxError):
        return None
    return value if isinstance(value, tuple) else None


def _value(then: str, want_return: bool) -> tuple[bool, object]:
    found = _RETURNS_TEXT.search(then)
    if found:
        return True, found.group(2)
    number = _RETURNS_VALUE.search(then) if want_return else None
    if number:
        return True, ast.literal_eval(number.group(1))
    return False, None


def _function_result(item) -> RequiredResult | None:
    for call in _CALL.finditer(item.when):
        args = _literals(call.group(2))
        has_value, value = _value(item.then, True)
        if args is not None and has_value and "return" in item.then.lower():
            return RequiredResult(item.id, "function", call.group(1), args, True, value)
    return None


def _cli_result(item) -> RequiredResult | None:
    found = _CLI.search(item.when)
    if not found:
        return None
    try:
        args = tuple(shlex.split(found.group(2)))
    except ValueError:
        return None
    has_value, value = _value(item.then, False)
    exit_code = _EXIT.search(item.then)
    if not has_value and not exit_code:
        return None
    code = exit_code.group(1) if exit_code else ""
    return RequiredResult(item.id, "cli", found.group(1), args, has_value, value, code)


def required_results(record: RequestRecord) -> list[RequiredResult]:
    found = []
    for item in record.acceptance_criteria:
        result = _cli_result(item) or _function_result(item)
        if result is not None:
            found.append(result)
    return found


def _defining_path(name: str, code: dict[str, str]) -> str:
    """The code file that has `name` as a top-level function ('' when none or unreadable)."""
    for path, text in code.items():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        if any(isinstance(n, ast.FunctionDef) and n.name == name for n in tree.body):
            return path
    return ""


def check_file(
    pairs: list[RequiredResult], code: dict[str, str]
) -> tuple[str, dict[str, tuple[RequiredResult, str]]]:
    """Fix G9 B3: a small unittest file that runs each function pair once, and a map of test
    method -> (pair, code path). A failure message says what the code really did. A command-line
    pair runs the script as a child process of this test (F3)."""
    methods, found = [], {}
    for number, pair in enumerate(pairs):
        if pair.kind == "cli":
            path = _script_path(pair.name, code)
            if path:
                found[f"test_r{number}"] = (pair, path)
                methods.append(_cli_method(f"test_r{number}", pair, path))
            continue
        path = _defining_path(pair.name, code) if pair.has_value else ""
        if not path:
            continue
        module = path.removeprefix("src/").removesuffix(".py").replace("/", ".")
        name = f"test_r{number}"
        found[name] = (pair, path)
        methods.append(
            f"    def {name}(self):\n"
            "        try:\n"
            f"            from {module} import {pair.name}\n"
            f"            got = {pair.name}(*{pair.args!r})\n"
            "        except Exception as error:\n"
            '            self.fail("raised " + type(error).__name__ + ": " + str(error))\n'
            f"        if got != {pair.value!r}:\n"
            '            self.fail("returned " + repr(got))\n'
        )
    text = "import unittest\n\n\nclass RequiredResults(unittest.TestCase):\n" + "\n".join(methods)
    return (text if found else ""), found


def _script_path(name: str, code: dict[str, str]) -> str:
    """The code file the command line names ('' when the Builder wrote no such file)."""
    wanted = name.removeprefix("./")
    return next((p for p in code if p == wanted or p.endswith("/" + wanted)), "")


def _cli_method(method: str, pair: RequiredResult, path: str) -> str:
    """One test that runs the script with the literal arguments (60 s limit; the sandbox already
    gives the clean environment and the Job Object). Output is compared with trailing spaces and
    line ends stripped; "non-zero" means any non-zero exit code."""
    return (
        f"    def {method}(self):\n"
        "        import subprocess, sys\n"
        "        def flat(text):\n"
        "            return '\\n'.join(line.rstrip() for line in text.strip().splitlines())\n"
        "        try:\n"
        f"            done = subprocess.run([sys.executable, {path!r}, *{list(pair.args)!r}],\n"
        "                capture_output=True, text=True, timeout=60)\n"
        "        except subprocess.TimeoutExpired:\n"
        "            self.fail('did not finish within 60 seconds')\n"
        "        except OSError as error:\n"
        "            self.fail('could not start: ' + str(error))\n"
        "        seen = []\n"
        f"        if {pair.has_value!r} and flat(done.stdout) != flat({pair.value or ''!r}):\n"
        "            seen.append('printed ' + repr(flat(done.stdout)))\n"
        f"        want = {pair.exit_code!r}\n"
        "        if want == 'non-zero' and done.returncode == 0:\n"
        "            seen.append('exited with code 0')\n"
        "        elif want.isdigit() and done.returncode != int(want):\n"
        "            seen.append('exited with code ' + str(done.returncode))\n"
        "        if seen:\n"
        "            self.fail(' and '.join(seen))\n"
    )


def mismatch_text(pair: RequiredResult, path: str, actual: str) -> str:
    """The repair note for one pair: criterion, expected, actual."""
    if pair.kind == "cli":
        expected = ", ".join(
            ([f"print {pair.value!r}"] if pair.has_value else [])
            + ([f"exit with code {pair.exit_code}"] if pair.exit_code else [])
        )
        return (
            f"{pair.criterion_id} requires running {pair.given} to {expected}, but it {actual}. "
            "Change the code so it does exactly this."
        )
    return (
        f"{pair.criterion_id} requires {pair.given} to return {pair.value!r}, "
        f"but it {actual}. Return the required value; do not raise."
    )


def required_results_block(record: RequestRecord) -> str:
    """The Builder prompt part: the pairs (when there are any) and the never-raise rule."""
    lines = [item.line() for item in required_results(record)]
    return (HEAD + "\n".join(lines) + "\n" if lines else "") + RETURN_RULE
