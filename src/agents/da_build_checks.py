"""Plain-code rules for the Build + test loop (spec sections 3, 4, 5, 7 and 8). No AI, no files,
no network, so every rule can be tested with made-up text.

Layer A is like the compile step: CRTBNDRPG gives a clean listing or a list of errors. Each check
returns plain sentences, so the Generator sees the whole list at once in the next round.
"""

import ast
import keyword
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from agents.da_approach_checks import library_name, matches_any, normalise_path
from agents.da_understand_agent import strip_think_block
from agents.da_workspace_checks import (
    apply_line_ending,
    line_ending_of,
    normalise,
    path_problem,
)
from pydantic_classes.da_approach_models import TestCase
from pydantic_classes.da_build_models import (
    LABEL_NOT_PASSING,
    NOT_PASSING,
    Contract,
    ContractFile,
    ContractItem,
    FailureItem,
    FailureReport,
    FileEdit,
    LayerAProblem,
    LayerAResult,
    LayerBResult,
    TestOutcome,
)
from pydantic_classes.da_models import STATUS_NOT_PASSING, STATUS_READY_FOR_REVIEW
from pydantic_classes.da_rulebook_models import Policy

TESTS_FOLDER = "tests/"
EVIDENCE_MODULE = "da_evidence"  # the helper copied into the sandbox (Fix D1)
TOO_BIG_MESSAGE = "This file is too big to send to the AI in one go."
RISKY_NAMES = ("eval", "exec", "compile", "__import__")
RISKY_OS_CALLS = ("system", "popen")
RISKY_OS_PREFIXES = ("exec", "spawn")
# Calls a test may only make when it also imports tempfile (it must make its own folder).
FILE_CALLS = ("open",)
FILE_METHODS = ("write_text", "write_bytes", "read_text", "read_bytes", "unlink", "rmdir")
FILE_OS_CALLS = ("remove", "unlink", "rmdir", "rename")
_TEST_NAME = re.compile(r"^test_t(\d+)_ac(\d+)_")
_TRACE_FILE = re.compile(r'File "([^"]+)"')
_SAFETY_NAME = re.compile(r"^test_s(\d+)_")  # Phase 9 safety-net methods


# --- small helpers ---


def module_of_path(path: str) -> str:
    """src/agents/upload_validator.py gives agents.upload_validator (relative to src)."""
    parts = normalise_path(path).removesuffix(".py").split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def is_valid_name(name: str) -> bool:
    return name.isidentifier() and not keyword.iskeyword(name)


def list_codevision_modules(src_dir: Path) -> set[str]:
    """Top-level module names under a CodeVision `src` folder: its packages and .py files."""
    names = set()
    for entry in Path(src_dir).iterdir():
        if entry.is_dir() and not entry.name.startswith((".", "_")):
            names.add(entry.name)
        elif entry.suffix == ".py":
            names.add(entry.stem)
    return names


def public_items(text: str) -> dict[str, ContractItem]:
    """The public top-level functions and classes of a file, with their argument names."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    items = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith(
            "_"
        ):
            items[node.name] = ContractItem(
                name=node.name, kind="function", args=_arg_names(node), summary="existing"
            )
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            items[node.name] = ContractItem(
                name=node.name, kind="class", args=_class_args(node), summary="existing"
            )
    return items


def _arg_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Argument names in order, without self or cls. *args and **kwargs are named without stars."""
    spec = node.args
    names = [arg.arg for arg in spec.posonlyargs + spec.args]
    if spec.vararg:
        names.append(spec.vararg.arg)
    names += [arg.arg for arg in spec.kwonlyargs]
    if spec.kwarg:
        names.append(spec.kwarg.arg)
    return [name for name in names if name not in ("self", "cls")]


def _last_name(expr: ast.expr) -> str:
    """`dataclass`, `dataclasses.dataclass`, `dataclass(frozen=True)` -> `dataclass`."""
    if isinstance(expr, ast.Call):
        expr = expr.func
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return expr.id if isinstance(expr, ast.Name) else ""


