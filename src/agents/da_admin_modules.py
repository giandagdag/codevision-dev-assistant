"""Modules per capability for the Admin catalog (fix 11-1, AF-9). Plain code, no AI.

A capability's modules are the indexed files that match its path patterns. With a built index
(B1's piece list) the files come from it; at home with no index, from the files under the folder
scope. Think of it as a "where used" list: which source members belong to which application area.
"""

import json
import os
from fnmatch import fnmatchcase
from pathlib import Path

from agents.da_code_index import DEFAULT_INDEX_DIR, PIECES_NAME
from pydantic_classes.da_rulebook_models import Capability

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHOWN_MODULES = 6


def scope_folder(folder_scope: str) -> Path:
    """The folder scope, else B1's DA_CODE_INDEX_SOURCE, else B1's default (the src folder)."""
    if folder_scope.strip():
        return PROJECT_ROOT / folder_scope.strip()
    return Path(os.environ.get("DA_CODE_INDEX_SOURCE") or PROJECT_ROOT / "src")


def module_paths(folder_scope: str = "", index_dir: Path | None = None) -> list[str]:
    """Sorted file paths: from the built index, else the .py files under the folder scope."""
    pieces_file = (index_dir or Path(os.environ.get("DA_CODE_INDEX_DIR") or DEFAULT_INDEX_DIR)) / (
        PIECES_NAME
    )
    try:
        raw = json.loads(pieces_file.read_text(encoding="utf-8"))
        return sorted({str(piece["path"]) for piece in raw["pieces"]})
    except OSError, ValueError, KeyError, TypeError:
        pass  # no usable index: fall back to the files themselves
    root = scope_folder(folder_scope)
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.py") if p.is_file())


def modules_by_capability(capabilities: list[Capability], paths: list[str]) -> dict[str, list[str]]:
    """Every capability with ALL the paths its patterns match (not first-match-wins), so a shared
    module shows under each capability that claims it."""
    return {
        c.name: [
            p
            for p in paths
            if any(fnmatchcase(p.lower(), pattern.lower()) for pattern in c.path_patterns)
        ]
        for c in capabilities
    }


def share_counts(by_capability: dict[str, list[str]]) -> dict[str, int]:
    """How many capabilities claim each path ("×2" on the screen when more than 1)."""
    counts: dict[str, int] = {}
    for paths in by_capability.values():
        for path in paths:
            counts[path] = counts.get(path, 0) + 1
    return counts


def module_chips(paths: list[str], counts: dict[str, int]) -> tuple[list[str], int]:
    """(chip labels for the first 6, how many more). A shared path gets " ×2" (or ×3 ...)."""
    labels = [
        Path(p).name + (f" ×{counts[p]}" if counts.get(p, 1) > 1 else "")
        for p in paths[:SHOWN_MODULES]
    ]
    return labels, max(0, len(paths) - SHOWN_MODULES)


def matches_search(name: str, description: str, paths: list[str], text: str) -> bool:
    """The catalog search: capability name, description or one of its module names."""
    needle = text.strip().lower()
    if not needle:
        return True
    return (
        needle in name.lower()
        or needle in description.lower()
        or any(needle in Path(p).name.lower() for p in paths)
    )
