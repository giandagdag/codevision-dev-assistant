"""Gian's answers and the "chief ran but nothing moved" count (Phase A fix 4, G2 to G5).

AS400 comparison: the scheduler reads the reply queue itself, so a job waiting in MSGW does not
need to be woken just to look. Plain Python, zero tokens, and no import of `chief_tick` (so the
tick can use it). Only comments by the repo owner count: a stranger's comment is never an order.

Two small notes in `ops/state/` (local, Git ignores them):
- `answers.json`: per issue, the key (comment id + hash of its text) of the last answer handled.
- `idle_runs.json`: how many chief runs in a row did nothing.
"""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

import stall
import usage_guard

Gh = Callable[[list[str]], str]
NO_ANSWER = "no answer yet"


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


# ---- reading the issues ----

def owner(gh: Gh) -> str:
    """The login of the repo owner (gh repo view --json owner), parsed here, no --jq."""
    data = json.loads(gh(["repo", "view", "--json", "owner"]) or "{}")
    login = (data.get("owner") or {}).get("login")
    if not isinstance(login, str) or not login:
        raise RuntimeError("could not read the repo owner")
    return login


def open_questions(gh: Gh, label: str = "needs-gian") -> list[tuple[int, str]]:
    """(number, title) of open `needs-gian` issues, our own `Team stalled` alarm left out.

    Only `needs-gian` blocks the team (waiting, stall check). Fix 7: `later_questions` reads the
    non-blocking `gian-later` issues the same way, so Gian can still overrule by commenting.
    """
    raw = gh(["issue", "list", "--label", label, "--state", "open",
              "--json", "number,title", "--limit", "100"]) or "[]"
    return [(int(x["number"]), str(x.get("title", ""))) for x in json.loads(raw)
            if isinstance(x, dict) and isinstance(x.get("number"), int)
            and not stall.is_stall_title(str(x.get("title", "")))]


def later_questions(gh: Gh) -> list[tuple[int, str]]:
    """Open `gian-later` issues (fix 7, S3): never blocking; his comment still wakes the chief.

    A failed read gives none, so it can never stop the `needs-gian` answers (code review).
    """
    try:
        return open_questions(gh, "gian-later")
    except Exception:  # noqa: BLE001
        return []


def open_issue_numbers(gh: Gh) -> set[int]:
    """Every open issue number (any label): the chief opening or closing one is progress."""
    raw = gh(["issue", "list", "--state", "open", "--json", "number", "--limit", "100"]) or "[]"
    return {int(x["number"]) for x in json.loads(raw)
            if isinstance(x, dict) and isinstance(x.get("number"), int)}


def newest_owner_comment(gh: Gh, number: int, who: str) -> tuple[str, str] | None:
    """(comment id, text) of the newest comment written by `who`, or None."""
    data = json.loads(gh(["issue", "view", str(number), "--json", "comments"]) or "{}")
    mine = [c for c in data.get("comments") or [] if isinstance(c, dict)
            and str((c.get("author") or {}).get("login", "")).lower() == who.lower()]
    if not mine:
        return None
    last = mine[-1]  # gh lists comments oldest first
    return str(last.get("id", "")), str(last.get("body", ""))


def answer_key(comment_id: str, text: str) -> str:
    return f"{comment_id}:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def find_new_answer(gh: Gh) -> tuple[int, str, str] | None:
    """(issue number, full text, key) of the first open question with a new owner comment.

    New means its key differs from the last one handled, so an edited comment counts once.
    """
    questions = open_questions(gh) + later_questions(gh)
    if not questions:
        return None
    who = owner(gh)
    seen = _read("answers.json")
    for number, _title in questions:
        found = newest_owner_comment(gh, number, who)
        if found is None:
            continue
        key = answer_key(*found)
        if seen.get(str(number)) != key:
            return number, found[1], key
    return None


def remember(number: int, key: str) -> None:
    seen = _read("answers.json")
    seen[str(number)] = key
    _write("answers.json", seen)


# ---- the no-progress count (G5) ----

def idle_runs() -> int:
    value = _read("idle_runs.json").get("count")
    return value if isinstance(value, int) and value > 0 else 0


def set_idle_runs(count: int) -> None:
    _write("idle_runs.json", {"count": count})
