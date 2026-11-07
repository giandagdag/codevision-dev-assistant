"""Layer C inside the loop: pause, Try again, Stop, restart, check 1, the cap and the write job
(spec 7-4, 7-14, 7-25, 7-26, 7-27, 7-28, 7-33)."""

import pytest

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_build_runner as runner
from agents import da_tester_flow as tflow
from agents import da_tester_review as review_text
from agents.da_llm_client import ContextTooLargeError, LLMClientError
from pydantic_classes.da_tester_models import Finding
from tests.da_build_play import (
    RecordingFactory,
    build_state,
    chat,
    event_types,
    files_of,
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


def start(settings, request_id):
    return flow.start_build(settings, request_id, flow.get_revision(settings, request_id))


class ReviewHook(RecordingFactory):
    """Runs `action(prompt)` just before every Tester REVIEW call (not the test-writing call)."""

    def __init__(self, action):
        super().__init__()
        self.action = action

    def __call__(self, settings, role):
        real = super().__call__(settings, role)
        action = self.action

        class Client:
            model = real.model

            def complete(self, prompt, system=None):
                if review_text.REVIEW_MARKER in prompt:
                    action(prompt)
                return real.complete(prompt, system)

        return Client()


def failing(error):
    def action(prompt):
        raise error

    return action


# --- the Tester cannot answer or the input is too big (7-25, 7-26) ---


@pytest.mark.parametrize(
    ("error", "words"),
    [
        (LLMClientError("no answer"), "the AI did not answer"),
        (ContextTooLargeError("HTTP 400"), "too big for the Tester"),
    ],
)
def test_7_25_26_a_tester_pause_uses_no_round_and_try_again_repeats_only_the_review(
    settings, request_id, error, words
):
    start(settings, request_id)
    assert loop.run_build(settings, request_id, ReviewHook(failing(error))) == "interrupted"

    paused = build_state(settings, request_id)
    assert paused.step == "b_interrupted" and words in paused.message
    assert paused.message.startswith("The Tester review paused")
    assert request_status(settings, request_id) == "TESTER_REVIEW"
    assert len(rounds_of(settings, request_id)) == 2  # round 1 failed, round 2 passed A and B

    flow.try_again(settings, request_id, flow.get_revision(settings, request_id))
    factory = RecordingFactory()
    assert loop.run_build(settings, request_id, factory) == "done"

    code = factory.code_calls()
    assert "Round: 2" not in " ".join(code)  # round 2 was NOT written again
    assert run_row(settings, request_id).rounds_used == 3
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"


# --- Stop and restart during the review (7-27, 7-28) ---


def test_7_27_stop_during_the_tester_review_writes_nothing_and_goes_back(settings, request_id):
    start(settings, request_id)
    seen = []

    def stop(prompt):
        seen.append(build_state(settings, request_id).step)
        flow.stop_build(settings, request_id, flow.get_revision(settings, request_id))

    assert loop.run_build(settings, request_id, ReviewHook(stop)) == "cancelled"

    assert seen == ["b_tester_review"]
    assert request_status(settings, request_id) == "READY_TO_BUILD"
    assert "build_stopped" in event_types(settings, request_id)
    assert tflow.get_tester_view(settings, request_id).review is None  # nothing saved


def test_7_28_a_restart_during_the_tester_review_pauses_and_try_again_repeats_it(
    settings, request_id
):
    start(settings, request_id)

    def restart(prompt):
        assert runner.recover_interrupted_builds(settings) == [request_id]

    assert loop.run_build(settings, request_id, ReviewHook(restart)) == "cancelled"

    paused = build_state(settings, request_id)
    assert paused.step == "b_interrupted" and paused.message == flow.SERVER_RESTART_MESSAGE
    flow.try_again(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    assert run_row(settings, request_id).rounds_used == 3


# --- check 1: no test for a criterion (7-4) ---


def test_7_4_a_criterion_without_a_test_ends_not_passing_without_another_round(
    settings, request_id, monkeypatch
):
    missing = Finding(
        finding_id="F-0",
        check=1,
        severity="must_fix",
        cites="AC-9",
        message="No test",
        made_by="plain",
        fixable=False,
    )
    monkeypatch.setattr(review_text, "check_criteria_have_tests", lambda record, text: [missing])
    start(settings, request_id)

    assert loop.run_build(settings, request_id) == "done"

    assert request_status(settings, request_id) == "NOT_PASSING"
    assert run_row(settings, request_id).rounds_used == 2  # no extra round was used
    assert "Criterion AC-9 has no test. Change the approach or get help." in chat(
        settings, request_id, "assistant"
    )
    assert files_of(settings, request_id, kind="code")  # the code is still there


# --- the cap (7-14) and the write job (7-33) ---


def test_7_14_and_7_33_the_cap_keeps_the_code_and_the_write_job_holds_code_only(
    settings, request_id, monkeypatch
):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"review_must_fix_always"}))
    start(settings, request_id)
    assert loop.run_build(settings, request_id) == "done"

    assert request_status(settings, request_id) == "NOT_PASSING"
    assert run_row(settings, request_id).label == "Not passing"
    view = tflow.get_tester_view(settings, request_id)
    assert [r.finding.severity for r in view.rows] == ["must_fix"]  # still open on the tab
    job = flow.prepare_write(settings, request_id, flow.get_revision(settings, request_id))
    paths = [item.path for item in job.files]
    assert paths and all(not p.startswith("tests/") and "report" not in p for p in paths)
    assert {f.kind for f in files_of(settings, request_id)} >= {"code"}
