"""The "Team status" issue (Phase A fix 2): one GitHub issue Gian can glance at on his phone.

AS400 comparison: a job that refreshes ONE message on a shared display every wake-up. Anyone can
look; nobody has to run a report. Plain Python, zero tokens. It only READS local files (STATUS.md,
`ops/state/running.json`, `ops/state/usage.json`, git, `gh issue list`) and WRITES one issue.

It never reads `usage_raw.json`, `.env` or worker reply files, and it never copies prompt text.
A failure is logged as one line in `logs/status_board.log` and never stops the tick.
"""

import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import stall
import usage_guard

ROOT = Path(__file__).resolve().parent.parent
TITLE = "🤖 Team status"
LABEL = "team-status"
MERGE_BASE = "auto/phases-7-10"
PHASES = (7, 8, 9, 10)
HOUR = 3600
USAGE_NOTE_AFTER = 600  # usage older than this gets "(as of HH:MM)" next to its bar
NEXT_CUT, LINE_CUT = 300, 160

# Shares of one phase (spec 3a). They add up to 100.
SHARE_SPEC, SHARE_PLAN, SHARE_BUILD, SHARE_REVIEW, SHARE_MERGED = 15, 10, 55, 15, 5

Gh = Callable[[list[str]], str]
Git = Callable[[list[str]], str]


class GitError(Exception):
    """A git command failed (missing branch, not a repository...)."""


def run_git(args: list[str]) -> str:
    # git prints UTF-8; the Windows default (cp1252) would garble commit subjects.
    done = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False, cwd=ROOT)
    if done.returncode != 0:
        raise GitError(f"git {' '.join(args[:2])} failed")
    return done.stdout


# ---- progress bars and percentages (pure) ----

