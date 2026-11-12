"""The chief's wake-up job (A4): plain Python, zero tokens when there is nothing to do.

AS400 comparison: the job schedule entry that runs every 30 minutes. It checks the data area
(usage guard) first, and only submits the worker job when the answer is GO and work exists.

Safe by default: `tick` only PRINTS what it would start unless you pass `--launch`.
Nothing in the tests starts a real `claude`, a real `gh` or touches GitHub.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from subprocess import DEVNULL

import answers
import ledger
import stall
import status
import status_board
import usage_guard

ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = ROOT / "STATUS.md"
TEMPLATE_FILE = ROOT / "ops" / "STATUS.template.md"  # fix 6: STATUS.md is not in git
FALLBACK_STATUS = "# STATUS\n\n## Where we are\n- Next: none\n\n## Log\n"
MERGE_BASE = "auto/phases-7-10"
LABELS = ("needs-gian", "needs-work-test", "gian-later")  # fix 7: gian-later never blocks
GUARD_BLIND_TITLE = "guard blind: usage cannot be read"
GREEN = {"SUCCESS", "NEUTRAL", "SKIPPED"}
HOOKS_BROKEN_TITLE = "hooks cannot start: no worker was launched"
AGENT_MODELS = {"chief": "sonnet", "spec-writer": "opus", "builder": "sonnet",
                "status-digest": "haiku", "plan-reviewer": "sonnet", "code-reviewer": "sonnet"}
# Phase A fix 5 (Gian, 10 Nov): from the weekly reset on Thu 12 Nov 19:00 SGT, the agents that
# judge (spec writing and the two reviews) run on Fable.
# Fix 5c (Gian, 12 Nov): the builder runs on Fable too, but only inside the Fable 5.2 launch offer
# (Pro plan: Fable included in the weekly limit 9 Nov to 16 Nov 23:59 PT = 17 Nov 15:59 SGT,
# up to 50% of the week). After the offer Fable on Pro is paid credits, so every agent goes back to
# AGENT_MODELS. FABLE_UNTIL stops new Fable launches 4 hours early, so a run started on Fable
# finishes inside the offer. FABLE_BAR_STOP: the Fable bar on Settings > Usage at or above this %
# also means "back to AGENT_MODELS" (Gian can press the Fable reset to refill it).
# AS400 comparison: a job description with a start date, an end date and a pool limit.
FABLE_MODEL = "fable"
FABLE_FROM = datetime(2026, 11, 12, 19, 0, tzinfo=usage_guard.SGT).timestamp()
FABLE_UNTIL = datetime(2026, 11, 17, 12, 0, tzinfo=usage_guard.SGT).timestamp()
FABLE_BAR_STOP = 90.0
# Fix 5d (12 Nov 22:45, project chat with Gian's authority): the first Fable run (Phase 11 spec)
# used 63% of a 5-hour window on its own. A Fable builder would get one run per window, so the
# builder goes back to sonnet; the judges stay on Fable. Add "builder" here to switch it back.
FABLE_AGENTS = ("spec-writer", "plan-reviewer", "code-reviewer")
# Turns a worker may use (F7). A whole-phase builder needs far more than a chief step.
AGENT_MAX_TURNS = {"chief": 60, "spec-writer": 80, "builder": 400, "status-digest": 20,
                   "plan-reviewer": 80, "code-reviewer": 80}
MAX_WORKER_HOURS = 6  # D-B: a worker running longer than this is stopped by the tick
LAUNCH_GRACE_SECONDS = 60  # running.json is written just before the pid is known
# Windows creation flags (F1): detached, own process group, no window. Plain numbers, because
# the subprocess module only has these names on Windows.
DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW = 0x8, 0x200, 0x08000000
WIN_FLAGS = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
GIT_BASH_DEFAULT = r"C:\Program Files\Git\bin\bash.exe"
HOOK_FILES = ("guard_hook.py", "quiet_hook.py", "safety_hook.py")

Gh = Callable[[list[str]], str]


class MergeRefused(Exception):
    """A merge was refused. The message says why, in plain words."""


@dataclass
class WorkerResult:
    exit_code: int
    stdout: str = ""
    crash: str = ""  # the error type when the launcher itself failed
    stderr: str = ""


Launcher = Callable[[str, str], WorkerResult]  # (prompt, agent)


def run_gh(args: list[str]) -> str:
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {done.stderr.strip()[:200]}")
    return done.stdout


# ---- questions for Gian (D-F) ----

def open_gian_issue(title: str, body: str, label: str, gh: Gh = run_gh) -> str | None:
    """One GitHub issue per question. No duplicate while one with the same title is open."""
    if label not in LABELS:
        raise ValueError(f"label must be one of {LABELS}")
    open_ones = json.loads(gh(["issue", "list", "--label", label, "--state", "open",
                               "--json", "title", "--limit", "100"]) or "[]")
    if any(item.get("title") == title for item in open_ones):
        return None
    return gh(["issue", "create", "--title", title, "--body", body, "--label", label]).strip()


# ---- merging (AC-5, code side) ----

def merge_pr(number: int, gh: Gh = run_gh) -> None:
    """Merge a PR only into `auto/phases-7-10` and only when every check is green."""
    info = json.loads(gh(["pr", "view", str(number), "--json", "baseRefName,statusCheckRollup"]))
    if info.get("baseRefName") != MERGE_BASE:
        raise MergeRefused(
            f"PR {number} targets {info.get('baseRefName')}, and the chief only merges into "
            f"{MERGE_BASE}")
    checks = info.get("statusCheckRollup") or []
    if not checks:
        raise MergeRefused(f"PR {number} has no checks, so green cannot be proven")
    bad = [c.get("name", "?") for c in checks
           if (c.get("conclusion") or c.get("state") or "").upper() not in GREEN]
    if bad:
        raise MergeRefused(f"PR {number} has checks that are not green: {', '.join(bad)}")
    gh(["pr", "merge", str(number), "--merge"])


# ---- the tick ----

def has_work(status_text: str) -> bool:
    """Work exists when STATUS.md has exactly one 'Next:' line and it is not 'none'."""
    next_lines = stall.next_lines(status_text)
    if len(next_lines) != 1:  # none, or more than one: the stall alarm (fix 3) reports it
        return False
    return not next_lines[0].lstrip("- ")[5:].strip().lower().startswith("none")


def worker_note_path() -> Path:
    return usage_guard.state_path().parent / "worker_note.md"


def hooks_ready(python: str | None = None) -> str | None:
    """Prove the three hooks can start with this interpreter, or return why not.

    A hook that cannot start is a NON-blocking error in Claude Code, so a worker would run with
    no guard. Each hook is run as a worker on garbage input, and must fail closed (exit 2).
    """
    python = python or sys.executable
    env = {**os.environ, "DA_WORKER": "1"}
    for name in HOOK_FILES:
        try:
            done = subprocess.run([python, str(ROOT / "ops" / name)], input="garbage",
                                  capture_output=True, text=True, env=env, timeout=30,
                                  check=False)
        except (OSError, subprocess.SubprocessError):
            return f"{name} could not be started with {python}"
        if done.returncode != 2:
            return f"{name} did not fail closed (exit code {done.returncode})"
    return None


def _refuse_stopped(decision, usage, status_file, gh, as_of) -> None:
    status.set_usage_line(status_file, usage.five_hour if usage else None,
                          usage.weekly if usage else None, as_of, stopped=True)
    status.set_line(status_file, "Stopped:", decision.reason)
    if usage is None:
        open_gian_issue(
            GUARD_BLIND_TITLE,
            "The chief could not read the plan usage, so nothing was started. "
            "Check that Claude Code is logged in on the laptop and that the usage endpoint "
            "still answers (docs/automation.md, A-P1).",
            "needs-gian", gh)


def _refuse_hooks(problem, status_file, gh, as_of) -> None:
    status.add_log(status_file, f"{as_of}: hooks cannot start ({problem}); no worker launched")
    open_gian_issue(HOOKS_BROKEN_TITLE,
                    f"Before starting a worker the chief checks that the safety hooks run. "
                    f"Problem: {problem}. Fix the interpreter (see docs/automation.md).",
                    "needs-gian", gh)


def tick(
    reader: usage_guard.Reader,
    gh: Gh = run_gh,
    launcher: Launcher | None = None,
    status_file: Path = STATUS_FILE,
    now: float | None = None,
    preflight: Callable[[], str | None] | None = None,
    alive: Callable[[int], bool] | None = None,
    killer: Callable[[int], None] | None = None,
    board: Callable[[str], object] | None = None,
    git: stall.Git | None = None,
) -> str:
    """One wake-up, then the Team status board (S2) whatever the result was. See `_tick`.

    `git=None` switches the stall alarm and the unpushed check off (fix 3); `main` passes real git.
    """
    ensure_status(status_file, time.time() if now is None else now)
    result = _tick(reader, gh, launcher, status_file, now, preflight, alive, killer, git)
    backup_status(status_file, time.time() if now is None else now)
    if git is not None and result != "idle":
        stall.clear_stall()  # a worker is running or work was found: not stalled any more
    run_board(board, result)
    return result


# ---- STATUS.md is machine-only (Phase A fix 6, H3) ----
# AS400 comparison: the data area now lives outside the source file, so the tick saves it after
# every wake (like a SAVOBJ) and restores it if it is gone. Plain file copies: git is never called.

def backup_path() -> Path:
    """`ops/state/STATUS.backup.md` (follows DA_STATE_DIR, so tests keep it in tmp_path)."""
    return usage_guard.state_path().parent / "STATUS.backup.md"


def ensure_status(status_file: Path, now: float) -> None:
    """A missing STATUS.md comes back from the backup, else from the template, with one Log line.

    An existing file is never touched. A failed copy is logged once and the tick goes on.
    """
    if status_file.exists():
        return
    backup = backup_path()
    source, note = ((backup, "STATUS.md restored from backup") if backup.exists()
                    else (TEMPLATE_FILE, "STATUS.md created from template"))
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as problem:  # template gone too: the smallest valid file, so the tick goes on
        status_board.log_failure(problem, now)
        text, note = FALLBACK_STATUS, "STATUS.md created from the built-in fallback"
    try:
        status_file.write_text(text, encoding="utf-8")
        status.add_log(status_file, f"{usage_guard.format_sgt(now)}: {note}")
    except OSError as problem:
        status_board.log_failure(problem, now)


def backup_status(status_file: Path, now: float) -> None:
    """Save STATUS.md whole-or-nothing (temp file, then replace). Never changes the tick result."""
    try:
        text = status_file.read_text(encoding="utf-8")
        if not stall.next_lines(text):
            return  # empty or broken file: keep the last good backup (code review, Should fix)
        backup = backup_path()
        backup.parent.mkdir(parents=True, exist_ok=True)
        temp = backup.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, backup)
    except OSError as problem:
        status_board.log_failure(problem, now)


def run_board(board: Callable[[str], object] | None, result: str) -> None:
    """Refresh the Team status issue. A failure here must never change what the tick returns."""
    if board is None:
        return
    try:
        board(result)
    except Exception:  # noqa: BLE001 - refresh logs its own failures; this is the safety net
        pass


def _tick(reader, gh, launcher, status_file, now, preflight, alive, killer, git=None) -> str:
    """One wake-up. Returns 'busy', 'stopped', 'idle', 'waiting', 'would-start', 'hooks-broken'
    or 'ran'.

    The job queue is looked at first (F4): a worker still running means 'busy' and nothing else
    happens (zero tokens). A finished, vanished or over-time worker is recorded, then the normal
    tick goes on, so the chief wakes up and acts on the result.
    """
    now = time.time() if now is None else now
    if check_queue(reader, status_file, now, alive, killer, git) == "busy":
        return "busy"
    heal_running_line(status_file, now)
    usage = usage_guard.get_usage(reader, now=now)
    decision = usage_guard.decide(usage)
    as_of = usage_guard.format_sgt(now)
    if not decision.go:
        _refuse_stopped(decision, usage, status_file, gh, as_of)
        return "stopped"
    status.set_usage_line(status_file, usage.five_hour, usage.weekly, as_of, stopped=False)
    status.set_line(status_file, "Stopped:", "no")
    watching = git is not None  # fix 3 and 4 watchers: off in old tests, on in `main`
    answer = new_answer(gh, now) if watching else None  # before has_work: it wakes `Next: none` too
    if answer:
        return _wake_for_answer(answer, reader, gh, launcher, status_file, now, preflight, as_of)
    text = status_file.read_text(encoding="utf-8")
    if watching and waiting_for_gian(text, gh, now):
        return "waiting"  # G3: zero tokens while Gian sleeps
    if not has_work(text):
        if watching:
            stall_alarm(status_file, gh, git, now, as_of)
        return "idle"
    if launcher is None:
        status.add_log(status_file, f"{as_of}: work found, not launched (no --launch)")
        return "would-start"
    return chief_run("Read STATUS.md and do the next step as the chief.", reader, gh, launcher,
                     status_file, now, preflight, watching)


# ---- Gian's answers, waiting, and the no-progress alarm (Phase A fix 4, G2, G3, G5) ----

NO_PROGRESS = "chief made no progress twice"
NO_PROGRESS_LIMIT = 2


def new_answer(gh: Gh, now: float):
    """G2: (issue, text, key) of a new comment by the repo owner, or None. A `gh` problem is
    logged once (board log) and means "no new answer" (AS-10)."""
    try:
        return answers.find_new_answer(gh)
    except Exception as problem:  # noqa: BLE001 - the tick must still return
        status_board.log_failure(problem, now)
        return None


def waiting_for_gian(text: str, gh: Gh, now: float) -> bool:
    """G3: Next says the team waits for Gian AND a real question (not our stall alarm) is open."""
    found = stall.next_lines(text)
    nxt = found[0].lower() if len(found) == 1 else ""
    if "wait" not in nxt:
        return False
    try:
        open_ones = answers.open_questions(gh)
    except Exception as problem:  # noqa: BLE001 - unknown means "not waiting"
        status_board.log_failure(problem, now)
        return False
    return bool(open_ones) and ("gian" in nxt or any(f"#{n}" in nxt for n, _title in open_ones))


def _wake_for_answer(answer, reader, gh, launcher, status_file, now, preflight, as_of) -> str:
    number, reply, key = answer
    if launcher is None:
        status.add_log(status_file, f"{as_of}: answer #{number} found, not launched (no --launch)")
        return "would-start"
    prompt = (f'Gian answered #{number}: "{reply}". Act on it, then close #{number} '
              "with a short comment.")
    result = chief_run(prompt, reader, gh, launcher, status_file, now, preflight, True)
    if result == "ran":  # only now is the answer "handled"; a refused start retries next tick
        status.add_log(status_file, f"{as_of}: ANSWER #{number} ({sgt_clock(now)}): "
                                    f"{' '.join(reply.split())[:300]}")
        answers.remember(number, key)
    return result


def _marks(status_file: Path, gh: Gh):
    """What G5 compares before and after a chief run: the Next line and the open issues
    (None for the issues when `gh` could not say)."""
    try:
        issues = answers.open_issue_numbers(gh)
    except Exception:  # noqa: BLE001 - unknown
        issues = None
    return stall.next_lines(status_file.read_text(encoding="utf-8")), issues


def chief_run(prompt, reader, gh, launcher, status_file, now, preflight, watching) -> str:
    """Run the chief in the foreground. With the watchers on, count runs that moved nothing (G5)."""
    before = _marks(status_file, gh) if watching else None
    result = launch_worker("chief", prompt, "chief", "", reader, gh, launcher, status_file, now,
                           preflight)
    if watching and result == "ran":
        after = _marks(status_file, gh)
        moved = (running_path().exists() or done_path().exists() or before[0] != after[0]
                 or before[1] is None or after[1] is None or before[1] != after[1])
        count_chief_run(moved, gh, status_file, now)
    return result


def count_chief_run(moved: bool, gh: Gh, status_file: Path, now: float) -> None:
    """G5: progress resets the count; otherwise add 1. At 2 in a row, one `Team stalled` issue."""
    try:
        if moved:
            answers.set_idle_runs(0)
            return
        count = answers.idle_runs() + 1
        answers.set_idle_runs(count)
        if count < NO_PROGRESS_LIMIT:
            return
        made = open_gian_issue(
            f"{stall.STALL_PREFIX}{NO_PROGRESS}",
            f"The chief was woken {count} times in a row and did nothing: it started no worker, "
            "did not change the `Next:` line and did not open or close an issue.\n\nRead the last "
            "chief replies in `logs/workers/`, fix the cause, then close this issue yourself.",
            "needs-gian", gh)
        if made:
            status.add_log(status_file,
                           f"{usage_guard.format_sgt(now)}: STALLED: {NO_PROGRESS} -> {made}")
    except Exception as problem:  # noqa: BLE001 - never stop the tick
        status_board.log_failure(problem, now)


def sgt_clock(epoch: float) -> str:
    """'10:21 SGT' from an epoch time."""
    return " ".join(usage_guard.format_sgt(epoch).split()[-2:])


def heal_running_line(status_file: Path, now: float) -> None:
    """G1: no running.json but a `Running:` line means the line is wrong. Delete it, say so once."""
    if running_path().exists():
        return
    if status.clear_running(status_file):
        status.add_log(status_file,
                       f"{usage_guard.format_sgt(now)}: Running line removed: no worker")


# ---- the stall alarm (Phase A fix 3, F1) ----

FINAL_PR = ["pr", "list", "--base", "main", "--head", MERGE_BASE, "--state", "open",
            "--json", "number", "--limit", "5"]
STALL_HELP = {
    stall.NO_NEXT: "STATUS.md must have exactly one `- Next:` line. Set it with "
                   "`chief_tick.py next \"...\"`.",
    stall.NOT_FINISHED: "STATUS.md says `Next: none`, no `needs-gian` issue is open and the "
                        "final PR (auto/phases-7-10 into main) is not open. Decide the next step.",
}


def _job_finished(gh: Gh) -> bool:
    """True when the team waits for Gian on purpose or the final PR is open (not a stall)."""
    asked = json.loads(gh(["issue", "list", "--label", "needs-gian", "--state", "open",
                           "--json", "title", "--limit", "100"]) or "[]")
    # Our own "Team stalled" issue is the alarm, not a question: it must not hide the stall.
    if any(not stall.is_stall_title(str(x.get("title", ""))) for x in asked):
        return True
    return bool(json.loads(gh(FINAL_PR) or "[]"))


def stall_alarm(status_file: Path, gh: Gh, git: stall.Git, now: float, as_of: str) -> None:
    """Called on an idle tick. A stall opens ONE `needs-gian` issue, one Log line and a note
    for the board. A failing `gh` or `git` is logged once and changes nothing else (AS-10)."""
    try:
        unpushed = stall.current_unpushed(git)
    except Exception as problem:  # noqa: BLE001 - "unknown" is not a stall
        status_board.log_failure(problem, now)
        unpushed = None
    try:
        text = status_file.read_text(encoding="utf-8")
        found = stall.reason(text, lambda: _job_finished(gh), unpushed)
        if found is None:
            stall.clear_stall()
            return
        stall.save_stall(found)
        help_text = STALL_HELP.get(found, "Push the branch (`git push`), then close this issue.")
        made = open_gian_issue(
            f"{stall.STALL_PREFIX}{found}",
            f"The team stopped and nobody was told. Reason: {found}.\n\n{help_text}\n\n"
            "The tick does not close this issue. Close it yourself once the cause is fixed.",
            "needs-gian", gh)
        if made:  # only the first time: no Log line every 30 minutes
            status.add_log(status_file, f"{as_of}: STALLED: {found} -> {made}")
    except Exception as problem:  # noqa: BLE001 - the tick must still return idle
        status_board.log_failure(problem, now)


def worker_log_dir() -> Path:
    return Path(os.environ.get("DA_WORKER_LOG_DIR", ROOT / "logs" / "workers"))


def _parse_reply(stdout: str):
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def denial_count(result: WorkerResult) -> int:
    data = _parse_reply(result.stdout) or {}
    denials = data.get("permission_denials")
    return len(denials) if isinstance(denials, list) else 0


def reply_first_line(result: WorkerResult) -> str:
    """The first line of the worker's answer, or why there is none (never empty)."""
    data = _parse_reply(result.stdout) or {}
    text = data.get("result")
    if isinstance(text, str) and text.strip():
        return text.strip().splitlines()[0][:160]
    detail = (result.stderr or result.stdout or "").strip().splitlines()
    return "(no reply text" + (f": {detail[0][:120]}" if detail else "") + ")"


