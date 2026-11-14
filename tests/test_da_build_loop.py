"""The build loop end to end with the fake provider, the real sandbox and a real database."""

import pytest

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_check_words import NOT_PROVEN_TEXT, SYSTEM_HELP_LINE
from pydantic_classes.da_build_models import LABEL_NOT_PASSING, LABEL_WITH_WARNINGS, BuildState
from tests.da_approach_play import events_of
from tests.da_build_play import (
    CREATE,
    MODIFY,
    ORIGINAL,
    RecordingFactory,
    build_state,
    chat,
    event_types,
    files_of,
    progress_of,
    ready_with_workspace,
    request_status,
    rounds_of,
    run_row,
)

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def build(settings, request_id, factory=None):
    state = flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    return state, loop.run_build(settings, request_id, factory)


def switches(monkeypatch, *names):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset(names))


# --- a normal build (home script): round 1 tests fail, round 2 Tester Must fix, round 3 yellow ---


def test_7_the_home_build_takes_three_rounds_and_ends_yellow_without_the_old_warning(
    settings, request_id
):
    factory = RecordingFactory()

    _, outcome = build(settings, request_id, factory)

    assert outcome == "done"
    state = build_state(settings, request_id)
    assert (state.step, state.current_round, state.write_state) == ("b_done", 3, "not_written")
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    run = run_row(settings, request_id)
    assert (run.rounds_used, run.label, run.result_status) == (
        3,
        LABEL_WITH_WARNINGS,
        "READY_FOR_REVIEW",
    )
    assert run.ended_at is not None
    said = " ".join(chat(settings, request_id, "assistant"))
    assert "not built yet" not in said  # test 7-23
    assert "Ready with warnings" in said and "Approved" not in said
    assert "Round 2: the Tester found 1 Must fix. Fixing only excel_processor.py." in said


def test_6_18_round_one_fails_three_tests_and_only_the_traced_file_is_regenerated(
    settings, request_id, monkeypatch
):
    factory = RecordingFactory()
    seen = []
    original = loop._Run._one_round

    def spy(self, number, contract, tests):
        passed = original(self, number, contract, tests)
        seen.append((number, passed, flow.get_state(settings, request_id).step))
        return passed

    monkeypatch.setattr(loop._Run, "_one_round", spy)

    build(settings, request_id, factory)

    # After round 1 the step is b_round_failed; rounds 2 and 3 pass Layers A and B, and the
    # Tester review (round 2: a Must fix) decides what happens next.
    assert seen == [
        (1, False, "b_round_failed"),
        (2, True, "b_running"),
        (3, True, "b_running"),
    ]
    first, second, _third = rounds_of(settings, request_id)
    assert first.layer_b.failed == 3 and not first.layer_b.ok
    report = first.failure_report
    assert [(i.test_id, i.criterion_id) for i in report.items] == [
        ("T-2", "AC-2"),
        ("T-5", "AC-4"),
        ("T-8", "AC-7"),
    ]
    assert all(i.expected.endswith(".") and i.message for i in report.items)
    assert first.files_to_fix == [CREATE] == report.files_to_fix
    assert second.failure_report is None and second.layer_b.ok
    code = factory.code_calls()
    assert len(code) == 4  # round 1: two files; rounds 2 and 3: only the file to fix
    assert f"File: {CREATE}" in code[2] and "Round: 2" in code[2]
    assert agent.FAILURE_HEADING in code[2] and "T-2" in code[2]
    assert "Do not change the tests" in code[2]
    # Round 3 gets the Tester's Must fix line only (test 7-13): no Should fix, no FYI.
    assert f"File: {CREATE}" in code[3] and "Round: 3" in code[3]
    assert "(Must fix)" in code[3] and "F-1" in code[3] and "Should fix" not in code[3]
    chat_lines = chat(settings, request_id, "assistant")
    assert "Round 1: 3 of 9 tests failed. Fixing only excel_processor.py." in chat_lines


def test_6_8_one_ai_call_per_file_and_one_each_for_the_contract_and_the_tests(settings, request_id):
    factory = RecordingFactory()

    build(settings, request_id, factory)

    roles = [role for role, _ in factory.calls]
    # contract, tests, round 1 (2 files), round 2 (1 file) + review, round 3 (1 file) + review
    assert roles == [
        "generator",
        "tester",
        "generator",
        "generator",
        "generator",
        "tester",
        "generator",
        "tester",
    ]
    contract_call, tests_call = factory.prompts()[0], factory.prompts()[1]
    assert agent.CONTRACT_MARKER in contract_call and agent.TESTS_MARKER in tests_call


