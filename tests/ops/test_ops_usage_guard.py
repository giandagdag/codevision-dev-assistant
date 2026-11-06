import io
import json
import subprocess
import sys
from pathlib import Path

import guard_hook
import pytest
import usage_guard as g

NOW = 1_800_000_000.0  # a fixed clock; tests never use the real time
ROOT = Path(__file__).resolve().parents[2]


def usage(five=10.0, weekly=10.0, read_at=NOW):
    return g.Usage(five, weekly, NOW + 3600, NOW + 86400, read_at)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DA_WORKER", raising=False)
    return tmp_path / "state"


def no_reader():
    raise AssertionError("the reader must not be called")


def blind_reader():
    raise g.GuardBlind("down")


# ---- decide (AC-1, AC-3) ----

def test_weekly_79_is_go_and_80_is_stop():
    assert g.decide(usage(weekly=79)).go
    d = g.decide(usage(weekly=80))
    assert not d.go and d.reason.startswith("weekly 80%, resets ")


def test_five_hour_84_is_go_and_85_is_stop():
    assert g.decide(usage(five=84)).go
    d = g.decide(usage(five=85))
    assert not d.go and d.reason.startswith("5-hour 85%")


def test_stopped_line_matches_ac1_and_shows_singapore_time():
    d = g.decide(usage(weekly=83))
    line = g.stopped_line(d)
    assert line.startswith("Stopped: weekly 83%, resets ")
    assert line.endswith(" SGT")
    # NOW + 86400 s is 2027-01-16 08:00 UTC = 16:00 SGT
    assert "16:00 SGT" in line


def test_blind_when_no_usage():
    d = g.decide(None)
    assert not d.go and "guard blind" in d.reason


# ---- state and refresh (X17) ----

def test_fresh_state_is_used_without_reading(isolated_state):
    g.write_state(usage(weekly=20, read_at=NOW - 100))
    assert g.get_usage(no_reader, now=NOW).weekly == 20


def test_stale_state_triggers_a_reread_and_saves_it(isolated_state):
    g.write_state(usage(weekly=20, read_at=NOW - 1000))
    got = g.get_usage(lambda: usage(weekly=33), now=NOW)
    assert got.weekly == 33
    assert g.read_state().weekly == 33


def test_failed_reread_is_blind(isolated_state):
    g.write_state(usage(read_at=NOW - 1000))
    assert g.get_usage(blind_reader, now=NOW) is None


def test_missing_or_broken_state_file_is_blind_when_reader_fails(isolated_state):
    assert g.get_usage(blind_reader, now=NOW) is None
    isolated_state.mkdir(parents=True)
    (isolated_state / "usage.json").write_text("not json")
    assert g.get_usage(blind_reader, now=NOW) is None


# ---- the real reader (no network in tests) ----

def test_endpoint_reader_is_blind_until_settings_are_filled(monkeypatch):
    monkeypatch.delenv("DA_USAGE_URL", raising=False)
    monkeypatch.delenv("DA_USAGE_TOKEN_FILE", raising=False)
    with pytest.raises(g.GuardBlind, match="not set yet"):
        g.endpoint_reader()


def test_endpoint_reader_refuses_plain_http(monkeypatch, tmp_path):
    monkeypatch.setenv("DA_USAGE_URL", "http://example.invalid/usage")
    monkeypatch.setenv("DA_USAGE_TOKEN_FILE", str(tmp_path / "t"))
    with pytest.raises(g.GuardBlind, match="https"):
        g.endpoint_reader()


def test_parse_accepts_status_line_names_and_rejects_other_shapes():
    body = {
        "five_hour": {"used_percentage": 12.5, "resets_at": NOW},
        "seven_day": {"used_percentage": 40, "resets_at": NOW + 5},
    }
    u = g.parse_usage_response(body, NOW)
    assert (u.five_hour, u.weekly, u.weekly_resets_at) == (12.5, 40.0, NOW + 5)
    with pytest.raises(g.GuardBlind):
        g.parse_usage_response({"something": "else"}, NOW)


def test_errors_never_contain_the_token(monkeypatch, tmp_path):
    secret = "sk-test-SECRET-TOKEN-123"
    token_file = tmp_path / "token"
    token_file.write_text(secret)
    monkeypatch.setenv("DA_USAGE_URL", "https://example.invalid/usage")
    monkeypatch.setenv("DA_USAGE_TOKEN_FILE", str(token_file))

    def boom(request, timeout):
        raise OSError(f"failed with header {request.get_header('Authorization')}")

    monkeypatch.setattr(g.urllib.request, "urlopen", boom)
    with pytest.raises(g.GuardBlind) as err:
        g.endpoint_reader()
    assert secret not in str(err.value)


def test_main_prints_go_or_stop(capsys, isolated_state):
    assert g.main(lambda: usage(weekly=10)) == 0
    assert capsys.readouterr().out.startswith("GO")
    (isolated_state / "usage.json").unlink()
    assert g.main(blind_reader) == 1
    assert capsys.readouterr().out.startswith("STOP: guard blind")


# ---- the hook (AC-2, X11, X12, X18) ----

