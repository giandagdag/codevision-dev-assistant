"""Phase A fix 3: the unpushed check (F3, AS-4) and the stall alarm (F1, AS-1 to AS-3, AS-10).
Fake gh and fake git only."""

import json
import os

import chief_tick as c
import pytest
import stall
import usage_guard as g

NOW = 1_800_000_000.0
TITLE_NO_NEXT = "🔴 Team stalled: no valid Next line"
TITLE_NOT_DONE = "🔴 Team stalled: nothing to do, but the job is not finished"


def usage():
    return g.Usage(10, 10, NOW + 3600, NOW + 86400, NOW)


class FakeGh:
    def __init__(self, open_titles=(), prs=(), fail=False):
        self.calls, self.titles, self.prs, self.fail = [], list(open_titles), list(prs), fail

    def __call__(self, args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError("gh down")
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"title": t} for t in self.titles])
        if args[:2] == ["pr", "list"]:
            return json.dumps([{"number": n} for n in self.prs])
        return "https://example.invalid/issues/9\n"

    def created(self):
        return [a for a in self.calls if a[:2] == ["issue", "create"]]


class FakeGit:
    """`git rev-list --count origin/X..X` answers from a dict; anything else fails."""

    def __init__(self, ahead=None, fail=False):
        self.ahead, self.fail, self.calls = ahead or {}, fail, []

    def __call__(self, args):
        self.calls.append(args)
        if self.fail or args[:2] != ["rev-list", "--count"]:
            raise RuntimeError("git failed")
        branch = args[2].split("..")[1]
        if branch not in self.ahead:
            raise RuntimeError("unknown branch")
        return f"{self.ahead[branch]}\n"


def status_with(path, body):
    path.write_text(body, encoding="utf-8")
    return path


def idle_status(tmp_path, next_line="- Next: none"):
    body = "# S\nUsage: x\n## Where we are\n" + (next_line + "\n" if next_line else "") + "## Log\n"
    return status_with(tmp_path / "STATUS.md", body)


def tick(status_file, gh, git, board=None):
    return c.tick(usage, gh, None, status_file, NOW, board=board, git=git)


def log_text(status_file):
    return status_file.read_text(encoding="utf-8")


# ---- F3: the unpushed check ----

def running(**over):
    data = {"agent": "builder", "stage": "build", "phase": "8", "prompt": "p", "pid": 4242,
            "started": NOW - 10, "five_hour_before": 10, "weekly_before": 11}
    c._write_note(c.running_path(), {**data, **over})


def done():
    c._write_note(c.done_path(), {"agent": "builder", "exit_code": 0, "crash": "",
                                  "finished": NOW - 5, "reply_file": "", "stdout": "{}",
                                  "stderr": ""})


def queue(status_file, git, alive=lambda pid: False):
    return c.check_queue(usage, status_file, NOW, alive, lambda pid: None, git)


def test_as4_a_finished_builder_with_two_unpushed_commits_is_logged(tmp_path):
    f = idle_status(tmp_path)
    running(), done()
    assert queue(f, FakeGit({"auto/phase-8": 2})) is None
    assert "UNPUSHED: 2 commits on auto/phase-8" in log_text(f)
    assert stall.current_unpushed(FakeGit({"auto/phase-8": 2})) == ("auto/phase-8", 2)


def test_one_unpushed_commit_is_singular(tmp_path):
    f = idle_status(tmp_path)
    running(), done()
    queue(f, FakeGit({"auto/phase-8": 1}))
    assert "UNPUSHED: 1 commit on auto/phase-8" in log_text(f)


def test_a_pushed_branch_logs_nothing_and_forgets_an_old_warning(tmp_path):
    f = idle_status(tmp_path)
    stall.remember_unpushed("auto/phase-8")
    running(), done()
    queue(f, FakeGit({"auto/phase-8": 0}))
    assert "UNPUSHED" not in log_text(f) and stall.current_unpushed(FakeGit()) is None


@pytest.mark.parametrize("kind", ["vanished", "over-time"])
def test_vanished_and_over_time_workers_are_checked_too(tmp_path, kind):
    f = idle_status(tmp_path)
    if kind == "vanished":
        running()
        queue(f, FakeGit({"auto/phase-8": 3}))
    else:
        running(started=NOW - 7 * 3600)
        queue(f, FakeGit({"auto/phase-8": 3}), alive=lambda pid: True)
    assert "UNPUSHED: 3 commits on auto/phase-8" in log_text(f)


