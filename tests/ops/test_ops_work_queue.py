"""Fix queue bar on the Team status board (17 Nov). No real git: a scripted fake."""

import json

import status_board as sb
import work_queue as wq

BASE = "auto/phases-7-10"
QUEUE = {
    "title": "Fix queue",
    "items": [
        {"name": "Batch B1", "branch": "auto/phase-b1-fixes", "size": 10, "done": True},
        {"name": "Batch C", "branch": "phase-c-fixes", "size": 10, "plan": "specs/c-plan.md"},
        {"name": "Fix D1", "branch": "phase-d1-test-report", "size": 20},
    ],
}
PLAN = "# Plan\n\n## Steps\n\n1. one\n2. two\n3. three\n4. four\n\n## Risks\n1. not a step\n"


class FakeGit:
    def __init__(self, queue=QUEUE, ancestors=(), merges="", logs=None, plan=PLAN):
        self.queue, self.ancestors, self.merges = queue, set(ancestors), merges
        self.logs, self.plan = logs or {}, plan

    def __call__(self, args):
        if args[0] == "show" and args[1] == f"origin/{BASE}:ops/work_queue.json":
            if self.queue is None:
                raise RuntimeError("no file")
            return json.dumps(self.queue) if isinstance(self.queue, dict) else self.queue
        if args[0] == "show" and args[1].endswith(":specs/c-plan.md"):
            return self.plan
        if args[:2] == ["merge-base", "--is-ancestor"] and args[2] in self.ancestors:
            return ""
        if args[0] == "log" and "--merges" in args:
            return self.merges
        if args[0] == "log" and args[1] in self.logs:
            return self.logs[args[1]]
        raise RuntimeError("not scripted")


def test_done_flag_counts_and_running_entry_shows_steps(tmp_path):
    git = FakeGit(logs={f"{BASE}..phase-c-fixes":
                        "C3: step 2 done\nFix batch C: steps 1 and 2\nreview round 1 fixes\n"})
    v = wq.view(git, tmp_path, BASE)
    # B1 10 done; C: 10 + 70*2/4 + 5 = 50% of 10 = 5 -> 15 of 40 = 37%
    assert v.percent == 37
    assert (v.done_count, v.total_count, v.now) == (1, 3, "Batch C")
    assert v.now_detail == "step 2 of 4, review round 1"
    assert v.upcoming == ("Fix D1",)


def test_branch_merged_by_ancestor_or_by_merge_subject(tmp_path):
    git = FakeGit(ancestors={"origin/phase-c-fixes"},
                  merges="Merge pull request #90 from giandagdag/phase-d1-test-report\n")
    v = wq.view(git, tmp_path, BASE)
    assert v.percent == 100 and v.done_count == 3 and v.now == ""


def test_step_ids_at_the_start_of_subjects_count_once(tmp_path):
    git = FakeGit(logs={f"{BASE}..phase-c-fixes": "C3: three\nC1/C2: one and two\nC3: again\n"})
    assert wq.view(git, tmp_path, BASE).now_detail == "step 3 of 4"


def test_running_entry_never_reaches_100_before_merge(tmp_path):
    git = FakeGit(logs={f"{BASE}..phase-c-fixes": "step 4\nreview round 3\n"})
    v = wq.view(git, tmp_path, BASE)
    assert v.percent == int((10 + 9.5) * 100 / 40)


def test_missing_or_broken_file_means_no_bar(tmp_path):
    assert wq.view(FakeGit(queue=None), tmp_path, BASE) is None
    assert wq.view(FakeGit(queue="{not json"), tmp_path, BASE) is None


def test_local_file_used_when_origin_has_none(tmp_path):
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "work_queue.json").write_text(json.dumps(QUEUE), encoding="utf-8")
    assert wq.view(FakeGit(queue=None), tmp_path, BASE).total_count == 3


def test_row_text():
    v = wq.QueueView("Fix queue", 37, 1, 3, "Batch C", "step 2 of 4", ("Fix D1",))
    expected = "| Fix queue | `▓▓▓░░░░░░░` 37% · 1 of 3 done · now: Batch C (step 2 of 4) |"
    assert v.row(sb.bar) == expected
    assert v.next_row() == "| Then | Fix D1 |"


def test_board_body_shows_the_queue_rows():
    i = sb.Inputs(result="idle", now=1_800_000_000.0,
                  queue=wq.QueueView("Fix queue", 37, 1, 3, "Batch C", "", ("Fix D1",)))
    body = sb.build_body(i)
    assert "| Fix queue | `▓▓▓░░░░░░░` 37% · 1 of 3 done · now: Batch C |" in body
    assert "| Then | Fix D1 |" in body


def test_board_body_without_queue_is_unchanged():
    body = sb.build_body(sb.Inputs(result="idle", now=1_800_000_000.0))
    assert "Fix queue" not in body
