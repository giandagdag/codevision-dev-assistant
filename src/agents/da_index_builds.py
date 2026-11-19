"""Numbered index builds and saved copies (Upgrade G, G5a and G5b). Plain code, no AI.

AS400 picture: a save file for every build. Each saved Full or Delta run gets a number K and a
manifest. The newest KEPT_INDEX_COPIES builds also keep full copies of the index files, so they
can be compared and restored; older builds keep the manifest only.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from agents.da_code_graph import GRAPH_NAME
from agents.da_code_index import FAISS_NAME, PIECES_NAME

BUILDS_NAME = "da_code_index_builds"
MANIFEST_NAME = "manifest.json"
KEPT_INDEX_COPIES = 5  # fixed in code on purpose, not an Admin setting
COPY_NAMES = (FAISS_NAME, PIECES_NAME, GRAPH_NAME)


def builds_dir(out: Path) -> Path:
    return out / BUILDS_NAME


def build_numbers(out: Path) -> list[int]:
    """Every saved build number, oldest first (a folder is a build when its manifest exists)."""
    try:
        folders = [p for p in builds_dir(out).iterdir() if (p / MANIFEST_NAME).is_file()]
    except OSError:
        return []
    return sorted(int(p.name) for p in folders if p.name.isdigit())


def next_build_number(out: Path) -> int:
    """Highest saved number + 1, so a rollback never reuses a number."""
    numbers = build_numbers(out)
    return numbers[-1] + 1 if numbers else 1


def current_build(out: Path | None = None) -> int | None:
    """The build number the saved index carries (G5e), or None: no index, or a command-line
    build that was not numbered."""
    from agents.da_admin_index import index_dir  # late: that module is imported by many callers

    try:
        raw = json.loads(((out or index_dir()) / PIECES_NAME).read_text(encoding="utf-8"))
        return int(raw.get("build") or 0) or None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def read_manifest(out: Path, number: int) -> dict | None:
    try:
        manifest = json.loads((builds_dir(out) / str(number) / MANIFEST_NAME).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def has_copy(out: Path, number: int) -> bool:
    folder = builds_dir(out) / str(number)
    return all((folder / name).is_file() for name in COPY_NAMES)


def save_build(out: Path, number: int, mode: str, started_by: str, when: datetime) -> dict:
    """Write the manifest and a copy of the index files for build `number`, then drop the copies
    (never the manifests) of builds older than the newest KEPT_INDEX_COPIES."""
    record = json.loads((out / PIECES_NAME).read_text(encoding="utf-8"))
    try:
        graph_files = json.loads((out / GRAPH_NAME).read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError):
        graph_files = {}
    pieces = record.get("pieces", [])
    manifest = {
        "build": number,
        "time": when.isoformat(timespec="seconds"),
        "mode": mode,
        "started_by": started_by,
        "files": {p["path"]: p["file_hash"] for p in pieces if "file_hash" in p},
        "pieces": len(pieces),
        "edges": sum(len(f.get("edges", [])) for f in graph_files.values()),
        "modules": len({p["path"] for p in pieces}),
    }
    folder = builds_dir(out) / str(number)
    folder.mkdir(parents=True, exist_ok=True)
    for name in COPY_NAMES:
        if (out / name).is_file():
            shutil.copy2(out / name, folder / name)
    (folder / MANIFEST_NAME).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    _drop_old_copies(out)
    return manifest


def compare_builds(out: Path, first: int, second: int) -> dict | None:
    """What changed from build `first` to build `second`, or None when a manifest is missing."""
    a, b = read_manifest(out, first), read_manifest(out, second)
    if a is None or b is None:
        return None
    old, new = a.get("files", {}), b.get("files", {})
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(p for p in set(old) & set(new) if old[p] != new[p]),
        "pieces": b.get("pieces", 0) - a.get("pieces", 0),
        "edges": b.get("edges", 0) - a.get("edges", 0),
    }


def compare_text(result: dict | None, first: int, second: int) -> str:
    if result is None:
        return "One of these builds has no saved manifest."
    return (
        f"Build {first} to build {second}: {len(result['added'])} modules added, "
        f"{len(result['removed'])} removed, {len(result['changed'])} changed. "
        f"Pieces {result['pieces']:+d}, links {result['edges']:+d}."
    )


def _drop_old_copies(out: Path) -> None:
    for number in build_numbers(out)[:-KEPT_INDEX_COPIES]:
        for name in COPY_NAMES:
            (builds_dir(out) / str(number) / name).unlink(missing_ok=True)
