"""Background builds: the thread, the parallel limit and recovery after a restart (6-27, 6-28)."""

import threading
import time

import pytest

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_runner as runner
from agents.da_llm_client import LLMClientError
from tests.da_build_play import (
    RecordingFactory,
    build_state,
    chat,
    event_types,
    files_of,
    progress_of,
    ready_with_workspace,
    request_status,
    run_row,
)

pytestmark = pytest.mark.usefixtures("published_rulebook")

CREATE_PATH = "src/agents/excel_processor.py"
MODIFY_PATH = "src/agents/upload_validator.py"


@pytest.fixture(autouse=True)
def clean_runner():
    """The runner keeps its queue in the module, so every test starts with it empty."""
    yield
    deadline = time.monotonic() + 10
    while runner.active_count() and time.monotonic() < deadline:
        time.sleep(0.05)
    runner._waiting.clear()
    runner._threads.clear()


@pytest.fixture
def settings(make_settings):
    return make_settings()


def started(settings, request_id):
    return flow.start_build(settings, request_id, flow.get_revision(settings, request_id))


def wait_for(condition, seconds=15.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


class GatedFactory(RecordingFactory):
    """The first AI call of every request waits at a gate, so builds stay 'running' on purpose."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()
        self.reached: set[str] = set()
        self.lock = threading.Lock()

    def __call__(self, settings, role):
        real = super().__call__(settings, role)
        outer = self

        class Client:
            model = real.model

            def complete(self, prompt, system=None):
                request_id = _request_id_in(prompt)
                with outer.lock:
                    outer.reached.add(request_id)
                outer.gate.wait(30)
                return real.complete(prompt, system)

        return Client()


def _request_id_in(prompt: str) -> str:
    import re

    return re.search(r"CVDA-\d{4}-\d{4}", prompt).group(0)


def test_a_build_runs_to_its_end_on_a_background_thread(settings):
    request_id = ready_with_workspace(settings)[0]
    started(settings, request_id)

    thread = runner.submit_build(settings, request_id)
    thread.join(timeout=60)

    assert not thread.is_alive() and thread.daemon
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    assert build_state(settings, request_id).step == "b_done"
    assert runner.active_count() == 0


def test_submitting_the_same_request_twice_runs_one_thread(settings):
    request_id = ready_with_workspace(settings)[0]
    started(settings, request_id)
    factory = GatedFactory()

    first = runner.submit_build(settings, request_id, factory)
    assert wait_for(lambda: factory.reached)
    second = runner.submit_build(settings, request_id, factory)
    factory.gate.set()
    first.join(timeout=60)

    assert second is first  # rule B4
    assert len(factory.prompts("tester")) == 1  # the tests were written once


def test_6_28_a_third_build_waits_for_a_free_slot_then_runs(settings):
    ids = [ready_with_workspace(settings)[0] for _ in range(3)]
    for request_id in ids:
        started(settings, request_id)
    factory = GatedFactory()

    threads = [runner.submit_build(settings, request_id, factory) for request_id in ids]
    assert wait_for(lambda: len(factory.reached) == 2)
    third = ids[2]
    assert wait_for(
        lambda: any(p.text == runner.waiting_text(1) for p in progress_of(settings, third))
    )

    assert factory.reached == set(ids[:2]) and third not in factory.reached
    assert runner.active_count() == 2
    assert build_state(settings, third).step == "b_running"

    factory.gate.set()
    for thread in threads:
        thread.join(timeout=90)
    assert [request_status(settings, r) for r in ids] == ["READY_FOR_REVIEW"] * 3


def test_a_build_stopped_while_it_waits_never_runs(settings):
    ids = [ready_with_workspace(settings)[0] for _ in range(3)]
    for request_id in ids:
        started(settings, request_id)
    factory = GatedFactory()
    threads = [runner.submit_build(settings, r, factory) for r in ids]
    third = ids[2]
    assert wait_for(
        lambda: any(p.text == runner.waiting_text(1) for p in progress_of(settings, third))
    )

    flow.stop_build(settings, third, flow.get_revision(settings, third))
    factory.gate.set()
    for thread in threads:
        thread.join(timeout=90)

    assert third not in factory.reached
    assert request_status(settings, third) == "READY_TO_BUILD"
    assert files_of(settings, third) == []
    assert runner.active_count() == 0


# --- server restart (row 6-27) ---


def test_6_27_a_build_marked_running_at_start_up_is_paused_with_the_restart_message(settings):
    request_id = ready_with_workspace(settings)[0]
    started(settings, request_id)  # marked running, but no thread: the server was restarted

    fixed = runner.recover_interrupted_builds(settings)

    assert fixed == [request_id]
    state = build_state(settings, request_id)
    assert (state.step, state.message) == ("b_interrupted", flow.SERVER_RESTART_MESSAGE)
    assert request_status(settings, request_id) == "BUILDING"
    assert chat(settings, request_id, "assistant")[-1] == (
        "The build paused: The server restarted during your build."
    )
    assert "build_interrupted" in event_types(settings, request_id)
    assert runner.recover_interrupted_builds(settings) == []  # nothing is fixed twice


def test_6_27_try_again_after_a_restart_does_not_regenerate_finished_files(settings):
    request_id = ready_with_workspace(settings)[0]
    started(settings, request_id)

    class Dies(RecordingFactory):
        """The server 'restarts' during the second code file: the AI call raises, so the first
        file is saved and the build stops mid-round."""

        def __call__(self, settings_, role):
            real = super().__call__(settings_, role)

            class Client:
                model = real.model

                def complete(self, prompt, system=None):
                    if (
                        agent.CODE_MARKER in prompt
                        and "upload_validator" in prompt.split("File:")[1][:60]
                    ):
                        raise LLMClientError("restart")
                    return real.complete(prompt, system)

            return Client()

    from agents import da_build_loop as loop

    loop.run_build(settings, request_id, Dies())
    flow.try_again(settings, request_id, flow.get_revision(settings, request_id))
    assert build_state(settings, request_id).step == "b_running"  # 'resumed', then the server dies
    assert runner.recover_interrupted_builds(settings) == [request_id]

    flow.try_again(settings, request_id, flow.get_revision(settings, request_id))
    factory = RecordingFactory()
    loop.run_build(settings, request_id, factory)

    first_file_asked = [p for p in factory.code_calls() if f"File: {CREATE_PATH}" in p]
    assert all("Round: 2" in p for p in first_file_asked)  # never asked again for round 1
    assert run_row(settings, request_id).rounds_used == 2
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"


def test_stop_then_build_again_while_the_old_thread_is_still_busy_runs_the_new_build(settings):
    """Code review round 1: the old thread (stuck in a slow AI call) must not stand in for the
    new build's thread, or the new build would show 'running' for ever."""
    request_id = ready_with_workspace(settings)[0]
    started(settings, request_id)
    factory = GatedFactory()
    old = runner.submit_build(settings, request_id, factory)
    assert wait_for(lambda: factory.reached)  # the old build is inside its first AI call

    flow.stop_build(settings, request_id, flow.get_revision(settings, request_id))
    second = started(settings, request_id)
    new = runner.submit_build(settings, request_id, factory)
    factory.gate.set()  # the slow AI call finally returns
    old.join(timeout=90)
    new.join(timeout=90)

    assert new is not old and second.build_number == 2
    state = build_state(settings, request_id)
    assert (state.build_number, state.step) == (2, "b_done")
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    assert run_row(settings, request_id, 1).ended_at is not None  # build 1 stayed stopped
    assert run_row(settings, request_id, 2).label == "Ready with warnings"
