"""Phase A fix 6: STATUS.md is machine-only (not in git), with a backup and a template.

AS400 comparison: the chief's data area moves out of the source file. The tick saves it after every
wake and restores it when it is gone. All files here live in tmp_path (conftest sets DA_STATE_DIR).
"""

import json
from pathlib import Path

import chief_tick as c
import pytest
import safety_hook as s
import stall
import usage_guard as g

NOW = 1_800_000_000.0
ROOT = Path(__file__).resolve().parents[2]
BODY = "# STATUS\nUsage: x\nStopped: no\n## Where we are\n- Next: Phase 7\n## Log\n"


class FakeGh:
    def __call__(self, args):
        if args[:2] == ["issue", "list"]:
            return json.dumps([])
        return "https://example.invalid/issues/1\n"


def usage(five=10, weekly=10):
    return g.Usage(five, weekly, NOW + 3600, NOW + 86400, NOW)


def run_tick(status_file):
    """A tick that stops at the guard (weekly 99%): zero workers, but ensure and backup both run."""
    return c.tick(lambda: usage(weekly=99), FakeGh(), None, status_file, NOW)


# ---- AS-1, AS-2: the git ignore line and the template ----

def test_as1_gitignore_lists_status_md():
    lines = [x.strip() for x in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert "/STATUS.md" in lines or "STATUS.md" in lines


def test_as2_template_has_one_next_line_and_the_top_lines():
    text = c.TEMPLATE_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert len(lines) <= 60
    assert [x for x in lines if x.lstrip("- ").startswith("Next:")] == ["- Next: none"]
    assert any(x.startswith("Stopped:") for x in lines)
    assert any(x.startswith("Usage:") for x in lines)
    assert stall.next_lines(text) == ["- Next: none"]
    assert not c.has_work(text)  # so fix 3's stall alarm tells Gian about a fresh copy


# ---- AS-3 to AS-6, AS-8: backup and self-heal in the tick ----

def test_as3_tick_end_writes_a_backup_with_the_same_text(tmp_path):
    f = tmp_path / "laptop-STATUS.md"  # conftest already made tmp_path/STATUS.md
    f.write_text(BODY, encoding="utf-8")
    assert run_tick(f) == "stopped"
    assert c.backup_path().read_text(encoding="utf-8") == f.read_text(encoding="utf-8")
    assert not c.backup_path().with_suffix(".tmp").exists()  # whole or nothing


def test_as4_missing_file_comes_back_from_the_backup(tmp_path):
    f = tmp_path / "laptop-STATUS.md"  # conftest already made tmp_path/STATUS.md
    c.backup_path().parent.mkdir(parents=True, exist_ok=True)
    c.backup_path().write_text(BODY, encoding="utf-8")
    c.ensure_status(f, NOW)
    text = f.read_text(encoding="utf-8")
    assert text.startswith(BODY.rstrip("\n"))
    assert "STATUS.md restored from backup" in text


def test_a_broken_file_never_replaces_a_good_backup(tmp_path):
    f = tmp_path / "laptop-STATUS.md"
    f.write_text(BODY, encoding="utf-8")
    c.backup_status(f, NOW)
    f.write_text("", encoding="utf-8")
    c.backup_status(f, NOW)
    assert c.backup_path().read_text(encoding="utf-8") == BODY


def test_as5_missing_file_and_no_backup_comes_from_the_template(tmp_path):
    f = tmp_path / "laptop-STATUS.md"  # conftest already made tmp_path/STATUS.md
    c.ensure_status(f, NOW)
    text = f.read_text(encoding="utf-8")
    assert text.startswith(c.TEMPLATE_FILE.read_text(encoding="utf-8").rstrip("\n"))
    assert "STATUS.md created from template" in text


def test_as5_a_full_tick_with_no_file_still_runs_and_keeps_one_next_line(tmp_path):
    f = tmp_path / "laptop-STATUS.md"  # conftest already made tmp_path/STATUS.md
    assert run_tick(f) == "stopped"
    assert len(stall.next_lines(f.read_text(encoding="utf-8"))) == 1


def test_as6_an_existing_file_is_never_overwritten(tmp_path):
    f = tmp_path / "laptop-STATUS.md"  # conftest already made tmp_path/STATUS.md
    f.write_text(BODY, encoding="utf-8")
    c.backup_path().parent.mkdir(parents=True, exist_ok=True)
    c.backup_path().write_text("# OLD BACKUP\n", encoding="utf-8")
    c.ensure_status(f, NOW)
    assert f.read_text(encoding="utf-8") == BODY


def test_as8_a_failed_backup_is_logged_and_the_result_is_unchanged(tmp_path, monkeypatch):
    f = tmp_path / "laptop-STATUS.md"  # conftest already made tmp_path/STATUS.md
    f.write_text(BODY, encoding="utf-8")
    logged = []
    monkeypatch.setattr(c.status_board, "log_failure", lambda problem, now: logged.append(problem))
    monkeypatch.setattr(c.os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("locked")))
    assert run_tick(f) == "stopped"
    assert len(logged) == 1


def test_as8_a_missing_template_falls_back_and_the_tick_still_runs(tmp_path, monkeypatch):
    f = tmp_path / "laptop-STATUS.md"  # conftest already made tmp_path/STATUS.md
    logged = []
    monkeypatch.setattr(c, "TEMPLATE_FILE", tmp_path / "no-such-template.md")
    monkeypatch.setattr(c.status_board, "log_failure", lambda problem, now: logged.append(problem))
    assert run_tick(f) == "stopped"
    assert len(logged) == 1
    assert "built-in fallback" in f.read_text(encoding="utf-8")


# ---- AS-9 (plan review Must fix 1): main passes the patched path, never the real one ----

def test_main_tick_passes_the_status_file_at_call_time(monkeypatch):
    seen = {}

    def fake_tick(*args, **kwargs):
        seen.update(kwargs)
        return "idle"

    monkeypatch.setattr(c, "tick", fake_tick)
    assert c.main(["tick"]) == 0
    assert seen["status_file"] == c.STATUS_FILE  # conftest points this at tmp_path
    assert seen["status_file"] != ROOT / "STATUS.md"


# ---- AS-7: the safety hook ----

@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("DA_WORKER", "1")


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(ROOT)}


@pytest.mark.parametrize("command", [
    "git add STATUS.md", "git add ./STATUS.md", "git add -- STATUS.md", "git -C . add STATUS.md",
    "git add src/da_x.py STATUS.md", "git add -f x.py", "git add --force x.py",
    "git add --forc x.py", "git add -fA",
])
def test_as7_status_md_and_force_add_are_refused(worker, command):
    assert s.check(bash(command))


@pytest.mark.parametrize("command", [
    "git add src/da_x.py", "git add -A", "git add .", "git add tests/ops/test_x.py specs/x.md",
])
def test_as7_normal_adds_are_still_allowed(worker, command):
    assert s.check(bash(command)) is None
