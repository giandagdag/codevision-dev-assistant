import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import chief_tick as c
import pytest
import usage_guard as g

NOW = 1_800_000_000.0
ROOT = Path(__file__).resolve().parents[2]


class FakeGh:
    def __init__(self, open_issues=(), pr=None):
        self.calls = []
        self.open_issues = list(open_issues)
        self.pr = pr

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"title": t} for t in self.open_issues])
        if args[:2] == ["pr", "view"]:
            return json.dumps(self.pr)
        return "https://example.invalid/issues/1\n"

    def created(self):
        return [a for a in self.calls if a[:2] == ["issue", "create"]]

    def merged(self):
        return [a for a in self.calls if a[:2] == ["pr", "merge"]]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DA_LEDGER_FILE", str(tmp_path / "ledger.csv"))
    return tmp_path


@pytest.fixture
def status_file(tmp_path):
    f = tmp_path / "STATUS.md"
    f.write_text("# STATUS\nUsage: x\nStopped: no\n## Where we are\n- Next: Phase 7\n## Log\n",
                 encoding="utf-8")
    return f


def usage(five=10, weekly=10):
    return g.Usage(five, weekly, NOW + 3600, NOW + 86400, NOW)


def no_launch(prompt, agent="chief"):
    raise AssertionError("no worker may start")


def ok_hooks():
    return None


def blind():
    raise g.GuardBlind("down")


# ---- AC-1 ----

def test_weekly_80_starts_no_worker_and_status_says_stopped(status_file):
    gh = FakeGh()
    result = c.tick(lambda: usage(weekly=83), gh, no_launch, status_file, NOW)
    text = status_file.read_text(encoding="utf-8")
    assert result == "stopped"
    assert "Stopped: weekly 83%, resets " in text and "SGT" in text
    assert "Usage: 5h 10% / weekly 83%" in text and "stopped yes" in text
    assert gh.created() == []  # not blind, so no issue


# ---- AC-3 ----

def test_blind_guard_starts_nothing_and_opens_one_issue_only(status_file):
    gh = FakeGh()
    assert c.tick(blind, gh, no_launch, status_file, NOW) == "stopped"
    assert len(gh.created()) == 1
    assert gh.created()[0][gh.created()[0].index("--label") + 1] == "needs-gian"
    assert "guard blind" in status_file.read_text(encoding="utf-8")
    again = FakeGh(open_issues=[c.GUARD_BLIND_TITLE])
    c.tick(blind, again, no_launch, status_file, NOW)
    assert again.created() == []  # no duplicate


# ---- idle, dry run, run ----

def test_idle_when_no_next_step_and_zero_workers(status_file):
    status_file.write_text("# S\nUsage: x\n- Next: none\n## Log\n", encoding="utf-8")
    assert c.tick(lambda: usage(), FakeGh(), no_launch, status_file, NOW) == "idle"


def test_without_launch_flag_it_only_reports(status_file):
    assert c.tick(lambda: usage(), FakeGh(), None, status_file, NOW) == "would-start"
    assert "not launched" in status_file.read_text(encoding="utf-8")