def test_6_4_the_contract_and_tests_are_saved_frozen_before_any_code(settings, request_id):
    build(settings, request_id)

    saved = files_of(settings, request_id)
    kinds = [item.kind for item in saved]
    assert kinds[:2] == ["contract", "test"] and set(kinds[2:]) == {"code"}
    contract = saved[0]
    assert CREATE in contract.text and MODIFY in contract.text and "tests/" not in contract.text
    audit = events_of(settings, request_id, "tests_frozen")
    assert audit[0].details["fingerprint"] == saved[1].fingerprint
    assert events_of(settings, request_id, "tests_written")[0].details == {"tests": 9}


def test_6_5_the_tester_prompt_holds_no_code_text(settings, request_id):
    factory = RecordingFactory()

    build(settings, request_id, factory)

    tester = [p for p in factory.prompts("tester") if agent.TESTS_MARKER in p]
    assert len(tester) == 1
    assert ORIGINAL not in tester[0] and "return True" not in tester[0]
    assert "def " not in tester[0].split("## How to reply")[0]


def test_the_audit_trail_lists_every_step_of_the_build_in_order(settings, request_id):
    build(settings, request_id)

    wanted = [
        "build_started",
        "contract_written",
        "tests_written",
        "tests_frozen",
        "code_generated",
        "code_generated",
        "layer_a_result",
        "layer_b_result",
        "round_failed",
        "code_generated",
        "layer_a_result",
        "layer_b_result",
        "tester_review_started",
        "tester_review_done",
        "round_failed",
        "code_generated",
        "layer_a_result",
        "layer_b_result",
        "tester_review_started",
        "tester_finding_rejected",
        "tester_review_done",
        "build_passed",
    ]
    types = [t for t in event_types(settings, request_id) if t in set(wanted)]
    assert types == wanted
    passed = events_of(settings, request_id, "build_passed")[0].details
    assert passed["rounds"] == 3 and passed["label"] == LABEL_WITH_WARNINGS
    assert passed["zones_touched"] == []  # recorded for Phase 10, never blocks


def test_the_progress_list_tells_the_story_and_ends_with_the_layer_c_result(settings, request_id):
    build(settings, request_id)

    lines = progress_of(settings, request_id)
    texts = [(line.text, line.state) for line in lines]
    assert ("Function names agreed", "done") in texts
    assert ("Tester wrote 9 tests (frozen)", "done") in texts
    limit = "(time limit 60 seconds per run)"
    assert (f"Layer B: 6 of 9 tests passed {limit}", "failed") in texts
    assert (f"Layer B: 9 of 9 tests passed {limit}", "done") in texts
    last_text, last_state = texts[-1]
    assert last_text.startswith("Layer C: 0 Must fix, 1 Should fix, 1 FYI") and last_state == "done"
    assert not any("coming in Phase 7" in text for text, _ in texts)
    assert [line.line_number for line in lines] == sorted({item.line_number for item in lines})


# --- the budget ---


def test_6_21_code_that_always_fails_uses_three_rounds_then_is_not_passing(
    settings, request_id, monkeypatch
):
    switches(monkeypatch, "always_fail")

    _, outcome = build(settings, request_id)

    assert outcome == "done"
    assert request_status(settings, request_id) == "NOT_PASSING"
    assert len(rounds_of(settings, request_id)) == 3
    run = run_row(settings, request_id)
    assert (run.rounds_used, run.label) == (3, LABEL_NOT_PASSING)
    state = build_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_done", "not_written")  # still to be written
    code = [f for f in files_of(settings, request_id) if f.kind == "code"]
    assert {f.round for f in code} == {1, 2, 3}
    said = chat(settings, request_id, "assistant")[-1]
    assert "used all 3 rounds" in said and "Not passing" in said
    assert "build_not_passing" in event_types(settings, request_id)


def test_f9a_when_the_code_checks_fail_in_every_round_the_last_line_says_the_tests_never_ran(
    settings, request_id, monkeypatch
):
    """The work-test case: Layer A failed in all 3 rounds, Layer B never ran. "0 test(s) still
    fail" would be untrue."""
    switches(monkeypatch, "bad_edit", "always_fail")

    build(settings, request_id)

    records = rounds_of(settings, request_id)
    assert len(records) == 3 and all(record.layer_b is None for record in records)
    said = chat(settings, request_id, "assistant")[-1]
    assert said == (
        "The code checks failed in every round, so the tests never ran. Result: Not passing. "
        "I will still write the code files so you can see them."
    )
    assert "0 test(s)" not in said and "still fail" not in said