def _class_args(node: ast.ClassDef) -> list[str]:
    """`__init__` args when written; else the fields of a Pydantic model or dataclass."""
    for child in node.body:
        if isinstance(child, ast.FunctionDef) and child.name == "__init__":
            return _arg_names(child)
    is_model = any(_last_name(base) == "BaseModel" for base in node.bases)
    is_dataclass = any(_last_name(deco) == "dataclass" for deco in node.decorator_list)
    if not (is_model or is_dataclass):
        return []
    return [
        child.target.id
        for child in node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and not child.target.id.startswith("_")
        and "ClassVar" not in ast.unparse(child.annotation)
    ]


# --- the contract (spec section 3, step 1) ---


def find_contract_problems(
    contract: Contract, planned_paths: list[str], current_texts: dict[str, str]
) -> list[str]:
    """Only planned files, every planned file present, valid Python names, and every existing
    public name of a `modify` file kept. `current_texts` holds the text of the modify files."""
    problems = []
    planned = {normalise_path(path) for path in planned_paths}
    seen: set[str] = set()
    for entry in contract.files:
        path = normalise_path(entry.path)
        if path not in planned:
            problems.append(f"{path} is not a planned code file. Use only the planned files.")
            continue
        if path in seen:
            problems.append(f"{path} is listed more than once.")
        seen.add(path)
        problems += _item_problems(path, entry)
        if path in current_texts:
            problems += _kept_name_problems(path, entry, current_texts[path])
    problems += [
        f"{path} is planned but missing from the contract." for path in sorted(planned - seen)
    ]
    return problems


def _item_problems(path: str, entry: ContractFile) -> list[str]:
    problems = []
    names = [item.name for item in entry.items]
    for item in entry.items:
        if not is_valid_name(item.name):
            problems.append(f"{path}: '{item.name}' is not a valid Python name.")
        problems += [
            f"{path}: argument '{arg}' of {item.name} is not a valid Python name."
            for arg in item.args
            if not is_valid_name(arg)
        ]
    problems += [
        f"{path}: '{name}' is listed more than once."
        for name in sorted(set(names))
        if names.count(name) > 1
    ]
    return problems


def _kept_name_problems(path: str, entry: ContractFile, current_text: str) -> list[str]:
    listed = {item.name for item in entry.items}
    return [
        f"{path} already has '{name}'. A file to modify must keep every existing public name."
        for name in public_items(current_text)
        if name not in listed
    ]


# --- the test file (spec section 3, step 2) ---


def case_method_prefix(case: TestCase) -> str:
    """T-6 and AC-4 give test_t6_ac4_ (spec section 3)."""
    test_id = case.test_id.lower().replace("-", "")
    criterion = case.criterion_id.lower().replace("-", "")
    return f"test_{test_id}_{criterion}_"


def case_ids_from_method(name: str) -> tuple[str, str] | None:
    """test_t6_ac4_empty gives ('T-6', 'AC-4'); None when the name has no case in it."""
    match = _TEST_NAME.match(name)
    return (f"T-{match.group(1)}", f"AC-{match.group(2)}") if match else None


