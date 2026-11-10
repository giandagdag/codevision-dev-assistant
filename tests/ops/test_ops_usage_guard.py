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

def test_weekly_94_is_go_and_95_is_stop():  # fix 5: the line moved from 80 to 95
    assert g.decide(usage(weekly=94)).go
    d = g.decide(usage(weekly=95))
    assert not d.go and d.reason.startswith("weekly 95%, resets ")


def test_five_hour_84_is_go_and_85_is_stop():
    assert g.decide(usage(five=84)).go
    d = g.decide(usage(five=85))
    assert not d.go and d.reason.startswith("5-hour 85%")


def test_stopped_line_matches_ac1_and_shows_singapore_time():
    d = g.decide(usage(weekly=96))
    line = g.stopped_line(d)
    assert line.startswith("Stopped: weekly 96%, resets ")
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

def test_parse_accepts_status_line_names_and_rejects_other_shapes():
    body = {
        "five_hour": {"used_percentage": 12.5, "resets_at": NOW},
        "seven_day": {"used_percentage": 40, "resets_at": NOW + 5},
    }
    u = g.parse_usage_response(body, NOW)
    assert (u.five_hour, u.weekly, u.weekly_resets_at) == (12.5, 40.0, NOW + 5)
    with pytest.raises(g.GuardBlind):
        g.parse_usage_response({"something": "else"}, NOW)


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


# ---- the real reader (Gian, 6 Nov): oauth usage endpoint, no network in tests ----

SECRET = "sk-test-SECRET-TOKEN-123"
GOOD_A = {"five_hour": {"used_percentage": 12.5, "resets_at": NOW},
          "seven_day": {"used_percentage": 40, "resets_at": NOW + 5}}
GOOD_B = {"five_hour": {"utilization": 12.5, "resets_at": "2027-01-15T09:00:00+00:00"},
          "seven_day": {"utilization": 40.0, "resets_at": "2027-01-20T00:00:00Z"}}


class FakeReply:
    def __init__(self, body):
        self._body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


@pytest.fixture
def creds(tmp_path, monkeypatch):
    f = tmp_path / ".credentials.json"
    f.write_text(json.dumps({"claudeAiOauth": {"accessToken": SECRET}}), encoding="utf-8")
    monkeypatch.setenv("DA_CREDENTIALS_FILE", str(f))
    monkeypatch.delenv("DA_USAGE_URL", raising=False)
    monkeypatch.delenv("DA_USAGE_REFRESHING", raising=False)
    return f


def unauthorized(url="x"):
    import urllib.error
    return urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)


def fake_urlopen(monkeypatch, *answers):
    """Each call returns/raises the next answer. Records the requests."""
    seen = []
    queue = list(answers)

    def opener(request, timeout):
        seen.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeReply(answer)

    monkeypatch.setattr(g.urllib.request, "urlopen", opener)
    return seen


def test_default_url_header_and_token_are_used(creds, monkeypatch):
    seen = fake_urlopen(monkeypatch, GOOD_A)
    usage_ = g.endpoint_reader()
    req = seen[0]
    assert req.full_url == "https://api.anthropic.com/api/oauth/usage"
    assert req.get_method() == "GET"
    assert req.get_header("Anthropic-beta") == "oauth-2025-04-20"
    assert req.get_header("Authorization") == f"Bearer {SECRET}"
    assert (usage_.five_hour, usage_.weekly) == (12.5, 40.0)


def test_both_reply_shapes_are_understood(creds, monkeypatch):
    fake_urlopen(monkeypatch, GOOD_B)
    u = g.endpoint_reader()
    assert (u.five_hour, u.weekly) == (12.5, 40.0)
    assert u.five_hour_resets_at == 1_800_003_600.0  # 2027-01-15 09:00 UTC (checked with datetime)


