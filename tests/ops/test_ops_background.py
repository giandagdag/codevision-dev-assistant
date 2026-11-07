"""Phase A fix 1: workers run in the background (AF-1 to AF-12). No real claude, no real process."""

import json
from pathlib import Path

import chief_tick as c
import pytest
import usage_guard as g

NOW = 1_800_000_000.0
ROOT = Path(__file__).resolve().parents[2]
HOUR = 3600


def usage(five=10, weekly=10):
    return g.Usage(five, weekly, NOW + 3600, NOW + 86400, NOW)


def ok_hooks():
    return None


class FakeGh:
    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        return "[]"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DA_LEDGER_FILE", str(tmp_path / "ledger.csv"))
    monkeypatch.setenv("DA_WORKER_LOG_DIR", str(tmp_path / "workers"))
    return tmp_path


@pytest.fixture
def status_file(tmp_path):
    f = tmp_path / "STATUS.md"
    f.write_text("# STATUS\nUsage: x\nStopped: no\n## Where we are\n- Next: Phase 7\n## Log\n",
                 encoding="utf-8")
    return f


@pytest.fixture
def ledger_rows(tmp_path):
    def rows():
        f = tmp_path / "ledger.csv"
        return f.read_text(encoding="utf-8").splitlines()[1:] if f.exists() else []
    return rows


def start(status_file, agent="builder", reader=None, spawn=None, hooks=ok_hooks, now=NOW):
    g.state_path().unlink(missing_ok=True)  # every call starts with no saved reading
    return c.start_background(agent, "Run pytest -q " + "x" * 300, "test", "7",
                              reader or (lambda: usage()), FakeGh(), status_file, now, hooks,
                              spawn or (lambda a, p: 4242))


def note():
    return json.loads(c.running_path().read_text(encoding="utf-8"))


def no_chief(prompt, agent="chief"):
    raise AssertionError("no chief may start")


def tick(status_file, launcher=no_chief, now=NOW, alive=lambda pid: True, killer=None,
         reader=lambda: usage()):
    killed = []
    result = c.tick(reader, FakeGh(), launcher, status_file, now, ok_hooks, alive,
                    killer or killed.append)
    return result, killed


def write_running(**over):
    data = {"agent": "builder", "stage": "build", "phase": "7", "prompt": "p", "pid": 4242,
            "started": NOW - 10, "five_hour_before": 10, "weekly_before": 11}
    c._write_note(c.running_path(), {**data, **over})


def write_done(**over):
    data = {"agent": "builder", "exit_code": 0, "crash": "", "finished": NOW - 5,
            "reply_file": "20270101-000000-builder.json",
            "stdout": json.dumps({"result": "Pytest: 120 passed.",
                                  "usage": {"input_tokens": 9, "output_tokens": 3}}),
            "stderr": ""}
    c._write_note(c.done_path(), {**data, **over})


# ---- AF-1, AF-2, AF-10: launch ----

def test_af1_launch_returns_started_and_writes_the_running_note(status_file):
    assert start(status_file) == "started builder"
    data = note()
    assert data["pid"] == 4242 and data["agent"] == "builder" and data["started"] == NOW
    assert data["stage"] == "test" and data["phase"] == "7"
    assert data["five_hour_before"] == 10 and len(data["prompt"]) == 200


def test_af2_launch_while_a_worker_runs_says_busy_and_starts_nothing(status_file):
    start(status_file)

    def boom(agent, prompt):
        raise AssertionError("nothing may start")

    assert start(status_file, agent="spec-writer", spawn=boom) == "busy builder"


@pytest.mark.parametrize("kind", ["stop", "blind", "hooks"])
def test_af10_nothing_starts_when_the_guard_says_stop_or_hooks_are_broken(status_file, kind):
    def boom(agent, prompt):
        raise AssertionError("nothing may start")

    def blind():
        raise g.GuardBlind("down")

    kwargs = {"stop": {"reader": lambda: usage(weekly=90)}, "blind": {"reader": blind},
              "hooks": {"hooks": lambda: "broken"}}[kind]
    expected = "hooks-broken" if kind == "hooks" else "stopped"
    assert start(status_file, spawn=boom, **kwargs) == expected
    assert not c.running_path().exists()


