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
) -> None:
    """Add one run to the store and keep the last 10."""
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


def run_line(run: dict) -> str:
    """One run in plain words: done with the count, skipped pieces, or not saved."""
    when = str(run.get("started_at", ""))[:16].replace("T", " ")
    who = run.get("started_by", "")
    if not run.get("saved"):
        return f"{when} {who}: ❌ Not saved: {run.get('message', '')}"
    skipped = run.get("skipped") or []
    if skipped:
        return f"{when} {who}: ⚠️ {len(skipped)} pieces skipped ({run.get('count', 0)} saved)"
    return f"{when} {who}: ✅ Done, {run.get('count', 0)} pieces"
