"""PreToolUse hook (workers only): the "Never" list from the chief rule, as code.

Permission rules cannot look inside a path or a branch, so this checks the real command:
no push to `main`/`master` or the integration branch, no force or delete push, no hard reset or
branch delete, no `gh` write calls (merging goes through chief_tick's merge helper, which checks
the base branch), no touching `.env`, no deleting files outside `logs/` and `ops/state/`, and no
editing the guard itself (`ops/`, `.claude/`, `ops/state/usage.json`).

This is best-effort defence in depth, not a sandbox: a determined program can still find a way.
This repo is private on a free GitHub plan, so there is NO branch protection: this hook, the
deny list and the ZIP backup of `main` are the safety net.
"""

import glob
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DELETE_DIRS = (ROOT / "logs", ROOT / "ops" / "state")
PROTECTED_DIRS = (ROOT / "ops", ROOT / ".claude")
NOTE = ROOT / "ops" / "state" / "worker_note.md"
STATUS_FILE = ROOT / "STATUS.md"
STATUS_EDITORS = ("chief", "status-digest")
NO_PUSH_TO = {"main", "master", "auto/phases-7-10"}
DELETERS = {"rm", "rmdir", "del", "erase", "unlink", "shred", "truncate", "dd"}
WRITERS = {"sed", "tee", "mv", "cp", "install", "chmod", "ln", "perl", "patch"} | DELETERS
SHELLS = {"bash", "sh", "zsh", "dash", "eval", "exec", "xargs"}
GH_OK = {"issue": None, "pr": {"create", "view", "checks", "list", "diff", "status"}}
REMOTE_CHANGES = {"add", "set-url", "remove", "rm"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
ALLOWED_VARS = ("$DA_PYTHON", "${DA_PYTHON}", "$CLAUDE_PROJECT_DIR", "${CLAUDE_PROJECT_DIR}")
ENV_SEARCH = re.compile(r"(^|[/\\*\s])\.env")


def split_segments(command: str) -> list[str] | None:
    """Split a command at `&&`, `||`, `;`, `|`, `&` and newlines that sit OUTSIDE quotes (G6).

    Follows bash's own quote rules, so the hook and the shell agree on where a command ends:
    inside single quotes nothing is special; inside double quotes a backslash hides the next
    character; outside quotes a backslash and the next character are one unit (so an escaped quote
    opens nothing, and an escaped backslash leaves the quote after it free to open).
    A backslash before a newline outside quotes joins the lines (no split), as in bash.
    Returns None for an unclosed quote: fail closed, the caller refuses.
    A `#` that starts a word (a comment) or a `<<` (a heredoc) outside quotes returns None too: a
    stray quote inside one could hide the next line from us. A `;` `|` or `&` after a backslash, or
    inside quotes, does not split (bash agrees; the old regex split there, which is why unclosed
    quotes are refused).
    """
    segments, current, quote, i = [], [], "", 0
    while i < len(command):
        ch = command[i]
        if quote == "'":
            quote = "" if ch == "'" else quote
        elif quote == '"':
            if ch == "\\" and i + 1 < len(command):
                current.append(ch)
                i += 1
                ch = command[i]
            elif ch == '"':
                quote = ""
        elif ch == "\\" and command[i + 1:i + 2] == "\n":
            i += 2  # a line continuation: bash joins the two lines, so the hook must too
            continue
        elif ch == "\\" and i + 1 < len(command):
            # Outside quotes a backslash and the next character are ONE unit, as in bash:
            # `\\'` is a backslash and then a quote that OPENS; `\'` and `\;` are plain text.
            current.append(ch)
            i += 1
            ch = command[i]
        elif ch in "'\"":
            quote = ch
        elif (ch == "#" and (not current or current[-1] in " \t")) or command[i:i + 2] == "<<":
            # A comment or a heredoc can hold a stray quote that bash ignores but we would not
            # (it would hide the next line). Workers do not need either, so fail closed.
            return None
        elif ch in ";|&\n":
            segments.append("".join(current))
            current = []
            # `&&`, `||` and `|&` are ONE operator in bash, so they end one command, not two
            i += 2 if command[i:i + 2] in ("&&", "||", "|&") else 1
            continue
        current.append(ch)
        i += 1
    if quote:
        return None
    segments.append("".join(current))
    return segments


def _inside(path: Path, base: Path) -> bool:
    return path == base or base in path.parents


def _is_env_name(word: str) -> bool:
    for piece in re.split(r"[=<>]", word):
        name = Path(piece.replace("\\", "/")).name
        if name == ".env" or name.startswith(".env."):
            return True
    return False


def current_branch(cwd: Path) -> str:
    try:
        done = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd,
                              capture_output=True, text=True, timeout=10, check=False)
        return done.stdout.strip() or "main"  # cannot tell = assume the worst
    except (OSError, subprocess.SubprocessError):
        return "main"


