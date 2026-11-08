"""Phase A fix 2: the Team status issue (AS-1 to AS-15). No real gh, git or claude."""

import json
import sys
from pathlib import Path

import chief_tick as c
import pytest
import stall
import status_board as sb
import usage_guard as g
from status_board import refresh as real_refresh  # imported before conftest turns it off

NOW = 1_800_000_000.0  # 2027-01-15 08:00 UTC = 16:00 SGT


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every note (usage.json, running.json, status_issue.json) goes to a temp folder."""
    monkeypatch.setenv("DA_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


def usage(five=34, weekly=34, read_at=NOW):
    return g.Usage(five, weekly, NOW + 3600, NOW + 86400, read_at)


class FakeGit:
    """Answers `git` with scripted text. Anything not scripted fails, like a missing branch."""

    def __init__(self, merged=(), refs=(), files=None, subjects=None, same=True, head="main"):
        self.merged, self.refs, self.files = set(merged), set(refs), files or {}
        self.subjects, self.same, self.head = subjects or {}, same, head
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["merge-base", "--is-ancestor"]:
            if args[2] in self.merged:
                return ""
        elif args[:2] == ["rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        elif args[:3] == ["rev-parse", "--verify", "-q"]:
            if args[3] in self.refs:
                return args[3]
        elif args[:2] == ["rev-parse", "--abbrev-ref"]:
            return self.head + "\n"
        elif args[:1] == ["rev-parse"] and len(args) == 2:
            if args[1] in self.refs:
                return "abc\n" if self.same or not args[1].startswith("origin/") else "def\n"
        elif args[:1] == ["show"]:
            ref, _, path = args[1].partition(":")
            if (ref, path) in self.files:
                return self.files[(ref, path)]
        elif args[:2] == ["ls-tree", "--name-only"]:
            ref = args[2]
            names = [p for (r, p) in self.files if r == ref]
            if names:
                return "\n".join(names) + "\n"
        elif args[:1] == ["log"] and args[1] in self.subjects:
            return "\n".join(self.subjects[args[1]]) + "\n"
        elif args[:2] == ["log", "-5"]:
            return f"{int(NOW) - 600}|Step 3/9: Layer C plain checks\n"
        raise sb.GitError(" ".join(args))


class FakeGh:
    def __init__(self, gian=(), work=(), fail=False, existing=None):
        self.calls, self.gian, self.work = [], list(gian), list(work)
        self.fail, self.existing = fail, existing

    def __call__(self, args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError("gh down")
        if args[:2] == ["issue", "list"]:
            if "needs-gian" in args:
                return json.dumps(self.gian)
            if "needs-work-test" in args:
                return json.dumps(self.work)
            return json.dumps([self.existing] if self.existing else [])
        if args[:2] == ["issue", "create"]:
            return "https://example.invalid/o/r/issues/42\n"
        return ""

    def verbs(self, *verb):
        return [a for a in self.calls if a[: len(verb)] == list(verb)]


MERGE_BASE_REF = sb.MERGE_BASE


def phase8_git(steps=3, plan_steps=6, plan=True, clean=False):
    plan_text = "\n".join(["# Plan", "## Steps"] + ["0. **Done**"]
                          + [f"{n}. **Step {n}**" for n in range(1, plan_steps + 1)])
    files = {("auto/phase-8", "specs/phase-8-refine.md"): "Status: APPROVED v1.0\n"}
    if plan:
        files[("auto/phase-8", "specs/phase-8-plan.md")] = plan_text
    subjects = [f"Phase 8 step {n}: x" for n in range(steps, 0, -1)]
    subjects.append("Phase 8 plan: plan-reviewer approved (0 Must fix)")
    return FakeGit(merged={"auto/phase-7"}, refs={"auto/phase-8", "origin/auto/phase-8"},
                   files=files, subjects={"auto/phase-8": subjects})


@pytest.fixture
def status_file(tmp_path):
    f = tmp_path / "STATUS.md"
    f.write_text("# STATUS\n## Where we are\n- Next: Phase 8 build\n## Log\n- one\n- two\n",
                 encoding="utf-8")
    return f


def build(result="idle", gh=None, git=None, status_file=None, alive=None, now=NOW):
    inputs = sb.gather(result, gh or FakeGh(), alive, git or phase8_git(), now, status_file)
    return sb.build_body(inputs)


def write_running(agent="builder", phase="7", started=NOW - 4320, pid=77):
    path = g.state_path().parent / "running.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"agent": agent, "phase": phase, "started": started, "pid": pid,
                                "prompt": "x" * 500}), encoding="utf-8")


def write_usage(**kw):
    g.write_state(usage(**kw))


# ---- progress maths: AS-13, AS-14 (bars), AS-15 ----

def test_bar_is_ten_characters_rounded_down():
    assert sb.bar(31) == "▓▓▓░░░░░░░" and sb.bar(0) == "░" * 10 and sb.bar(100) == "▓" * 10
    assert sb.bar(99.9) == "▓" * 9 + "░" and len(sb.bar(52)) == 10


def test_as13_phase_8_reads_52_percent_and_overall_38(status_file):
    facts = sb.current_phase(phase8_git(), Path("/nonexistent"))
    merged, f, overall = facts
    progress = sb.phase_progress(f)
    assert (merged, progress.percent, overall) == (1, 52, 38)
    assert progress.stage == "Build, step 3 of 6" and not progress.estimate


def test_as15_missing_plan_counts_zero_build_and_says_estimate():
    _, f, overall = sb.current_phase(phase8_git(plan=False), Path("/nonexistent"))
    progress = sb.phase_progress(f)
    assert progress.percent == 15 and progress.estimate  # spec only
    assert progress.line().endswith("(estimate)") and overall == 28


def test_a_brand_new_phase_is_a_plain_zero_not_an_estimate():
    git = FakeGit(merged={"auto/phase-7"})
    _, f, _ = sb.current_phase(git, Path("/nonexistent"))
    progress = sb.phase_progress(f)
    assert progress.percent == 0 and progress.stage == "Spec" and not progress.estimate


def test_plan_steps_skip_step_zero_and_nested_numbers_and_read_step_headings():
    plan = ("## Steps (each ends with pytest)\n0. **Done:** x\n1. **A**\n   1. nested\n"
            "2. **B**\n## Risks\n1. not a step\n")
    assert sb.count_plan_steps(plan) == 2
    assert sb.count_plan_steps("### Step 1: a\n### Step 2: b\ntext\n") == 2
    assert sb.count_plan_steps("nothing") == 0


def test_step_commits_take_the_highest_number_and_ignore_the_letter():
    subjects = ["Phase 7 step 8b: docs", "Phase 7 step 8a: smoke", "Phase 7 step 5: loop",
                "Phase 8 step 9: other phase", "Phase 7 plan: x"]
    assert sb.highest_step(subjects, 7) == 8 and sb.highest_step([], 7) == 0


def test_code_review_is_five_per_round_and_full_only_when_pushed_and_clean():
    base = dict(spec_approved=True, plan_exists=True, plan_approved=True, steps_total=2,
                step_done=2)
    two = sb.phase_progress(sb.PhaseFacts(8, **base, review_rounds=2))
    assert two.percent == 15 + 10 + 55 + 10 and two.stage == "Code review"
    clean = sb.PhaseFacts(8, **base, review_rounds=1, last_review_clean=True, pushed=True)
    assert sb.phase_progress(clean).percent == 95
    unpushed = sb.PhaseFacts(8, **base, review_rounds=1, last_review_clean=True)
    assert sb.phase_progress(unpushed).percent == 85


def test_not_approved_is_not_approved_and_all_merged_is_100():
    assert sb.is_approved("Status: APPROVED v1.0") and not sb.is_approved("Status: NOT APPROVED")
    assert not sb.is_approved("DRAFT")
    git = FakeGit(merged={f"auto/phase-{n}" for n in (7, 8, 9, 10)})
    assert sb.current_phase(git, Path("/nonexistent")) == (4, None, 100)


# ---- the top line: AS-1 to AS-6 ----

def test_as1_a_running_builder_is_green_with_agent_phase_and_time(status_file):
    write_running()
    body = build("busy", status_file=status_file, alive=lambda pid: True)
    first = body.splitlines()[0]
    assert first.startswith("## 🟢 WORKING: builder on Phase 7 (running 1h 12m, since ")


def test_a_dead_worker_is_not_shown_as_working(status_file):
    write_running()
    body = build("idle", status_file=status_file, alive=lambda pid: False)
    assert body.splitlines()[0].startswith("## 🔵 READY")


def test_as2_an_open_needs_gian_issue_is_red_and_linked(status_file):
    gh = FakeGh(gian=[{"number": 5, "title": "Q: pick one", "url": "https://x.invalid/5"}])
    body = build(gh=gh, status_file=status_file)
    assert body.splitlines()[0].startswith("## 🔴 WAITING FOR YOU")
    assert "[#5](https://x.invalid/5) Q: pick one" in body


def test_as3_next_line_waiting_for_gian_is_red(tmp_path):
    f = tmp_path / "STATUS.md"
    f.write_text("# S\n- Next: waiting for Gian to approve the spec\n## Log\n", encoding="utf-8")
    assert build(status_file=f).splitlines()[0].startswith("## 🔴 WAITING FOR YOU")


def test_as4_guard_stop_is_yellow_with_the_line_and_the_reset_time(status_file):
    write_usage(five=85)
    first = build("stopped", status_file=status_file).splitlines()[0]
    assert first.startswith("## 🟡 PAUSED: usage (5-hour 85%, resets ") and "SGT" in first


def test_as5_blind_guard_is_black(status_file):
    first = build("stopped", status_file=status_file).splitlines()[0]  # no usage.json
    assert first.startswith("## ⚫ GUARD BLIND")
    write_usage(read_at=NOW - 1000)  # a stale file is not proof
    assert build("stopped", status_file=status_file).splitlines()[0].startswith("## ⚫")


def test_blind_bars_read_blind(status_file):
    body = build("stopped", status_file=status_file)
    assert "| Usage 5h | `blind` |" in body and "| Usage weekly | `blind` |" in body


def test_as6_work_laptop_issues_are_listed_and_do_not_make_it_red(status_file):
    gh = FakeGh(work=[{"number": 20, "title": "WF-1 (Q9)", "url": "https://x.invalid/20"}])
    body = build(gh=gh, status_file=status_file)
    assert not body.splitlines()[0].startswith("## 🔴")
    assert "### Needs the work laptop (does not block)\n- [#20](https://x.invalid/20) WF-1" in body


def test_hooks_broken_idle_and_ready_lines(tmp_path, status_file):
    assert build("hooks-broken", status_file=status_file).startswith("## 🟠 HOOKS BROKEN")
    assert build("idle", status_file=status_file).startswith("## 🔵 READY")
    none = tmp_path / "S.md"
    none.write_text("# S\n- Next: none\n## Log\n", encoding="utf-8")
    assert build("idle", status_file=none).startswith("## ⚪ IDLE")


def test_as14_usage_bars_show_the_percent_and_the_stop_lines(status_file):
    write_usage(five=34, weekly=34)
    body = build(status_file=status_file)
    assert "| Usage 5h | `▓▓▓░░░░░░░` 34% of the 85% stop line |" in body
    assert "| Usage weekly | `▓▓▓░░░░░░░` 34% of the 80% stop line |" in body


def test_the_body_shows_progress_commits_and_cut_log_lines(tmp_path):
    f = tmp_path / "STATUS.md"
    f.write_text("# S\n- Next: Phase 8 build\n  continues here\n## Log\n- " + "x" * 400 + "\n",
                 encoding="utf-8")
    body = build(status_file=f, git=phase8_git())
    assert "| Phases 7 to 10 | `▓▓▓░░░░░░░` 38% (Phase 8 of 10) |" in body
    assert "| Phase 8 | `▓▓▓▓▓░░░░░` 52% · Build, step 3 of 6 |" in body
    assert "Phase 8 build continues here" in body
    assert "### Latest commits on main\n- " in body and "Step 3/9: Layer C plain checks" in body
    log_line = body.split("### Last log lines (STATUS.md)\n- ")[1].strip()
    assert len(log_line) == 160 and log_line.endswith("…")


def test_as12_nothing_from_usage_raw_env_or_prompts_reaches_the_body(status_file, tmp_path):
    state = g.state_path().parent
    state.mkdir(parents=True, exist_ok=True)
    (state / "usage_raw.json").write_text('{"secret": "RAW-TOKEN-123"}', encoding="utf-8")
    (tmp_path / ".env").write_text("KEY=ENV-SECRET-456", encoding="utf-8")
    write_running()  # its prompt is 500 characters of x
    write_usage()
    body = build("busy", status_file=status_file, alive=lambda pid: True)
    assert "RAW-TOKEN-123" not in body and "ENV-SECRET-456" not in body and "xxxxx" not in body


def test_damaged_running_json_and_missing_usage_do_not_break_the_board(status_file):
    path = g.state_path().parent / "running.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert build("idle", status_file=status_file).startswith("## 🔵")


# ---- the writer: AS-7, AS-8 ----

def test_as7_no_state_and_no_issue_creates_one_with_the_label_and_remembers_it():
    gh = FakeGh()
    assert sb.write_issue("## body\n", gh, NOW) == "created"
    create = gh.verbs("issue", "create")[0]
    assert create[create.index("--label") + 1] == "team-status" and sb.TITLE in create
    assert gh.verbs("issue", "pin") == [["issue", "pin", "42"]]
    state = json.loads(sb.status_file_path().read_text(encoding="utf-8"))
    assert state["number"] == 42 and state["pinned"] is True


def test_an_issue_found_by_title_is_edited_not_duplicated():
    gh = FakeGh(existing={"number": 9, "title": sb.TITLE})
    assert sb.write_issue("## body\n", gh, NOW) == "edited"
    assert gh.verbs("issue", "create") == [] and gh.verbs("issue", "edit")[0][2] == "9"


def test_as8_same_content_within_the_hour_makes_no_edit_but_an_hour_later_does():
    gh = FakeGh()
    sb.write_issue("Updated 10:00\nbody (running 1h 1m, since 9:00)\n", gh, NOW)
    gh.calls.clear()
    same = "Updated 10:30\nbody (running 1h 31m, since 9:00)\n"
    assert sb.write_issue(same, gh, NOW + 1800) == "unchanged" and gh.calls == []
    assert sb.write_issue(same, gh, NOW + 3601) == "edited"
    assert gh.verbs("issue", "edit")
    gh.calls.clear()
    assert sb.write_issue("a real change\n", gh, NOW + 3700) == "edited"


def test_an_issue_deleted_by_hand_is_created_again():
    class Gone(FakeGh):
        def __call__(self, args):
            if args[:3] == ["issue", "edit", "42"]:
                raise RuntimeError("could not resolve")
            return super().__call__(args)

    gh = Gone()
    sb.write_issue("one\n", gh, NOW)
    assert sb.write_issue("two\n", gh, NOW + 5) == "created"


def test_an_issue_with_a_garbled_emoji_is_still_found_by_title():
    gh = FakeGh(existing={"number": 9, "title": "ðŸ¤– Team status"})
    assert sb.write_issue("## body\n", gh, NOW) == "edited" and gh.verbs("issue", "create") == []


def test_a_branch_cut_from_the_base_with_no_work_is_not_merged():
    refs = {"auto/phase-7", MERGE_BASE_REF, "origin/" + MERGE_BASE_REF}
    git = FakeGit(merged={"auto/phase-7"}, refs=refs)
    # both tips resolve to the same commit ("abc"): nothing was merged, nothing was built
    _, facts, _ = sb.current_phase(git, Path("/nonexistent"))
    assert facts.phase == 7 and not facts.merged


def test_a_failing_pin_is_ignored_and_a_damaged_state_file_acts_as_no_state():
    class NoPin(FakeGh):
        def __call__(self, args):
            if args[:2] == ["issue", "pin"]:
                raise RuntimeError("no pin")
            return super().__call__(args)

    assert sb.write_issue("x\n", NoPin(), NOW) == "created"
    sb.status_file_path().write_text("{broken", encoding="utf-8")
    assert sb.write_issue("x\n", FakeGh(), NOW) == "created"


def test_as15_the_board_is_still_written_when_the_plan_is_missing(status_file):
    gh = FakeGh()
    result = real_refresh("idle", gh, git=phase8_git(plan=False), now=NOW, status_file=status_file)
    assert result == "created"
    body = gh.verbs("issue", "create")[0][gh.verbs("issue", "create")[0].index("--body") + 1]
    assert "(estimate)" in body


# ---- the tick: AS-9, AS-10, AS-11 ----

def _usage(five=10, weekly=10):
    return g.Usage(five, weekly, NOW + 3600, NOW + 86400, NOW)


DEFAULT_STATUS = "# S\nUsage: x\nStopped: no\n## Where we are\n- Next: Phase 8\n## Log\n"


def _status(tmp_path, text=DEFAULT_STATUS):
    f = tmp_path / "STATUS.md"
    f.write_text(text, encoding="utf-8")
    return f


def _fail_launch(prompt, agent="chief"):
    raise AssertionError("no worker")


def test_as9_a_failing_gh_leaves_one_log_line_and_the_tick_result(tmp_path, monkeypatch):
    log = tmp_path / "board.log"
    monkeypatch.setenv("DA_STATUS_BOARD_LOG", str(log))
    gh = FakeGh(fail=True)
    result = c.tick(lambda: _usage(), gh, None, _status(tmp_path), NOW,
                    board=lambda r: real_refresh(r, gh, git=phase8_git(), now=NOW))
    assert result == "would-start"
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and "RuntimeError: gh down" in lines[0] and "SGT" in lines[0]


def test_a_board_that_raises_cannot_change_the_tick_result(tmp_path):
    def boom(result):
        raise ValueError("bug")

    assert c.tick(lambda: _usage(), FakeGh(), None, _status(tmp_path), NOW, board=boom) == (
        "would-start")


@pytest.mark.parametrize("case", ["busy", "stopped", "idle", "would-start", "hooks-broken"])
def test_as10_the_board_is_refreshed_after_every_tick_result(tmp_path, case):
    seen = []
    status = _status(tmp_path, "# S\nUsage: x\n## Log\n- Next: none\n" if case == "idle"
                     else "# S\nUsage: x\n## Where we are\n- Next: Phase 8\n## Log\n")
    kwargs = {}
    if case == "busy":
        write_running()
        kwargs["alive"] = lambda pid: True
    reader = (lambda: _usage(weekly=90)) if case == "stopped" else (lambda: _usage())
    if case == "hooks-broken":
        kwargs["launcher"] = lambda p, a: c.WorkerResult(0, "{}")
        kwargs["preflight"] = lambda: "bad"
    result = c.tick(reader, FakeGh(), status_file=status, now=NOW, board=seen.append, **kwargs)
    assert result == case and seen == [case]


def test_as10_the_board_also_runs_after_a_worker_ran(tmp_path):
    seen = []
    ok = c.WorkerResult(0, json.dumps({"result": "done"}))
    result = c.tick(lambda: _usage(), FakeGh(), lambda p, a="chief": ok, _status(tmp_path), NOW,
                    preflight=lambda: None, board=seen.append)
    assert result == "ran" and seen == ["ran"]


def test_as10_main_refreshes_the_board_after_tick_launch_and_stop(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(sb, "refresh", lambda result, *a, **k: seen.append(result))
    monkeypatch.setattr(c, "tick", lambda *a, board=None, **k: (board("idle"), "idle")[1])
    assert c.main(["tick"], FakeGh()) == 0
    monkeypatch.setattr(c, "STATUS_FILE", _status(tmp_path))
    assert c.main(["stop"], FakeGh()) == 0
    assert seen == ["idle", "nothing running"]


# ---- the hidden window: AS-11 ----

def _capture_run(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)

        class Done:
            returncode, stdout, stderr = 0, "{}", ""

        return Done()

    monkeypatch.setattr(c.subprocess, "run", fake_run)
    return seen


def test_as11_on_windows_claude_starts_without_a_window(monkeypatch):
    seen = _capture_run(monkeypatch)
    c.real_launcher("hi", "builder", platform="win32")
    assert seen["creationflags"] == c.CREATE_NO_WINDOW


def test_off_windows_no_creation_flags_are_passed(monkeypatch):
    seen = _capture_run(monkeypatch)
    c.real_launcher("hi", "builder", platform="linux")
    assert "creationflags" not in seen


def test_the_runner_keeps_its_own_flags():
    assert c.WIN_FLAGS & c.CREATE_NO_WINDOW and c.WIN_FLAGS & c.DETACHED_PROCESS


def test_status_board_never_imports_chief_tick_and_has_no_real_calls_in_tests():
    assert "chief_tick" not in sys.modules["status_board"].__dict__


# ---- Phase A fix 3: STALLED top line and the UNPUSHED warning ----




class AheadGit(FakeGit):
    """The normal phase 8 answers, plus `git rev-list --count` for the unpushed check."""

    def __init__(self, ahead, **kw):
        super().__init__(**kw)
        self.ahead = ahead

    def __call__(self, args):
        if args[:2] == ["rev-list", "--count"]:
            return f"{self.ahead}\n"
        return super().__call__(args)


def ahead_git(ahead):
    base = phase8_git()
    return AheadGit(ahead, merged=base.merged, refs=base.refs, files=base.files,
                    subjects=base.subjects)


def test_stalled_outranks_idle_and_ready(tmp_path):
    for next_line in ("- Next: none", "- Next: Phase 8 build"):
        f = tmp_path / "STATUS.md"
        f.write_text(f"# S\n## Where we are\n{next_line}\n## Log\n", encoding="utf-8")
        stall.save_stall(stall.NO_NEXT)
        first = build("idle", status_file=f).splitlines()[0]
        assert first == "## 🔴 STALLED: no valid Next line"


def test_waiting_for_you_outranks_stalled(status_file):
    stall.save_stall(stall.NOT_FINISHED)
    gh = FakeGh(gian=[{"number": 5, "title": "Q", "url": "u"}])
    assert build("idle", gh=gh, status_file=status_file).splitlines()[0].startswith(
        "## 🔴 WAITING FOR YOU")


def test_stalled_is_gone_when_the_note_is_gone_or_the_tick_is_not_idle(status_file):
    stall.save_stall(stall.NO_NEXT)
    assert "STALLED" not in build("would-start", status_file=status_file).splitlines()[0]
    stall.clear_stall()
    assert "STALLED" not in build("idle", status_file=status_file).splitlines()[0]


def test_as4_unpushed_commits_show_a_warning_that_goes_when_pushed(status_file):
    stall.remember_unpushed("auto/phase-8")
    body = build("idle", git=ahead_git(2), status_file=status_file)
    assert "> ⚠️ UNPUSHED: 2 commits on auto/phase-8" in body.splitlines()[:4]
    body = build("idle", git=ahead_git(0), status_file=status_file)
    assert "UNPUSHED" not in body


def test_a_git_problem_in_the_warning_check_shows_no_warning(status_file):
    stall.remember_unpushed("auto/phase-8")
    assert "UNPUSHED" not in build("idle", status_file=status_file)  # FakeGit fails rev-list