def test_a_start_that_fails_leaves_no_note_and_says_why(status_file):
    def broken(agent, prompt):
        raise FileNotFoundError("python")

    with pytest.raises(RuntimeError, match="could not be started"):
        start(status_file, spawn=broken)
    assert not c.running_path().exists()
    assert "could not be started" in status_file.read_text(encoding="utf-8")


def test_launch_through_main_prints_started_and_refuses_in_plain_words(
    status_file, monkeypatch, capsys
):
    monkeypatch.setattr(c, "STATUS_FILE", status_file)
    monkeypatch.setattr(c.usage_guard, "endpoint_reader", lambda: usage())
    monkeypatch.setattr(c, "hooks_ready", lambda python=None: None)
    monkeypatch.setattr(c, "spawn_runner", lambda a, p: 77)
    args = ["launch", "--agent", "builder", "--stage", "t", "--prompt", "x"]
    assert c.main(args, FakeGh()) == 0
    assert capsys.readouterr().out.strip() == "started builder"
    assert c.main(args, FakeGh()) == 0
    assert capsys.readouterr().out.strip() == "busy builder"


# ---- the runner (F2) ----

def test_the_runner_writes_the_end_message_and_the_reply_file(status_file, isolated):
    seen = []

    def fake(prompt, agent="chief"):
        seen.append((prompt, agent))
        return c.WorkerResult(3, json.dumps({"result": "done"}), stderr="warn")

    c.run_worker("builder", "go", fake)
    done = json.loads(c.done_path().read_text(encoding="utf-8"))
    assert seen == [("go", "builder")]
    assert done["exit_code"] == 3 and done["stderr"] == "warn" and done["finished"] > 0
    assert (isolated / "workers" / done["reply_file"]).exists()


def test_a_runner_whose_claude_cannot_start_still_writes_the_end_message():
    def boom(prompt, agent="chief"):
        raise FileNotFoundError("claude")

    c.run_worker("builder", "go", boom)
    assert json.loads(c.done_path().read_text(encoding="utf-8"))["crash"] == "FileNotFoundError"


def test_run_worker_is_a_command_line_subcommand(monkeypatch):
    seen = []
    monkeypatch.setattr(c, "real_launcher",
                        lambda p, a="chief": seen.append((p, a)) or c.WorkerResult(0, "{}"))
    assert c.main(["run-worker", "--agent", "builder", "--prompt", "hi"], FakeGh()) == 0
    assert seen == [("hi", "builder")] and c.done_path().exists()


# ---- AF-3, AF-4: the tick looks at the queue first ----

def test_af3_a_running_worker_means_busy_and_nothing_changes(status_file, ledger_rows):
    write_running()
    before = status_file.read_text(encoding="utf-8")
    result, killed = tick(status_file)
    assert result == "busy" and killed == []
    assert status_file.read_text(encoding="utf-8") == before
    assert ledger_rows() == [] and c.running_path().exists()


def test_busy_also_with_no_launch_flag(status_file):
    write_running()
    assert tick(status_file, launcher=None)[0] == "busy"


def test_af4_a_finished_worker_is_recorded_once_then_the_chief_starts(status_file, ledger_rows):
    write_running()
    write_done()
    started = []

    def chief(prompt, agent="chief"):
        started.append(agent)
        return c.WorkerResult(0, "{}")

    result, _ = tick(status_file, launcher=chief)
    log = status_file.read_text(encoding="utf-8")
    assert result == "ran" and started == ["chief"]
    assert "builder: Pytest: 120 passed. -> logs/workers/20270101-000000-builder.json" in log
    rows = ledger_rows()
    assert len(rows) == 2  # the builder's line and the chief's line
    assert ",7,build,sonnet,10,10,11,10,9,3,,,,ok" in rows[0]
    assert not c.running_path().exists() and not c.done_path().exists()


def test_a_finished_worker_is_recorded_even_with_no_launch_flag(status_file, ledger_rows):
    write_running()
    write_done()
    assert tick(status_file, launcher=None)[0] == "would-start"
    assert len(ledger_rows()) == 1