def test_f9a_the_wording_when_the_tests_ran_is_the_one_from_before(
    settings, request_id, monkeypatch
):
    switches(monkeypatch, "always_fail")
    build(settings, request_id)
    records = rounds_of(settings, request_id)
    assert all(record.layer_b is not None for record in records)

    said = loop._finish_text(False, 3, "Not passing", records, 9)

    assert said.startswith("I used all 3 rounds and ")
    assert " test(s) still fail. Result: Not passing. " in said


def test_f9a_when_only_the_last_round_was_stopped_by_the_code_checks_it_says_so(
    settings, request_id, monkeypatch
):
    switches(monkeypatch, "always_fail")
    build(settings, request_id)
    records = rounds_of(settings, request_id)
    records[-1] = records[-1].model_copy(update={"layer_b": None})

    said = loop._finish_text(False, 3, "Not passing", records, 9)

    assert said == (
        "The code checks failed in the last round, so the tests did not run in it. "
        "Result: Not passing. I will still write the code files so you can see them."
    )


# --- layer A and layer B problems reach the report ---


def test_6_10_an_edit_block_that_matches_nothing_fails_the_round_through_layer_a(
    settings, request_id, monkeypatch
):
    switches(monkeypatch, "bad_edit")

    build(settings, request_id)

    first = rounds_of(settings, request_id)[0]
    assert first.layer_b is None  # layer A failed, so the tests never ran
    assert [(p.code, p.path) for p in first.layer_a.problems] == [("E1", MODIFY)]
    assert "Edit block 1 did not match the file" in first.layer_a.problems[0].text
    assert first.files_to_fix == [MODIFY]
    assert any(
        "problem(s) in the code checks" in line for line in chat(settings, request_id, "assistant")
    )


def test_6_14_a_test_that_runs_out_of_time_is_named_and_the_round_fails(
    settings, request_id, monkeypatch
):
    switches(monkeypatch, "slow_test")
    real = loop.run_tests
    monkeypatch.setattr(loop, "run_tests", lambda *a, **k: real(*a, **{**k, "timeout_seconds": 1}))

    build(settings, request_id)

    first = rounds_of(settings, request_id)[0]
    assert first.timed_out and first.layer_b.timed_out
    assert first.failure_report.timed_out
    assert first.failure_report.running_test.startswith("test_t1_ac1_")
    assert any("ran out of time" in line for line in chat(settings, request_id, "assistant"))


# --- not the code's fault: no round is used ---


def test_b1_3_tests_that_never_report_pause_the_build_and_no_repair_round_is_used(
    settings, request_id, monkeypatch
):
    real = loop.run_tests
    drop = {"on": True}

    def quiet_runner(*args, **kwargs):
        result = real(*args, **kwargs)
        if drop["on"]:  # the last 3 tests "never reported"
            result.tests[-3:] = [
                t.model_copy(update={"result": "not_proven", "message": ""})
                for t in result.tests[-3:]
            ]
        return result

    monkeypatch.setattr(loop, "run_tests", quiet_runner)
    factory = RecordingFactory()

    _, outcome = build(settings, request_id, factory)

    assert outcome == "interrupted"
    assert build_state(settings, request_id).step == "b_interrupted"
    rounds = rounds_of(settings, request_id)
    assert len(rounds) == 1 and len(rounds[0].layer_b.not_proven) == 3
    assert not rounds[0].layer_b.ok and rounds[0].failure_report is not None
    assert loop.NOT_PROVEN_TEXT in chat(settings, request_id, "assistant")
    assert len(factory.code_calls()) == 2  # round 1 only: nobody was asked to fix anything

    drop["on"] = False  # Run again: the same round is replaced, not a new round used
    flow.try_again(settings, request_id, flow.get_revision(settings, request_id))
    loop.run_build(settings, request_id, factory)

    rows = rounds_of(settings, request_id)
    assert rows[0].layer_b.not_proven  # the old row stays as the record (rounds are append-only)
    assert rows[1].round == 2 and not rows[1].layer_b.not_proven
    assert loop._rounds_used(rows[:1]) == 0


def test_b1_6_get_help_after_not_proven_says_it_is_the_assistants_problem(
    settings, request_id, monkeypatch
):
    real = loop.run_tests

    def quiet_runner(*args, **kwargs):
        result = real(*args, **kwargs)
        result.tests[-1] = result.tests[-1].model_copy(update={"result": "not_proven"})
        return result

    monkeypatch.setattr(loop, "run_tests", quiet_runner)
    build(settings, request_id, RecordingFactory())
    state = build_state(settings, request_id)
    assert flow.is_system_failure(state)
    server, _ = flow._build_buttons(state, False)
    assert (flow.HELP_KEY, "Send to my senior") in server

    flow.request_help(settings, request_id, flow.get_revision(settings, request_id))

    said = chat(settings, request_id, "assistant")
    assert NOT_PROVEN_TEXT in said and SYSTEM_HELP_LINE in said
    assert SYSTEM_HELP_LINE.startswith("This looks like a problem in the Developer Assistant")


