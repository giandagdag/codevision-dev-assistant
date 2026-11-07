import io
import json
import time
from pathlib import Path

import pytest
import quiet
import quiet_hook
import usage_guard as g

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_LOG_DIR", str(tmp_path / "logs"))
    return tmp_path / "logs"


def project(tmp_path, body):
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "test_sample.py").write_text(body, encoding="utf-8")
    return folder


# ---- AC-6: summary plus the one failure, full log on disk ----

def test_pytest_with_one_failure_shows_summary_and_that_failure_only(
    tmp_path, logs, monkeypatch, capsys
):
    monkeypatch.chdir(project(tmp_path, (
        "def test_ok_1(): assert True\n"
        "def test_ok_2(): assert True\n"
        "def test_broken():\n    value = 2\n    assert value == 3\n"
    )))
    code = quiet.main(["pytest", "-p", "no:cacheprovider"])
    out = capsys.readouterr().out
    assert code == 1  # the real exit code is kept
    assert "test_broken" in out and "assert 2 == 3" in out
    assert "test_ok_1" not in out and "test_ok_2" not in out
    assert "1 failed, 2 passed" in out
    log = next(logs.glob("*.log"))
    assert "(exit code 1)" in log.read_text(encoding="utf-8")
    assert f"[full output: {log}]" in out


def test_pytest_all_green_is_one_summary_line_plus_the_log_pointer(
    tmp_path, logs, monkeypatch, capsys
):
    monkeypatch.chdir(project(tmp_path, "def test_a(): assert True\n"))
    assert quiet.main(["pytest", "-p", "no:cacheprovider"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2 and "1 passed" in lines[0]
    assert len(list(logs.glob("*.log"))) == 1


def test_ruff_clean_and_with_findings(tmp_path, logs, monkeypatch, capsys):
    folder = project(tmp_path, "import os\n")  # unused import
    monkeypatch.chdir(folder)
    code = quiet.main(["ruff", "check", "--no-cache", "--isolated", "test_sample.py"])
    assert code == 1 and "F401" in capsys.readouterr().out
    (folder / "test_sample.py").write_text("x = 1\n", encoding="utf-8")
    code = quiet.main(["ruff", "check", "--no-cache", "--isolated", "test_sample.py"])
    assert code == 0 and "All checks passed" in capsys.readouterr().out


def test_git_status_is_run_and_long_output_is_cut_with_a_pointer(logs, monkeypatch, capsys):
    text = quiet.summarize("log", "\n".join(f"line {i}" for i in range(100)), 0)
    assert text.splitlines()[-1].startswith("... 60 more lines")
    monkeypatch.chdir(ROOT)
    assert quiet.main(["git", "status", "--short"]) == 0
    assert "[full output:" in capsys.readouterr().out


@pytest.mark.parametrize("args", [
    ["git", "commit", "-m", "x"], ["git", "push"], ["rm", "-rf", "x"], ["git"], [],
])
def test_other_commands_are_refused(args, logs, capsys):
    assert quiet.main(args) == 2
    assert "only runs" in capsys.readouterr().err
    assert not logs.exists() or not list(logs.glob("*.log"))


# ---- the rewrite hook (D-E, X19) ----

@pytest.mark.parametrize("command", [
    "pytest", "pytest -x tests/ops", ".venv/bin/python -m pytest -q",
    ".venv\\Scripts\\python -m pytest", "python -m ruff check .", "ruff check .",
    "git status", "git diff --stat", "git log --oneline -5",
])
def test_rewrite_sends_allowed_commands_through_quiet(command):
    new = quiet_hook.rewrite(command)
    assert new is not None and "quiet.py" in new


@pytest.mark.parametrize("command", [
    "echo hi", "git commit -m x", "git push origin phase-a", "pytest && rm -rf x",
    "pytest | tail", "pytest > out.txt", "ls", "git status; rm x", "pytest $(whoami)", "",
])
def test_rewrite_leaves_everything_else_alone(command):
    assert quiet_hook.rewrite(command) is None


def _go():
    return g.Usage(1, 1, None, None, time.time())


def test_hook_rewrites_keeping_other_input_fields(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DA_WORKER", "1")
    monkeypatch.setenv("DA_STATE_DIR", str(tmp_path))
    g.write_state(_go())
    payload = {"tool_name": "Bash", "tool_input": {"command": "pytest -x", "timeout": 5000}}
    assert quiet_hook.main(io.StringIO(json.dumps(payload))) == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "allow"
    assert out["updatedInput"]["timeout"] == 5000
    assert "quiet.py" in out["updatedInput"]["command"]


def test_hook_leaves_other_commands_and_other_tools_alone(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DA_WORKER", "1")
    monkeypatch.setenv("DA_STATE_DIR", str(tmp_path))
    g.write_state(_go())
    for payload in ({"tool_name": "Bash", "tool_input": {"command": "echo hi"}},
                    {"tool_name": "Read", "tool_input": {"file_path": "x"}}):
        assert quiet_hook.main(io.StringIO(json.dumps(payload))) == 0
    assert capsys.readouterr().out == ""


def test_guard_wins_when_it_blocks_nothing_is_rewritten(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DA_WORKER", "1")
    monkeypatch.setenv("DA_STATE_DIR", str(tmp_path))
    g.write_state(g.Usage(99, 99, None, None, time.time()))  # fresh and over the line
    payload = {"tool_name": "Bash", "tool_input": {"command": "pytest"}}
    assert quiet_hook.main(io.StringIO(json.dumps(payload))) == 2
    captured = capsys.readouterr()
    assert "Usage line reached" in captured.err and captured.out == ""


def test_hook_does_nothing_outside_workers(monkeypatch, capsys):
    monkeypatch.delenv("DA_WORKER", raising=False)
    payload = {"tool_name": "Bash", "tool_input": {"command": "pytest"}}
    assert quiet_hook.main(io.StringIO(json.dumps(payload))) == 0
    assert capsys.readouterr().out == ""


def test_settings_json_registers_the_quiet_hook_on_bash_only():
    cfg = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    quiet_groups = [x for x in cfg["hooks"]["PreToolUse"] if "quiet_hook" in json.dumps(x)]
    assert len(quiet_groups) == 1 and quiet_groups[0]["matcher"] == "Bash"
