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


# --- Fix G4 L2/L3: the patterns list and the Add modules picker (plain code) ---


def split_patterns(text: str) -> list[str]:
    """The Patterns cell is one pattern per line."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def is_exact(pattern: str) -> bool:
    """An exact file has no wildcard; anything else is a pattern."""
    return not any(ch in pattern for ch in "*?[")


def count_matches(pattern: str, paths: list[str]) -> int:
    """How many indexed modules the pattern matches now (same matching as the catalog)."""
    return sum(1 for p in paths if fnmatchcase(p.lower(), pattern.strip().lower()))


def first_matches(pattern: str, paths: list[str], limit: int = 5) -> list[str]:
    """The first few indexed paths a pattern matches, for the live hint (Fix G5 L3)."""
    p = pattern.strip().lower()
    return [x for x in paths if fnmatchcase(x.lower(), p)][:limit]


def example_pattern(paths: list[str]) -> str:
    """A placeholder built from the index: the first module's folder, like `agent_flows/*`."""
    folder = paths[0].rpartition("/")[0] if paths else ""
    return f"{folder}/*" if folder else "src/agents/*limits*"


def edit_patterns(form: dict, index: int, remove: str = "", add: str = "") -> dict:
    """Remove or add one pattern in catalog row `index` of the draft. A blank add is ignored."""
    rows = form.get("capabilities", [])
    if 0 <= index < len(rows):
        lines = [p for p in split_patterns(rows[index].get("path_patterns", "")) if p != remove]
        if add.strip() and add.strip() not in lines:
            lines.append(add.strip())
        rows[index]["path_patterns"] = "\n".join(lines)
    return form


def add_modules_to_form(form: dict, capability: str, paths: list[str]) -> dict:
    """Exact-path patterns on `capability`; the same exact entry leaves other capabilities (a move).
    Known limit: a module an earlier wildcard pattern claims stays with that capability."""
    for row in form.get("capabilities", []):
        lines = split_patterns(row.get("path_patterns", ""))
        if row.get("name") == capability:
            lines += [p for p in paths if p not in lines]
        else:
            lines = [p for p in lines if p not in paths]
        row["path_patterns"] = "\n".join(lines)
    return form


def module_rows(
    capabilities: list[Capability],
    paths: list[str],
    summaries: dict[str, str],
    target: str = "",
    search: str = "",
    unassigned_only: bool = True,
) -> list[dict]:
    """One row per indexed module: path, current capability (first match), summary, and the name
    it would move from when `target` is another capability."""
    owner: dict[str, str] = {}
    for name, mine in modules_by_capability(capabilities, paths).items():
        for p in mine:
            owner.setdefault(p, name)
    needle = search.strip().lower()
    rows = []
    for p in paths:
        current = owner.get(p, "")
        summary = summaries.get(p, "")
        if unassigned_only and current:
            continue
        if needle and needle not in p.lower() and needle not in summary.lower():
            continue
        moves = current if current and current != target else ""
        rows.append({"path": p, "current": current, "summary": summary, "moves_from": moves})
    return rows


def matches_search(
    name: str, description: str, paths: list[str], text: str, seniors: tuple[str, ...] = ()
) -> bool:
    """The catalog search: capability name, description, a module name or a senior's name."""
    needle = text.strip().lower()
    if not needle:
        return True
    return (
        needle in name.lower()
        or needle in description.lower()
        or any(needle in Path(p).name.lower() for p in paths)
        or any(needle in s.lower() for s in seniors)
    )
