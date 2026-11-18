"""The fix queue bar on the Team status board (17 Nov): how much of the agreed fix list is done.

AS400 comparison: a job queue display. Each entry is a fix batch; the bar shows the share of the
whole queue that has ended normally, plus how far the running entry is.

The list lives in `ops/work_queue.json` (committed). Claude chat or Gian edit it; the builder never
does (guard files). It is read from `origin/auto/phases-7-10` first, so a new entry pushed there
shows on the board without waiting for the laptop's branch, then from the working folder.

An entry is done when its JSON says `"done": true`, or its branch is merged into the merge base
(`merge-base --is-ancestor`), or a merge commit on the merge base names its branch (the branch may
be deleted after the merge). Plain Python, zero tokens, reads only. Any failure means "no bar".
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

Git = Callable[[list[str]], str]
QUEUE_PATH = "ops/work_queue.json"
# Shares of the running entry: spec and plan 10, build 70 (by steps), review 5 per round (max 15).
SHARE_START, SHARE_BUILD, SHARE_PER_REVIEW, SHARE_REVIEW_MAX = 10, 70, 5, 15


@dataclass
class Entry:
    name: str
    branch: str
    size: int
    plan: str = ""
    done: bool = False


@dataclass
class QueueView:
    title: str
    percent: int
    done_count: int
    total_count: int
    now: str = ""  # the running entry, "" when all are done
    now_detail: str = ""
    upcoming: tuple[str, ...] = ()

    def row(self, bar: Callable[[int], str]) -> str:
        tail = f" · now: {self.now}" + (f" ({self.now_detail})" if self.now_detail else "") \
            if self.now else " · all done"
        return (f"| {self.title} | `{bar(self.percent)}` {self.percent}% · "
                f"{self.done_count} of {self.total_count} done{tail} |")

    def next_row(self) -> str | None:
        return f"| Then | {', '.join(self.upcoming)} |" if self.upcoming else None


def _try(git: Git, args: list[str]) -> str | None:
    try:
        return git(args)
    except Exception:  # noqa: BLE001 - any git failure means "cannot say"
        return None


def load(git: Git, root: Path, base: str) -> tuple[str, list[Entry]] | None:
    text = _try(git, ["show", f"origin/{base}:{QUEUE_PATH}"])
    if text is None:
        try:
            text = (root / QUEUE_PATH).read_text(encoding="utf-8")
        except OSError:
            return None
    try:
        data = json.loads(text)
        entries = [Entry(str(e["name"]), str(e["branch"]), max(1, int(e.get("size", 1))),
                         str(e.get("plan", "")), bool(e.get("done", False)))
                   for e in data["items"]]
        return str(data.get("title", "Fix queue")), entries
    except (ValueError, KeyError, TypeError):
        return None


def _merged(git: Git, entry: Entry, base: str, merge_subjects: str) -> bool:
    if entry.done:
        return True
    for ref in (f"origin/{entry.branch}", entry.branch):
        for target in (f"origin/{base}", base):
            if _try(git, ["merge-base", "--is-ancestor", ref, target]) is not None:
                return True
    return any(line.rstrip().endswith(("/" + entry.branch, " " + entry.branch))
               for line in merge_subjects.splitlines())


def _plan_steps(git: Git, root: Path, entry: Entry) -> int:
    """Numbered lines under '## Steps' in the entry's plan file (branch copy first)."""
    if not entry.plan:
        return 0
    text = None
    for ref in (f"origin/{entry.branch}", entry.branch):
        text = _try(git, ["show", f"{ref}:{entry.plan}"])
        if text is not None:
            break
    if text is None:
        try:
            text = (root / entry.plan).read_text(encoding="utf-8")
        except OSError:
            return 0
    count, inside = 0, False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.lower().startswith("## steps")
        elif inside and re.match(r"\d+\.\s", line):
            count += 1
    return count


def _running(git: Git, root: Path, entry: Entry, base: str) -> tuple[Fraction, str]:
    """(share of this entry done, short text). Steps and review rounds from its own commits."""
    out = None
    for ref in (entry.branch, f"origin/{entry.branch}"):
        for target in (base, f"origin/{base}"):
            out = _try(git, ["log", f"{target}..{ref}", "--format=%s", "-300"])
            if out is not None:
                break
        if out is not None:
            break
    if not out:
        return Fraction(0), "not started"
    steps = [int(n) for s in out.splitlines()
             for m in [re.search(r"\bsteps? (\d+)(?: (?:and|to) (\d+))?", s, re.IGNORECASE)] if m
             for n in m.groups() if n]
    # Also "C1/C2: ..." style subjects: each step ID named at the start counts once.
    ids = {i for s in out.splitlines()
           for m in [re.match(r"([A-Z]+\d+[a-z]?(?:/[A-Z]+\d+[a-z]?)*):", s)] if m
           for i in m.group(1).split("/")}
    steps.append(len(ids))
    reviews = [int(m.group(1)) for s in out.splitlines()
               if (m := re.search(r"\breview (?:round )?(\d+)\b", s, re.IGNORECASE))]
    total = _plan_steps(git, root, entry)
    done = min(max(steps, default=0), total) if total else 0
    share = Fraction(SHARE_START)
    if total:
        share += Fraction(SHARE_BUILD * done, total)
    review = max(reviews, default=0)
    share += min(SHARE_REVIEW_MAX, SHARE_PER_REVIEW * review)
    share = min(share, Fraction(95))  # 100 only when merged
    parts = [f"step {done} of {total}" if total else "planning"]
    if review:
        parts.append(f"review round {review}")
    return share / 100, ", ".join(parts)


def view(git: Git, root: Path, base: str) -> QueueView | None:
    """The bar, or None when the queue file is missing or broken (the board then skips it)."""
    loaded = load(git, root, base)
    if not loaded:
        return None
    title, entries = loaded
    if not entries:
        return None
    subjects = ""
    for target in (f"origin/{base}", base):
        got = _try(git, ["log", target, "--merges", "--format=%s", "-500"])
        if got is not None:
            subjects = got
            break
    finished = [_merged(git, e, base, subjects) for e in entries]
    total = sum(e.size for e in entries)
    done_size = Fraction(sum(e.size for e, f in zip(entries, finished, strict=True) if f))
    waiting = [e for e, f in zip(entries, finished, strict=True) if not f]
    now, detail = "", ""
    if waiting:
        share, detail = _running(git, root, waiting[0], base)
        done_size += share * waiting[0].size
        now = waiting[0].name
    return QueueView(title, int(done_size * 100 / total), sum(finished), len(entries), now,
                     detail, tuple(e.name for e in waiting[1:]))
