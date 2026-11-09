import io
import json
from pathlib import Path

import pytest
import safety_hook as s

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def worker(monkeypatch):
    monkeypatch.setenv("DA_WORKER", "1")


def bash(command, cwd=None):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd or ROOT)}


@pytest.mark.parametrize("command", [
    "git push origin main", "git push origin HEAD:main", "git push --force origin auto/phase-7",
    "git push -f", "git push origin +auto/phase-7", "git push --force-with-lease",
    "gh pr merge 7 --merge", "git rm -r src", "git clean -fd", "find . -name x -delete",
    "cat .env", "echo KEY=1 >> .env", "sed -i s/a/b/ .env.local",
    "rm src/agents/da_config.py", "rm -rf src", "rm logs/../src/x.py", "del src\\x.py",
    "git status && rm README.md", "python3 -c \"import shutil; shutil.rmtree('x')\"",
])
def test_dangerous_commands_are_blocked(command):
    assert s.check(bash(command)) is not None


@pytest.mark.parametrize("command", [
    "git push origin auto/phase-7", "git push -u origin phase-a", "git status",
    "python3 ops/quiet.py pytest", "gh issue create --title x", "rm logs/quiet/a.log",
    "rm ops/state/usage.json", "git add -A && git commit -m x", "ls .venv/bin", "git switch main",
])
def test_normal_work_is_allowed(command):
    assert s.check(bash(command)) is None


def test_delete_only_allowed_inside_logs_and_state_dirs(tmp_path):
    assert s.check(bash("rm ../src/x.py", cwd=ROOT / "logs")) is not None
    assert s.check(bash("rm a.log", cwd=ROOT / "logs")) is None


@pytest.mark.parametrize("tool", ["Read", "Edit", "Write"])
def test_env_file_is_off_limits_for_file_tools(tool):
    payload = {"tool_name": tool, "tool_input": {"file_path": str(ROOT / ".env")}}
    assert s.check(payload) is not None
    other = {"tool_name": tool, "tool_input": {"file_path": str(ROOT / "README.md")}}
    assert s.check(other) is None


def test_hook_does_nothing_outside_a_worker(monkeypatch):
    monkeypatch.delenv("DA_WORKER")
    assert s.check(bash("git push --force origin main")) is None
    assert s.main(io.StringIO("garbage")) == 0


def test_main_blocks_with_exit_2_and_a_plain_message(capsys):
    assert s.main(io.StringIO(json.dumps(bash("git push origin main")))) == 2
    assert "Blocked: pushing to main is not allowed." in capsys.readouterr().err
    assert s.main(io.StringIO("garbage")) == 2


def test_worker_settings_deny_list_has_the_required_rules():
    cfg = json.loads((ROOT / "ops" / "worker_settings.json").read_text(encoding="utf-8"))
    deny = " ".join(cfg["permissions"]["deny"])
    for needed in ("git push origin main", "git push --force", "git push -f", "gh pr merge",
                   "Edit(.env)", "Write(.env)", "rm -rf", "git rm", "git clean",
                   "claude plugin"):
        assert needed in deny
    assert not any(a.startswith("Bash(rm") for a in cfg["permissions"]["allow"])


def test_settings_json_registers_the_safety_hook():
    cfg = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    groups = [g for g in cfg["hooks"]["PreToolUse"] if "safety_hook" in json.dumps(g)]
    assert len(groups) == 1 and "Bash" in groups[0]["matcher"] and "Edit" in groups[0]["matcher"]


# ---- review round 1: bypass forms (written before the fix) ----

@pytest.mark.parametrize("command", [
    "git remote add evil https://example.invalid/x.git", "git remote set-url origin https://x.invalid",
    "git remote remove origin", "git remote rm origin", "git -C . remote add x y",
    "git -c a=b remote set-url origin z", "git config remote.origin.url https://x.invalid",
    "git config --add remote.origin.pushurl https://x.invalid",
    "git config url.https://x.invalid/.insteadOf https://github.com/",
    "git push origin HEAD:refs/heads/main", "git push origin HEAD:heads/main",
    "git push origin HEAD:refs/heads/auto/phases-7-10", "bash -c 'git push origin main'",
    "sh -c \"rm -rf src\"", "git -C . push origin main", "git -c x=y push origin main",
    "echo $(git push origin main)", "echo `git push origin main`",
    "git push --delete origin auto/phase-7", "git push origin :auto/phase-7",
    "git push origin auto/phases-7-10", "git push origin master", "git push -fu origin x",
    "git reset --hard", "git branch -D phase-6", "git branch --delete x", "git tag -d v1",
    "mv src /tmp/x", "find . -exec rm {} +", "find . -execdir rm {} +",
    "cat .e''nv", "cat $(echo .en)v", "E=.env; cat $E", "cat .e*", "cat ./.env.local",
    "gh api -X PUT repos/o/r/pulls/1/merge", "gh api repos/o/r -X DELETE",
    "gh repo delete o/r", "gh release delete v1", "shred -u README.md", "dd if=/dev/zero of=x",
    "sed -i s/a/b/ ops/safety_hook.py", "tee .claude/settings.json", "echo x > ops/usage_guard.py",
    "cp x ops/state/usage.json", "rm ops/state/../quiet.py",
])
def test_bypass_forms_are_blocked(command, monkeypatch):
    monkeypatch.setattr(s, "current_branch", lambda cwd: "phase-a")
    assert s.check(bash(command)) is not None


