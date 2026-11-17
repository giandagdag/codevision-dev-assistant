"""Phase A fix 3, F5a and AS-9: read-only commands are allowed, the deny list is unchanged."""

import json
from pathlib import Path

SETTINGS = json.loads((Path(__file__).resolve().parents[2] / "ops" / "worker_settings.json")
                      .read_text(encoding="utf-8"))
ALLOW, DENY = SETTINGS["permissions"]["allow"], SETTINGS["permissions"]["deny"]

NEW_ALLOWED = [
    "Bash(grep:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(git show:*)",
    "Bash(git rev-parse:*)", "Bash(git rev-list:*)", "Bash(git branch --list:*)",
    "Bash(git branch --show-current:*)", "Bash(git branch -a:*)", "Bash(git ls-remote:*)",
    "Bash(python src/da_smoke_check.py:*)",
    "Bash(.venv/Scripts/python src/da_smoke_check.py:*)",
    'Bash("$DA_PYTHON" src/da_smoke_check.py:*)',
]
# The deny list as it was before fix 3 (copied here on purpose: it must not change).
DENY_BEFORE = [
    "Bash(git push --force:*)", "Bash(git push -f:*)", "Bash(git push --force-with-lease:*)",
    "Bash(git push origin main:*)", "Bash(git push origin HEAD:main:*)", "Bash(gh pr merge:*)",
    "Bash(rm -r:*)", "Bash(rm -rf:*)", "Bash(rmdir:*)", "Bash(del:*)", "Bash(git rm:*)",
    "Bash(git clean:*)", "Read(.env)", "Edit(.env)", "Write(.env)", "Read(**/.env)",
    "Edit(**/.env)", "Write(**/.env)", "Bash(claude plugin:*)", "Bash(claude mcp add:*)",
    "Bash(git remote add:*)", "Bash(git remote set-url:*)", "Bash(git remote remove:*)",
    "Bash(git remote rm:*)", "PowerShell",
    "Bash(.venv/bin/python ops/chief_tick.py run-worker:*)",
    "Bash(.venv\\Scripts\\python ops/chief_tick.py run-worker:*)",
    "Bash(.venv/Scripts/python ops/chief_tick.py run-worker:*)",
    'Bash("$DA_PYTHON" ops/chief_tick.py run-worker:*)',
    "Bash(python ops/chief_tick.py run-worker:*)",
    "Bash(.venv/bin/python ops/chief_tick.py stop:*)",
    "Bash(.venv\\Scripts\\python ops/chief_tick.py stop:*)",
    "Bash(.venv/Scripts/python ops/chief_tick.py stop:*)",
    'Bash("$DA_PYTHON" ops/chief_tick.py stop:*)', "Bash(python ops/chief_tick.py stop:*)",
]


def matches(pattern: str, command: str) -> bool:
    """A tiny copy of the `Bash(prefix:*)` rule: the command starts with the prefix."""
    if not (pattern.startswith("Bash(") and pattern.endswith(":*)")):
        return False
    prefix = pattern[len("Bash("):-len(":*)")]
    return command == prefix or command.startswith(prefix + " ")


def allowed(command: str) -> bool:
    return (any(matches(p, command) for p in ALLOW)
            and not any(matches(p, command) for p in DENY))


def test_as9_the_read_only_commands_are_in_the_allow_list():
    for entry in NEW_ALLOWED:
        assert entry in ALLOW


def test_as9_grep_is_allowed_and_a_force_push_is_still_denied():
    assert allowed("grep -n x file")
    assert allowed("git rev-list --count origin/auto/phase-8..auto/phase-8")
    assert allowed("git show auto/phase-8:STATUS.md")
    assert allowed("python src/da_smoke_check.py")
    assert not allowed("git push --force origin auto/phase-8")
    assert not allowed("git push -f")
    assert not allowed("git rm file")
    assert not allowed("gh pr merge 5")
    assert not allowed("rm -rf logs")


def test_git_branch_can_only_list_never_move_rename_or_delete():
    assert allowed("git branch --list")
    assert allowed("git branch --show-current")
    assert allowed("git branch -a")
    for command in ("git branch -f auto/phases-7-10 abc123", "git branch -m old new",
                    "git branch -D auto/phase-8", "git branch -d x", "git branch new-name",
                    "git branch"):
        assert not allowed(command), command
    assert "Bash(git branch:*)" not in ALLOW


def test_the_deny_list_did_not_change():
    assert DENY == DENY_BEFORE


def test_nothing_new_in_the_allow_list_writes_deletes_or_merges():
    for entry in NEW_ALLOWED:
        for word in ("push", "merge", "rm", "delete", "clean", "commit"):
            assert word not in entry.split("(", 1)[1].split()


def test_so1_the_builder_can_catch_up_with_its_own_branch():
    """16 Nov (#79): SO-1 says the builder merges, but merge and pull were not allowed."""
    assert allowed("git merge --ff-only origin/phase-11-fix-1")
    assert allowed("git merge origin/auto/phases-7-10")
    assert allowed("git pull --ff-only origin phase-11-fix-1")
    # A plain pull (it could make a merge commit by surprise) and every force push stay out.
    assert not allowed("git pull origin phase-11-fix-1")
    assert not allowed("git push --force origin phase-11-fix-1")