def bar(percent) -> str:
    """10 characters, rounded down: 31 -> 3 filled."""
    filled = max(0, min(10, int(percent // 10)))
    return "▓" * filled + "░" * (10 - filled)


@dataclass
class PhaseFacts:
    """What the markers say about one phase. Missing or unreadable means 'not done'."""
    phase: int
    spec_approved: bool = False
    plan_exists: bool = False
    plan_approved: bool = False
    steps_total: int = 0
    step_done: int = 0
    review_rounds: int = 0
    last_review_clean: bool = False
    pushed: bool = False
    merged: bool = False
    unreadable: bool = False  # git could not be asked at all


@dataclass
class Progress:
    percent: int
    stage: str
    estimate: bool = False

    def line(self) -> str:
        tail = " (estimate)" if self.estimate else ""
        return f"`{bar(self.percent)}` {self.percent}% · {self.stage}{tail}"


def phase_progress(f: PhaseFacts) -> Progress:
    """Spec 3a: Spec 15, Plan 10, Build 55 (by steps), Code review 15, Merged 5."""
    if f.merged:
        return Progress(100, "Merged")
    total = Fraction(0)
    if f.spec_approved:
        total += SHARE_SPEC
    plan_done = f.plan_exists and f.plan_approved
    if plan_done:
        total += SHARE_PLAN
    done_steps = min(f.step_done, f.steps_total) if f.steps_total > 0 else 0
    if f.steps_total > 0:
        total += Fraction(SHARE_BUILD * done_steps, f.steps_total)
    if f.pushed and f.last_review_clean:
        review = SHARE_REVIEW
    else:
        review = min(SHARE_REVIEW, 5 * f.review_rounds)
    total += review
    build_done = f.steps_total > 0 and done_steps >= f.steps_total
    if not f.spec_approved:
        stage = "Spec"
    elif not plan_done:
        stage = "Plan"
    elif not build_done:
        stage = (f"Build, step {done_steps} of {f.steps_total}" if f.steps_total else "Build")
    elif review < SHARE_REVIEW:
        stage = "Code review"
    else:
        stage = "Waiting to merge"
    # A stage after a finished one that cannot be read: say so (AS-15). A phase with nothing
    # yet is a plain 0%.
    estimate = (f.unreadable or (f.spec_approved and not f.plan_exists)
                or (f.plan_exists and f.steps_total == 0))
    return Progress(int(total), stage, estimate)


def overall_percent(merged_count: int, current: Progress | None) -> int:
    """(merged phases x 100 + current phase %) / 4, rounded down. No current phase: all merged."""
    if current is None:
        return 100
    return (merged_count * 100 + current.percent) // len(PHASES)


# ---- reading plans, specs and commits ----

def count_plan_steps(plan_text: str) -> int:
    """Numbered items at column 0 under '## Steps' (step 0 is 'Done', not counted), or
    '### Step N' headings. Nested (indented) numbers are not steps."""
    numbered, in_steps = 0, False
    for line in plan_text.splitlines():
        if re.match(r"^#{1,6}\s*Steps\b", line):
            in_steps = True
        elif re.match(r"^#{1,2}\s", line):
            in_steps = False
        elif in_steps and re.match(r"^[1-9]\d*\.\s", line):
            numbered += 1
    headings = len(re.findall(r"^#{2,4}\s*Step\s+[1-9]\d*\b", plan_text, flags=re.MULTILINE))
    return numbered or headings


def highest_step(subjects: list[str], phase: int) -> int:
    """Highest K in commit subjects like 'Phase 7 step 8a: ...' (the letter is ignored)."""
    found = [int(m.group(1)) for s in subjects
             if (m := re.match(rf"\s*Phase {phase} step (\d+)", s, flags=re.IGNORECASE))]
    return max(found, default=0)


def is_approved(text: str) -> bool:
    """APPROVED in the first lines, and not 'NOT APPROVED'."""
    head = "\n".join(text.splitlines()[:30])
    return bool(re.search(r"(?<!NOT )\bAPPROVED\b", head))


def _ok(git: Git, args: list[str]) -> bool:
    try:
        git(args)
    except Exception:  # noqa: BLE001 - any git problem means "no"
        return False
    return True


def _merged_into(git: Git, ref: str, base: str) -> bool:
    """An ancestor of the base, but not the same commit: a branch just cut from the base with
    no work yet is an ancestor too, and must not count as merged."""
    if not _ok(git, ["merge-base", "--is-ancestor", ref, base]):
        return False
    tips = (_try(git, ["rev-parse", ref]), _try(git, ["rev-parse", base]))
    return not (tips[0] and tips[0] == tips[1])


def _try(git: Git, args: list[str]) -> str | None:
    try:
        return git(args)
    except Exception:  # noqa: BLE001
        return None


def phase_facts(phase: int, git: Git, root: Path = ROOT) -> PhaseFacts:
    f = PhaseFacts(phase)
    mine = [f"auto/phase-{phase}", f"origin/auto/phase-{phase}"]
    bases = [MERGE_BASE, f"origin/{MERGE_BASE}"]
    f.merged = any(_merged_into(git, r, b) for r in mine for b in bases)
    if f.merged:
        return f
    if _try(git, ["rev-parse", "--is-inside-work-tree"]) is None:
        f.unreadable = True
    live = [r for r in mine + bases if _ok(git, ["rev-parse", "--verify", "-q", r])]

    def read(path: str) -> str | None:
        for ref in live:
            text = _try(git, ["show", f"{ref}:{path}"])
            if text is not None:
                return text
        try:
            return (root / path).read_text(encoding="utf-8")
        except OSError:
            return None

    spec_text = None
    for ref in live:
        listing = _try(git, ["ls-tree", "--name-only", ref, "specs/"])
        names = _spec_names(listing.splitlines() if listing else [], phase)
        if names:
            spec_text = _try(git, ["show", f"{ref}:{names[0]}"])
            break
    if spec_text is None and (root / "specs").is_dir():
        names = _spec_names([f"specs/{p.name}" for p in (root / "specs").iterdir()], phase)
        spec_text = read(names[0]) if names else None
    f.spec_approved = bool(spec_text) and is_approved(spec_text)
    plan_text = read(f"specs/phase-{phase}-plan.md")
    f.plan_exists = plan_text is not None
    f.steps_total = count_plan_steps(plan_text or "")
    subjects = _commit_subjects(git, mine)
    f.plan_approved = f.plan_exists and any(
        re.search(r"plan-reviewer approved", s, flags=re.IGNORECASE) for s in subjects)
    f.step_done = highest_step(subjects, phase)
    rounds = [s for s in subjects if re.search(r"code review round", s, flags=re.IGNORECASE)]
    f.review_rounds = len(rounds)
    f.last_review_clean = bool(rounds) and bool(re.search(r"0 must fix", rounds[0], re.IGNORECASE))
    local, remote = (_try(git, ["rev-parse", r]) for r in mine)
    f.pushed = bool(local) and local == remote
    return f


def _spec_names(paths: list[str], phase: int) -> list[str]:
    """specs/phase-N-<name>.md that is not a plan, facts, fixes or review file."""
    names = [p.strip() for p in paths
             if re.fullmatch(rf"specs/phase-{phase}-[a-z0-9-]+\.md", p.strip())]
    skip = ("-plan", "-facts", "-fixes", "-review")
    return sorted(n for n in names if not any(word in n for word in skip))


def _commit_subjects(git: Git, refs: list[str]) -> list[str]:
    for ref in refs:
        out = _try(git, ["log", ref, "--format=%s", "-300"])
        if out is not None:
            return out.splitlines()
    return []


def current_phase(git: Git, root: Path = ROOT) -> tuple[int, PhaseFacts | None, int]:
    """(merged count, facts of the first unmerged phase or None, overall percent)."""
    merged = 0
    for phase in PHASES:
        facts = phase_facts(phase, git, root)
        if facts.merged:
            merged += 1
            continue
        progress = phase_progress(facts)
        return merged, facts, overall_percent(merged, progress)
    return merged, None, 100


# ---- what the board is told ----

@dataclass
class Issue:
    number: int | None
    title: str
    url: str = ""

    def link(self) -> str:
        return f"[#{self.number}]({self.url}) {self.title}" if self.url else (
            f"#{self.number} {self.title}")


@dataclass
class Inputs:
    result: str  # what the tick (or launch/stop) returned
    now: float
    next_text: str = ""
    log_lines: list[str] = field(default_factory=list)
    running: dict | None = None  # running.json, only when the worker is alive
    usage: usage_guard.Usage | None = None
    usage_fresh: bool = True
    needs_gian: list[Issue] = field(default_factory=list)
    needs_work: list[Issue] = field(default_factory=list)
    branch: str = ""
    commits: list[str] = field(default_factory=list)
    facts: PhaseFacts | None = None
    merged_count: int = 0
    overall: int = 0
    stall: str | None = None  # why the last idle tick found the team stalled
    warnings: list[str] = field(default_factory=list)


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _clock(epoch: float) -> str:
    return usage_guard.format_sgt(epoch)[7:]  # "13:17 SGT" from "07 Nov 13:17 SGT"


def _duration(seconds: float) -> str:
    minutes = max(0, int(seconds // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def _next_is_none(text: str) -> bool:
    return not text or text.strip().lower().startswith("none")


def top_line(i: Inputs) -> str:
    """First match wins (spec section 3)."""
    nxt = i.next_text.lower()
    if i.needs_gian or "waiting for gian" in nxt:
        count = f" ({len(i.needs_gian)} open)" if i.needs_gian else ""
        return f"## 🔴 WAITING FOR YOU{count}"
    if i.stall and i.result == "idle":
        return f"## 🔴 STALLED: {i.stall}"
    if i.result == "stopped":
        if i.usage is None or not i.usage_fresh:
            return "## ⚫ GUARD BLIND: the usage cannot be read, nothing starts"
        decision = usage_guard.decide(i.usage)
        if not decision.go:
            return f"## 🟡 PAUSED: usage ({decision.reason})"
    if i.result == "hooks-broken":
        return "## 🟠 HOOKS BROKEN: no worker was started"
    if i.running:
        agent = i.running.get("agent") or "worker"
        phase = f" on Phase {i.running['phase']}" if i.running.get("phase") else ""
        started = float(i.running.get("started") or i.now)
        return (f"## 🟢 WORKING: {agent}{phase} (running {_duration(i.now - started)}, "
                f"since {_clock(started)})")
    if _next_is_none(i.next_text):
        return "## ⚪ IDLE: nothing to do"
    return "## 🔵 READY FOR NEXT STEP: the next tick starts it"


def _usage_row(label: str, value, stop: int, i: Inputs) -> str:
    if i.usage is None or (i.result == "stopped" and not i.usage_fresh):
        return f"| {label} | `blind` |"
    note = ""
    if i.now - i.usage.read_at > USAGE_NOTE_AFTER:
        note = f" (as of {_clock(i.usage.read_at)})"
    return f"| {label} | `{bar(value)}` {value:g}% of the {stop}% stop line{note} |"


def build_body(i: Inputs) -> str:
    out = [top_line(i), f"Updated {_clock(i.now)}"]
    out += [f"> ⚠️ {w}" for w in i.warnings]
    out += ["", "| Progress | |", "|---|---|"]
    if i.facts is None:
        out.append(f"| Phases 7 to 10 | `{bar(100)}` 100% (all merged) |")
    else:
        progress = phase_progress(i.facts)
        out.append(f"| Phases 7 to 10 | `{bar(i.overall)}` {i.overall}% "
                   f"(Phase {i.facts.phase} of {PHASES[-1]}) |")
        out.append(f"| Phase {i.facts.phase} | {progress.line()} |")
    five = i.usage.five_hour if i.usage else 0
    weekly = i.usage.weekly if i.usage else 0
    out.append(_usage_row("Usage 5h", five, usage_guard.FIVE_HOUR_STOP, i))
    out.append(_usage_row("Usage weekly", weekly, usage_guard.WEEKLY_STOP, i))
    out += ["", "### Waiting for you"]
    out += [f"- {x.link()}" for x in i.needs_gian] or ["None."]
    out += ["", "### Needs the work laptop (does not block)"]
    out += [f"- {x.link()}" for x in i.needs_work] or ["None."]
    out += ["", "### Next step (from STATUS.md)", _cut(i.next_text, NEXT_CUT) or "none"]
    out += ["", f"### Latest commits on {i.branch or 'the current branch'}"]
    out += [f"- {_cut(c, LINE_CUT)}" for c in i.commits] or ["- none"]
    out += ["", "### Last log lines (STATUS.md)"]
    out += [f"- {_cut(x, LINE_CUT)}" for x in i.log_lines] or ["- none"]
    return "\n".join(out) + "\n"


def hash_text(body: str) -> str:
    """Hash of the body without the 'Updated' time and the 'running 1h 12m' counter, so a clock
    that only moved forward does not count as a change (S4)."""
    plain = re.sub(r"^Updated .*$", "", body, flags=re.MULTILINE)
    plain = re.sub(r"\(running [^,)]*,", "(running", plain)
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


# ---- gathering (reads only) ----

def read_status(path: Path) -> tuple[str, list[str]]:
    """(the 'Next:' text with its continuation lines, the last 5 Log lines)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", []
    next_text = ""
    for n, line in enumerate(lines):
        if line.lstrip("- ").startswith("Next:"):
            parts = [line.lstrip("- ")[5:].strip()]
            for more in lines[n + 1:]:
                if more.startswith("  ") and more.strip():
                    parts.append(more.strip())
                else:
                    break
            next_text = " ".join(parts)
            break
    log = []
    if "## Log" in lines:
        log = [x.lstrip("- ").strip() for x in lines[lines.index("## Log") + 1:] if x.strip()]
    return next_text, log[-5:]


def read_running(alive: Callable[[int], bool] | None, now: float) -> dict | None:
    """running.json when it is a live worker; damaged or dead means None."""
    try:
        data = json.loads((usage_guard.state_path().parent / "running.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    if pid is None:
        return data if now - float(data.get("started") or 0) < 60 else None
    return data if (alive is None or alive(pid)) else None


def read_usage(now: float) -> tuple[usage_guard.Usage | None, bool]:
    """(saved usage, was it fresh enough to have been used by the guard)."""
    saved = usage_guard.read_state()
    if saved is None:
        return None, False
    return saved, 0 <= now - saved.read_at <= usage_guard.MAX_AGE_SECONDS


def _issues(gh: Gh, label: str) -> list[Issue]:
    raw = gh(["issue", "list", "--label", label, "--state", "open",
              "--json", "number,title,url", "--limit", "50"]) or "[]"
    return [Issue(x.get("number"), str(x.get("title", "")), str(x.get("url", "")))
            for x in json.loads(raw) if isinstance(x, dict)]


def _warnings(git: Git) -> list[str]:
    """Unpushed commits left by a finished worker (fix 3, F3), counted again now."""
    try:
        found = stall.current_unpushed(git)
    except Exception:  # noqa: BLE001 - unknown means no warning; the tick logs git problems
        return []
    return [f"UNPUSHED: {stall.commits(found[1])} on {found[0]}"] if found else []


def gather(result: str, gh: Gh, alive=None, git: Git = run_git, now: float | None = None,
           status_file: Path | None = None, root: Path = ROOT) -> Inputs:
    now = time.time() if now is None else now
    next_text, log = read_status(status_file or root / "STATUS.md")
    usage, fresh = read_usage(now)
    merged, facts, overall = current_phase(git, root)
    branch = (_try(git, ["rev-parse", "--abbrev-ref", "HEAD"]) or "").strip()
    commits = []
    for line in (_try(git, ["log", "-5", "--format=%ct|%s"]) or "").splitlines():
        stamp, _, subject = line.partition("|")
        if stamp.isdigit():
            commits.append(f"{_clock(float(stamp))[:5]} {subject}")
    return Inputs(result, now, next_text, log, read_running(alive, now), usage, fresh,
                  _issues(gh, "needs-gian"), _issues(gh, "needs-work-test"), branch, commits,
                  facts, merged, overall, stall.read_stall() if result == "idle" else None,
                  _warnings(git))


# ---- writing the issue ----

def status_file_path() -> Path:
    return usage_guard.state_path().parent / "status_issue.json"


def _read_state() -> dict:
    try:
        data = json.loads(status_file_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(state: dict) -> None:
    path = status_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _find_by_title(gh: Gh) -> int | None:
    # By label, not `--search`: GitHub's search index lags behind new issues. The match ignores
    # the emoji, in case the console encoding garbled it on the way in.
    raw = gh(["issue", "list", "--label", LABEL, "--state", "open",
              "--json", "number,title", "--limit", "20"]) or "[]"
    for item in json.loads(raw):
        if isinstance(item, dict) and str(item.get("title", "")).endswith("Team status") \
                and isinstance(item.get("number"), int):
            return item["number"]
    return None


def _create(gh: Gh, body: str) -> int:
    try:
        gh(["label", "create", LABEL, "--color", "0E8A16",
            "--description", "Team status dashboard"])
    except Exception:  # noqa: BLE001 - the label usually exists already
        pass
    url = gh(["issue", "create", "--title", TITLE, "--body", body, "--label", LABEL]).strip()
    match = re.search(r"(\d+)\s*$", url)
    if not match:
        raise RuntimeError("gh issue create gave no issue number")
    return int(match.group(1))


def write_issue(body: str, gh: Gh, now: float) -> str:
    """Create or edit the one issue. Returns 'created', 'edited' or 'unchanged' (S3, S4)."""
    state = _read_state()
    digest = hash_text(body)
    number = state.get("number") if isinstance(state.get("number"), int) else None
    written = state.get("written_at") if isinstance(state.get("written_at"), int | float) else 0
    if number and state.get("hash") == digest and 0 <= now - written < HOUR:
        return "unchanged"
    action = "edited"
    if number:
        try:
            gh(["issue", "edit", str(number), "--body", body])
        except Exception:  # noqa: BLE001 - maybe deleted by hand: look it up again
            number = None
    if not number:
        number = _find_by_title(gh)
        if number:
            gh(["issue", "edit", str(number), "--body", body])
        else:
            number, action = _create(gh, body), "created"
            state["pinned"] = False
    if not state.get("pinned"):
        try:
            gh(["issue", "pin", str(number)])
            state["pinned"] = True
        except Exception:  # noqa: BLE001 - pinning is nice to have
            state["pinned"] = False
    state.update({"number": number, "hash": digest, "written_at": now})
    _save_state(state)
    return action


# ---- the entry point the tick uses ----

def log_path() -> Path:
    return Path(os.environ.get("DA_STATUS_BOARD_LOG", ROOT / "logs" / "status_board.log"))


def log_failure(problem: Exception, now: float) -> None:
    """One line, never the token or a long message."""
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{usage_guard.format_sgt(now)}: {type(problem).__name__}: "
                         f"{str(problem)[:200]}\n")
    except OSError:
        pass  # the board must never break the tick


def refresh(result: str, gh: Gh, alive=None, git: Git = run_git, now: float | None = None,
            status_file: Path | None = None) -> str:
    """Build the board and write it. Returns what happened; never raises."""
    now = time.time() if now is None else now
    try:
        inputs = gather(result, gh, alive, git, now, status_file)
        return write_issue(build_body(inputs), gh, now)
    except Exception as problem:  # noqa: BLE001 - AS-9: log it, keep going
        log_failure(problem, now)
        return "failed"
