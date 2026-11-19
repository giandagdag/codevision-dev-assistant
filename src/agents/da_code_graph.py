"""Code links: who imports, calls and uses whom (Upgrade G, G1). Plain code, no AI.

AS400 picture: DSPPGMREF for every Python module. Only links that can be PROVEN from the code are
kept (a name defined in the same module, a name brought in by `from x import y`, or `alias.name`
where alias is an imported module). Everything else is counted per module and never drawn.
Standard library only (the `ast` module).
"""

import ast
import builtins
import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from agents.da_impact import module_name
from da_logging import get_logger

logger = get_logger(__name__)

GRAPH_NAME = "da_code_graph.json"
IMPORTS, CALLS, USES_CLASS = "imports", "calls", "uses class"
_BUILTINS = frozenset(dir(builtins))


@dataclass
class GraphResult:
    graph: dict
    reread: int = 0  # files parsed this time (Delta: only new or changed files)
    skipped: list[str] = field(default_factory=list)  # "path: reason"


def file_module(path: str) -> str:
    """agents/limits.py gives agents.limits; a package's __init__ is the package itself."""
    return module_name(path).removesuffix(".__init__")


def build_graph(
    source: Path,
    paths: Iterable[str],
    old: dict | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> GraphResult:
    """Read `paths` (relative to `source`). A file whose hash matches `old` is not parsed again."""
    paths = sorted(paths)
    old_files = (old or {}).get("files", {})
    files: dict[str, dict] = {}
    skipped: list[str] = []
    reread = 0
    for number, path in enumerate(paths, start=1):
        raw = (source / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        kept = old_files.get(path)
        if kept is not None and kept.get("hash") == digest:
            files[path] = {**kept, "edges": [], "unresolved": 0}
        else:
            reread += 1
            try:
                files[path] = _read_file(path, digest, raw.decode("utf-8", errors="replace"))
            except (SyntaxError, ValueError) as error:
                skipped.append(f"{path}: {type(error).__name__}: {error}"[:200])
        if progress is not None:
            progress(number, len(paths))
    _resolve(files)
    return GraphResult({"version": 1, "files": files}, reread, skipped)


def save_graph(graph: dict, directory: Path) -> None:
    """Same .new then replace habit as the index files: a half-written graph is never seen."""
    directory.mkdir(parents=True, exist_ok=True)
    side = directory / (GRAPH_NAME + ".new")
    side.write_text(json.dumps(graph, separators=(",", ":")), encoding="utf-8")
    side.replace(directory / GRAPH_NAME)


def load_graph(directory: Path) -> dict | None:
    """The saved graph, or None when it is missing or damaged."""
    try:
        graph = json.loads((directory / GRAPH_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(graph, dict) or not isinstance(graph.get("files"), dict):
        return None
    ok = all(isinstance(e, dict) and "module" in e for e in graph["files"].values())
    return graph if ok else None


# --- reading one file ------------------------------------------------------------------------


def _read_file(path: str, digest: str, text: str) -> dict:
    tree = ast.parse(text)
    module = file_module(path)
    names = _imported_names(tree, module, path.endswith("__init__.py"))
    defs = {
        node.name: "class" if isinstance(node, ast.ClassDef) else "function"
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    refs: list = [["imports", module, [[m]]] for m in sorted(names.imports)]
    unresolved = 0
    for scope, node in _scoped_nodes(tree, module):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                alts = _alternatives(base, module, names, defs)
                if alts:
                    refs.append(["base", scope, alts])
        elif isinstance(node, ast.Call):
            alts = _alternatives(node.func, module, names, defs)
            if alts:
                refs.append(["call", scope, alts])
            elif not _is_builtin(node.func):
                unresolved += 1
    return {
        "hash": digest, "module": module, "defs": defs, "refs": refs, "raw_unresolved": unresolved,
    }


def _is_builtin(func: ast.expr) -> bool:
    return isinstance(func, ast.Name) and func.id in _BUILTINS


@dataclass
class _Names:
    imports: set[str] = field(default_factory=set)  # every module this file imports
    modules: dict[str, str] = field(default_factory=dict)  # local name -> module
    symbols: dict[str, tuple[str, str]] = field(default_factory=dict)  # name -> (module, name)


def _imported_names(tree: ast.Module, module: str, is_package: bool) -> _Names:
    names = _Names()
    package = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.imports.add(alias.name)
                names.modules[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(node, package)
            if base is None:
                continue
            names.imports.add(base)
            for alias in node.names:
                names.imports.add(f"{base}.{alias.name}")
                names.symbols[alias.asname or alias.name] = (base, alias.name)
    return names


def _absolute(node: ast.ImportFrom, package: list[str]) -> str | None:
    if not node.level:
        return node.module
    if node.level - 1 > len(package):
        return None
    parent = package[: len(package) - (node.level - 1)]
    return ".".join(parent + ([node.module] if node.module else []))


def _alternatives(node: ast.expr, module: str, names: _Names, defs: dict) -> list[list[str]]:
    """The places a call or base class may point to, as [module, name] pairs, best first."""
    if isinstance(node, ast.Name):
        if node.id in names.symbols:
            return [list(names.symbols[node.id])]
        return [[module, node.id]] if node.id in defs else []
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        base = node.value.id
        found: list[list[str]] = []
        if base in names.symbols:  # from x import y, then y.f(): y may be a module x.y
            found.append([f"{names.symbols[base][0]}.{names.symbols[base][1]}", node.attr])
        if base in names.modules:
            found.append([names.modules[base], node.attr])
        return found
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
        dotted = _dotted(node.value)  # import a.b, then a.b.f()
        if dotted and dotted in {m for m in names.imports}:
            return [[dotted, node.attr]]
    return []


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (inner := _dotted(node.value)):
        return f"{inner}.{node.attr}"
    return ""


def _scoped_nodes(tree: ast.Module, module: str):
    """Every class and call node with the name of the function or class it sits in."""

    def dotted(prefix: str, name: str) -> str:
        return f"{prefix}.{name}" if prefix else name

    def walk(node: ast.AST, scope: str, in_class: str):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                # nested functions belong to the top-level function around them
                inner = scope if scope != module else dotted(in_class, child.name)
                yield from walk(child, inner, in_class)
            elif isinstance(child, ast.ClassDef):
                yield dotted(in_class, child.name), child
                yield from walk(child, scope, dotted(in_class, child.name))
            else:
                if isinstance(child, ast.Call):
                    yield scope, child
                yield from walk(child, scope, in_class)

    yield from walk(tree, module, "")


# --- turning references into edges -------------------------------------------------------------


def _resolve(files: dict[str, dict]) -> None:
    """Keep only references whose target module and name exist in these files. Run every build:
    an unchanged file can start (or stop) pointing at a file that was added or removed."""
    by_module = {entry["module"]: entry for entry in files.values()}
    for entry in files.values():
        edges: set[tuple[str, str, str]] = set()
        unresolved = entry.get("raw_unresolved", 0)
        for kind, source, alts in entry["refs"]:
            hit = _first_hit(alts, by_module)
            if kind == "imports":
                if hit and hit[0] != source:
                    edges.add((IMPORTS, source, hit[0]))
                continue
            if hit is None or hit[0] == entry["module"] and hit[1] == source:
                unresolved += hit is None
                continue
            target = f"{hit[0]}.{hit[1]}"
            is_class = by_module[hit[0]]["defs"][hit[1]] == "class"
            link = USES_CLASS if kind == "base" or is_class else CALLS
            edges.add((link, _full(entry, source), target))
        entry["edges"] = sorted(list(edge) for edge in edges)
        entry["unresolved"] = unresolved


def _full(entry: dict, scope: str) -> str:
    return scope if scope == entry["module"] else f"{entry['module']}.{scope}"


def _first_hit(alts: list[list[str]], by_module: dict[str, dict]) -> tuple[str, str] | None:
    for alt in alts:
        module = alt[0]
        if module not in by_module:
            continue
        if len(alt) == 1:
            return module, ""
        if alt[1] in by_module[module]["defs"]:
            return module, alt[1]
    return None
