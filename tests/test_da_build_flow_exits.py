"""Stop, Try again, Get help and Change the approach (rows 6-19, 6-25, 6-26, 6-30, rules B5-B7)."""

import pytest

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_approach_flow import CAP_MESSAGE
from agents.da_llm_client import LLMClientError
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_state, save_approach_state
from db_table_functions.db_tbl_da_build import BuildError
from db_table_functions.db_tbl_da_workspace import read_known_files, read_workspace_state
from tests.da_approach_play import events_of
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


def revision(settings, request_id):
    return flow.get_revision(settings, request_id)


def start(settings, request_id):
    return flow.start_build(settings, request_id, revision(settings, request_id))


def written_paths(settings, request_id) -> set[str]:
    with open_db(settings.db_path) as conn:
        known = read_known_files(conn, request_id)
    return {path for path, item in known.items() if item.kind == "written"}


def pause_it(settings, request_id, monkeypatch):
    """Start a build that pauses at b_interrupted because the AI does not answer."""
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"no_answer"}))
    start(settings, request_id)
    assert loop.run_build(settings, request_id) == "interrupted"
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset())


class FlakyFactory(RecordingFactory):
    """Like RecordingFactory, but the AI fails to answer on chosen call numbers (1 = first)."""

    def __init__(self, fail_on=()):
        super().__init__()
        self.fail_on = set(fail_on)
        self.number = 0

    def __call__(self, settings, role):
        real = super().__call__(settings, role)
        outer = self

        class Client:
            model = real.model

            def complete(self, prompt, system=None):
                outer.number += 1
                if outer.number in outer.fail_on:
                    raise LLMClientError("The AI did not answer (test).")
                return real.complete(prompt, system)

        return Client()


# --- Stop build (B5, row 6-26) ---


def test_6_26_stop_ends_the_build_with_no_label_and_writes_nothing(
    settings, request_id, monkeypatch
):
    written_before = written_paths(settings, request_id)
    pause_it(settings, request_id, monkeypatch)

    state = flow.stop_build(settings, request_id, revision(settings, request_id))

    assert state.step == "start" and request_status(settings, request_id) == "READY_TO_BUILD"
    run = run_row(settings, request_id)
    assert run.ended_at is not None and run.label == "" and run.stop_reason.startswith("Stopped")
    assert "build_stopped" in event_types(settings, request_id)
    assert "Nothing was written" in chat(settings, request_id, "assistant")[-1]
    assert written_paths(settings, request_id) == written_before  # the build wrote no new file


def test_stop_while_the_ai_is_working_cancels_the_loop_without_saving_anything_more(
    settings, request_id
):
    start(settings, request_id)
    stopped = []

    class StopsOnFirstCodeCall(RecordingFactory):
        def __call__(self, settings_, role):
            real = super().__call__(settings_, role)
            outer = self

            class Client:
                model = real.model

                def complete(self, prompt, system=None):
                    reply = real.complete(prompt, system)
                    if outer.agent.CODE_MARKER in prompt and not stopped:
                        stopped.append(
                            flow.stop_build(settings, request_id, revision(settings, request_id))
                        )
                    return reply

            return Client()

    outcome = loop.run_build(settings, request_id, StopsOnFirstCodeCall())

    assert outcome == "cancelled" and stopped
    assert request_status(settings, request_id) == "READY_TO_BUILD"
    assert [f.kind for f in files_of(settings, request_id)] == ["contract", "test"]  # no code kept
    assert rounds_of(settings, request_id) == []
    assert "build_passed" not in event_types(settings, request_id)


def test_stop_is_refused_when_nothing_is_running_to_stop(settings, request_id):
    start(settings, request_id)
    loop.run_build(settings, request_id)  # finishes: b_done

    with pytest.raises(BuildError, match="finished"):
        flow.stop_build(settings, request_id, revision(settings, request_id))


# --- Try again (6-19) and a new build after Stop (6-25) ---


def test_6_19_try_again_resumes_without_rewriting_finished_files_or_using_a_round(
    settings, request_id
):
    start(settings, request_id)
    factory = FlakyFactory(fail_on={4})  # call 4 = the second code file of round 1

    assert loop.run_build(settings, request_id, factory) == "interrupted"
    paused = build_state(settings, request_id)
    assert (paused.step, paused.current_round) == ("b_interrupted", 0)
    assert [f.path for f in files_of(settings, request_id, kind="code")] == [CREATE_PATH]

    resumed = flow.try_again(settings, request_id, revision(settings, request_id))
    assert resumed.step == "b_running" and "build_resumed" in event_types(settings, request_id)
    assert loop.run_build(settings, request_id, factory) == "done"

    code_calls = factory.code_calls()
    first_file = [p for p in code_calls if f"File: {CREATE_PATH}" in p and "Round: 1" in p]
    assert len(first_file) == 1  # the finished file was NOT asked for again
    run = run_row(settings, request_id)
    assert run.rounds_used == 2 and request_status(settings, request_id) == "READY_FOR_REVIEW"


