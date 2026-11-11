"""Impact: who calls the functions being changed (Phase 9, spec section 7, light P16).

Plain code and the standard-library `ast` module, no AI. AS400 picture: DSPPGMREF turned around.
Not "what does this program call" but "who calls this program": a where-used list before you
change a parameter. It reads the server's reference copy, never the developer's folder (rule R1).
"""

import ast
from pathlib import Path

from agents.da_approach_checks import matches_any
from agents.da_code_splitter import SKIPPED_FOLDERS
from agents.da_enhance_checks import lookup_capability
from agents.da_search_index import looks_secret
from da_logging import get_logger
from pydantic_classes.da_enhance_models import ImpactResult, ImpactRow
from pydantic_classes.da_rulebook_models import Capability, FlagReviewZone

logger = get_logger(__name__)

LIMITS_LINE = (
    "Impact is found by reading the code, not by running it. It cannot see calls made by name "
    "in text, Dash callbacks wired by component IDs, or `getattr`."
)
UNAVAILABLE_TEXT = "Impact could not be checked."
MODULE_LEVEL = "<module>"
_KIND_ORDER = {"direct": 0, "possible": 1, "imports_only": 2}


def module_name(path: str) -> str:
    """src/agents/limits.py gives agents.limits (src is the import root)."""
    parts = path.replace("\\", "/").removesuffix(".py").split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def find_impact(
    reference_dir: Path | None,
    scope_by_target: dict[str, list[str]],
    capabilities: list[Capability],
    zones: list[FlagReviewZone],
    max_callers: int,
) -> ImpactResult:
    """Walk every .py file of the reference copy. `scope_by_target` maps each target path to the
    in-scope symbols it has. The target files themselves are skipped."""
    if reference_dir is None or not Path(reference_dir).is_dir():
        return ImpactResult(available=False)
    root = Path(reference_dir)
    targets = {path.replace("\\", "/").lower() for path in scope_by_target}
    rows: list[ImpactRow] = []
    for file in sorted(root.rglob("*.py")):
        relative = file.relative_to(root).as_posix()
        if SKIPPED_FOLDERS & set(file.relative_to(root).parts) or looks_secret(relative):
            continue
        if relative.lower() in targets:
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        rows += rows_for_file(relative, text, scope_by_target, capabilities, zones)
    rows.sort(key=lambda r: (_KIND_ORDER[r.kind], r.caller_path, r.line, r.function_in_scope))
    return ImpactResult(rows=rows[:max_callers], more=max(len(rows) - max_callers, 0))


def rows_for_file(
    path: str,
    text: str,
    scope_by_target: dict[str, list[str]],
    capabilities: list[Capability],
    zones: list[FlagReviewZone],
) -> list[ImpactRow]:
    """The impact rows of one caller file (empty if it does not parse or imports no target)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        logger.warning("Impact skipped a file that does not parse.")
        return []
    capability = lookup_capability(path, capabilities)
    labels = {"capability": capability.name if capability else "", "zone": _zone_of(path, zones)}
    rows: list[ImpactRow] = []
    for target, scope in scope_by_target.items():
        scan = _Scan(path, module_name(target), set(scope))
        scan.visit(tree)
        found = scan.rows or scan.import_only_rows()
        rows += [row.model_copy(update=labels) for row in found]
    return rows


def _zone_of(path: str, zones: list[FlagReviewZone]) -> str:
    lower = path.lower()
    for zone in zones:
        if matches_any(lower, zone.path_patterns):
            return zone.name
    return ""


def _dotted(node: ast.expr) -> str:
    """a.b.c for a chain of names and attributes, else ''."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else ""
    return ""


class _Scan(ast.NodeVisitor):
    """Looks for calls to one target module's in-scope functions inside one caller file."""

    def __init__(self, path: str, target_module: str, scope: set[str]) -> None:
        self.path = path
        self.target_module = target_module
        self.scope = scope
        # Plain functions and classes in scope, and method names (the part after the last dot).
        self.top_names = {name for name in scope if "." not in name}
        self.method_names = {name.rsplit(".", 1)[1] for name in scope if "." in name}
        self.imported_names: dict[str, str] = {}  # local name -> original name
        self.module_aliases: set[str] = set()
        self.import_lines: list[int] = []
        self.rows: list[ImpactRow] = []
        self._stack: list[str] = []

    # --- imports ---

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            if item.name == self.target_module:
                self.module_aliases.add(item.asname or item.name)
                self.import_lines.append(node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            return
        base = node.module or ""
        for item in node.names:
            local = item.asname or item.name
            if base == self.target_module:
                self.imported_names[local] = item.name
                self.import_lines.append(node.lineno)
            elif f"{base}.{item.name}" == self.target_module:
                self.module_aliases.add(local)
                self.import_lines.append(node.lineno)

    # --- where we are ---

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    # --- calls ---

    def visit_Call(self, node: ast.Call) -> None:
        self._look_at_call(node)
        self.generic_visit(node)

    def _look_at_call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            original = self.imported_names.get(func.id)
            if original in self.top_names:
                self._add(node, original, "direct")
        elif isinstance(func, ast.Attribute):
            if _dotted(func.value) in self.module_aliases and func.attr in self.top_names:
                self._add(node, func.attr, "direct")
            elif func.attr in self.method_names and self._imports_target():
                self._add(node, self._owner_of(func.attr), "possible")

    def _imports_target(self) -> bool:
        return bool(self.import_lines)

    def _owner_of(self, method: str) -> str:
        for name in sorted(self.scope):
            if "." in name and name.rsplit(".", 1)[1] == method:
                return name
        return method

    def _add(self, node: ast.Call, function: str, kind: str) -> None:
        caller = ".".join(self._stack) or MODULE_LEVEL
        self.rows.append(
            ImpactRow(
                caller_path=self.path,
                caller_function=caller,
                line=node.lineno,
                function_in_scope=function,
                kind=kind,
            )
        )

    def import_only_rows(self) -> list[ImpactRow]:
        if not self.import_lines:
            return []
        return [
            ImpactRow(
                caller_path=self.path,
                caller_function=MODULE_LEVEL,
                line=min(self.import_lines),
                function_in_scope="",
                kind="imports_only",
            )
        ]


# --- what impact means for the rest of the request (spec section 7, "Effects of impact") ---


def locked_signatures(rows: list[ImpactRow], modify_paths: set[str]) -> list[str]:
    """In-scope functions whose name and arguments must not change: a Direct caller sits in
    another file, and the accepted file plan does not also change that file (rule A9)."""
    planned = {path.lower() for path in modify_paths}
    return sorted(
        {
            row.function_in_scope
            for row in rows
            if row.kind == "direct" and row.caller_path.lower() not in planned
        }
    )


def zone_reasons(rows: list[ImpactRow]) -> dict[str, str]:
    """Zone name -> reason, for callers that sit in a flag-for-review zone (warning only)."""
    return {row.zone: "a caller is in this zone" for row in rows if row.zone}


def summary_line(result: ImpactResult) -> str:
    """One plain line for the chat: how many callers, or why there are none."""
    if not result.available:
        return UNAVAILABLE_TEXT
    if not result.rows:
        return "No callers found in the reference copy."
    shown = len(result.rows)
    more = f" and {result.more} more" if result.more else ""
    return f"{shown} caller(s) found{more}."