def _resolve(word: str, cwd: Path) -> Path:
    return (cwd / word).resolve()


def _protected(path: Path) -> bool:
    if path == NOTE.resolve():
        return False
    return any(_inside(path, d.resolve()) for d in PROTECTED_DIRS)


def _git_sub(words: list[str]) -> tuple[str | None, list[str]]:
    """The git subcommand and its arguments, skipping options like -C and -c."""
    i = 1
    while i < len(words):
        w = words[i]
        if w in GIT_VALUE_OPTIONS:
            i += 2
        elif w.startswith("-"):
            i += 1
        else:
            return w, words[i + 1:]
    return None, []


def _push_problem(args: list[str], cwd: Path) -> str | None:
    positional = []
    for w in args:
        if w in ("--delete", "-d", "--mirror", "--all", "--prune") or "force" in w:
            return f"git push {w} is not allowed"
        if w.startswith("-") and not w.startswith("--") and "f" in w[1:]:
            return "force push is not allowed"
        if not w.startswith("-"):
            positional.append(w)
    refspecs = positional[1:]  # first positional is the remote
    if not refspecs:
        refspecs = ["HEAD"]
    for ref in refspecs:
        if ref.startswith("+"):
            return "force push is not allowed"
        if ref.startswith(":"):  # an empty source means "delete this remote branch"
            return "deleting a branch with push is not allowed"
        dst = ref.split(":", 1)[1] if ":" in ref else ref
        if not dst:
            return "deleting a branch with push is not allowed"
        dst = dst.removeprefix("refs/").removeprefix("heads/")  # refs/heads/x and heads/x
        if dst == "HEAD":
            dst = current_branch(cwd)
        if dst in NO_PUSH_TO:
            return f"pushing to {dst} is not allowed"
    return None


def _add_problem(args: list[str], cwd: Path) -> str | None:
    """Fix 6 (H4): STATUS.md is not in git, and `--force` could push an ignored file back in.

    Every word after `add` is checked, flags included, so `git add -- STATUS.md` is caught too.
    """
    for w in args:
        if w == "--force" or (w.startswith("-") and not w.startswith("--") and "f" in w[1:]):
            return "git add --force is not allowed"
        if not w.startswith("-") and _resolve(w, cwd) == STATUS_FILE.resolve():
            return "STATUS.md is not in git (Phase A fix 6)"
    return None


def _git_problem(words: list[str], cwd: Path) -> str | None:
    sub, args = _git_sub(words)
    if sub == "add":
        return _add_problem(args, cwd)
    if sub in ("rm", "clean"):
        return f"git {sub} deletes files, which is not allowed"
    if sub == "reset" and "--hard" in args:
        return "git reset --hard is not allowed"
    if sub in ("branch", "tag") and any(a in ("-D", "-d", "--delete") for a in args):
        return f"deleting a {sub} is not allowed"
    if sub == "push":
        return _push_problem(args, cwd)
    if sub == "remote" and args and args[0] in REMOTE_CHANGES:
        return f"git remote {args[0]} is not allowed (the remotes must not change)"
    if sub == "config" and any(a.lower().startswith(("remote.", "url.")) for a in args):
        return "changing git remote or url settings is not allowed"
    return None


def _gh_problem(words: list[str]) -> str | None:
    group = words[1] if len(words) > 1 else ""
    sub = words[2] if len(words) > 2 else ""
    if group in GH_OK and (GH_OK[group] is None or sub in GH_OK[group]):
        return None
    return "only gh issue and gh pr create/view/checks/list/diff/status are allowed for workers"