def test_a_second_tick_records_nothing_more(status_file, ledger_rows):
    write_running()
    write_done()
    tick(status_file, launcher=None)
    tick(status_file, launcher=None)
    assert len(ledger_rows()) == 1
    assert status_file.read_text(encoding="utf-8").count("Pytest: 120 passed.") == 1


def test_an_end_message_without_a_running_note_is_still_recorded(status_file, ledger_rows):
    write_done()
    tick(status_file, launcher=None)
    assert "builder: Pytest: 120 passed." in status_file.read_text(encoding="utf-8")
    assert len(ledger_rows()) == 1 and not c.done_path().exists()


def test_the_worker_note_is_kept_in_the_log(status_file, isolated):
    write_running()
    write_done()
    (isolated / "state").mkdir(exist_ok=True)
    (isolated / "state" / "worker_note.md").write_text("stopped at step 3", encoding="utf-8")
    tick(status_file, launcher=None)
    assert "worker note: stopped at step 3" in status_file.read_text(encoding="utf-8")


# ---- AF-5, AF-6, AF-12: vanished, over the limit, stop ----

def test_af5_a_vanished_worker_is_recorded_and_the_chief_wakes(status_file, ledger_rows):
    write_running()
    started = []
    result, killed = tick(status_file, launcher=lambda p, a="chief": started.append(a) or
                          c.WorkerResult(0, "{}"), alive=lambda pid: False)
    log = status_file.read_text(encoding="utf-8")
    assert "builder ended without a result (vanished)" in log
    assert ledger_rows()[0].endswith(",vanished") and started == ["chief"] and killed == []
    assert not c.running_path().exists() and result == "ran"


def test_a_damaged_running_note_counts_as_vanished(status_file, ledger_rows):
    c.running_path().parent.mkdir(parents=True, exist_ok=True)
    c.running_path().write_text("{not json", encoding="utf-8")
    assert tick(status_file, launcher=None)[0] == "would-start"
    assert "worker ended without a result (vanished)" in status_file.read_text(encoding="utf-8")
    assert not c.running_path().exists() and len(ledger_rows()) == 1


def test_a_note_still_waiting_for_its_pid_is_busy_for_a_minute_only(status_file):
    write_running(pid=None, started=NOW - 5)
    assert tick(status_file, launcher=None)[0] == "busy"
    assert tick(status_file, launcher=None, now=NOW + 120)[0] == "would-start"


def test_af6_a_worker_over_the_time_limit_is_stopped_and_the_chief_wakes(
    status_file, ledger_rows
):
    write_running(started=NOW - (c.MAX_WORKER_HOURS * HOUR + 1))
    result, killed = tick(status_file, launcher=None)
    assert killed == [4242] and result == "would-start"
    assert "builder stopped: over the time limit" in status_file.read_text(encoding="utf-8")
    assert ledger_rows()[0].endswith(",stopped: over the time limit")
    assert not c.running_path().exists()


def test_a_worker_just_under_the_limit_is_left_alone(status_file):
    write_running(started=NOW - (c.MAX_WORKER_HOURS * HOUR - 5))
    result, killed = tick(status_file, launcher=None)
    assert result == "busy" and killed == []


def test_af12_stop_ends_the_worker_and_records_it(status_file, ledger_rows):
    write_running()
    killed = []
    out = c.stop_worker(lambda: usage(), status_file, NOW, killer=killed.append)
    assert out == "stopped builder" and killed == [4242]
    assert "builder stopped: by hand" in status_file.read_text(encoding="utf-8")
    assert ledger_rows()[0].endswith(",stopped: by hand") and not c.running_path().exists()
    assert c.stop_worker(lambda: usage(), status_file, NOW) == "nothing running"
    assert len(ledger_rows()) == 1  # a second stop writes nothing


def test_stop_leaves_a_finished_worker_for_the_tick_to_record(status_file, ledger_rows):
    write_running()
    write_done()
    out = c.stop_worker(lambda: usage(), status_file, NOW, killer=lambda pid: 1 / 0)
    assert "already finished" in out and ledger_rows() == [] and c.running_path().exists()


