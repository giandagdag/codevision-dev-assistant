"""Suggest a capability for a new (Unassigned) module from what it imports (fix 11-1, AF-12).

Plain code, no AI. Think of it as a "where used" check: a program that CALLs mostly Limits members
probably belongs to Limits. The text comes from the index snippets, else from the file itself.
"""

import json
import os
import re
from pathlib import Path

from agents.da_admin_modules import PROJECT_ROOT, module_paths, modules_by_capability
from agents.da_code_index import DEFAULT_INDEX_DIR, PIECES_NAME
from pydantic_classes.da_rulebook_models import Capability

NO_MATCH = "No matching capability found"
_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE)


def imported_names(text: str) -> list[str]:
    """Dotted module names imported by the text, in order."""
    return [a or b for a, b in _IMPORT.findall(text)]


def _source_text(path: str, folder_scope: str) -> str:
    """Snippets of the path from the built index, else the file under the folder scope."""
    index = Path(os.environ.get("DA_CODE_INDEX_DIR") or DEFAULT_INDEX_DIR) / PIECES_NAME
    try:
        raw = json.loads(index.read_text(encoding="utf-8"))
        text = "\n".join(p["snippet"] for p in raw["pieces"] if p["path"] == path)
        if text:
            return text
    except OSError, ValueError, KeyError, TypeError:
        pass
    root = PROJECT_ROOT / folder_scope.strip() if folder_scope.strip() else PROJECT_ROOT / "src"
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError:
        return ""


def suggest_capability(
    path: str, capabilities: list[Capability], folder_scope: str = "", text: str | None = None
) -> tuple[str, str]:
    """(capability name or "", plain reason). The capability whose modules the file imports most."""
    known = module_paths(folder_scope)
    by_cap = modules_by_capability(capabilities, known)
    text = _source_text(path, folder_scope) if text is None else text
    wanted = {name.split(".")[-1] for name in imported_names(text)}
    counts = {
        cap: sum(1 for p in paths if Path(p).stem in wanted and p != path)
        for cap, paths in by_cap.items()
    }
    best = max(counts.values(), default=0)
    if best == 0:
        return "", NO_MATCH
    name = next(cap for cap, n in counts.items() if n == best)  # tie: first in the catalog
    return name, f"Imports {best} module{'s' if best != 1 else ''} from {name}"