def save_worker_reply(agent: str, result: WorkerResult, now: float) -> Path | None:
    """Keep the worker's whole reply (result text, permission denials, usage, errors) in
    `logs/workers/` so Gian can see why a worker stopped. Local only (`logs/` is ignored).
    A save problem returns None and never stops the run."""
    reply = _parse_reply(result.stdout)
    record = {"agent": agent, "exit_code": result.exit_code, "crash": result.crash,
              "reply": reply, "raw_stdout": None if reply is not None else result.stdout,
              "stderr": result.stderr}
    stamp = datetime.fromtimestamp(now, UTC).strftime("%Y%m%d-%H%M%S")
    try:
        folder = worker_log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        number, path = 1, folder / f"{stamp}-{agent}.json"
        while path.exists():  # two runs in the same second
            number += 1
            path = folder / f"{stamp}-{number}-{agent}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return path
    except OSError:
        return None


_UNREAD = object()


def fable_bar_percent(raw_path: Path | None = None) -> float | None:
    """The Fable bar (% of the Fable allowance used) from the last usage reading, or None.

    It is the `weekly_scoped` limit whose scope model is "Fable" in ops/state/usage_raw.json.
    Anything missing or damaged gives None (the date window still applies).
    """
    path = raw_path or usage_guard.state_path().parent / "usage_raw.json"
    try:
        limits = json.loads(path.read_text(encoding="utf-8")).get("limits") or []
        for item in limits:
            model = ((item.get("scope") or {}).get("model") or {})
            if item.get("kind") == "weekly_scoped" and model.get("display_name") == "Fable":
                return float(item["percent"])
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    return None