def _delete_problem(words: list[str], cwd: Path) -> str | None:
    targets = [w for w in words[1:] if not w.startswith("-")]
    for target in targets:
        if not any(_inside(_resolve(target, cwd), d.resolve()) for d in DELETE_DIRS):
            return f"deleting {target} is not allowed (only inside logs/ and ops/state/)"
    return None


def _segment_problem(words: list[str], cwd: Path) -> str | None:
    if not words:
        return None
    first = Path(words[0]).name
    if first in SHELLS and ("-c" in words or first in ("eval", "exec", "xargs")):
        return "running a command through a shell string is not allowed"
    if first == "git":
        return _git_problem(words, cwd)
    if first == "gh":
        return _gh_problem(words)
    if first in DELETERS:
        problem = _delete_problem(words, cwd)
        if problem or first not in ("dd", "truncate", "shred"):
            return problem
        return f"{first} is not allowed"
    if first == "mv":
        for w in [x for x in words[1:] if not x.startswith("-")]:
            if not _inside(_resolve(w, cwd), ROOT):
                return "moving files out of the repository is not allowed"
    if first == "find" and any(w in ("-delete", "-exec", "-execdir", "-ok") for w in words):
        return "find with -delete or -exec is not allowed"
    if first in WRITERS and any(_protected(_resolve(w, cwd)) for w in words[1:]
                                if not w.startswith("-")):
        return "editing the guard files (ops/, .claude/) is not allowed"
    return None


def _redirect_problem(words: list[str], cwd: Path) -> str | None:
    for i, w in enumerate(words):
        target = None
        if w in (">", ">>", ">|") and i + 1 < len(words):
            target = words[i + 1]
        elif w.startswith(">") and len(w) > 1:
            target = w.lstrip(">|")
        if target and _protected(_resolve(target, cwd)):
            return "editing the guard files (ops/, .claude/) is not allowed"
    return None


def _env_in_words(words: list[str], cwd: Path) -> bool:
    for w in words:
        if _is_env_name(w):
            return True
        if any(c in w for c in "*?[") and any(_is_env_name(m) for m in glob.glob(str(cwd / w))):
            return True
    return False


def command_problem(command: str, cwd: Path) -> str | None:
    cleaned = command
    for var in ALLOWED_VARS:
        cleaned = cleaned.replace(var, "")
    if "$" in cleaned or "`" in cleaned or "<(" in cleaned:
        return "variables and command substitution are not allowed in worker commands"
    if re.search(r"rmtree|os\.remove|os\.unlink|\.unlink\(|os\.system|subprocess|popen",
                 command):
        return "deleting or running programs from inline code is not allowed"
    segments = split_segments(command)
    if segments is None:
        return "this command could not be read safely"
    for segment in segments:
        try:
            words = shlex.split(segment.replace("\\", "/"))
        except ValueError:
            return "this command could not be read safely"
        if _env_in_words(words, cwd):
            return "the .env file is off limits"
        problem = _segment_problem(words, cwd) or _redirect_problem(words, cwd)
        if problem:
            return problem
    return None


def _file_problem(tool: str, given: dict, cwd: Path) -> str | None:
    path = given.get("file_path") or given.get("notebook_path") or ""
    if _is_env_name(path):
        return "the .env file is off limits"
    if tool == "Read" or not path:
        return None
    resolved = _resolve(path, cwd)
    if _protected(resolved):
        return "editing the guard files (ops/, .claude/) is not allowed"
    if resolved == STATUS_FILE.resolve() and os.environ.get("DA_AGENT") not in STATUS_EDITORS:
        return "only the chief edits STATUS.md"
    return None


def check(payload: dict) -> str | None:
    if os.environ.get("DA_WORKER") != "1":
        return None
    tool, given = payload.get("tool_name"), payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or ".")
    if tool == "Bash":
        return command_problem(given.get("command", ""), cwd)
    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        return _file_problem(tool, given, cwd)
    if tool in ("Grep", "Glob"):
        text = " ".join(str(given.get(k, "")) for k in ("path", "glob", "pattern"))
        if ENV_SEARCH.search(text):
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