def test_bare_push_is_blocked_only_while_on_main(monkeypatch):
    monkeypatch.setattr(s, "current_branch", lambda cwd: "main")
    assert s.check(bash("git push")) is not None
    assert s.check(bash("git push -u origin HEAD")) is not None
    monkeypatch.setattr(s, "current_branch", lambda cwd: "phase-a")
    assert s.check(bash("git push")) is None
    assert s.check(bash("git push -u origin HEAD")) is None


@pytest.mark.parametrize("command", [
    "gh pr create --base auto/phases-7-10 --title x", "gh pr view 3", "gh pr checks 3",
    "gh issue list --label needs-gian", "git -C . status", "mv a.txt b.txt",
    "git push -u origin auto/phase-7", "git remote -v", "git remote show origin",
    "git config user.name x", "cat ops/usage_guard.py", "grep -n x ops/quiet.py",
    "\"$DA_PYTHON\" ops/chief_tick.py issue --label needs-gian --title x --body y",
    "git diff -- ops/quiet.py",
])
def test_normal_forms_still_allowed(command, monkeypatch):
    monkeypatch.setattr(s, "current_branch", lambda cwd: "phase-a")
    assert s.check(bash(command)) is None


@pytest.mark.parametrize("path", [
    "ops/usage_guard.py", "ops/guard_hook.py", ".claude/settings.json",
    "ops/worker_settings.json", "ops/state/usage.json", "ops/state/../quiet.py",
])
def test_workers_cannot_edit_their_own_guard_files(path):
    for tool in ("Edit", "Write"):
        payload = {"tool_name": tool, "tool_input": {"file_path": str(ROOT / path)}}
        assert s.check(payload) is not None


def test_note_and_normal_files_are_still_writable(monkeypatch):
    for ok in ("ops/state/worker_note.md", "src/x.py", "specs/phase-7.md", "tests/ops/t.py"):
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / ok)}}
        assert s.check(payload) is None


def test_status_md_only_for_the_chief_and_digest(monkeypatch):
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(ROOT / "STATUS.md")}}
    monkeypatch.setenv("DA_AGENT", "builder")
    assert s.check(payload) is not None
    monkeypatch.setenv("DA_AGENT", "chief")
    assert s.check(payload) is None


@pytest.mark.parametrize("fields", [{"path": ".env"}, {"glob": "**/.env"}, {"pattern": ".env*"},
                                    {"path": "/x/.env.local"}])
def test_grep_and_glob_cannot_reach_env(fields):
    for tool in ("Grep", "Glob"):
        assert s.check({"tool_name": tool, "tool_input": fields}) is not None
    assert s.check({"tool_name": "Grep", "tool_input": {"pattern": "def x", "path": "src"}}) is None


def test_settings_matcher_covers_grep_and_glob():
    cfg = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    group = next(g for g in cfg["hooks"]["PreToolUse"] if "safety_hook" in json.dumps(g))
    assert "Grep" in group["matcher"] and "Glob" in group["matcher"]


def test_worker_deny_list_has_the_git_remote_rules():
    cfg = json.loads((ROOT / "ops" / "worker_settings.json").read_text(encoding="utf-8"))
    deny = cfg["permissions"]["deny"]
    for rule in ("Bash(git remote add:*)", "Bash(git remote set-url:*)",
                 "Bash(git remote remove:*)", "Bash(git remote rm:*)"):
        assert rule in deny


def test_the_powershell_tool_is_denied_for_workers():
    cfg = json.loads((ROOT / "ops" / "worker_settings.json").read_text(encoding="utf-8"))
    assert "PowerShell" in cfg["permissions"]["deny"]
    assert "PowerShell" not in cfg["permissions"]["allow"]