def test_worker_run_writes_one_ledger_line_and_records_the_note(status_file, isolated):
    states = iter([usage(10, 10), usage(20, 12)])

    def reader():
        return next(states)

    def launcher(prompt, agent="chief"):
        (isolated / "state").mkdir(exist_ok=True)
        (isolated / "state" / "worker_note.md").write_text("stopped at step 3", encoding="utf-8")
        return c.WorkerResult(0, json.dumps({"total_cost_usd": 0.5,
                                             "usage": {"input_tokens": 9, "output_tokens": 3}}))

    assert c.tick(reader, FakeGh(), launcher, status_file, NOW, preflight=ok_hooks) == "ran"
    rows = (isolated / "ledger.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2  # header plus ONE line (AC-7)
    assert ",chief,sonnet,10,20,10,12,9,3,0.5,ok (worker saved a note)" in rows[1]
    assert "stopped at step 3" in status_file.read_text(encoding="utf-8")


def test_failed_worker_still_gets_a_ledger_line(status_file, isolated):
    c.tick(lambda: usage(), FakeGh(), lambda p, a="chief": c.WorkerResult(1, ""), status_file, NOW,
           preflight=ok_hooks)
    rows = (isolated / "ledger.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2 and "exit code 1" in rows[1]


# ---- AC-4 ----

def test_gian_issue_has_a_label_and_no_duplicates():
    gh = FakeGh()
    assert c.open_gian_issue("Q9", "body", "needs-work-test", gh)
    assert gh.created()[0][-1] == "needs-work-test"
    assert c.open_gian_issue("Q9", "body", "needs-work-test", FakeGh(open_issues=["Q9"])) is None
    with pytest.raises(ValueError):
        c.open_gian_issue("x", "y", "random-label", gh)


def test_pause_marks_the_stage_in_status(status_file):
    c.status.mark_paused(status_file, "Phase 7 spec D-C", "Q9")
    assert "PAUSED Phase 7 spec D-C: waiting for Gian, see Q9" in status_file.read_text(
        encoding="utf-8")


# ---- AC-5 ----

def pr(base, checks):
    return {"baseRefName": base, "statusCheckRollup": checks}


GREEN = [{"name": "tests", "conclusion": "SUCCESS"}]


def test_merge_into_the_integration_branch_with_green_checks_works():
    gh = FakeGh(pr=pr("auto/phases-7-10", GREEN))
    c.merge_pr(7, gh)
    assert gh.merged() == [["pr", "merge", "7", "--merge"]]


def test_merge_into_main_is_refused_before_anything_is_merged():
    gh = FakeGh(pr=pr("main", GREEN))
    with pytest.raises(c.MergeRefused, match="only merges into auto/phases-7-10"):
        c.merge_pr(7, gh)
    assert gh.merged() == []


@pytest.mark.parametrize("checks", [
    [], [{"name": "tests", "conclusion": "FAILURE"}], [{"name": "tests", "state": "PENDING"}],
    GREEN + [{"name": "lint", "conclusion": "FAILURE"}],
])
def test_merge_refused_when_checks_are_missing_red_or_pending(checks):
    gh = FakeGh(pr=pr("auto/phases-7-10", checks))
    with pytest.raises(c.MergeRefused):
        c.merge_pr(7, gh)
    assert gh.merged() == []


# ---- the launcher flags (X15, F3) ----

def test_worker_command_keeps_hooks_on_and_mcp_off():
    cmd = c.worker_command("go")
    assert "--bare" not in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "--strict-mcp-config" in cmd and "--disable-slash-commands" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == "project,local"
    assert cmd[cmd.index("--mcp-config") + 1].endswith("mcp-empty.json")
    assert cmd[cmd.index("--settings") + 1].endswith("worker_settings.json")


def test_real_launcher_sets_the_worker_variable(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs["env"]

        class Done:
            returncode, stdout = 0, "{}"

        return Done()

    monkeypatch.setattr(c.subprocess, "run", fake_run)
    c.real_launcher("hi", "builder")
    assert seen["env"]["DA_WORKER"] == "1"
    assert seen["env"]["DA_AGENT"] == "builder"
    assert seen["env"]["DA_PYTHON"] == sys.executable


def test_main_refuses_a_bad_merge_with_a_plain_message(capsys):
    gh = FakeGh(pr=pr("main", GREEN))
    assert c.main(["merge", "--pr", "7"], gh) == 1
    assert "Refused: PR 7 targets main, and the chief only merges" in capsys.readouterr().err
    assert gh.merged() == []


# ---- review round 1, Must fix 2: hooks must be able to start, or no worker starts ----

def test_no_worker_starts_when_the_hooks_cannot_start(status_file):
    gh = FakeGh()
    result = c.tick(lambda: usage(), gh, no_launch, status_file, NOW,
                    preflight=lambda: "guard_hook.py did not block")
    assert result == "hooks-broken"
    assert "hooks cannot start" in status_file.read_text(encoding="utf-8")
    assert len(gh.created()) == 1


def test_hooks_ready_runs_each_hook_and_wants_a_fail_closed_exit_2(monkeypatch):
    seen = []

    class Done:
        def __init__(self, code):
            self.returncode = code

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs["env"]["DA_WORKER"], kwargs["input"]))
        return Done(2)

    monkeypatch.setattr(c.subprocess, "run", fake_run)
    assert c.hooks_ready("/py") is None
    assert [Path(x[0][1]).name for x in seen] == ["guard_hook.py", "quiet_hook.py",
                                                  "safety_hook.py"]
    assert all(x[0][0] == "/py" and x[1] == "1" for x in seen)

    monkeypatch.setattr(c.subprocess, "run", lambda cmd, **kw: Done(0))
    assert "guard_hook.py" in c.hooks_ready("/py")

    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(c.subprocess, "run", missing)
    assert "could not be started" in c.hooks_ready("/missing-python")


GIT_BASH_DEFAULTS = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
    r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe",
)


def find_bash(platform=None, which=None, exists=None):
    """A bash to run the hook strings with: PATH first, then Git for Windows' default places.

    On Windows `bash` on PATH can be the WSL launcher in System32, which runs a different Linux,
    so that one is skipped (Claude Code itself uses Git Bash). Returns None when none is found.
    """
    platform = platform or sys.platform
    which = which or shutil.which
    exists = exists or os.path.exists
    found = which("bash")
    if found and not (platform == "win32" and "system32" in found.lower()):
        return found
    if platform == "win32":
        for candidate in GIT_BASH_DEFAULTS:
            candidate = os.path.expandvars(candidate)
            if exists(candidate):
                return candidate
    return None


def test_find_bash_prefers_path_skips_wsl_then_tries_git_for_windows_defaults():
    git = r"C:\Program Files\Git\bin\bash.exe"
    assert find_bash("linux", lambda _: "/usr/bin/bash") == "/usr/bin/bash"
    assert find_bash("win32", lambda _: r"C:\tools\Git\bin\bash.exe") == (
        r"C:\tools\Git\bin\bash.exe")
    # WSL launcher on PATH is skipped, Git Bash default path is used
    wsl = r"C:\Windows\System32\bash.exe"
    assert find_bash("win32", lambda _: wsl, exists=lambda p: p == git) == git
    # not on PATH at all (the PowerShell case): default path
    assert find_bash("win32", lambda _: None, exists=lambda p: p == git) == git
    assert find_bash("win32", lambda _: None, exists=lambda p: False) is None
    assert find_bash("linux", lambda _: None, exists=lambda p: True) is None