CREATE_PATH = "src/agents/excel_processor.py"


def test_after_a_stop_the_next_build_asks_for_no_new_contract_or_tests(settings, request_id):
    start(settings, request_id)
    flaky = FlakyFactory(fail_on={3})  # the first code file fails, after contract and tests
    assert loop.run_build(settings, request_id, flaky) == "interrupted"
    flow.stop_build(settings, request_id, revision(settings, request_id))
    frozen = [f.kind for f in files_of(settings, request_id, 1)]
    assert frozen == ["contract", "test"]

    factory = RecordingFactory()
    second = start(settings, request_id)
    loop.run_build(settings, request_id, factory)

    assert second.build_number == 2
    assert factory.prompts("tester") == []  # the Tester was not asked again
    assert all(agent.CONTRACT_MARKER not in prompt for prompt in factory.prompts())
    assert run_row(settings, request_id, 2).rounds_used == 2  # a fresh budget of 3, two used


# --- Get help (B6, row 6-30) ---


@pytest.mark.parametrize("where", ["b_interrupted", "b_unable", "b_done"])
def test_6_30_get_help_escalates_from_a_paused_unable_or_finished_build(
    settings, request_id, monkeypatch, where
):
    if where == "b_interrupted":
        pause_it(settings, request_id, monkeypatch)
    elif where == "b_unable":
        monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"bad_tests"}))
        start(settings, request_id)
        assert loop.run_build(settings, request_id) == "unable"
    else:
        start(settings, request_id)
        loop.run_build(settings, request_id)

    flow.request_help(settings, request_id, revision(settings, request_id))

    assert request_status(settings, request_id) == "ESCALATION_REQUIRED"
    with open_db(settings.db_path) as conn:
        approach = read_approach_state(conn, request_id)
    assert approach.step == "escalated" and approach.open_item == f"Escalated in Build: {where}"
    assert events_of(settings, request_id, "escalated")[0].details["step"] == where
    assert run_row(settings, request_id).ended_at is not None  # no build is left open
    assert build_state(settings, request_id).step == "escalated"


def test_get_help_is_refused_while_the_build_is_running(settings, request_id):
    start(settings, request_id)

    with pytest.raises(BuildError, match="running"):
        flow.request_help(settings, request_id, revision(settings, request_id))


# --- Change the approach (B7) and Try again from b_unable ---


def unable(settings, request_id, monkeypatch):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"bad_tests"}))
    start(settings, request_id)
    assert loop.run_build(settings, request_id) == "unable"
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset())


def test_b7_change_the_approach_reopens_it_and_counts_as_a_change(
    settings, request_id, monkeypatch
):
    unable(settings, request_id, monkeypatch)
    with open_db(settings.db_path) as conn:
        before = read_approach_state(conn, request_id).change_count

    flow.change_approach(settings, request_id, revision(settings, request_id))

    assert request_status(settings, request_id) == "APPROACH_PROPOSED"
    with open_db(settings.db_path) as conn:
        approach = read_approach_state(conn, request_id)
        workspace = read_workspace_state(conn, request_id)
    assert (approach.step, approach.change_count) == ("change", before + 1)
    assert approach.change_from_tests is True
    assert workspace.step == "start" and workspace.last_check is None
    assert build_state(settings, request_id).step == "start"
    assert "approach_reopened" in event_types(settings, request_id)


def test_the_third_change_is_the_last(settings, request_id, monkeypatch):
    unable(settings, request_id, monkeypatch)
    with open_db(settings.db_path) as conn:
        approach = read_approach_state(conn, request_id)
        revision_now = approach.revision
        approach.change_count = 3
        save_approach_state(
            conn,
            approach,
            revision_now,
            __import__("datetime").datetime.now(__import__("datetime").UTC),
        )
        conn.commit()

    with pytest.raises(BuildError, match=CAP_MESSAGE.split(".")[0]):
        flow.change_approach(settings, request_id, revision(settings, request_id))


def test_try_again_from_unable_starts_a_new_build(settings, request_id, monkeypatch):
    unable(settings, request_id, monkeypatch)

    state = flow.try_again(settings, request_id, revision(settings, request_id))

    assert (state.step, state.build_number) == ("b_running", 2)
    assert request_status(settings, request_id) == "BUILDING"
    assert loop.run_build(settings, request_id) == "done"


def test_change_the_approach_is_only_offered_from_unable(settings, request_id, monkeypatch):
    pause_it(settings, request_id, monkeypatch)

    with pytest.raises(BuildError, match="paused"):
        flow.change_approach(settings, request_id, revision(settings, request_id))