def model_for(agent: str, now: float | None = None, fable_bar=_UNREAD) -> str:
    """The model one worker runs on. AS400 comparison: a job description picked by date."""
    now = time.time() if now is None else now
    if agent in FABLE_AGENTS and FABLE_FROM <= now < FABLE_UNTIL:
        bar = fable_bar_percent() if fable_bar is _UNREAD else fable_bar
        if bar is None or bar < FABLE_BAR_STOP:
            return FABLE_MODEL
    return AGENT_MODELS[agent]


def worker_env(agent: str, base: dict | None = None, platform: str | None = None,
               exists=os.path.exists, now: float | None = None) -> dict:
    """The environment a worker runs in.

    DA_PYTHON is the interpreter the hooks use. DA_AGENT tells the safety hook who is writing.
    The venv folder goes first on PATH, so plain `pytest` and `ruff` resolve. On Windows the
    PowerShell tool is switched off (the allow list is written for Bash) and Claude Code is
    pointed at Git Bash when it sits in the default place (a value Gian set himself wins).
    """
    env = dict(os.environ if base is None else base)
    env.update({"DA_WORKER": "1", "DA_AGENT": agent, "DA_PYTHON": sys.executable})
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    if (platform or sys.platform) == "win32":
        env["CLAUDE_CODE_USE_POWERSHELL_TOOL"] = "0"
        if not env.get("CLAUDE_CODE_GIT_BASH_PATH") and exists(GIT_BASH_DEFAULT):
            env["CLAUDE_CODE_GIT_BASH_PATH"] = GIT_BASH_DEFAULT
    # Fix 5: the builder starts plan-reviewer and code-reviewer itself, as subagents. Their
    # `model: sonnet` line would win, so FORCE makes every subagent of the builder use Fable.
    if agent == "builder" and model_for("plan-reviewer", now) == FABLE_MODEL:
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = FABLE_MODEL
        env["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"] = "1"
    return env


