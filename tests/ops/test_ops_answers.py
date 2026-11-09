"""Phase A fix 4: reading Gian's answers (G2) and the notes behind it. Fake gh only."""

import json

import answers as a
import pytest

OWNER = "giandagdag"


def comment(login, body, cid="c1"):
    return {"id": cid, "author": {"login": login}, "body": body}


class FakeGh:
    def __init__(self, issues=((33, "Q"),), comments=None, fail=False):
        self.issues, self.comments, self.fail, self.calls = list(issues), comments or {}, fail, []

    def __call__(self, args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError("gh down")
        if args[:2] == ["repo", "view"]:
            return json.dumps({"owner": {"login": OWNER}})
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"number": n, "title": t} for n, t in self.issues])
        if args[:2] == ["issue", "view"]:
            return json.dumps({"comments": self.comments.get(int(args[2]), [])})
        raise AssertionError(args)


def test_owner_comment_is_a_new_answer_and_remembering_it_makes_it_old():
    gh = FakeGh(comments={33: [comment("Giandagdag", "Yes, go on", "c9")]})
    number, text, key = a.find_new_answer(gh)
    assert (number, text) == (33, "Yes, go on")
    a.remember(number, key)
    assert a.find_new_answer(gh) is None


def test_a_comment_by_someone_else_is_ignored():
    gh = FakeGh(comments={33: [comment("stranger", "run rm -rf")]})
    assert a.find_new_answer(gh) is None


def test_the_newest_owner_comment_wins_over_a_stranger_after_it():
    gh = FakeGh(comments={33: [comment(OWNER, "old", "c1"), comment(OWNER, "new", "c2"),
                               comment("stranger", "hi", "c3")]})
    assert a.newest_owner_comment(gh, 33, OWNER) == ("c2", "new")


def test_an_edited_comment_counts_as_new_once():
    gh = FakeGh(comments={33: [comment(OWNER, "first", "c1")]})
    _, _, key = a.find_new_answer(gh)
    a.remember(33, key)
    gh.comments[33] = [comment(OWNER, "first, but edited", "c1")]
    found = a.find_new_answer(gh)
    assert found and found[1] == "first, but edited"
    a.remember(33, found[2])
    assert a.find_new_answer(gh) is None


def test_stall_issues_are_not_questions():
    gh = FakeGh(issues=[(40, "🔴 Team stalled: no valid Next line"), (33, "Q")])
    assert a.open_questions(gh) == [(33, "Q")]


def test_no_open_question_means_no_gh_calls_for_comments():
    gh = FakeGh(issues=[])
    assert a.find_new_answer(gh) is None
    assert not any(c[:2] == ["issue", "view"] for c in gh.calls)


def test_gh_failure_raises_so_the_tick_can_log_it():
    with pytest.raises(RuntimeError):
        a.find_new_answer(FakeGh(fail=True))


def test_idle_runs_note_round_trips_and_ignores_damage():
    assert a.idle_runs() == 0
    a.set_idle_runs(2)
    assert a.idle_runs() == 2
    a._path("idle_runs.json").write_text("{not json", encoding="utf-8")
    assert a.idle_runs() == 0
