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
from datetime import UTC, datetime
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
    preflight: Callable[[], str | None] | None = None,
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


def worker_env(agent: str, base: dict | None = None, platform: str | None = None,
               exists=os.path.exists) -> dict:
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
    return env


def launch_worker(agent, prompt, stage, phase, reader, gh, launcher, status_file, now,
                  preflight=None) -> str:
    """Start ONE worker if the guard says GO and the hooks can start. Writes a ledger line."""
    if agent not in AGENT_MODELS:
        raise ValueError(f"unknown agent {agent!r}; choose one of {sorted(AGENT_MODELS)}")
    preflight = preflight or hooks_ready  # looked up now, not when the function was defined
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
    reply_file = save_worker_reply(agent, result, now)
    denied = denial_count(result)
    line = f"{as_of}: {agent}: {reply_first_line(result)}"
    if denied:
        line += f" [{denied} tool call{'s' if denied != 1 else ''} denied]"
    if reply_file:
        line += f" -> logs/workers/{reply_file.name}"
    status.add_log(status_file, line.replace("\n", " "))
    outcome = ("ok" if result.exit_code == 0 else
               f"launcher error: {result.crash}" if result.crash
               else f"exit code {result.exit_code}")
    if denied:
        outcome += f" ({denied} tool call{'s' if denied != 1 else ''} denied)"
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
    done = subprocess.run(worker_command(prompt, agent, AGENT_MODELS[agent]), capture_output=True,
                          text=True, env=worker_env(agent), cwd=ROOT, check=False)
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
    args = parser.parse_args(argv)
    try:
        if args.cmd == "tick":
            launcher = real_launcher if args.launch else None
            print(tick(usage_guard.endpoint_reader, gh, launcher))
        elif args.cmd == "issue":
            print(open_gian_issue(args.title, args.body, args.label, gh) or "already open")
        elif args.cmd == "launch":
            outcome = launch_worker(args.agent, args.prompt, args.stage, args.phase,
                                    usage_guard.endpoint_reader, gh, real_launcher, STATUS_FILE,
                                    time.time())
            print(outcome)
            if outcome == "ran":  # "ran" only means the worker process ended, not that it worked
                print("What the worker said: last line of the Log in STATUS.md, "
                      "full reply in logs/workers/")
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