def test_settings_hooks_use_da_python_and_are_silent_without_it(tmp_path):
    bash = find_bash()
    if bash is None:
        pytest.skip("no bash found (install Git for Windows); the hook strings need bash to run")
    cfg = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for g_ in cfg["hooks"]["PreToolUse"] for h in g_["hooks"]]
    assert len(commands) == 3 and all("${DA_PYTHON:-true}" in x for x in commands)
    # Keep the normal environment (Windows Python needs SYSTEMROOT), minus any DA_ variables.
    base = {k: v for k, v in os.environ.items() if not k.startswith("DA_")}
    base["CLAUDE_PROJECT_DIR"] = str(ROOT)
    for command in commands:  # no DA_PYTHON: `true` ignores the args, so nothing is in the way
        run = subprocess.run([bash, "-c", command], input="{}", capture_output=True,
                             text=True, env=base)
        assert run.returncode == 0 and run.stdout == "" and run.stderr == ""
    worker = {**base, "DA_WORKER": "1", "DA_PYTHON": sys.executable}
    for command in commands:  # with it: the real hook runs and fails closed on garbage
        run = subprocess.run([bash, "-c", command], input="garbage", capture_output=True,
                             text=True, env=worker)
        assert run.returncode == 2


# ---- review round 1, Must fix 3: the chief can run its own commands ----

def test_every_chief_command_is_in_the_allow_list_and_none_is_denied():
    cfg = json.loads((ROOT / "ops" / "worker_settings.json").read_text(encoding="utf-8"))
    allow = [a[len("Bash("):-len(":*)")] for a in cfg["permissions"]["allow"]
             if a.startswith("Bash(") and a.endswith(":*)")]
    for name in ("chief", "builder"):
        text = (ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
        commands = re.findall(r"`(\"\$DA_PYTHON\" ops/[a-z_]+\.py[^`]*)`", text)
        if name == "chief":
            assert len(commands) >= 5
        for command in commands:
            assert any(command.startswith(prefix) for prefix in allow), command


def test_launch_starts_one_named_worker_and_writes_a_ledger_line(status_file, isolated):
    seen = []

    def launcher(prompt, agent="chief"):
        seen.append(agent)
        return c.WorkerResult(0, "{}")

    out = c.launch_worker("spec-writer", "write the spec", "spec", "7",
                          lambda: usage(), FakeGh(), launcher, status_file, NOW, ok_hooks)
    assert out == "ran" and seen == ["spec-writer"]
    row = (isolated / "ledger.csv").read_text(encoding="utf-8").splitlines()[1]
    assert ",7,spec,opus," in row


def test_launch_refuses_unknown_agents_stopped_guard_and_broken_hooks(status_file, isolated):
    def go(agent, reader=lambda: usage(), hooks=ok_hooks):
        g.state_path().unlink(missing_ok=True)  # each call starts with no saved reading
        return c.launch_worker(agent, "x", "s", "7", reader, FakeGh(), no_launch, status_file,
                               NOW, hooks)
    with pytest.raises(ValueError):
        go("not-an-agent")
    assert go("builder", reader=lambda: usage(weekly=90)) == "stopped"
    assert go("builder", reader=blind) == "stopped"
    assert go("builder", hooks=lambda: "broken") == "hooks-broken"
    assert not (isolated / "ledger.csv").exists()


def test_a_launcher_that_crashes_still_gets_a_ledger_line(status_file, isolated):
    def boom(prompt, agent="chief"):
        raise FileNotFoundError("claude")

    out = c.launch_worker("builder", "x", "build", "7", lambda: usage(), FakeGh(), boom,
                          status_file, NOW, ok_hooks)
    assert out == "ran"
    assert "launcher error: FileNotFoundError" in (isolated / "ledger.csv").read_text(
        encoding="utf-8")


def test_a_crash_while_reading_usage_after_the_run_does_not_lose_the_ledger_line(
    status_file, isolated
):
    calls = iter([usage()])

    def flaky():
        try:
            return next(calls)
        except StopIteration:
            raise ConnectionError("reset") from None

    c.launch_worker("builder", "x", "build", "7", flaky, FakeGh(),
                    lambda p, a="chief": c.WorkerResult(0, ""), status_file, NOW, ok_hooks)
    assert len((isolated / "ledger.csv").read_text(encoding="utf-8").splitlines()) == 2


def test_launch_command_line_passes_the_agent_and_its_model():
    cmd = c.worker_command("go", "spec-writer", c.AGENT_MODELS["spec-writer"])
    assert cmd[cmd.index("--agent") + 1] == "spec-writer"
    assert cmd[cmd.index("--model") + 1] == "opus"
