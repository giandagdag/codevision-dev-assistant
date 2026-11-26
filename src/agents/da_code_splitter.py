"""Cuts Python files into pieces, one per function, class and method (spec 3.2a, decision D-F).

Like splitting a source member into its subroutines so each can be found and reused alone.
Standard library only (the `ast` module). Phase 3 uses it in tests and to check the pretend
index; the real index is built by the work adapter (P15).
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from agents.da_search_index import PIECE_TEXT_LIMIT, looks_secret
from da_logging import get_logger

logger = get_logger(__name__)

SNIPPET_LIMIT = PIECE_TEXT_LIMIT  # one number, kept in the loader so the two can never differ
MODULE_SYMBOL = "<module>"
SKIPPED_FOLDERS = frozenset({".venv", "__pycache__"})


@dataclass(frozen=True)
class CodePiece:
    path: str
    symbol: str
    line_start: int
    line_end: int
    # The source text of the piece, cut to SNIPPET_LIMIT. The full text stays in the file.
    snippet: str


def split_python_file(path: str, text: str) -> list[CodePiece]:
    """One piece per top-level function, class and method, plus one `<module>` piece for any
    other module-level code. A file that does not parse gives one whole-file piece."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        logger.warning("Could not parse a Python file; using it as one whole-file piece.")
        return [_whole_file_piece(path, text)]
    lines = text.splitlines()
    pieces: list[CodePiece] = []
    module_lines: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            pieces += _pieces_for_definition(path, node, lines, prefix="")
        else:
            module_lines.update(range(_first_line(node), node.end_lineno + 1))
    module_piece = _module_piece(path, lines, module_lines)
    return ([module_piece] if module_piece else []) + pieces


def split_folder(root: Path) -> list[CodePiece]:
    """Every .py file under root, sorted by path so the piece numbers are stable."""
    root = Path(root)
    pieces: list[CodePiece] = []
    for file in sorted(root.rglob("*.py")):
        relative = file.relative_to(root)
        if SKIPPED_FOLDERS & set(relative.parts) or looks_secret(relative.as_posix()):
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        pieces += split_python_file(relative.as_posix(), text)
    return pieces


def _pieces_for_definition(
    path: str, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, lines: list[str],
    prefix: str,
) -> list[CodePiece]:
    symbol = f"{prefix}{node.name}"
    first = _first_line(node)
    pieces = [_piece(path, symbol, first, node.end_lineno, lines)]
    if isinstance(node, ast.ClassDef):
        for child in node.body:
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                pieces += _pieces_for_definition(path, child, lines, prefix=f"{symbol}.")
    return pieces


def _first_line(node: ast.stmt) -> int:
    # A decorator belongs to the function it decorates.
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno] + [decorator.lineno for decorator in decorators])


def _piece(path: str, symbol: str, first: int, last: int, lines: list[str]) -> CodePiece:
    text = "\n".join(lines[first - 1 : last])
    return CodePiece(path, symbol, first, last, text[:SNIPPET_LIMIT])


def _module_piece(path: str, lines: list[str], module_lines: set[int]) -> CodePiece | None:
    if not module_lines:
        return None
    first, last = min(module_lines), max(module_lines)
    text = "\n".join(lines[number - 1] for number in sorted(module_lines))
    if not text.strip():
        return None
    return CodePiece(path, MODULE_SYMBOL, first, last, text[:SNIPPET_LIMIT])


def _whole_file_piece(path: str, text: str) -> CodePiece:
    return CodePiece(path, "", 1, max(1, len(text.splitlines())), text[:SNIPPET_LIMIT])