def test_stop_is_a_command_line_subcommand(status_file, monkeypatch, capsys):
    monkeypatch.setattr(c, "STATUS_FILE", status_file)
    monkeypatch.setattr(c.usage_guard, "endpoint_reader", lambda: usage())
    assert c.main(["stop"], FakeGh()) == 0
    assert capsys.readouterr().out.strip() == "nothing running"


# ---- AF-7, AF-8, AF-9 ----

def test_af7_max_turns_come_from_the_table_per_agent():
    def turns(agent):
        cmd = c.worker_command("go", agent)
        return int(cmd[cmd.index("--max-turns") + 1])

    assert turns("builder") == 400 and turns("chief") == 60
    assert turns("spec-writer") == 80 and turns("status-digest") == 20
    assert turns("plan-reviewer") == 80 and turns("code-reviewer") == 80
    assert set(c.AGENT_MAX_TURNS) == set(c.AGENT_MODELS)


def settings():
    return json.loads((ROOT / "ops" / "worker_settings.json").read_text(encoding="utf-8"))


def test_af8_worker_settings_have_the_two_bash_time_outs():
    assert settings()["env"] == {"BASH_DEFAULT_TIMEOUT_MS": "900000",
                                 "BASH_MAX_TIMEOUT_MS": "1800000"}


def test_af9_chief_rulebook_says_a_launch_ends_the_step():
    text = (ROOT / ".claude" / "agents" / "chief.md").read_text(encoding="utf-8")
    assert "ENDS your step" in text and "Running: <agent> since <time>" in text
    assert "vanished" in text and "over the time limit" in text
    assert "continue from your last commit" in text and "second time" in text
    assert "run-worker" not in text  # only `launch` starts the runner


def test_workers_cannot_call_run_worker_or_stop_in_any_interpreter_spelling():
    cfg = settings()["permissions"]
    interpreters = [a[len("Bash("):-len(" ops/chief_tick.py:*)")] for a in cfg["allow"]
                    if a.endswith(" ops/chief_tick.py:*)")]
    for allow in cfg["allow"]:  # every way of writing the interpreter that the allow list has
        if allow.startswith("Bash(.venv") and allow.endswith("python:*)"):
            interpreters.append(allow[len("Bash("):-len(":*)")])
    assert len(set(interpreters)) >= 4
    for py in set(interpreters):
        for sub in ("run-worker", "stop"):
            assert f"Bash({py} ops/chief_tick.py {sub}:*)" in cfg["deny"], (py, sub)


# ---- AF-11: how the runner is started ----

class FakePopen:
    def __init__(self):
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))

        class Proc:
            pid = 999

        return Proc()


def test_af11_on_windows_the_runner_gets_the_three_creation_flags():
    popen = FakePopen()
    assert c.spawn_runner("builder", "go", "win32", popen) == 999
    command, kwargs = popen.calls[0]
    assert kwargs["creationflags"] == 0x8 | 0x200 | 0x08000000
    assert "start_new_session" not in kwargs
    assert command[-5:] == ["run-worker", "--agent", "builder", "--prompt", "go"]


def test_on_linux_the_runner_leads_its_own_session_and_holds_no_pipes():
    popen = FakePopen()
    c.spawn_runner("builder", "go", "linux", popen)
    _, kwargs = popen.calls[0]
    assert kwargs["start_new_session"] is True and "creationflags" not in kwargs
    assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == c.DEVNULL


def test_stopping_a_tree_uses_taskkill_on_windows_and_the_group_elsewhere():
    ran, groups = [], []
    c.stop_tree(5, "win32", run=lambda cmd, **kw: ran.append(cmd))
    assert ran == [["taskkill", "/PID", "5", "/T", "/F"]]
    c.stop_tree(5, "linux", killpg=lambda pid, sig: groups.append(pid))
    assert groups == [5]
    c.stop_tree(5, "linux", killpg=lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))


def test_pid_alive_knows_this_process_and_a_missing_one():
    import os
    assert c.pid_alive(os.getpid())
    assert not c.pid_alive(2**22 + 12345)