def find_test_methods(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    """Every method called test... inside a class, by name."""
    methods = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name.startswith("test"):
                    methods[child.name] = child
    return methods


def find_test_file_problems(
    text: str, cases: list[TestCase], contract: Contract, policy: Policy
) -> list[str]:
    """Parses; one method per accepted case with the right name and a docstring; imports only
    unittest, the allowed standard library and the contract; no outside files; no network."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return [f"The test file has a syntax error on line {error.lineno}: {error.msg}."]
    return (
        _method_problems(tree, cases)
        + _evidence_problems(tree)
        + _test_import_problems(tree, contract, policy)
        + _risky_call_problems(tree, "the test file")
        + _file_access_problems(tree)
    )


def _method_problems(tree: ast.AST, cases: list[TestCase]) -> list[str]:
    methods = find_test_methods(tree)
    problems = []
    claimed: set[str] = set()
    for case in cases:
        prefix = case_method_prefix(case)
        found = [name for name in methods if name.startswith(prefix)]
        claimed.update(found)
        if len(found) != 1:
            problems.append(
                f"Case {case.test_id} ({case.criterion_id}) needs exactly one test method named "
                f"{prefix}<short words>; found {len(found)}."
            )
            continue
        if not re.fullmatch(rf"{re.escape(prefix)}[a-z0-9]+(_[a-z0-9]+)*", found[0]):
            problems.append(f"{found[0]}: use lower case words joined with underscores.")
        if not ast.get_docstring(methods[found[0]]):
            problems.append(f"{found[0]} needs a one-sentence docstring saying what is expected.")
    problems += [
        f"{name} does not belong to any accepted case. Remove it."
        for name in methods
        if name not in claimed
    ]
    return problems


def _calls_evidence(method: ast.FunctionDef) -> bool:
    return any(
        isinstance(node, ast.Call) and _called_name(node) == "evidence" for node in ast.walk(method)
    )


def _evidence_problems(tree: ast.AST) -> list[str]:
    """Fix D1 (E2): every test method records at least one evidence line."""
    problems = []
    for name, method in find_test_methods(tree).items():
        if not _calls_evidence(method):
            ids = case_ids_from_method(name)
            code = re.match(r"test_c(\d+)_", name)  # a code test (Fix D1): C-3
            label = ids[0] if ids else (f"C-{int(code.group(1))}" if code else name)
            problems.append(f"Test {label} records no evidence")
    return problems


def evidence_note(outcome: TestOutcome, test_text: str) -> str:
    """The words for a test row that has evidence lines: none. A frozen test file with no
    `evidence(` call at all was written before D1 (17 Nov); anything else just did not record."""
    if outcome.evidence:
        return ""
    if "evidence(" not in test_text:
        return "Evidence not recorded (test written before 17 Nov)"
    return "Evidence not recorded"


def _test_import_problems(tree: ast.AST, contract: Contract, policy: Policy) -> list[str]:
    allowed = {
        module_of_path(entry.path): {i.name for i in entry.items} for entry in contract.files
    }
    allowed[EVIDENCE_MODULE] = {"evidence"}  # the sandbox's own helper, not a contract name
    blocked = {name.lower() for name in policy.build_blocked_imports}
    problems = []
    for module, names, _line in imported_modules(tree):
        top = module.split(".")[0]
        if top.lower() in blocked:
            problems.append(f"The test file imports '{module}', which is blocked.")
        elif top in sys.stdlib_module_names:
            continue
        elif not _is_contract_import(module, names, allowed):
            problems.append(
                f"The test file imports '{module}'. Tests may import only unittest, the standard "
                "library and the names in the contract."
            )
    return problems


def _is_contract_import(module: str, names: list[str], allowed: dict[str, set[str]]) -> bool:
    if module in allowed:
        return "*" not in names and all(name in allowed[module] for name in names)
    # from agents import upload_validator: every name must be a contract module
    return bool(names) and all(f"{module}.{name}" in allowed for name in names)


def _file_access_problems(tree: ast.AST) -> list[str]:
    modules = {module.split(".")[0] for module, _names, _line in imported_modules(tree)}
    if "tempfile" in modules:
        return []  # the test makes its own temporary folder
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _touches_files(_called_name(node)):
            problems.append(
                f"Line {node.lineno}: {_called_name(node)}() touches files. A test may only use "
                "a temporary folder it makes itself (import tempfile)."
            )
    return problems


def _touches_files(name: str) -> bool:
    if name in FILE_CALLS or name == "shutil.rmtree":
        return True
    if name.startswith("os."):
        return name.split(".", 1)[1] in FILE_OS_CALLS
    return name.rsplit(".", 1)[-1] in FILE_METHODS and "." in name


# --- Layer A (spec section 5) ---


def imported_modules(tree: ast.AST) -> list[tuple[str, list[str], int]]:
    """(dotted module, imported names, line) for every import. A relative import has the module
    name '.' plus its own text, and counts as CodeVision's own."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(alias.name, [], node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            found.append((module, [alias.name for alias in node.names], node.lineno))
    return found


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """`import os as o` gives {"o": "os"}, so o.system(...) is read as os.system(...)."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
    return aliases


def _called_name(node: ast.Call, aliases: dict[str, str] | None = None) -> str:
    """eval for eval(...), os.system for os.system(...), x.write_text for x.write_text(...)"""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = func.value.id if isinstance(func.value, ast.Name) else ""
        base = (aliases or {}).get(base, base)
        return f"{base}.{func.attr}" if base else f"._.{func.attr}"
    return ""


# Modules whose risky functions are named in full. Cheap, common ways round the plain rules are
# closed (an alias, importlib, builtins, fork, posix_spawn, asyncio subprocess). Layer A is a
# guard, not a jail: the sandbox's honest limits are in the plan and the README.
RISKY_MODULE_CALLS = {
    "builtins": RISKY_NAMES,
    "importlib": ("import_module", "__import__"),
    "asyncio": ("create_subprocess_exec", "create_subprocess_shell"),
    "os": ("fork", "forkpty", "posix_spawn", "posix_spawnp", "system", "popen"),
}


def _risky_call_problems(tree: ast.AST, subject: str) -> list[str]:
    problems = []
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _called_name(node, aliases)
            if _is_risky(name):
                problems.append(f"Line {node.lineno}: {name}() is not allowed in {subject}.")
        elif isinstance(node, ast.ImportFrom) and node.module in RISKY_MODULE_CALLS:
            problems += [
                f"Line {node.lineno}: importing {alias.name} from {node.module} is not allowed "
                f"in {subject}."
                for alias in node.names
                if _is_risky(f"{node.module}.{alias.name}")
            ]
    return problems


def _is_risky(name: str) -> bool:
    if name in RISKY_NAMES:
        return True
    module, _, call = name.partition(".")
    if module == "os" and (call in RISKY_OS_CALLS or call.startswith(RISKY_OS_PREFIXES)):
        return True
    return call in RISKY_MODULE_CALLS.get(module, ())


@dataclass(frozen=True)
class LayerAContext:
    """What Layer A needs besides the code: the plan, the rulebook and the contract."""

    planned_paths: list[str]
    policy: Policy
    contract: Contract
    # Top-level module names of the CodeVision source (list_codevision_modules).
    codevision_modules: set[str]


def check_layer_a(files: dict[str, str], context: LayerAContext) -> LayerAResult:
    """Run A1 to A7 on every code file of the round. Any problem fails the round."""
    problems: list[LayerAProblem] = []
    for path, text in files.items():
        problems += _check_one_file(path, text, context)
    # A7: the rulebook has no plain-code rule today, so none run (plan P2).
    return LayerAResult(problems=problems, rulebook_checks_applied=0)


def _check_one_file(path: str, text: str, context: LayerAContext) -> list[LayerAProblem]:
    def problem(code: str, message: str) -> LayerAProblem:
        return LayerAProblem(code=code, path=path, text=message)

    placement = _placement_problems(path, context)
    if placement:  # a file that must not be written is not worth reading further
        return [problem(code, text_) for code, text_ in placement]
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return [problem("A1", f"Syntax error on line {error.lineno}: {error.msg}.")]
    found = [("A4", message) for message in _code_import_problems(tree, context)]
    found += [("A5", message) for message in _risky_call_problems(tree, "generated code")]
    found += [("A6", message) for message in _contract_problems(path, tree, context.contract)]
    return [problem(code, message) for code, message in found]


def _placement_problems(path: str, context: LayerAContext) -> list[tuple[str, str]]:
    normal = normalise_path(path)
    bad_path = path_problem(normal)
    if bad_path:
        return [("A2", bad_path)]
    if normal.lower().startswith(TESTS_FOLDER):
        return [("A2", "Tests are frozen. The Generator may not write anything under tests/.")]
    if normal not in {normalise_path(p) for p in context.planned_paths}:
        return [("A2", "This file is not in the accepted file plan.")]
    if matches_any(normal.lower(), context.policy.protected_files):
        return [("A3", "This file is protected. The AI may never write it.")]
    return []


def _code_import_problems(tree: ast.AST, context: LayerAContext) -> list[str]:
    policy = context.policy
    blocked = {name.lower() for name in policy.build_blocked_imports}
    approved = {library_name(name) for name in policy.approved_libraries}
    planned_tops = {module_of_path(p).split(".")[0] for p in context.planned_paths}
    problems = []
    for module, _names, line in imported_modules(tree):
        top = module.lstrip(".").split(".")[0]
        if module.startswith("."):
            continue  # a relative import stays inside CodeVision
        if top.lower() in blocked:  # a blocked module wins over an approved library (P1)
            problems.append(f"Line {line}: '{module}' is blocked and may never be imported.")
        elif top in sys.stdlib_module_names or library_name(top) in approved:
            continue
        elif top not in context.codevision_modules | planned_tops:
            problems.append(
                f"Line {line}: '{module}' is not the standard library, an approved library or "
                "a CodeVision module."
            )
    return problems


def _contract_problems(path: str, tree: ast.Module, contract: Contract) -> list[str]:
    entry = next(
        (c for c in contract.files if normalise_path(c.path) == normalise_path(path)), None
    )
    if entry is None:
        return []
    top_level: dict[str, ContractItem] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            top_level[node.name] = ContractItem(
                name=node.name, kind="function", args=_arg_names(node), summary="in the code"
            )
        elif isinstance(node, ast.ClassDef):
            top_level[node.name] = ContractItem(
                name=node.name, kind="class", args=_class_args(node), summary="in the code"
            )
    problems = []
    for item in entry.items:
        found = top_level.get(item.name)
        if found is None or found.kind != item.kind:
            problems.append(f"The contract promises {item.kind} {item.name}, but it is missing.")
        elif found.args != item.args:
            problems.append(
                f"{item.name} must take ({', '.join(item.args)}) as agreed, "
                f"but takes ({', '.join(found.args)})."
            )
    return problems


# --- edit blocks (decision D-C) ---


def apply_edits(
    start_text: str, edits: list[FileEdit], path: str
) -> tuple[str, list[LayerAProblem]]:
    """Apply edit blocks in order. Each "find" text must appear exactly once in the text as it is
    at that moment. The result keeps the file's own line endings."""
    ending = line_ending_of(start_text)
    text = normalise(start_text)
    problems = []
    for number, edit in enumerate(edits, start=1):
        find = normalise(edit.find)
        count = text.count(find)
        if count != 1:
            problems.append(
                LayerAProblem(
                    code="E1",
                    path=path,
                    text=(
                        f"Edit block {number} did not match the file: its find text appears "
                        f"{count} times, it must appear exactly once."
                    ),
                )
            )
            continue
        text = text.replace(find, normalise(edit.replace), 1)
    return apply_line_ending(text, ending), problems


# --- reading the Generator's replies (plan P6, refined in step 7) ---

_CODE_FENCE = re.compile(r"^```[A-Za-z]*\s*\n(.*?)\n?```$", re.DOTALL)
_EDIT_BLOCK = re.compile(r"<<<<<<< FIND\n(.*?)\n=======\n(.*?)\n?>>>>>>> REPLACE", re.DOTALL)


def clean_code_reply(text: str) -> str:
    """The reply as plain code: a leading think block and a whole-reply code fence are removed.
    Empty text stays empty."""
    cleaned = strip_think_block(text).strip()
    fenced = _CODE_FENCE.match(cleaned)
    if fenced:
        cleaned = fenced.group(1).strip("\n")
    return cleaned + "\n" if cleaned else ""


def parse_edit_blocks(text: str) -> list[FileEdit]:
    """Edit blocks in the visible FIND / REPLACE format:

    <<<<<<< FIND / the exact old text / ======= / the new text / >>>>>>> REPLACE

    An empty list means the reply had no usable block."""
    body = clean_code_reply(text)
    return [
        FileEdit(find=match.group(1), replace=match.group(2))
        for match in _EDIT_BLOCK.finditer(body)
        if match.group(1).strip()
    ]


# --- which files to fix, and the failure report (spec section 7) ---


def failing_tests(result: LayerBResult) -> list[str]:
    return [item.name for item in result.tests if item.result in NOT_PASSING]


def choose_files_to_fix(
    layer_a: LayerAResult,
    layer_b: LayerBResult | None,
    planned_paths: list[str],
    contract: Contract,
    test_source: str,
) -> list[str]:
    """Decision D-J. Layer A problems name their files. Otherwise the planned files named in the
    failing tests' tracebacks, else the files whose contract names the failing tests use, else
    every planned file. Never the tests. Order follows the file plan."""
    planned = [normalise_path(p) for p in planned_paths]
    if layer_a.problems:
        named = {normalise_path(item.path) for item in layer_a.problems}
    else:
        named = _files_from_tracebacks(layer_b, planned) or _files_from_contract(
            layer_b, contract, test_source
        )
    chosen = [path for path in planned if path in named]
    return chosen or planned


def _files_from_tracebacks(layer_b: LayerBResult | None, planned: list[str]) -> set[str]:
    named = set()
    for item in layer_b.tests if layer_b else []:
        if item.result not in NOT_PASSING:
            continue
        for line in item.traceback_tail:
            match = _TRACE_FILE.search(line)
            if match:
                shown = match.group(1).replace("\\", "/")
                named.update(path for path in planned if shown.endswith("/" + path))
    return named


def _files_from_contract(
    layer_b: LayerBResult | None, contract: Contract, test_source: str
) -> set[str]:
    try:
        methods = find_test_methods(ast.parse(test_source))
    except SyntaxError:
        return set()
    wanted = set(failing_tests(layer_b)) if layer_b else set()
    used = {
        node.id if isinstance(node, ast.Name) else node.attr
        for name, method in methods.items()
        if name in wanted
        for node in ast.walk(method)
        if isinstance(node, ast.Name | ast.Attribute)
    }
    return {
        normalise_path(entry.path)
        for entry in contract.files
        if any(item.name in used for item in entry.items)
    }


def build_failure_report(
    layer_a: LayerAResult,
    layer_b: LayerBResult | None,
    cases: list[TestCase],
    test_source: str,
    files_to_fix: list[str],
    safety_notes: dict[str, str] | None = None,
) -> FailureReport:
    """Built by plain code, not AI. One item per failed test, with the case, the criterion, the
    expected sentence (the test's docstring) and the assertion message. `safety_notes` (Phase 9,
    case ID -> sentence) puts a safety-net test in its own words."""
    by_id = {case.test_id: case for case in cases}
    try:
        methods = find_test_methods(ast.parse(test_source))
    except SyntaxError:
        methods = {}
    items = []
    for item in layer_b.tests if layer_b else []:
        if item.result not in NOT_PASSING:
            continue
        ids = case_ids_from_method(item.name)
        case = by_id.get(ids[0]) if ids else None
        method = methods.get(item.name)
        docstring = (ast.get_docstring(method) or "").strip() if method else ""
        safety = _SAFETY_NAME.match(item.name)
        safety_id = f"S-{safety.group(1)}" if safety else ""
        items.append(
            FailureItem(
                test_id=ids[0] if ids else (safety_id or item.name),
                criterion_id=ids[1] if ids else "",
                yours=bool(case and case.source == "developer"),
                expected=docstring.split("\n")[0] if docstring else "(no description)",
                message=item.message or item.result,
                traceback_tail=item.traceback_tail,
                note=(safety_notes or {}).get(safety_id, ""),
            )
        )
    return FailureReport(
        items=items,
        layer_a=list(layer_a.problems),
        timed_out=bool(layer_b and layer_b.timed_out),
        running_test=layer_b.running_test if layer_b else "",
        files_to_fix=files_to_fix,
    )


def report_for_developer(report: FailureReport) -> str:
    """Plain lines for the Build tab: test ID, 'Yours' tag, criterion, expected, message."""
    lines = []
    if report.timed_out:
        lines.append(f"Timed out. The test running was {report.running_test or 'unknown'}.")
    lines += [f"{p.path}: {p.text}" for p in report.layer_a]
    for item in report.items:
        if item.note:
            lines.append(f"{item.note} Got: {item.message}")
            continue
        tag = " (Yours)" if item.yours else ""
        lines.append(
            f"{item.test_id}{tag}, {item.criterion_id}: expected {item.expected} "
            f"Got: {item.message}"
        )
    return "\n".join(lines)


def report_for_generator(report: FailureReport) -> str:
    """The developer's lines plus the cut traceback lines of each failed test."""
    lines = [report_for_developer(report)]
    for item in report.items:
        if item.traceback_tail:
            lines.append(f"Traceback for {item.test_id}:")
            lines += [f"  {line}" for line in item.traceback_tail]
    return "\n".join(line for line in lines if line)


# --- results and labels (spec section 8) ---


def result_for(passed: bool, label: str) -> tuple[str, str]:
    """(status, label) once the build ends. A pass keeps the label the Tester review gave it
    (Phase 7, plain code in da_tester_review.compute_label); anything else is Not passing."""
    if passed:
        return STATUS_READY_FOR_REVIEW, label
    return STATUS_NOT_PASSING, LABEL_NOT_PASSING


def prompt_too_big(prompt: str, limit: int) -> bool:
    return len(prompt) > limit


def code_paths_refused(paths: Iterable[str]) -> list[str]:
    """Paths under tests/ never go into a write job or a Generator reply (6-7, 6-37)."""
    return [path for path in paths if normalise_path(path).lower().startswith(TESTS_FOLDER)]
