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


def save_store(store: dict, directory: Path | None = None) -> None:
    """Write all or nothing: a temp file first, then swap it in (never a half-written file)."""
    path = tags_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(store, indent=1), encoding="utf-8")
    temp.replace(path)


def last_tagged(directory: Path | None = None) -> str:
    """When the newest saved tagging run started ("" before the first one)."""
    runs = read_store(directory)["runs"]
    started = runs[0].get("started_at", "") if runs and isinstance(runs[0], dict) else ""
    return str(started).replace("T", " ")


def read_tags(directory: Path | None = None) -> dict[str, dict]:
    """Module path to its entry (summary, proposed capability, state ...)."""
    return {p: e for p, e in read_store(directory)["modules"].items() if isinstance(e, dict)}