def test_b1_6_a_developer_caused_failure_keeps_the_old_get_help_words():
    state = BuildState(
        request_id="CVDA-2026-0001", step="b_interrupted", message="The server restarted."
    )
    server, _ = flow._build_buttons(state, False)
    assert not flow.is_system_failure(state)
    assert (flow.HELP_KEY, "Get help") in server


def test_6_6_a_tester_that_misses_a_case_twice_means_unable_with_nothing_written(
    settings, request_id, monkeypatch
):
    switches(monkeypatch, "bad_tests")
    factory = RecordingFactory()

    _, outcome = build(settings, request_id, factory)

    assert outcome == "unable"
    state = build_state(settings, request_id)
    assert state.step == "b_unable" and state.message == flow.UNABLE_MESSAGE
    assert request_status(settings, request_id) == "READY_TO_BUILD"
    assert rounds_of(settings, request_id) == [] and factory.code_calls() == []
    assert [f.kind for f in files_of(settings, request_id)] == ["contract"]
    assert "Unable to assess" in chat(settings, request_id, "assistant")[-1]
    assert run_row(settings, request_id).label == "Unable to assess"
    assert len(factory.prompts("tester")) == 2  # two attempts, then it gives up


def test_6_19_an_ai_that_does_not_answer_pauses_the_build_and_uses_no_round(
    settings, request_id, monkeypatch
):
    switches(monkeypatch, "no_answer")

    _, outcome = build(settings, request_id)

    assert outcome == "interrupted"
    state = build_state(settings, request_id)
    assert (state.step, state.current_round) == ("b_interrupted", 0)
    assert "did not answer" in state.message
    assert request_status(settings, request_id) == "BUILDING"  # the build is still open
    assert rounds_of(settings, request_id) == []
    assert any(
        line.startswith("The build paused:") for line in chat(settings, request_id, "assistant")
    )


def test_6_12_an_http_400_reply_pauses_with_the_too_big_message_and_uses_no_round(
    settings, request_id, monkeypatch
):
    switches(monkeypatch, "too_big")

    _, outcome = build(settings, request_id)

    assert outcome == "interrupted"
    state = build_state(settings, request_id)
    assert state.step == "b_interrupted" and state.message.startswith(
        "This file is too big to send to the AI in one go."
    )
    assert rounds_of(settings, request_id) == []


def test_a_missing_reference_folder_pauses_before_any_ai_call(
    make_settings, published_rulebook, tmp_path
):
    settings = make_settings(sandbox_source_dir=tmp_path / "nowhere")
    request_id = ready_with_workspace(settings)[0]
    factory = RecordingFactory()

    _, outcome = build(settings, request_id, factory)

    assert outcome == "interrupted" and factory.calls == []
    assert "DA_SANDBOX_SOURCE_DIR" in build_state(settings, request_id).message


def test_a_file_whose_edit_blocks_failed_is_not_kept_as_finished_for_a_resume(
    settings, request_id, monkeypatch
):
    """Code review round 1: a pause must not turn a failed edit into a pass."""
    switches(monkeypatch, "bad_edit")

    build(settings, request_id)

    rows = [f for f in files_of(settings, request_id, kind="code") if f.path == MODIFY]
    assert rows[0].round == 1 and rows[0].made_by == "system"  # marked: not a clean file
    assert all(
        f.made_by == "generator"
        for f in files_of(settings, request_id, kind="code")
        if f.path == CREATE
    )


def test_a_failure_before_the_inputs_are_read_pauses_the_build_instead_of_leaving_it_running(
    settings, request_id, monkeypatch
):
    def boom(self):
        raise RuntimeError("database busy")

    monkeypatch.setattr(loop._Run, "_load", boom)
    flow.start_build(settings, request_id, 0)

    outcome = loop.run_build(settings, request_id)

    assert outcome == "interrupted"
    state = build_state(settings, request_id)
    assert state.step == "b_interrupted" and "could not start" in state.message


def test_a_thread_for_an_older_build_does_not_run_the_newer_build(settings, request_id):
    """Code review round 2: run_build(build_number=...) runs only that build."""
    flow.start_build(settings, request_id, 0)  # build 1 is the running build
    factory = RecordingFactory()

    assert loop.run_build(settings, request_id, factory, build_number=7) == "cancelled"

    assert factory.calls == []  # nothing was asked of the AI
    assert flow.get_state(settings, request_id).step == "b_running"  # and nothing was changed
    assert loop.run_build(settings, request_id, build_number=1) == "done"