def test_unknown_shape_or_bad_numbers_are_blind(creds, monkeypatch):
    for body in ({"five_hour": {"pct": 5}, "seven_day": {"pct": 5}}, {},
                 {"five_hour": {"utilization": float("nan")}, "seven_day": {"utilization": 1}}):
        fake_urlopen(monkeypatch, body)
        with pytest.raises(g.GuardBlind):
            g.endpoint_reader()


def test_the_credentials_file_is_only_read_never_written(creds, monkeypatch):
    before = (creds.read_bytes(), creds.stat().st_mtime_ns)
    fake_urlopen(monkeypatch, GOOD_A)
    g.endpoint_reader()
    assert (creds.read_bytes(), creds.stat().st_mtime_ns) == before


@pytest.mark.parametrize("content", [None, "not json", "{}", '{"claudeAiOauth": {}}'])
def test_missing_or_odd_credentials_are_blind_without_a_network_call(
    tmp_path, monkeypatch, content
):
    f = tmp_path / "c.json"
    if content is not None:
        f.write_text(content, encoding="utf-8")
    monkeypatch.setenv("DA_CREDENTIALS_FILE", str(f))
    seen = fake_urlopen(monkeypatch)
    with pytest.raises(g.GuardBlind):
        g.endpoint_reader()
    assert seen == []


def test_http_401_runs_claude_usage_once_then_retries_with_the_new_token(creds, monkeypatch):
    runs = []

    def refresh():
        runs.append(1)
        creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "NEW-TOKEN"}}),
                         encoding="utf-8")

    monkeypatch.setattr(g, "refresh_login", refresh)
    seen = fake_urlopen(monkeypatch, unauthorized(), GOOD_A)
    assert g.endpoint_reader().weekly == 40.0
    assert runs == [1]
    assert seen[1].get_header("Authorization") == "Bearer NEW-TOKEN"


def test_a_second_401_is_blind_and_claude_is_run_only_once(creds, monkeypatch):
    runs = []
    monkeypatch.setattr(g, "refresh_login", lambda: runs.append(1))
    seen = fake_urlopen(monkeypatch, unauthorized(), unauthorized())
    with pytest.raises(g.GuardBlind, match="still refused"):
        g.endpoint_reader()
    assert runs == [1] and len(seen) == 2


def test_other_http_errors_do_not_trigger_a_refresh(creds, monkeypatch):
    import urllib.error
    monkeypatch.setattr(g, "refresh_login", lambda: pytest.fail("must not refresh"))
    fake_urlopen(monkeypatch, urllib.error.HTTPError("x", 500, "boom", {}, None))
    with pytest.raises(g.GuardBlind, match="did not answer"):
        g.endpoint_reader()