def _check_guard_and_hooks(reader, gh, status_file, now, preflight):
    """(usage, None) when a worker may start, else (None, 'stopped' or 'hooks-broken')."""
    preflight = preflight or hooks_ready  # looked up now, not when the function was defined
    usage = usage_guard.get_usage(reader, now=now)
    decision = usage_guard.decide(usage)
    as_of = usage_guard.format_sgt(now)
    if not decision.go:
        _refuse_stopped(decision, usage, status_file, gh, as_of)
        return None, "stopped"
    problem = preflight()
    if problem:
        _refuse_hooks(problem, status_file, gh, as_of)
        return None, "hooks-broken"
    return usage, None


def launch_worker(agent, prompt, stage, phase, reader, gh, launcher, status_file, now,
                  preflight=None) -> str:
    """Run ONE worker in the foreground (the chief, from `tick`). Writes the Log and ledger line.

    Other workers go through `start_background`, which returns at once.
    """
    if agent not in AGENT_MODELS:
        raise ValueError(f"unknown agent {agent!r}; choose one of {sorted(AGENT_MODELS)}")
    usage, refusal = _check_guard_and_hooks(reader, gh, status_file, now, preflight)
    if refusal:
        return refusal
    note = worker_note_path()
    note.unlink(missing_ok=True)
    try:
        result = launcher(prompt, agent)
    except Exception as crash:  # noqa: BLE001 - the ledger line must still be written
        result = WorkerResult(-1, "", type(crash).__name__)
    reply_file = save_worker_reply(agent, result, now)
    record_result(agent, stage, phase, result, usage.five_hour, usage.weekly, _read_after(reader),
                  now, status_file, reply_file.name if reply_file else "")
    return "ran"


