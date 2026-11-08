"""Stall rules and the two small notes behind the alarm (Phase A fix 3).

AS400 comparison: a job in MSGW (waiting for a reply) looks the same as a job that is simply
quiet, unless something watches for it. This module is the part that decides "stalled or not".
It is plain Python, zero tokens, and it never imports `chief_tick` or `status_board`, so both can
use it.

Two notes in `ops/state/` (local, Git ignores them):
- `unpushed.json`: the branch a finished worker left with commits that `origin` lacks.
- `stall.json`: the reason the last idle tick found the team stalled (the board reads it).
"""

import json
import os
from collections.abc import Callable
from pathlib import Path

import usage_guard

Git = Callable[[list[str]], str]


def _path(name: str) -> Path:
    return usage_guard.state_path().parent / name


def _read(name: str) -> dict:
    try:
        data = json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(name: str, data: dict) -> None:
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _remove(name: str) -> None:
    try:
        _path(name).unlink(missing_ok=True)
    except OSError:
        pass  # a note that cannot be removed must not stop the tick


# ---- unpushed commits (F3) ----

def commits(count: int) -> str:
    return f"{count} commit" + ("" if count == 1 else "s")


def branch_for(phase) -> str | None:
    """`auto/phase-8` for phase '8'; None when the worker had no phase (the chief itself)."""
    text = str(phase or "").strip()
    return f"auto/phase-{text}" if text.isdigit() else None


def unpushed_count(branch: str, git: Git) -> int:
    """Commits on the local branch that the last known `origin/<branch>` lacks.

    Uses the remote-tracking branch git already has (a push updates it), so nothing is fetched.
    Raises when git cannot answer, for example when the branch was never pushed.
    """
    return int(git(["rev-list", "--count", f"origin/{branch}..{branch}"]).strip())


def remember_unpushed(branch: str) -> None:
    _write("unpushed.json", {"branch": branch})


def forget_unpushed() -> None:
    _remove("unpushed.json")


def current_unpushed(git: Git) -> tuple[str, int] | None:
    """(branch, count) while the remembered branch is still ahead of origin, else None.

    Counted again every time, so the warning goes away as soon as the branch is pushed.
    """
    branch = _read("unpushed.json").get("branch")
    if not isinstance(branch, str) or not branch:
        return None
    count = unpushed_count(branch, git)
    if count <= 0:
        forget_unpushed()
        return None
    return branch, count


# ---- the stall note (F1) ----

def save_stall(reason: str) -> None:
    _write("stall.json", {"reason": reason})


def read_stall() -> str | None:
    reason = _read("stall.json").get("reason")
    return reason if isinstance(reason, str) and reason else None


def clear_stall() -> None:
    _remove("stall.json")


# ---- when is the team stalled? (spec section 3) ----

NO_NEXT = "no valid Next line"
NOT_FINISHED = "nothing to do, but the job is not finished"


def next_lines(text: str) -> list[str]:
    """The `Next:` lines of STATUS.md (the same rule `has_work` uses)."""
    return [x for x in text.splitlines() if x.lstrip("- ").startswith("Next:")]


def reason(text: str, finished: Callable[[], bool], unpushed: tuple[str, int] | None) -> str | None:
    """Why the team is stalled, or None. Call it only when the tick came out `idle`.

    First match wins. `finished()` says whether the team is waiting for Gian on purpose (an open
    `needs-gian` issue) or the final PR is open; it is asked only when needed.
    """
    found = next_lines(text)
    if len(found) != 1:
        return NO_NEXT
    if found[0].lstrip("- ")[5:].strip().lower().startswith("none") and not finished():
        return NOT_FINISHED
    if unpushed:
        return f"unpushed commits on {unpushed[0]}"
    return None