def test_refresh_runs_claude_p_usage_without_the_worker_variable(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["env"] = cmd, kwargs["env"]

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setenv("DA_WORKER", "1")
    monkeypatch.setattr(g.subprocess, "run", fake_run)
    g.refresh_login()
    assert seen["cmd"] == ["claude", "-p", "/usage"]
    # no DA_WORKER, so the child claude's own hooks do nothing (no loop back into this guard)
    assert "DA_WORKER" not in seen["env"] and seen["env"]["DA_USAGE_REFRESHING"] == "1"


def test_refresh_refuses_to_nest_and_a_missing_claude_is_blind(monkeypatch):
    monkeypatch.setenv("DA_USAGE_REFRESHING", "1")
    with pytest.raises(g.GuardBlind, match="already refreshing"):
        g.refresh_login()
    monkeypatch.delenv("DA_USAGE_REFRESHING")

    def missing(cmd, **kw):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(g.subprocess, "run", missing)
    with pytest.raises(g.GuardBlind, match="could not run claude"):
        g.refresh_login()


def test_nothing_in_any_error_contains_the_token(creds, monkeypatch):
    monkeypatch.setattr(g, "refresh_login", lambda: None)
    for answers in ([OSError(f"x {SECRET}")], [unauthorized(), unauthorized()],
                    [ValueError(SECRET)]):
        fake_urlopen(monkeypatch, *answers)
        with pytest.raises(g.GuardBlind) as err:
            g.endpoint_reader()
        assert SECRET not in str(err.value)


def test_plain_http_override_is_refused(creds, monkeypatch):
    monkeypatch.setenv("DA_USAGE_URL", "http://example.invalid/usage")
    with pytest.raises(g.GuardBlind, match="https"):
        g.endpoint_reader()


# ---- Gian, 6 Nov (3rd batch): raw reply saved on every read; bad values are blind ----

def raw_file(isolated_state):
    return isolated_state / "usage_raw.json"


def test_the_raw_reply_is_saved_on_a_good_read(creds, monkeypatch, isolated_state):
    fake_urlopen(monkeypatch, GOOD_A)
    g.endpoint_reader()
    assert json.loads(raw_file(isolated_state).read_text(encoding="utf-8")) == GOOD_A


def test_the_raw_reply_is_saved_even_when_the_shape_is_unknown(creds, monkeypatch, isolated_state):
    limits_layout = {"limits": [{"name": "five_hour", "utilization": 3}]}
    fake_urlopen(monkeypatch, limits_layout)
    with pytest.raises(g.GuardBlind):  # an unconfirmed layout is blind, never a guess
        g.endpoint_reader()
    assert json.loads(raw_file(isolated_state).read_text(encoding="utf-8")) == limits_layout


def test_the_raw_file_is_overwritten_each_run_and_is_git_ignored(
    creds, monkeypatch, isolated_state
):
    fake_urlopen(monkeypatch, GOOD_A, GOOD_B)
    g.endpoint_reader()
    g.endpoint_reader()
    assert json.loads(raw_file(isolated_state).read_text(encoding="utf-8")) == GOOD_B
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "ops/state/" in ignore.splitlines()


def test_a_save_problem_never_stops_the_guard_or_loses_the_answer(creds, monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x")
    monkeypatch.setenv("DA_STATE_DIR", str(blocker / "sub"))  # cannot be created
    fake_urlopen(monkeypatch, GOOD_A)
    assert g.endpoint_reader().weekly == 40.0


@pytest.mark.parametrize("bad", [None, "", "12", [], {}, 101, -0.5, 100.01, float("inf")])
def test_a_missing_or_out_of_range_value_is_blind(creds, monkeypatch, bad):
    for key in ("used_percentage", "utilization"):
        body = {"five_hour": {key: bad}, "seven_day": {key: 10}}
        fake_urlopen(monkeypatch, body)
        with pytest.raises(g.GuardBlind):
            g.endpoint_reader()
    body = {"five_hour": {"utilization": 10}, "seven_day": {}}
    fake_urlopen(monkeypatch, body)
    with pytest.raises(g.GuardBlind):
        g.endpoint_reader()


@pytest.mark.parametrize("edge", [0, 0.0, 100, 100.0])
def test_the_edges_0_and_100_are_valid(creds, monkeypatch, edge):
    fake_urlopen(monkeypatch, {"five_hour": {"utilization": edge},
                               "seven_day": {"utilization": edge}})
    assert g.endpoint_reader().weekly == float(edge)


# ---- usage credits (Phase A fix 5) ----

def credits(weekly=96.0, five=10.0, on=True, used=0.0, limit=50.0):
    return g.Usage(five, weekly, NOW + 3600, NOW + 86400, NOW, on, used, limit)


def extra(**changes):
    base = {"is_enabled": True, "monthly_limit": 5000, "used_credits": 0.0,
            "currency": "USD", "decimal_places": 2, "disabled_reason": None,
            "user_disabled": False, "spend_limit_reached": False}
    base.update(changes)
    return {"five_hour": {"utilization": 2.0, "resets_at": "2026-11-10T07:19:59+00:00"},
            "seven_day": {"utilization": 96.0, "resets_at": "2026-11-12T10:59:59+00:00"},
            "extra_usage": base}


def test_past_the_weekly_line_credits_under_the_cap_are_go():
    d = g.decide(credits(used=12.5))
    assert d.go and d.reason == "on usage credits: weekly 96%, $12.50 of $50 spent"


def test_credits_off_or_at_a_cap_are_stop_with_the_weekly_reason():
    for u in (credits(on=False), credits(used=50.0), credits(used=20.0, limit=20.0)):
        d = g.decide(u)
        assert not d.go and d.reason.startswith("weekly 96%, resets ")


def test_credits_do_not_override_the_five_hour_line():
    d = g.decide(credits(five=85))
    assert not d.go and d.reason.startswith("5-hour 85%")


def test_below_the_weekly_line_credits_change_nothing():
    assert g.decide(credits(weekly=50)).reason == "within the usage lines"


def test_parse_reads_credits_in_cents():
    u = g.parse_usage_response(extra(used_credits=1234), NOW)
    assert (u.credits_on, u.credits_used, u.credits_limit) == (True, 12.34, 50.0)
    assert g.decide(u).go


def test_parse_real_10_nov_reply_out_of_credits_is_stop():
    body = extra(is_enabled=False, disabled_reason="out_of_credits")
    u = g.parse_usage_response(body, NOW)
    assert u.credits_on is False and not g.decide(u).go


@pytest.mark.parametrize("change", [
    {"spend_limit_reached": True}, {"user_disabled": True}, {"is_enabled": "yes"},
    {"currency": "SGD"}, {"decimal_places": "2"}, {"used_credits": "1"},
    {"used_credits": float("nan")}, {"used_credits": -5}, {"monthly_limit": True},
    {"used_credits": None}, {"decimal_places": None}, {"currency": None},
    {"used_credits": 10 ** 400}, {"monthly_limit": 10 ** 400},
])
def test_odd_credit_parts_mean_no_credits_never_blind(change):
    u = g.parse_usage_response(extra(**change), NOW)
    assert u.weekly == 96.0 and not g.decide(u).go


def test_no_extra_usage_part_means_no_credits():
    body = extra()
    body.pop("extra_usage")
    assert g.parse_usage_response(body, NOW).credits_on is False
    body["extra_usage"] = "on"
    assert g.parse_usage_response(body, NOW).credits_on is False


def test_state_file_keeps_the_credit_fields_and_old_files_still_load(isolated_state):
    g.write_state(credits(used=3.0))
    assert g.read_state().credits_used == 3.0 and g.read_state().credits_on is True
    old = {"five_hour": 1, "weekly": 2, "five_hour_resets_at": None,
           "weekly_resets_at": None, "read_at": NOW}
    (isolated_state / "usage.json").write_text(json.dumps(old))
    assert g.read_state().credits_on is False


@pytest.mark.parametrize("bad", [{"credits_on": 1}, {"credits_used": float("inf")},
                                 {"credits_limit": -1.0}, {"credits_used": True}])
def test_bad_credit_fields_cannot_be_built(bad):
    args = {"five_hour": 1.0, "weekly": 99.0, "five_hour_resets_at": None,
            "weekly_resets_at": None, "read_at": NOW, **bad}
    with pytest.raises(ValueError):
        g.Usage(**args)


@pytest.mark.parametrize("key", ["used_credits", "decimal_places", "currency"])
def test_review_fix_a_missing_spend_unit_or_currency_means_no_credits(key):
    body = extra()
    body["extra_usage"].pop(key)
    u = g.parse_usage_response(body, NOW)
    assert u.credits_on is False and not g.decide(u).go


def test_review_fix_a_huge_number_never_crashes(isolated_state):
    body = extra()
    body["seven_day"]["utilization"] = 10 ** 400
    with pytest.raises(g.GuardBlind):
        g.parse_usage_response(body, NOW)
    isolated_state.mkdir(parents=True)
    huge = {"five_hour": 1, "weekly": 2, "five_hour_resets_at": None, "weekly_resets_at": None,
            "read_at": NOW, "credits_on": True, "credits_used": 10 ** 400}
    (isolated_state / "usage.json").write_text(json.dumps(huge))
    assert g.read_state() is None
