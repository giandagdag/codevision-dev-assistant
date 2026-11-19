"""Tag versions: every Admin tag decision saves the tag file as version T (Upgrade G, G5f).

AS400 picture: a save file of the tag file after each change, with a list and a restore. Plain code,
no AI. An AI tagger run is NOT a version event: it only proposes, it decides nothing.
Restore brings back the tag file only; the rulebook version made by Approve is undone with History.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from agents.da_admin_audit import TAGS_RESTORED, add_admin_event
from agents.da_admin_index import index_dir
from agents.da_admin_tag_store import read_store, save_store

FOLDER_NAME = "da_module_tags_versions"
LIST_NAME = "list.json"
BUSY = "A rebuild or tag job is running. Wait for it to finish."
_TAGGED = ("approved", "matched")


def versions_dir(directory: Path | None = None) -> Path:
    return (directory or index_dir()) / FOLDER_NAME


def list_versions(directory: Path | None = None) -> list[dict]:
    """Newest first: [{"version", "note", "who", "at"}]. Missing or damaged file = empty."""
    try:
        rows = json.loads((versions_dir(directory) / LIST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    rows = [r for r in rows if isinstance(r, dict) and "version" in r]
    return sorted(rows, key=lambda r: -r["version"])


def save_version(
    note: str, who: str, directory: Path | None = None, now: datetime | None = None
) -> int:
    """Copy the current tag file as the next version number and add it to the list."""
    folder = versions_dir(directory)
    folder.mkdir(parents=True, exist_ok=True)
    rows = list_versions(directory)
    # Also look at the files on disk: a damaged list must never make us reuse (overwrite) a number.
    on_disk = [int(p.stem) for p in folder.glob("*.json") if p.stem.isdigit()]
    number = max([rows[0]["version"] if rows else 0, *on_disk]) + 1
    row = {
        "version": number, "note": note, "who": who,
        "at": (now or datetime.now()).isoformat(timespec="seconds"),
    }
    _write(folder / f"{number}.json", {**row, "modules": read_store(directory)["modules"]})
    _write(folder / LIST_NAME, [row, *rows])
    return number


def _write(path: Path, data) -> None:
    side = path.with_name(path.name + ".new")
    side.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(side, path)


def read_version(number: int, directory: Path | None = None) -> dict | None:
    """The saved tag modules of version `number`, or None when it does not exist."""
    try:
        raw = json.loads((versions_dir(directory) / f"{number}.json").read_text(encoding="utf-8"))
        return raw["modules"] if isinstance(raw["modules"], dict) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _tagged(modules: dict) -> dict[str, str]:
    return {
        path: str(e.get("proposed_capability", ""))
        for path, e in modules.items()
        if isinstance(e, dict) and e.get("state") in _TAGGED and e.get("proposed_capability")
    }


def compare_versions(a: int, b: int, directory: Path | None = None) -> dict | None:
    """What changed from version a to version b: modules added, moved and removed."""
    old, new = read_version(a, directory), read_version(b, directory)
    if old is None or new is None:
        return None
    before, after = _tagged(old), _tagged(new)
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "moved": sorted(p for p in set(before) & set(after) if before[p] != after[p]),
    }


def compare_text(diff: dict | None, a: int, b: int) -> str:
    if diff is None:
        return "One of those versions is missing."
    if not any(diff.values()):
        return f"No tag changes between version {a} and version {b}."
    return f"Version {a} to {b}: " + "; ".join(
        f"{len(diff[key])} {key}" + (f" ({', '.join(diff[key][:3])})" if diff[key] else "")
        for key in ("added", "moved", "removed")
    )


def restore_version(
    number: int, who: str, directory: Path | None = None, now: datetime | None = None
) -> tuple[bool, str]:
    """Put version `number`'s tags back as a NEW version "Restored from T". Never deletes history.
    Refused while a rebuild or tag job runs (it would write the same file)."""
    from agents.da_admin_rebuild import running_since  # late: that module is large

    modules = read_version(number, directory)
    if modules is None:
        return False, f"Tag version {number} was not found."
    if running_since(now, directory) is not None:
        return False, BUSY
    store = read_store(directory)
    save_store({**store, "modules": modules}, directory)
    text = f"Restored from {number}"
    new = save_version(text, who, directory, now)
    add_admin_event(TAGS_RESTORED, who, f"{text}, saved as tag version {new}", directory, now)
    return True, f"Tags restored from version {number}. Saved as version {new}."