def _read_after(reader):
    try:
        return reader()
    except Exception:  # noqa: BLE001 - any failure reading usage after the run means "unknown"
        return None


def record_result(agent, stage, phase, result, five_before, weekly_before, after, now,
                  status_file, reply_name="") -> None:
    """The STATUS.md Log line and the ONE ledger line for a worker that ended with a result."""
    as_of = usage_guard.format_sgt(now)
    saved = _take_worker_note()
    denied = denial_count(result)
    line = f"{as_of}: {agent}: {reply_first_line(result)}"
    if denied:
        line += f" [{denied} tool call{'s' if denied != 1 else ''} denied]"
    if reply_name:
        line += f" -> logs/workers/{reply_name}"
    status.add_log(status_file, line.replace("\n", " "))
    outcome = ("ok" if result.exit_code == 0 else
               f"launcher error: {result.crash}" if result.crash
               else f"exit code {result.exit_code}")
    if denied:
        outcome += f" ({denied} tool call{'s' if denied != 1 else ''} denied)"
    if saved:
        outcome += " (worker saved a note)"
        status.add_log(status_file, f"{as_of}: worker note: " + saved.replace("\n", " ")[:200])
    _ledger(agent, stage, phase, five_before, weekly_before, after, outcome, now,
            ledger.tokens_from_result(result.stdout))


