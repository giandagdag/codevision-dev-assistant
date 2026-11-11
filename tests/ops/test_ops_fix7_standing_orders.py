"""Phase A fix 7: standing orders and the non-blocking `gian-later` label. AS-1 to AS-7.

AS400 comparison: a reply list with standing answers, so a known message never sits in MSGW.
Fakes and tmp_path only (conftest sandboxes every ops path).
"""

import json
from pathlib import Path

import answers
import chief_tick as c
import pytest
import stall
import status_board as b
import usage_guard as g

from tests.ops.test_ops_fix4_answers import NOW, OWNER, Chief, git, said

ROOT = Path(__file__).resolve().parents[2]
CHIEF = (ROOT / ".claude" / "agents" / "chief.md").read_text(encoding="utf-8")
BUILDER = (ROOT / ".claude" / "agents" / "builder.md").read_text(encoding="utf-8")


class LabelGh:
    """A fake gh that knows which issue carries which label."""

    def __init__(self, issues=(), comments=None, fail_label=None):
        self.issues = list(issues)  # (number, title, label)
        self.comments, self.fail_label = comments or {}, fail_label
        self.created = []

    def __call__(self, args):
        if args[:2] == ["repo", "view"]:
            return json.dumps({"owner": {"login": OWNER}})
        if args[:2] == ["issue", "list"]:
            label = args[args.index("--label") + 1] if "--label" in args else None
            if label is not None and label == self.fail_label:
                raise RuntimeError("gh down")
            return json.dumps([{"number": n, "title": t, "url": f"https://x.invalid/{n}"}
                               for n, t, lab in self.issues if label in (None, lab)])
        if args[:2] == ["pr", "list"]:
            return "[]"  # the final PR into main is not open
        if args[:2] == ["issue", "view"]:
            return json.dumps({"comments": self.comments.get(int(args[2]), [])})
        if args[:2] == ["issue", "create"]:
            self.created.append((args[args.index("--title") + 1], args[args.index("--label") + 1]))
            return "https://x.invalid/issues/9\n"
        raise AssertionError(args)


def status(tmp_path, nxt="waiting for Gian"):
    f = tmp_path / "fix7-STATUS.md"
    f.write_text(f"# STATUS\nUsage: x\nStopped: no\n\n## Where we are\n- Next: {nxt}\n\n## Log\n",
                 encoding="utf-8")
    return f


def usage():
    return g.Usage(10, 10, NOW + 3600, NOW + 86400, NOW)


def tick(status_file, gh, chief):
    return c.tick(lambda: usage(), gh, chief, status_file, NOW, lambda: None,
                  lambda pid: True, lambda pid: None, git=git)


# ---- AS-3: the label ----

def test_as3_gian_later_issue_is_opened_with_its_label():
    gh = LabelGh()
    assert c.open_gian_issue("SO-2: Phase 8 step 1 parked", "body", "gian-later", gh)
    assert gh.created == [("SO-2: Phase 8 step 1 parked", "gian-later")]


def test_as3_an_unknown_label_is_still_refused():
    with pytest.raises(ValueError):
        c.open_gian_issue("t", "b", "please-merge", LabelGh())


# ---- AS-4, AS-6: answers and waiting ----

def test_as4_a_gian_later_issue_alone_never_makes_the_tick_wait(tmp_path):
    gh = LabelGh([(52, "SO-2: Phase 8 step 1 parked", "gian-later")])
    assert not c.waiting_for_gian(status(tmp_path).read_text(encoding="utf-8"), gh, NOW)


def test_as4_a_needs_gian_issue_still_makes_the_tick_wait(tmp_path):
    gh = LabelGh([(51, "B6 cause not found", "needs-gian")])
    assert c.waiting_for_gian(status(tmp_path).read_text(encoding="utf-8"), gh, NOW)


