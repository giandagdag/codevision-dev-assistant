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
    "git push origin HEAD:refs/heads/main", "bash -c 'git push origin main'",
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
    "git push -u origin auto/phase-7", "cat ops/usage_guard.py", "grep -n x ops/quiet.py",
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
