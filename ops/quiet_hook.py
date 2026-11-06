"""PreToolUse hook on Bash: send pytest, ruff and git status|diff|log through ops/quiet.py.

Only in workers (DA_WORKER=1), only for one plain command (no pipes, `&&`, redirects).
The usage guard is checked FIRST, so when the guard blocks, the guard wins and nothing is
rewritten (X19). The rewrite replaces the whole tool input, keeping its other fields.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

import guard_hook

QUIET = Path(__file__).resolve().with_name("quiet.py")
PLAIN = re.compile(r"^[\w\s./\\:=,@+\-\"']+$")  # no | & ; > < ` $ ( )
PYTHON_LIKE = re.compile(r"(^|[/\\])python[\d.]*(\.exe)?$")


def rewrite(command: str) -> str | None:
    """The quiet command for a plain pytest/ruff/git status|diff|log command, else None."""
    text = command.strip()
    if not text or not PLAIN.match(text):
        return None
    try:
        words = shlex.split(text.replace("\\", "/"))  # Windows paths: keep the backslashes
    except ValueError:
        return None
    if len(words) >= 3 and PYTHON_LIKE.search(words[0]) and words[1] == "-m":
        words = words[2:]  # `python -m pytest ...` is the same as `pytest ...`
    if not words:
        return None
    if words[0] in ("pytest", "ruff") or (
        words[0] == "git" and len(words) > 1 and words[1] in ("status", "diff", "log")
    ):
        return f'python3 "{QUIET}" ' + " ".join(shlex.quote(w) for w in words)
    return None


def main(stdin=None) -> int:
    if os.environ.get("DA_WORKER") != "1":
        return 0
    try:
        payload = json.load(stdin or sys.stdin)
        blocked = guard_hook.check(payload)
    except Exception:  # noqa: BLE001 - fail closed inside a worker
        print("Guard hook failed, so nothing runs. Write ops/state/worker_note.md and stop.",
              file=sys.stderr)
        return 2
    if blocked:
        print(blocked, file=sys.stderr)
        return 2
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = dict(payload.get("tool_input") or {})
    new = rewrite(tool_input.get("command", ""))
    if new is None:
        return 0
    tool_input["command"] = new
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": tool_input,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