def test_every_pytest_form_a_worker_may_use_on_windows_and_linux_is_allowed():
    cfg = json.loads((ROOT / "ops" / "worker_settings.json").read_text(encoding="utf-8"))
    allow = [a[len("Bash("):-len(":*)")] for a in cfg["permissions"]["allow"]
             if a.startswith("Bash(") and a.endswith(":*)")]
    for command in ("pytest -q", "ruff check .", ".venv/Scripts/python -m pytest -q",
                    ".venv\\Scripts\\python -m pytest", ".venv/bin/python -m pytest",
                    "python -m pytest -q", "python -m ruff check .",
                    "python ops/quiet.py pytest", '"$DA_PYTHON" ops/quiet.py pytest'):
        assert any(command.startswith(prefix) for prefix in allow), command


# ---- Phase A fix 4 (G6, AS-8): the splitter reads quotes the way bash does ----

@pytest.mark.parametrize("command", [
    "gh issue view 33 --json comments --jq '.comments|last|.body'",
    "gh issue view 33 --json comments --jq \".comments|last|.body\"",
    "gh issue view 33 --json comments --jq '.comments\\|last\\|.body'",
    "git commit -m \"fix a; b | c && d\"",
    "echo 'a; b'",
    "echo \"it's fine; really\"",
])
def test_as8_a_separator_inside_quotes_does_not_split(command):
    assert s.check(bash(command)) is None


@pytest.mark.parametrize("command", [
    "echo 'x' ; git push --force",
    "echo \"x\" && git push origin main",
    "echo 'x' | git push -f",
    "echo ok\ngit push --force",
    "echo 'a;b' ; rm src/da_config.py",
    "echo hi & git reset --hard",
])
def test_as8_a_separator_outside_quotes_still_splits(command):
    assert s.check(bash(command)) is not None


@pytest.mark.parametrize("command", [
    "echo 'unclosed", "echo \"unclosed", "git commit -m 'a; git push --force",
    "echo \\\"; rm src/x.py; echo \\\"",       # escaped quotes hide nothing: rm is still seen
    "echo \\'; git push --force; echo \\'",
])
def test_as8_an_unclosed_quote_or_an_escaped_quote_cannot_hide_a_command(command):
    assert s.check(bash(command)) is not None


def test_as8_an_escaped_semicolon_outside_quotes_still_splits_stricter_than_bash():
    backslash = chr(92)
    assert s.split_segments(f"echo a{backslash};git push --force") == [
        f"echo a{backslash}", "git push --force"]


def test_as8_split_segments_keeps_quoted_text_whole():
    assert s.split_segments("a 'b;c' ; d \"e|f\"") == ["a 'b;c' ", " d \"e|f\""]
    assert s.split_segments("echo 'x") is None


@pytest.mark.parametrize("command", [
    # Round 1 code review: an escaped backslash must leave the next quote free to OPEN.
    chr(92) * 2 + "' a '; git push --force; echo " + chr(92) + "'" + chr(92) + "'",
    "echo " + chr(92) * 2 + "' a '; git push --force; echo " + chr(92) + "'" + chr(92) + "'",
    "echo " + chr(92) * 2 + '" a "; git push --force; echo ' + chr(92) + '"' + chr(92) + '"',
    "echo " + chr(92) * 2 + "' a '; rm src/x.py; echo '",
    "echo a' ; git push --force ; echo 'b'",    # quote opened mid-word swallows nothing wrongly
])
def test_as8_escaped_backslashes_cannot_hide_a_command(command):
    assert s.check(bash(command)) is not None


def test_as8_escaped_backslash_then_quote_opens_a_quote_like_bash():
    b = chr(92)
    assert s.split_segments(f"echo {b}{b}'a;b'") == [f"echo {b}{b}'a;b'"]
    assert s.split_segments(f"echo {b}'a;b") == [f"echo {b}'a", "b"]


def test_as8_a_backslash_at_the_very_end_is_read_without_error():
    assert s.split_segments("echo ok " + chr(92)) == ["echo ok " + chr(92)]  # hides nothing


@pytest.mark.parametrize("command", [
    "git push " + chr(92) + "\n --force origin x",
    "git push origin " + chr(92) + "\nmain",
    "git push origin x " + chr(92) + "\n+main",
    "git push " + chr(92) + "\n--delete origin x",
    "git push origin ma" + chr(92) + "\nin",
])
def test_as8_a_line_continuation_cannot_hide_a_force_or_a_protected_branch(command):
    assert s.check(bash(command)) is not None


def test_as8_backslash_newline_joins_the_lines_but_a_plain_newline_still_splits():
    b = chr(92)
    assert s.split_segments(f"git push {b}\n --force") == ["git push  --force"]
    assert s.split_segments("echo a\necho b") == ["echo a", "echo b"]
    assert s.split_segments(f'echo "a{b}\nb"') == [f'echo "a{b}\nb"']


def test_as8_an_escaped_backslash_before_a_newline_is_still_a_real_split():
    b = chr(92)
    assert s.split_segments(f"git push origin x{b}{b}\n--force") == [
        f"git push origin x{b}{b}", "--force"]
