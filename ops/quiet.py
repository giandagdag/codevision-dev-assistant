"""Quiet runner (A2): `python ops/quiet.py pytest|ruff|git status|diff|log ...`.

Prints a short summary plus failures only. The full output goes to `logs/quiet/<time>.log`.
Our own small version of RTK, standard library only, so it works on Windows and in the cloud.
AS400 comparison: like reading the job log summary instead of the whole spooled file.
The real exit code of the command is returned, so a failing test still fails the step.
"""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT_ALLOWED = ("status", "diff", "log")
LINE_CAPS = {"status": 40, "log": 40, "diff": 200, "ruff": 30}
FAILURE_CAP = 80  # lines of failure text shown for pytest


def project_python() -> str:
    for candidate in (ROOT / ".venv" / "bin" / "python", ROOT / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def build_command(args: list[str]) -> list[str] | None:
    """The real command for the allowed tools, or None when the tool is not allowed."""
    if not args:
        return None
    tool, rest = args[0], args[1:]
    if tool in ("pytest", "ruff"):
        return [project_python(), "-m", tool, *rest]
    if tool == "git" and rest and rest[0] in GIT_ALLOWED:
        return ["git", *rest]
    return None


def log_path() -> Path:
    folder = Path(os.environ.get("DA_LOG_DIR", ROOT / "logs" / "quiet"))
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    return folder / f"{stamp}.log"


def summarize(tool: str, output: str, code: int) -> str:
    lines = output.splitlines()
    if tool == "pytest":
        return _pytest_summary(lines)
    cap = LINE_CAPS.get(tool, 40)
    if len(lines) <= cap:
        return output.rstrip()
    return "\n".join(lines[:cap] + [f"... {len(lines) - cap} more lines (full output in the log)"])


def _pytest_summary(lines: list[str]) -> str:
    final = next((x for x in reversed(lines) if " passed" in x or " failed" in x
                  or " error" in x or "no tests ran" in x), "no summary line found")
    failures = []
    inside = False
    for line in lines:
        if line.startswith("=") and (" FAILURES " in line or " ERRORS " in line):
            inside = True
            continue
        if inside and line.startswith("=") and "short test summary" in line:
            inside = False
        if inside:
            failures.append(line)
    failed = [x for x in lines if x.startswith(("FAILED ", "ERROR "))]
    shown = failures[:FAILURE_CAP]
    parts = []
    if shown:
        parts += shown
        if len(failures) > FAILURE_CAP:
            parts.append(f"... {len(failures) - FAILURE_CAP} more failure lines (see the log)")
    parts += failed
    parts.append(final.strip("= ").strip())
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = build_command(args)
    if command is None:
        print("quiet.py only runs: pytest, ruff, git status, git diff, git log. "
              "Run anything else directly.", file=sys.stderr)
        return 2
    done = subprocess.run(command, capture_output=True, text=True, errors="replace")
    output = done.stdout + done.stderr
    path = log_path()
    path.write_text(f"$ {' '.join(command)}\n(exit code {done.returncode})\n\n{output}",
                    encoding="utf-8")
    print(summarize(args[0], output, done.returncode))
    print(f"[full output: {path}]")
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