def test_a_worker_without_a_phase_or_without_git_is_not_checked(tmp_path):
    f = idle_status(tmp_path)
    git = FakeGit({"auto/phase-8": 2})
    running(phase=""), done()
    queue(f, git)
    running(), done()
    queue(f, None)
    assert git.calls == [] and "UNPUSHED" not in log_text(f)


def test_a_git_problem_is_one_board_log_line_and_no_unpushed_line(tmp_path):
    f = idle_status(tmp_path)
    running(), done()
    queue(f, FakeGit(fail=True))
    lines = open(os.environ["DA_STATUS_BOARD_LOG"], encoding="utf-8").read().splitlines()
    assert len(lines) == 1 and "RuntimeError" in lines[0]
    assert "UNPUSHED" not in log_text(f)


# ---- F1: the stall alarm ----

def test_as1_no_next_line_opens_one_needs_gian_issue_and_one_log_line(tmp_path):
    f, gh = idle_status(tmp_path, next_line=""), FakeGh()
    assert tick(f, gh, FakeGit()) == "idle"
    assert len(gh.created()) == 1
    args = gh.created()[0]
    assert args[args.index("--title") + 1] == TITLE_NO_NEXT
    assert args[args.index("--label") + 1] == "needs-gian"
    assert f"STALLED: {stall.NO_NEXT}" in log_text(f)
    assert stall.read_stall() == stall.NO_NEXT


@pytest.mark.parametrize("first", ["- Next: none", "- Next: builder continue Phase 8 from step 10"])
def test_any_second_next_line_is_a_stall_whatever_the_first_says(tmp_path, first):
    f, gh = idle_status(tmp_path, first + "\n- Next: builder go"), FakeGh()
    assert tick(f, gh, FakeGit()) == "idle"  # not "would-start": two Next lines are no work
    assert gh.created()[0][gh.created()[0].index("--title") + 1] == TITLE_NO_NEXT
    assert not c.has_work(f.read_text(encoding="utf-8"))


def test_one_next_line_with_work_is_still_work(tmp_path):
    f = idle_status(tmp_path, "- Next: builder go")
    assert c.has_work(f.read_text(encoding="utf-8"))


def test_as2_the_same_open_issue_means_no_second_issue_and_no_second_log_line(tmp_path):
    f, gh = idle_status(tmp_path, next_line=""), FakeGh(open_titles=[TITLE_NO_NEXT])
    assert tick(f, gh, FakeGit()) == "idle"
    assert gh.created() == [] and "STALLED" not in log_text(f)
    assert stall.read_stall() == stall.NO_NEXT  # the board still shows it


def test_as3_next_none_with_an_open_needs_gian_issue_is_not_a_stall(tmp_path):
    f, gh = idle_status(tmp_path), FakeGh(open_titles=["Q: which model?"])
    assert tick(f, gh, FakeGit()) == "idle"
    assert gh.created() == [] and stall.read_stall() is None


def test_our_own_stall_issue_does_not_hide_a_case_2_stall(tmp_path):
    f, gh = idle_status(tmp_path), FakeGh(open_titles=[TITLE_NOT_DONE])
    tick(f, gh, FakeGit())
    assert stall.read_stall() == stall.NOT_FINISHED  # the only open needs-gian issue is ours
    assert gh.created() == []  # and no second one is opened
    gh2 = FakeGh(open_titles=[TITLE_NOT_DONE, "Q: which model?"])
    tick(f, gh2, FakeGit())
    assert stall.read_stall() is None  # a real question is open: waiting on purpose


def test_next_none_with_the_final_pr_open_is_finished_not_stalled(tmp_path):
    f, gh = idle_status(tmp_path), FakeGh(prs=[41])
    assert tick(f, gh, FakeGit()) == "idle"
    assert gh.created() == [] and stall.read_stall() is None


def test_next_none_with_nothing_open_is_a_stall(tmp_path):
    f, gh = idle_status(tmp_path), FakeGh()
    tick(f, gh, FakeGit())
    assert gh.created()[0][gh.created()[0].index("--title") + 1] == TITLE_NOT_DONE
    assert stall.read_stall() == stall.NOT_FINISHED