def _take_worker_note() -> str:
    note = worker_note_path()
    return note.read_text(encoding="utf-8").strip() if note.exists() else ""


def _ledger(agent, stage, phase, five_before, weekly_before, after, outcome, now, tokens) -> None:
    ledger.add_line({
        "phase": phase, "stage": stage,
        "model": model_for(agent, now) if agent in AGENT_MODELS else "",
        "five_hour_before": five_before, "weekly_before": weekly_before,
        "five_hour_after": after.five_hour if after else None,
        "weekly_after": after.weekly if after else None,
        **tokens, "outcome": outcome,
    }, now=now)


# ---- background workers (Phase A fix 1) ----
# AS400 comparison: `launch` is SBMJOB (submit and return), `running.json` is the job queue entry,
# `worker_done.json` is the job's end message, and the tick looks at the queue on each wake-up.

def running_path() -> Path:
    return usage_guard.state_path().parent / "running.json"


def done_path() -> Path:
    return usage_guard.state_path().parent / "worker_done.json"


def _read_note(path: Path) -> dict | None:
    """The note as a dict, or None when it is missing or damaged."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_note(path: Path, data: dict) -> None:
    """Write whole or not at all, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, path)


def pid_alive(pid: int, platform: str | None = None) -> bool:
    """Does this process id exist? (On Windows os.kill(pid, 0) would KILL it, so ask the API.)"""
    if (platform or sys.platform) == "win32":
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_tree(pid: int, platform: str | None = None, run=None, killpg=None) -> None:
    """Stop the runner and everything it started (claude and its tools)."""
    if (platform or sys.platform) == "win32":
        (run or subprocess.run)(["taskkill", "/PID", str(pid), "/T", "/F"],
                                capture_output=True, check=False)
        return
    try:  # the runner leads its own session (start_new_session), so its pid is the group id
        # SIGKILL does not exist on Windows; the tests still run this branch there with a fake.
        (killpg or os.killpg)(pid, getattr(signal, "SIGKILL", 9))
    except (ProcessLookupError, PermissionError):
        pass


def spawn_runner(agent: str, prompt: str, platform: str | None = None, popen=None) -> int:
    """Start `run-worker` as its own process that outlives this one. Returns its process id.

    All three standard streams go to nowhere, so the chief's Bash tool is not held open by a
    pipe the runner inherited.
    """
    command = [sys.executable, str(Path(__file__).resolve()), "run-worker", "--agent", agent,
               "--prompt", prompt]
    options = {"stdin": DEVNULL, "stdout": DEVNULL, "stderr": DEVNULL, "cwd": ROOT}
    if (platform or sys.platform) == "win32":
        options["creationflags"] = WIN_FLAGS
    else:
        options["start_new_session"] = True
    return (popen or subprocess.Popen)(command, **options).pid