def bash(cwd="/x"):
    return {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": cwd}


def run_hook(payload, reader, worker=True, monkeypatch=None):
    if worker:
        monkeypatch.setenv("DA_WORKER", "1")
    return guard_hook.main(io.StringIO(json.dumps(payload)), reader)


def test_hook_does_nothing_outside_a_worker_even_when_blind(monkeypatch):
    assert run_hook(bash(), blind_reader, worker=False, monkeypatch=monkeypatch) == 0


def test_hook_allows_when_go(monkeypatch):
    assert run_hook(bash(), lambda: usage(five=10), monkeypatch=monkeypatch) == 0


def test_hook_blocks_with_exit_2_and_a_plain_message_at_85(monkeypatch, capsys):
    code = run_hook(bash(), lambda: usage(five=86, read_at=0), monkeypatch=monkeypatch)
    err = capsys.readouterr().err
    assert code == 2
    assert "Usage line reached" in err and "worker_note.md" in err and "stop" in err


def test_hook_blocks_when_blind(monkeypatch, capsys):
    assert run_hook(bash(), blind_reader, monkeypatch=monkeypatch) == 2
    assert "guard blind" in capsys.readouterr().err


def test_hook_blocks_when_the_hook_itself_breaks(monkeypatch, capsys):
    monkeypatch.setenv("DA_WORKER", "1")
    assert guard_hook.main(io.StringIO("not json"), blind_reader) == 2


def test_on_stop_only_the_exact_note_path_may_be_written(monkeypatch, isolated_state):
    stop = lambda: usage(five=90, read_at=0)  # noqa: E731
    note = str(isolated_state / "worker_note.md")
    ok = {"tool_name": "Write", "tool_input": {"file_path": note}, "cwd": "/x"}
    assert run_hook(ok, stop, monkeypatch=monkeypatch) == 0
    sneaky = str(isolated_state / ".." / "x.md")
    for bad in (
        {"tool_name": "Write", "tool_input": {"file_path": sneaky}, "cwd": "/x"},
        {"tool_name": "Write", "tool_input": {"file_path": note + ".bak"}, "cwd": "/x"},
        {"tool_name": "Bash", "tool_input": {"command": f"echo hi > {note}"}, "cwd": "/x"},
    ):
        assert run_hook(bad, stop, monkeypatch=monkeypatch) == 2


def test_note_path_with_dotdot_that_resolves_to_the_note_is_allowed_only_if_exact(
    monkeypatch, isolated_state
):
    stop = lambda: usage(five=90, read_at=0)  # noqa: E731
    tricky = str(isolated_state / "sub" / ".." / "worker_note.md")
    p = {"tool_name": "Edit", "tool_input": {"file_path": tricky}, "cwd": "/x"}
    assert run_hook(p, stop, monkeypatch=monkeypatch) == 0  # resolves to the exact note


def test_settings_json_registers_the_hook_for_every_tool():
    cfg = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    groups = cfg["hooks"]["PreToolUse"]
    assert any("guard_hook.py" in h["command"] for g_ in groups for h in g_["hooks"])
    assert all("matcher" not in g_ for g_ in groups if "guard_hook" in json.dumps(g_))


def test_hook_script_runs_as_a_real_process_and_is_silent_outside_a_worker(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "DA_STATE_DIR": str(tmp_path)}
    run = subprocess.run(
        [sys.executable, str(ROOT / "ops" / "guard_hook.py")],
        input=json.dumps(bash()), capture_output=True, text=True, env=env,
    )
    assert run.returncode == 0 and run.stderr == ""


# ---- review round 1, Must fix 1: bad numbers must never mean GO ----

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 100.5])
def test_garbled_numbers_in_the_reply_are_blind(bad):
    body = {"five_hour": {"used_percentage": bad}, "seven_day": {"used_percentage": 10}}
    with pytest.raises(g.GuardBlind):
        g.parse_usage_response(body, NOW)
    body = {"five_hour": {"used_percentage": 10}, "seven_day": {"used_percentage": bad}}
    with pytest.raises(g.GuardBlind):
        g.parse_usage_response(body, NOW)


@pytest.mark.parametrize("field", ["five_hour", "weekly", "read_at"])
def test_a_tampered_state_file_is_blind_not_go(isolated_state, field):
    data = dict(five_hour=10, weekly=10, five_hour_resets_at=None, weekly_resets_at=None,
                read_at=NOW)
    for bad in ("NaN", "-5", "250", "Infinity"):
        data[field] = float(bad)
        isolated_state.mkdir(parents=True, exist_ok=True)
        (isolated_state / "usage.json").write_text(json.dumps(data), encoding="utf-8")
        if field != "read_at" or bad in ("NaN", "Infinity"):
            assert g.read_state() is None
        # in every case a reader that fails means blind, never GO
        assert g.get_usage(blind_reader, now=NOW) is None


def test_decide_cannot_return_go_for_nan_even_if_built_by_hand():
    with pytest.raises(ValueError):
        g.Usage(float("nan"), float("nan"), None, None, NOW)


def test_a_json_true_is_not_read_as_one_percent():
    body = {"five_hour": {"used_percentage": True}, "seven_day": {"used_percentage": 10}}
    with pytest.raises(g.GuardBlind):
        g.parse_usage_response(body, NOW)
