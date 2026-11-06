"""PreToolUse hook (workers only): the "Never" list from the chief rule, as code.

Permission rules cannot look inside a path, so this checks the real command: no push to
`main`, no force push, no `gh pr merge` (merging goes through chief_tick's merge helper, which
checks the base branch), no touching `.env`, and no deleting files outside `logs/` and
`ops/state/`. GitHub branch protection (O2) is still the real wall for `main`.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DELETE_DIRS = (ROOT / "logs", ROOT / "ops" / "state")
DELETERS = {"rm", "rmdir", "del", "erase", "unlink"}
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")


def _inside(path: Path, base: Path) -> bool:
    return path == base or base in path.parents


def _is_env_name(word: str) -> bool:
    name = Path(word.replace("\\", "/")).name
    return name == ".env" or name.startswith(".env.")


def _delete_problem(words: list[str], cwd: Path) -> str | None:
    targets = [w for w in words[1:] if not w.startswith("-")]
    if not targets:
        return None
    for target in targets:
        resolved = (cwd / target).resolve()
        if not any(_inside(resolved, d.resolve()) for d in DELETE_DIRS):
            return f"deleting {target} is not allowed (only inside logs/ and ops/state/)"
    return None


def _segment_problem(words: list[str], cwd: Path) -> str | None:
    if not words:
        return None
    first = Path(words[0]).name
    if first == "git" and len(words) > 1:
        sub = words[1]
        if sub in ("rm", "clean"):
            return f"git {sub} deletes files, which is not allowed"
        if sub == "push":
            for w in words[2:]:
                if w in ("-f", "--force") or w.startswith(("--force", "+")):
                    return "force push is not allowed"
                if w == "main" or w.endswith(":main") or w == "refs/heads/main":
                    return "pushing to main is not allowed"
    if first == "gh" and words[1:3] == ["pr", "merge"]:
        return "workers do not merge; the chief's merge helper does (base branch checked)"
    if first in DELETERS:
        return _delete_problem(words, cwd)
    if first == "find" and "-delete" in words:
        return "find -delete is not allowed"
    return None


def command_problem(command: str, cwd: Path) -> str | None:
    if any(_is_env_name(w) for w in re.split(r"[\s'\"=<>]+", command)):
        return "the .env file is off limits"
    for segment in SEGMENT_SPLIT.split(command):
        try:
            words = shlex.split(segment.replace("\\", "/"))
        except ValueError:
            return "this command could not be read safely"
        problem = _segment_problem(words, cwd)
        if problem:
            return problem
    if re.search(r"rmtree|os\.remove|os\.unlink|\.unlink\(", command):
        return "deleting files from code is not allowed"
    return None


def check(payload: dict) -> str | None:
    if os.environ.get("DA_WORKER") != "1":
        return None
    tool, given = payload.get("tool_name"), payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or ".")
    if tool == "Bash":
        return command_problem(given.get("command", ""), cwd)
    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        path = given.get("file_path") or given.get("notebook_path") or ""
        if _is_env_name(path):
            return "the .env file is off limits"
    return None


def main(stdin=None) -> int:
    try:
        message = check(json.load(stdin or sys.stdin))
    except Exception:  # noqa: BLE001 - fail closed inside a worker
        if os.environ.get("DA_WORKER") != "1":
            return 0
        message = "the safety hook could not read this call"
    if message:
        print(f"Blocked: {message}.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