def start_background(agent, prompt, stage, phase, reader, gh, status_file, now,
                     preflight=None, spawn=None) -> str:
    """F1: check the queue, the guard and the hooks, start the runner, return at once.

    Returns 'started <agent>', 'busy <agent>', 'stopped' or 'hooks-broken'.
    """
    if agent not in AGENT_MODELS:
        raise ValueError(f"unknown agent {agent!r}; choose one of {sorted(AGENT_MODELS)}")
    if running_path().exists():
        return f"busy {(_read_note(running_path()) or {}).get('agent', 'worker')}"
    usage, refusal = _check_guard_and_hooks(reader, gh, status_file, now, preflight)
    if refusal:
        return refusal
    worker_note_path().unlink(missing_ok=True)
    done_path().unlink(missing_ok=True)  # a leftover from an older run must not pass as ours
    note = {"agent": agent, "stage": stage, "phase": phase, "prompt": prompt[:200], "pid": None,
            "started": now, "five_hour_before": usage.five_hour, "weekly_before": usage.weekly}
    _write_note(running_path(), note)  # before the start, so a fast worker never beats the note
    try:
        note["pid"] = (spawn or spawn_runner)(agent, prompt)
    except OSError as problem:
        running_path().unlink(missing_ok=True)
        status.add_log(status_file, f"{usage_guard.format_sgt(now)}: {agent} could not be "
                                    f"started ({type(problem).__name__})")
        raise RuntimeError(f"{agent} could not be started: {problem}") from problem
    try:
        _write_note(running_path(), note)
    except OSError:  # without the pid the tick would call a live worker "vanished"
        stop_tree(note["pid"])
        running_path().unlink(missing_ok=True)
        raise
    status.set_running(status_file, agent, sgt_clock(note["started"]))  # G1: the tick owns it
    return f"started {agent}"


def run_worker(agent: str, prompt: str, launcher: Launcher | None = None) -> None:
    """F2: the runner. Run `claude -p` like the foreground launcher, then write the end message."""
    try:
        result = (launcher or real_launcher)(prompt, agent)
    except Exception as crash:  # noqa: BLE001 - the end message must still be written
        result = WorkerResult(-1, "", type(crash).__name__)
    finished = time.time()
    reply_file = save_worker_reply(agent, result, finished)
    _write_note(done_path(), {
        "agent": agent, "exit_code": result.exit_code, "crash": result.crash,
        "finished": finished, "reply_file": reply_file.name if reply_file else "",
        "stdout": result.stdout, "stderr": result.stderr})


def _forget_notes() -> None:
    running_path().unlink(missing_ok=True)
    done_path().unlink(missing_ok=True)


def _record_without_result(running: dict, text: str, outcome: str, reader, status_file, now):
    agent = running.get("agent") or "worker"
    status.add_log(status_file, f"{usage_guard.format_sgt(now)}: {agent} {text}")
    _ledger(agent, running.get("stage", ""), running.get("phase", ""),
            running.get("five_hour_before"), running.get("weekly_before"), _read_after(reader),
            outcome, now, {})


def check_queue(reader, status_file, now, alive=None, killer=None, git=None) -> str | None:
    """F4 to F6: look at the running worker. Returns 'busy' (touch nothing) or None.

    None means there is nothing to wait for any more: a finished, vanished or over-time worker
    was recorded (one Log line, one ledger line) and both notes are gone.
    """
    alive, killer = alive or pid_alive, killer or stop_tree
    if not running_path().exists() and not done_path().exists():
        return None
    # A damaged running.json reads as {} and falls through to "vanished" below.
    running, done = _read_note(running_path()) or {}, _read_note(done_path())
    if done is not None:
        _forget_notes()  # first, so a second call can never record the same worker twice
        status.clear_running(status_file)
        result = WorkerResult(done.get("exit_code", -1), done.get("stdout", ""),
                              done.get("crash", ""), done.get("stderr", ""))
        record_result(running.get("agent") or done.get("agent", "worker"),
                      running.get("stage", ""), running.get("phase", ""), result,
                      running.get("five_hour_before"), running.get("weekly_before"),
                      _read_after(reader), done.get("finished", now), status_file,
                      done.get("reply_file", ""))
        check_unpushed(running, git, status_file, now)
        return None
    age, pid = now - float(running.get("started") or 0), running.get("pid")
    limit = MAX_WORKER_HOURS * 3600
    if age <= limit and ((pid and alive(pid)) or (pid is None and age < LAUNCH_GRACE_SECONDS)):
        return "busy"
    status.clear_running(status_file)
    if age > limit and pid and alive(pid):
        killer(pid)
        _forget_notes()
        _record_without_result(running, "stopped: over the time limit",
                               "stopped: over the time limit", reader, status_file, now)
    else:
        _forget_notes()
        _record_without_result(running, "ended without a result (vanished)", "vanished",
                               reader, status_file, now)
    check_unpushed(running, git, status_file, now)
    return None


def check_unpushed(running: dict, git, status_file: Path, now: float) -> None:
    """F3: did the worker that just ended leave commits on `auto/phase-N` that origin lacks?

    Adds the Log line `UNPUSHED: <n> commits on <branch>` and remembers the branch for the board
    and the stall alarm. A git problem is logged once and means "unknown".
    """
    branch = stall.branch_for(running.get("phase"))
    if git is None or branch is None:
        return
    try:
        count = stall.unpushed_count(branch, git)
    except Exception as problem:  # noqa: BLE001 - never stop the tick
        status_board.log_failure(problem, now)
        return
    if count <= 0:
        stall.forget_unpushed()
        return
    stall.remember_unpushed(branch)
    status.add_log(status_file,
                   f"{usage_guard.format_sgt(now)}: UNPUSHED: {stall.commits(count)} on {branch}")


