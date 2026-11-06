import json

import chief_tick as c
import pytest
import usage_guard as g

NOW = 1_800_000_000.0


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


def no_launch(prompt):
    raise AssertionError("no worker may start")


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

    def launcher(prompt):
        (isolated / "state").mkdir(exist_ok=True)
        (isolated / "state" / "worker_note.md").write_text("stopped at step 3", encoding="utf-8")
        return c.WorkerResult(0, json.dumps({"total_cost_usd": 0.5,
                                             "usage": {"input_tokens": 9, "output_tokens": 3}}))

    assert c.tick(reader, FakeGh(), launcher, status_file, NOW) == "ran"
    rows = (isolated / "ledger.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2  # header plus ONE line (AC-7)
    assert ",chief,sonnet,10,20,10,12,9,3,0.5,ok (worker saved a note)" in rows[1]
    assert "stopped at step 3" in status_file.read_text(encoding="utf-8")


def test_failed_worker_still_gets_a_ledger_line(status_file, isolated):
    c.tick(lambda: usage(), FakeGh(), lambda p: c.WorkerResult(1, ""), status_file, NOW)
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
    c.real_launcher("hi")
    assert seen["env"]["DA_WORKER"] == "1"


def test_main_refuses_a_bad_merge_with_a_plain_message(capsys):
    gh = FakeGh(pr=pr("main", GREEN))
    assert c.main(["merge", "--pr", "7"], gh) == 1
    assert "Refused: PR 7 targets main, and the chief only merges" in capsys.readouterr().err
    assert gh.merged() == []
