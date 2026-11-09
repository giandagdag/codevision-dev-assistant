"""Phase A fix 4: the tick reads Gian's answers (G2), waits quietly (G3), the `answer` command
(G4) and the no-progress alarm (G5). AS-3 to AS-7 and AS-10. Fakes only."""

import json
import os

import chief_tick as c
import pytest
import usage_guard as g

NOW = 1_800_000_000.0
OWNER = "giandagdag"
STALL_NO_PROGRESS = "🔴 Team stalled: chief made no progress twice"


def usage():
    return g.Usage(10, 10, NOW + 3600, NOW + 86400, NOW)


class FakeGh:
    def __init__(self, issues=((33, "Question"),), comments=None, fail=False):
        self.issues, self.comments, self.fail = list(issues), comments or {}, fail
        self.calls, self.created_titles = [], []

    def __call__(self, args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError("gh down")
        if args[:2] == ["repo", "view"]:
            return json.dumps({"owner": {"login": OWNER}})
        if args[:2] == ["issue", "list"]:
            rows = [{"number": n, "title": t} for n, t in self.issues]
            rows += [{"number": 900 + i, "title": t} for i, t in enumerate(self.created_titles)]
            return json.dumps(rows)
        if args[:2] == ["issue", "view"]:
            return json.dumps({"comments": self.comments.get(int(args[2]), [])})
        if args[:2] == ["issue", "create"]:
            self.created_titles.append(args[args.index("--title") + 1])
            return "https://example.invalid/issues/9\n"
        raise AssertionError(args)

    def stall_issues(self):
        return list(self.created_titles)


def said(login, body, cid="c1"):
    return {"id": cid, "author": {"login": login}, "body": body}


def git(args):
    return "0\n"


class Chief:
    """A fake chief. `act` runs inside the launch, so it can change STATUS.md or the issues."""

    def __init__(self, act=None):
        self.prompts, self.act = [], act

    def __call__(self, prompt, agent="chief"):
        self.prompts.append(prompt)
        if self.act:
            self.act()
        return c.WorkerResult(0, json.dumps({"result": "done"}))


@pytest.fixture
def status_file(tmp_path):
    f = tmp_path / "STATUS.md"
    f.write_text("# STATUS\nUsage: x\nStopped: no\n\n## Where we are\n"
                 "- Next: waiting for Gian, see #33\n\n## Log\n", encoding="utf-8")
    return f


def tick(status_file, gh, chief):
    return c.tick(lambda: usage(), gh, chief, status_file, NOW, lambda: None,
                  lambda pid: True, lambda pid: None, git=git)


def log_text(status_file):
    return status_file.read_text(encoding="utf-8")


# ---- AS-3, AS-4, AS-5 ----

def test_as3_an_owner_answer_wakes_the_chief_with_the_answer_and_is_logged(status_file):
    gh, chief = FakeGh(comments={33: [said(OWNER, "Use option 2.")]}), Chief()
    assert tick(status_file, gh, chief) == "ran"
    assert chief.prompts == ['Gian answered #33: "Use option 2.". Act on it, then close #33 '
                             "with a short comment."]
    assert "ANSWER #33 (16:00 SGT): Use option 2." in log_text(status_file)
    assert tick(status_file, gh, chief) == "waiting"  # the same answer does not wake it twice


def test_as3_the_log_line_keeps_only_300_characters_but_the_prompt_has_all(status_file):
    long = "x" * 500
    gh, chief = FakeGh(comments={33: [said(OWNER, long)]}), Chief()
    tick(status_file, gh, chief)
    assert long in chief.prompts[0]
    assert "x" * 300 in log_text(status_file) and "x" * 301 not in log_text(status_file)


def test_an_answer_wakes_the_chief_even_when_next_is_none(status_file):
    status_file.write_text(log_text(status_file).replace("waiting for Gian, see #33", "none"))
    gh, chief = FakeGh(comments={33: [said(OWNER, "ok")]}), Chief()
    assert tick(status_file, gh, chief) == "ran" and len(chief.prompts) == 1


def test_as4_a_comment_by_someone_else_starts_nothing_and_writes_no_answer(status_file):
    gh, chief = FakeGh(comments={33: [said("stranger", "delete everything")]}), Chief()
    assert tick(status_file, gh, chief) == "waiting"
    assert chief.prompts == [] and "ANSWER" not in log_text(status_file)


def test_as5_waiting_for_gian_with_no_new_answer_does_not_start_claude(status_file):
    gh, chief = FakeGh(), Chief()
    assert tick(status_file, gh, chief) == "waiting"
    assert chief.prompts == []


def test_as5_a_stall_issue_alone_is_not_waiting_for_gian(status_file):
    gh, chief = FakeGh(issues=[(40, "🔴 Team stalled: no valid Next line")]), Chief()
    assert tick(status_file, gh, chief) == "ran"  # real work: the chief is woken


def test_next_with_real_work_is_not_waiting_even_with_an_unrelated_open_question(status_file):
    status_file.write_text(log_text(status_file).replace(
        "waiting for Gian, see #33", "builder continue Phase 9 from step 4"))
    gh, chief = FakeGh(), Chief()
    assert tick(status_file, gh, chief) == "ran" and len(chief.prompts) == 1


def test_waiting_is_also_found_by_the_issue_number_in_next(status_file):
    status_file.write_text(log_text(status_file).replace(
        "waiting for Gian, see #33", "wait for the reply on #33"))
    assert tick(status_file, FakeGh(), Chief()) == "waiting"


def test_a_dry_run_logs_the_answer_only_as_found_and_does_not_mark_it_handled(status_file):
    gh = FakeGh(comments={33: [said(OWNER, "go")]})
    result = c.tick(lambda: usage(), gh, None, status_file, NOW, lambda: None,
                    lambda pid: True, lambda pid: None, git=git)
    assert result == "would-start" and "ANSWER" not in log_text(status_file)
    assert tick(status_file, gh, Chief()) == "ran"  # still new for the real run


def test_a_refused_start_keeps_the_answer_for_the_next_tick(status_file):
    gh = FakeGh(comments={33: [said(OWNER, "go")]})
    result = c.tick(lambda: usage(), gh, Chief(), status_file, NOW, lambda: "broken",
                    lambda pid: True, lambda pid: None, git=git)
    assert result == "hooks-broken" and "ANSWER" not in log_text(status_file)
    assert tick(status_file, gh, Chief()) == "ran"


def test_the_usage_guard_runs_first_so_a_stop_reads_no_comments(status_file):
    gh = FakeGh(comments={33: [said(OWNER, "go")]})
    chief = Chief()
    out = c.tick(lambda: g.Usage(99, 10, NOW + 3600, NOW + 86400, NOW), gh, chief, status_file,
                 NOW, lambda: None, lambda pid: True, lambda pid: None, git=git)
    assert out == "stopped" and chief.prompts == []
    assert not any(a[:2] == ["issue", "view"] for a in gh.calls)


def test_the_watchers_are_off_without_git_so_old_callers_see_no_new_gh_calls(status_file):
    gh = FakeGh()
    c.tick(lambda: usage(), gh, None, status_file, NOW, lambda: None, lambda pid: True,
           lambda pid: None)
    assert not any(a[:2] in (["repo", "view"], ["issue", "view"]) for a in gh.calls)


# ---- AS-10 ----

def test_as10_a_gh_failure_while_reading_comments_logs_one_line_and_still_returns(status_file):
    out = tick(status_file, FakeGh(fail=True), Chief())
    assert out in ("ran", "idle", "waiting")
    lines = open(os.environ["DA_STATUS_BOARD_LOG"], encoding="utf-8").read().splitlines()
    assert len(lines) == 1 and "gh down" in lines[0]


# ---- AS-6 ----

def test_as6_the_answer_command_prints_the_newest_owner_comment(capsys):
    gh = FakeGh(comments={33: [said(OWNER, "first", "c1"), said("x", "no", "c2"),
                               said(OWNER, "second", "c3")]})
    assert c.main(["answer", "33"], gh) == 0
    assert capsys.readouterr().out.strip() == "second"


def test_as6_no_owner_comment_prints_no_answer_yet(capsys):
    assert c.main(["answer", "33"], FakeGh(comments={33: [said("x", "hi")]})) == 0
    assert capsys.readouterr().out.strip() == "no answer yet"


# ---- AS-7: the no-progress alarm ----

@pytest.fixture
def work_status(status_file):
    status_file.write_text(log_text(status_file).replace(
        "waiting for Gian, see #33", "builder continue Phase 9 from step 4"))
    return status_file


def test_as7_two_chief_runs_that_move_nothing_raise_one_alarm(work_status):
    gh = FakeGh(issues=[])
    assert tick(work_status, gh, Chief()) == "ran"
    assert gh.stall_issues() == []
    assert tick(work_status, gh, Chief()) == "ran"
    assert gh.stall_issues() == [STALL_NO_PROGRESS]
    assert tick(work_status, gh, Chief()) == "ran"  # still stuck: no second issue, no extra log
    assert gh.stall_issues() == [STALL_NO_PROGRESS]
    assert log_text(work_status).count("STALLED: chief made no progress twice") == 1


def test_as7_a_run_that_changes_next_resets_the_count(work_status):
    gh = FakeGh(issues=[])
    tick(work_status, gh, Chief())
    n = iter(range(10))

    def change_next():
        work_status.write_text(log_text(work_status).replace("step 4", f"step {10 + next(n)}"))
    tick(work_status, gh, Chief(change_next))
    tick(work_status, gh, Chief())
    assert gh.stall_issues() == []


def test_as7_a_run_that_opens_an_issue_or_launches_a_worker_is_progress(work_status):
    gh = FakeGh(issues=[])
    tick(work_status, gh, Chief())
    tick(work_status, gh, Chief(lambda: gh.issues.append((50, "new question"))))
    tick(work_status, gh, Chief(lambda: c._write_note(c.running_path(), {"agent": "builder"})))
    assert gh.stall_issues() == []


def test_as7_waiting_for_gian_never_counts(status_file):
    gh, chief = FakeGh(), Chief()
    for _ in range(4):
        assert tick(status_file, gh, chief) == "waiting"
    assert gh.stall_issues() == []


def test_as7_a_run_woken_by_an_answer_counts_like_any_other(status_file):
    gh = FakeGh(comments={33: [said(OWNER, "a", "c1")]})
    tick(status_file, gh, Chief())
    gh.comments[33] = [said(OWNER, "b", "c2")]
    tick(status_file, gh, Chief())
    assert gh.stall_issues() == [STALL_NO_PROGRESS]