def stop_worker(reader, status_file, now, alive=None, killer=None) -> str:
    """For Gian: stop the running worker and record it like the time limit does (F6, AF-12)."""
    killer = killer or stop_tree
    running = _read_note(running_path())
    if running is None:
        return "nothing running"
    if _read_note(done_path()) is not None:
        return "already finished; the next tick records it"
    alive = alive or pid_alive
    pid = running.get("pid")
    _forget_notes()
    status.clear_running(status_file)
    if pid and alive(pid):  # a dead pid may now belong to a stranger: never kill it
        killer(pid)
        _record_without_result(running, "stopped: by hand", "stopped: by hand",
                               reader, status_file, now)
        return f"stopped {running.get('agent', 'worker')}"
    _record_without_result(running, "ended without a result (vanished)", "vanished",
                           reader, status_file, now)
    return "worker was already gone (recorded as vanished)"


def worker_command(prompt: str, agent: str = "chief", model: str = "sonnet") -> list[str]:
    """The `claude -p` command for one worker. Never --bare: that would skip our hooks."""
    return [
        "claude", "-p", prompt, "--agent", agent, "--model", model,
        "--output-format", "json", "--permission-mode", "dontAsk",
        "--settings", str(ROOT / "ops" / "worker_settings.json"),
        "--setting-sources", "project,local",
        "--strict-mcp-config", "--mcp-config", str(ROOT / ".claude" / "mcp-empty.json"),
        "--disable-slash-commands", "--max-turns", str(AGENT_MAX_TURNS.get(agent, 60)),
    ]


def real_launcher(prompt: str, agent: str = "chief", platform: str | None = None) -> WorkerResult:
    # S5: the runner has no console, so on Windows its `claude` child would open a black window
    # (which could be closed by mistake). CREATE_NO_WINDOW keeps it hidden.
    extra = {"creationflags": CREATE_NO_WINDOW} if (platform or sys.platform) == "win32" else {}
    done = subprocess.run(worker_command(prompt, agent, model_for(agent)), capture_output=True,
                          text=True, env=worker_env(agent), cwd=ROOT, check=False, **extra)
    return WorkerResult(done.returncode, done.stdout, stderr=done.stderr)


def main(argv: list[str] | None = None, gh: Gh | None = None) -> int:
    gh = gh or run_gh  # looked up now, so tests can pass a fake
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick", help="one wake-up")
    t.add_argument("--launch", action="store_true", help="really start the worker")
    i = sub.add_parser("issue", help="open a question for Gian")
    i.add_argument("--label", required=True, choices=LABELS)
    i.add_argument("--title", required=True)
    i.add_argument("--body", required=True)
    p = sub.add_parser("pause", help="mark a stage paused in STATUS.md")
    p.add_argument("--stage", required=True)
    p.add_argument("--issue", required=True)
    m = sub.add_parser("merge", help="merge a PR into the integration branch")
    m.add_argument("--pr", type=int, required=True)
    ln = sub.add_parser("launch", help="start ONE named worker (the chief uses this)")
    ln.add_argument("--agent", required=True, choices=sorted(AGENT_MODELS))
    ln.add_argument("--prompt", required=True)
    ln.add_argument("--stage", required=True)
    ln.add_argument("--phase", default="")
    rw = sub.add_parser("run-worker", help="the detached runner (started by `launch`, not by hand)")
    rw.add_argument("--agent", required=True, choices=sorted(AGENT_MODELS))
    rw.add_argument("--prompt", required=True)
    sub.add_parser("stop", help="stop the running worker (for Gian)")
    an = sub.add_parser("answer", help="print the newest comment by the repo owner on an issue")
    an.add_argument("number", type=int)
    nx = sub.add_parser("next", help="set the one 'Next:' line in STATUS.md")
    nx.add_argument("text")
    args = parser.parse_args(argv)

    def board(result: str) -> None:
        status_board.refresh(result, gh, alive=pid_alive)

    try:
        if args.cmd == "tick":
            launcher = real_launcher if args.launch else None
            # status_file is passed at call time (fix 6): the default is bound at import, so a
            # patched STATUS_FILE in tests would not reach it.
            print(tick(usage_guard.endpoint_reader, gh, launcher, status_file=STATUS_FILE,
                       board=board, git=status_board.run_git))
        elif args.cmd == "issue":
            print(open_gian_issue(args.title, args.body, args.label, gh) or "already open")
        elif args.cmd == "launch":
            result = start_background(args.agent, args.prompt, args.stage, args.phase,
                                      usage_guard.endpoint_reader, gh, STATUS_FILE, time.time())
            print(result)
            run_board(board, result)
        elif args.cmd == "run-worker":
            run_worker(args.agent, args.prompt)
        elif args.cmd == "stop":
            result = stop_worker(usage_guard.endpoint_reader, STATUS_FILE, time.time())
            print(result)
            run_board(board, result)
        elif args.cmd == "answer":
            found = answers.newest_owner_comment(gh, args.number, answers.owner(gh))
            print(found[1] if found else answers.NO_ANSWER)
        elif args.cmd == "next":
            status.set_next(STATUS_FILE, args.text)
            print(f"Next: {' '.join(args.text.split())}")
        elif args.cmd == "pause":
            status.mark_paused(STATUS_FILE, args.stage, args.issue)
        else:
            merge_pr(args.pr, gh)
            print(f"merged into {MERGE_BASE}")
    except (MergeRefused, RuntimeError, ValueError) as problem:
        print(f"Refused: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