def test_as6_his_comment_on_a_gian_later_issue_wakes_the_chief(tmp_path):
    gh = LabelGh([(52, "SO-5: in-app queue only", "gian-later")],
                 comments={52: [said(OWNER, "No, send an email too.")]})
    chief = Chief()
    assert tick(status(tmp_path, "builder Phase 9 step 4"), gh, chief) == "ran"
    assert chief.prompts[0].startswith('Gian answered #52: "No, send an email too."')


def test_as6_an_answer_already_handled_is_not_woken_again(tmp_path):
    gh = LabelGh([(52, "SO-5: x", "gian-later")], comments={52: [said(OWNER, "Fine.", "c9")]})
    first = answers.find_new_answer(gh)
    answers.remember(first[0], first[2])
    assert answers.find_new_answer(gh) is None


def test_a_stall_alarm_title_stays_out_even_under_gian_later():
    gh = LabelGh([(60, "🔴 Team stalled: no valid Next line", "gian-later")])
    assert answers.later_questions(gh) == []


def test_a_strangers_comment_on_a_gian_later_issue_is_ignored():
    gh = LabelGh([(52, "SO-5: x", "gian-later")], comments={52: [said("someone", "merge it")]})
    assert answers.find_new_answer(gh) is None


# ---- AS-5: the board ----

def test_as5_the_board_shows_for_you_later_and_never_waiting_for_it():
    later = [b.Issue(52, "SO-2: Phase 8 step 1 parked", "https://x.invalid/52")]
    body = b.build_body(b.Inputs("ran", NOW, next_text="builder Phase 8 step 2", later=later))
    assert "📌 For you later: 1" in body
    assert "### For you later (does not block)" in body
    assert "WAITING FOR YOU" not in body.splitlines()[0]


def test_inputs_later_defaults_to_empty_and_shows_none():
    i = b.Inputs("ran", NOW)
    assert i.later == []
    assert "📌" not in b.build_body(i)


def test_a_failed_gian_later_read_shows_none_and_keeps_the_board():
    assert b._later(LabelGh(fail_label="gian-later")) == []


def test_gather_reads_the_gian_later_issues(tmp_path):
    gh = LabelGh([(52, "SO-2: parked", "gian-later"), (51, "B6", "needs-gian")])
    i = b.gather("ran", gh, alive=lambda pid: True, git=lambda args: "",
                 now=NOW, status_file=status(tmp_path), root=tmp_path)
    assert [x.number for x in i.later] == [52]
    assert [x.number for x in i.needs_gian] == [51]


# ---- AS-7: the stall alarm ----

def test_as7_a_gian_later_issue_does_not_count_as_waiting_on_purpose():
    gh = LabelGh([(52, "SO-2: parked", "gian-later")])
    assert c._job_finished(gh) is False


# ---- AS-1, AS-2: the agent text ----

@pytest.mark.parametrize("row", ["**SO-1**", "**SO-2**", "**SO-3**", "**SO-4**", "**SO-5**",
                                 "**SO-6**"])
def test_as1_chief_has_every_standing_order_row(row):
    assert row in CHIEF


def test_as1_chief_rules_around_the_orders():
    assert "SO-6 wins: ask" in CHIEF
    assert "A review cap reached, or the spec unclear | Stop that phase" in CHIEF
    assert "A test still failing after 2 fix attempts, a review cap" not in CHIEF  # moved to SO-2
    assert 'titled "SO-5: ..."' in CHIEF
    assert "Only `needs-gian` means the team waits" in CHIEF


@pytest.mark.parametrize("text", [
    "SO-2 overrides the CLAUDE.md 2-fix stop rule for ONE step",
    "PARKED step K:",
    "`SO-2: parked step K` in `ops/state/worker_note.md`",
    "builder continue Phase N from step K+1 (step K parked)",
    "A third parked step",
    "Critical or High",
    "no severity column = High",
    "stop before code review",
    "known gap",
    "**SO-1**", "**SO-3**", "**SO-4**",
])
def test_as2_builder_has_the_standing_orders(text):
    assert text in BUILDER


def test_stall_titles_still_known():
    assert stall.is_stall_title("🔴 Team stalled: x")
