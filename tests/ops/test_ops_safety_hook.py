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
