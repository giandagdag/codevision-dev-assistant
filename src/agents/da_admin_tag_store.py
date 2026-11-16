"""The AI program tags file, `da_module_tags.json`, next to the code index (fix 11-2, D-D).

AS400 picture: a small physical file keyed by program name. One entry per module. Plain code, no AI.
This step only reads it; the tagger (a later step) writes it.
"""

import json
from pathlib import Path

from agents.da_admin_index import index_dir

TAGS_NAME = "da_module_tags.json"


def tags_path(directory: Path | None = None) -> Path:
    return (directory or index_dir()) / TAGS_NAME


def read_store(directory: Path | None = None) -> dict:
    """The whole file as {"modules": {path: entry}, "runs": [...]}. Missing or damaged = empty."""
    try:
        raw = json.loads(tags_path(directory).read_text(encoding="utf-8"))
        modules = raw["modules"]
        runs = raw.get("runs", [])
        if isinstance(modules, dict) and isinstance(runs, list):
            return {"modules": modules, "runs": runs}
    except OSError, ValueError, KeyError, TypeError:
        pass
    return {"modules": {}, "runs": []}


def read_tags(directory: Path | None = None) -> dict[str, dict]:
    """Module path to its entry (summary, proposed capability, state ...)."""
    return {p: e for p, e in read_store(directory)["modules"].items() if isinstance(e, dict)}
