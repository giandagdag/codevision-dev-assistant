"""Index health and recent refreshes for Repository and index (fix 11-1, AF-6). Plain code, no AI.

AS400 picture: health is read from the piece list (the physical file); the run store is a small
job log next to it. The run file keeps "path symbol" names only, never any code text.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from agents.da_code_index import DEFAULT_INDEX_DIR, PIECES_NAME

RUNS_NAME = "da_code_index_runs.json"
KEPT_RUNS = 10
FRESH_FOR = timedelta(days=1)
NEEDS_BUILDING = "The CodeVision index needs building"

# B1's own skips, shown as fixed rows with a lock (pattern, why).
FIXED_SKIPS = (
    ("da_*", "The assistant's own files and folders"),
    ("__pycache__, .venv", "Python working folders"),
    ("secret-looking paths", "Keys, tokens and .env files"),
)


@dataclass(frozen=True)
class IndexHealth:
    built: bool
    built_at: datetime | None = None
    modules: int = 0
    pieces: int = 0
    source: str = ""
    build_id: str = ""

    def is_fresh(self, now: datetime) -> bool:
        return self.built and self.built_at is not None and now - self.built_at <= FRESH_FOR

    def pill(self, now: datetime) -> str:
        if not self.built or self.built_at is None:
            return NEEDS_BUILDING
        age = now - self.built_at
        if age <= FRESH_FOR:
            return f"Index is fresh, built {_ago(age)}"
        return f"Index is older than a day, built {_ago(age)}"


def _ago(age: timedelta) -> str:
    hours = int(age.total_seconds() // 3600)
    if hours < 1:
        return "just now"
    return f"{hours} hours ago" if hours < 48 else f"{hours // 24} days ago"


def index_dir() -> Path:
    return Path(os.environ.get("DA_CODE_INDEX_DIR") or DEFAULT_INDEX_DIR)


def storage_line(db_path: Path) -> str:
    """Fix G5 R9: where the index and the database live (paths only), for the start-up log."""
    return f"Developer Assistant data: index folder {index_dir().resolve()}, database {db_path}"


def read_health(directory: Path | None = None) -> IndexHealth:
    """Health from the piece list. Missing or unreadable files mean "not built yet"."""
    try:
        raw = json.loads(((directory or index_dir()) / PIECES_NAME).read_text(encoding="utf-8"))
        pieces = raw["pieces"]
        return IndexHealth(
            True,
            datetime.fromisoformat(raw["built_at"]),
            len({piece["path"] for piece in pieces}),
            len(pieces),
            str(raw.get("source", "")),
            str(raw.get("build_id", "")),
        )
    except OSError, ValueError, KeyError, TypeError:
        return IndexHealth(False)


def record_run(
    started_by: str,
    started_at: datetime,
    saved: bool,
    count: int,
    skipped: list[str],
    message: str,
    directory: Path | None = None,
    extra: dict | None = None,
) -> None:
    """Add one run to the store and keep the last 10. `extra` holds fix 3's columns (mode, trigger,
    pieces re-read, seconds, programs tagged)."""
    path = (directory or index_dir()) / RUNS_NAME
    runs = recent_runs(directory)
    runs.insert(
        0,
        {
            "started_by": started_by,
            "started_at": started_at.isoformat(timespec="seconds"),
            "saved": saved,
            "count": count,
            "skipped": list(skipped),
            "message": message,
            **(extra or {}),
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(runs[:KEPT_RUNS], indent=1), encoding="utf-8")


def recent_runs(directory: Path | None = None) -> list[dict]:
    """Newest first, at most 10. A missing or damaged file is an empty list."""
    try:
        runs = json.loads(((directory or index_dir()) / RUNS_NAME).read_text(encoding="utf-8"))
        return [r for r in runs if isinstance(r, dict)][:KEPT_RUNS]
    except OSError, ValueError:
        return []


def tag_line(run: dict) -> tuple[str, str] | None:
    """Fix G5 R6: the Tags result of a run as (text, colour), or None when the run has no tag step.
    Green: all tagged. Amber: some could not be read. Red: the step failed."""
    if run.get("tag_error"):
        return f"Tags: {run['tag_error']}", "red"
    if "tag_total" not in run:
        return None
    total, bad = int(run["tag_total"]), int(run.get("unreadable", 0))
    if not bad:
        return f"Tags: all {total} programs tagged", "green"
    return f"Tags: {total - bad} of {total} tagged, {bad} could not be read", "orange"


def run_line(run: dict) -> str:
    """One run in plain words: done with the count, skipped pieces, or not saved."""
    when = str(run.get("started_at", ""))[:16].replace("T", " ")
    who = run.get("started_by", "")
    if run.get("trigger") == "Nightly":  # AH-10: the row says who started it
        who = f"{who} (Nightly)"
    if not run.get("saved"):
        return f"{when} {who}: ❌ Not saved: {run.get('message', '')}"
    if run.get("rolled_back_to"):  # G5d
        return f"{when} {who}: ↩️ Rolled back to build {run['rolled_back_to']}"
    build = f" (Build {run['build']})" if run.get("build") else ""  # G5a
    skipped = run.get("skipped") or []
    if skipped:
        noun = "piece" if len(skipped) == 1 else "pieces"
        return (
            f"{when} {who}: ⚠️ {len(skipped)} {noun} skipped ({run.get('count', 0)} saved){build}"
        )
    return f"{when} {who}: ✅ Done, {run.get('count', 0)} pieces{build}"