def test_unpushed_commits_are_a_stall_even_while_waiting_for_gian(tmp_path):
    f, gh = idle_status(tmp_path), FakeGh(open_titles=["Q: which model?"])
    stall.remember_unpushed("auto/phase-8")
    tick(f, gh, FakeGit({"auto/phase-8": 2}))
    assert stall.read_stall() == "unpushed commits on auto/phase-8"
    assert gh.created()[0][gh.created()[0].index("--title") + 1] == (
        "🔴 Team stalled: unpushed commits on auto/phase-8")


def test_as10_a_gh_failure_still_returns_idle_and_logs_one_line(tmp_path):
    f, gh = idle_status(tmp_path), FakeGh(fail=True)
    assert tick(f, gh, FakeGit()) == "idle"
    lines = open(os.environ["DA_STATUS_BOARD_LOG"], encoding="utf-8").read().splitlines()
    assert len(lines) == 1 and "gh down" in lines[0]
    assert "STALLED" not in log_text(f)


def test_the_note_goes_when_the_cause_is_gone_and_the_tick_never_closes_the_issue(tmp_path):
    f, gh = idle_status(tmp_path, next_line=""), FakeGh()
    tick(f, gh, FakeGit())
    assert stall.read_stall()
    idle_status(tmp_path, "- Next: none")  # a valid Next line returns
    gh2 = FakeGh(prs=[41])
    tick(f, gh2, FakeGit())
    assert stall.read_stall() is None
    assert all(a[:2] != ["issue", "close"] for a in gh.calls + gh2.calls)


def test_the_note_goes_when_the_tick_finds_work(tmp_path):
    f = idle_status(tmp_path, next_line="")
    tick(f, FakeGh(), FakeGit())
    idle_status(tmp_path, "- Next: builder continue Phase 8 from step 10")
    assert tick(f, FakeGh(), FakeGit()) == "would-start"
    assert stall.read_stall() is None


def test_a_pushed_branch_is_no_longer_a_stall(tmp_path):
    f, gh = idle_status(tmp_path), FakeGh(prs=[41])
    stall.remember_unpushed("auto/phase-8")
    tick(f, gh, FakeGit({"auto/phase-8": 0}))
    assert stall.read_stall() is None and stall.current_unpushed(FakeGit()) is None


def test_git_none_switches_the_alarm_off(tmp_path):
    f, gh = idle_status(tmp_path, next_line=""), FakeGh()
    assert tick(f, gh, None) == "idle"
    assert gh.calls == [] and stall.read_stall() is None


def test_a_git_failure_in_the_stall_check_is_logged_once_and_other_rules_still_run(tmp_path):
    f, gh = idle_status(tmp_path, next_line=""), FakeGh()
    stall.remember_unpushed("auto/phase-8")
    assert tick(f, gh, FakeGit(fail=True)) == "idle"
    lines = open(os.environ["DA_STATUS_BOARD_LOG"], encoding="utf-8").read().splitlines()
    assert len(lines) == 1
    assert len(gh.created()) == 1  # rule 1 does not need git


# ---- 20 Nov (#107): "Next: idle: <why>" is a resting state, not a stall ----

def test_next_idle_with_nothing_open_rests_without_an_alarm(tmp_path):
    line = "- Next: idle: queue empty after Fix G1, Gian picks the next job"
    f, gh = idle_status(tmp_path, line), FakeGh()
    assert tick(f, gh, FakeGit()) == "idle"
    tick(f, gh, FakeGit())
    assert gh.created() == [] and stall.read_stall() is None


def test_next_idle_still_reports_unpushed_commits(tmp_path):
    f, gh = idle_status(tmp_path, "- Next: idle: queue empty"), FakeGh()
    stall.remember_unpushed("phase-g-fix-2")
    tick(f, gh, FakeGit({"phase-g-fix-2": 1}))
    assert stall.read_stall() == "unpushed commits on phase-g-fix-2"


def test_idle_is_no_work_but_a_real_next_step_is():
    assert not c.has_work("# S\n- Next: idle: queue empty\n## Log\n")
    assert c.has_work("# S\n- Next: builder start Fix G2\n## Log\n")
