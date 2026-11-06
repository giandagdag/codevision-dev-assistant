"""The chief's wake-up job (A4): plain Python, zero tokens when there is nothing to do.

AS400 comparison: the job schedule entry that runs every 30 minutes. It checks the data area
(usage guard) first, and only submits the worker job when the answer is GO and work exists.

Safe by default: `tick` only PRINTS what it would start unless you pass `--launch`.
Nothing in the tests starts a real `claude`, a real `gh` or touches GitHub.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import ledger
import status
import usage_guard

ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = ROOT / "STATUS.md"
MERGE_BASE = "auto/phases-7-10"
LABELS = ("needs-gian", "needs-work-test")
GUARD_BLIND_TITLE = "guard blind: usage cannot be read"
GREEN = {"SUCCESS", "NEUTRAL", "SKIPPED"}
HOOKS_BROKEN_TITLE = "hooks cannot start: no worker was launched"
AGENT_MODELS = {"chief": "sonnet", "spec-writer": "opus", "builder": "sonnet",
                "status-digest": "haiku", "plan-reviewer": "sonnet", "code-reviewer": "sonnet"}
HOOK_FILES = ("guard_hook.py", "quiet_hook.py", "safety_hook.py")

Gh = Callable[[list[str]], str]


class MergeRefused(Exception):
    """A merge was refused. The message says why, in plain words."""


@dataclass
class WorkerResult:
    exit_code: int
    stdout: str = ""
    crash: str = ""  # the error type when the launcher itself failed


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
    """Work exists when STATUS.md has a 'Next:' line that is not 'none' and nothing is paused."""
    next_lines = [x for x in status_text.splitlines() if x.lstrip("- ").startswith("Next:")]
    if not next_lines:
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
    preflight: Callable[[], str | None] = hooks_ready,
) -> str:
    """One wake-up. Returns 'stopped', 'idle', 'would-start', 'hooks-broken' or 'ran'."""
    now = time.time() if now is None else now
    usage = usage_guard.get_usage(reader, now=now)
    decision = usage_guard.decide(usage)
    as_of = usage_guard.format_sgt(now)
    if not decision.go:
        _refuse_stopped(decision, usage, status_file, gh, as_of)
        return "stopped"
    status.set_usage_line(status_file, usage.five_hour, usage.weekly, as_of, stopped=False)
    status.set_line(status_file, "Stopped:", "no")
    if not has_work(status_file.read_text(encoding="utf-8")):
        return "idle"
    if launcher is None:
        status.add_log(status_file, f"{as_of}: work found, not launched (no --launch)")
        return "would-start"
    return launch_worker("chief", "Read STATUS.md and do the next step as the chief.", "chief",
                         "", reader, gh, launcher, status_file, now, preflight)


def launch_worker(agent, prompt, stage, phase, reader, gh, launcher, status_file, now,
                  preflight=hooks_ready) -> str:
    """Start ONE worker if the guard says GO and the hooks can start. Writes a ledger line."""
    if agent not in AGENT_MODELS:
        raise ValueError(f"unknown agent {agent!r}; choose one of {sorted(AGENT_MODELS)}")
    usage = usage_guard.get_usage(reader, now=now)
    decision = usage_guard.decide(usage)
    as_of = usage_guard.format_sgt(now)
    if not decision.go:
        _refuse_stopped(decision, usage, status_file, gh, as_of)
        return "stopped"
    problem = preflight()
    if problem:
        _refuse_hooks(problem, status_file, gh, as_of)
        return "hooks-broken"
    note = worker_note_path()
    note.unlink(missing_ok=True)
    try:
        result = launcher(prompt, agent)
    except Exception as crash:  # noqa: BLE001 - the ledger line must still be written
        result = WorkerResult(-1, "", type(crash).__name__)
    try:
        after = reader()
    except Exception:  # noqa: BLE001 - any failure reading usage after the run means "unknown"
        after = None
    saved = note.read_text(encoding="utf-8").strip() if note.exists() else ""
    outcome = ("ok" if result.exit_code == 0 else
               f"launcher error: {result.crash}" if result.crash
               else f"exit code {result.exit_code}")
    if saved:
        outcome += " (worker saved a note)"
        status.add_log(status_file, f"{as_of}: worker note: " + saved.replace("\n", " ")[:200])
    ledger.add_line({
        "phase": phase, "stage": stage, "model": AGENT_MODELS[agent],
        "five_hour_before": usage.five_hour, "weekly_before": usage.weekly,
        "five_hour_after": after.five_hour if after else None,
        "weekly_after": after.weekly if after else None,
        **ledger.tokens_from_result(result.stdout), "outcome": outcome,
    }, now=now)
    return "ran"


def worker_command(prompt: str, agent: str = "chief", model: str = "sonnet") -> list[str]:
    """The `claude -p` command for one worker. Never --bare: that would skip our hooks."""
    return [
        "claude", "-p", prompt, "--agent", agent, "--model", model,
        "--output-format", "json", "--permission-mode", "dontAsk",
        "--settings", str(ROOT / "ops" / "worker_settings.json"),
        "--setting-sources", "project,local",
        "--strict-mcp-config", "--mcp-config", str(ROOT / ".claude" / "mcp-empty.json"),
        "--disable-slash-commands", "--max-turns", "60",
    ]


def real_launcher(prompt: str, agent: str = "chief") -> WorkerResult:
    # DA_PYTHON is the interpreter the hooks run with (settings.json uses it). DA_AGENT lets the
    # safety hook know who is writing (only the chief edits STATUS.md).
    env = {**os.environ, "DA_WORKER": "1", "DA_AGENT": agent, "DA_PYTHON": sys.executable}
    done = subprocess.run(worker_command(prompt, agent, AGENT_MODELS[agent]), capture_output=True,
                          text=True, env=env, cwd=ROOT, check=False)
    return WorkerResult(done.returncode, done.stdout)


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
    args = parser.parse_args(argv)
    try:
        if args.cmd == "tick":
            launcher = real_launcher if args.launch else None
            print(tick(usage_guard.endpoint_reader, gh, launcher))
        elif args.cmd == "issue":
            print(open_gian_issue(args.title, args.body, args.label, gh) or "already open")
        elif args.cmd == "launch":
            print(launch_worker(args.agent, args.prompt, args.stage, args.phase,
                                usage_guard.endpoint_reader, gh, real_launcher, STATUS_FILE,
                                time.time()))
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
