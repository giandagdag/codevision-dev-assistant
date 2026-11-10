"""Phase 9 step 12a: the safety-net flow, write, check, fix calls and drop (tests 9-27, 9-28, 9-30
flow part, 9-33). No real AI or sandbox: the scripted fake client and a small runner that runs the
test file in a plain subprocess on the made-up code."""

import ast
import re
import subprocess
import sys

import pytest

from agents import da_build_agent as build_agent
from agents import da_discover_flow as discover
from agents import da_safety_net_flow as net_flow
from agents.da_build_agent import ScriptedBuildClient
from agents.da_build_checks import find_test_methods
from agents.da_llm_client import LLMClientError
from agents.da_safety_net_checks import DROPPED_REASON
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_enhance import (
    EnhanceError,
    read_enhance_state,
    read_safety_nets,
)
from db_table_functions.db_tbl_da_understand import StaleRevisionError, list_messages
from pydantic_classes.da_build_models import LayerBResult, TestOutcome
from tests import da_play
from tests.test_da_enhance_discover import confirmed_enhance

pytestmark = pytest.mark.usefixtures("published_rulebook")


class Runner:
    """Runs the net's test file on the baseline code in a plain subprocess; counts the runs."""

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.runs = 0

    def __call__(self, test_code, files):
        self.runs += 1
        for path, text in files.items():
            target = self.tmp_path / path.removeprefix("src/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        (self.tmp_path / "net_checks.py").write_text(test_code, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, "-m", "unittest", "net_checks"],
            cwd=self.tmp_path, capture_output=True, text=True, timeout=60,
        )
        failing = set(re.findall(r"^(?:FAIL|ERROR): (test_\w+)", done.stderr, re.MULTILINE))
        names = list(find_test_methods(ast.parse(test_code)))
        return LayerBResult(
            tests=[TestOutcome(name=n, result="fail" if n in failing else "pass") for n in names]
        )


class Flaky:
    """The scripted Tester for the first call; then the AI cannot be reached."""

    model = "fake"

    def __init__(self):
        self.inner = ScriptedBuildClient("tester")
        self.calls = 0

    def complete(self, prompt, system=None):
        self.calls += 1
        if self.calls > 1:
            raise LLMClientError("The AI could not be reached.")
        return self.inner.complete(prompt, system)


def switches(monkeypatch, *names):
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset(names))


def at_s_writing(settings):
    """An enhance request taken through Understand and Discover to the safety-net step."""
    request_id = confirmed_enhance(settings)
    view = discover.start_discovery(settings, request_id, 0)
    discover.confirm_discovery(settings, request_id, view.revision)
    return request_id


def state_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_enhance_state(conn, request_id)


def nets_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_safety_nets(conn, request_id)


def events_of(settings, request_id):
    return [e.event_type for e in list_audit_events(settings.db_path, request_id)]


def test_confirming_discovery_sends_an_enhance_request_to_the_safety_net(make_settings):
    settings = make_settings()
    request_id = confirmed_enhance(settings)
    assert state_of(settings, request_id).step == "e_fresh"

    view = discover.start_discovery(settings, request_id, 0)
    discover.confirm_discovery(settings, request_id, view.revision)

    assert state_of(settings, request_id).step == "s_writing"


def test_confirming_discovery_leaves_a_new_program_request_alone(make_settings):
    settings = make_settings()
    request_id = da_play.to_confirmed(settings).request.request_id
    view = discover.start_discovery(settings, request_id, 0)

    discover.confirm_discovery(settings, request_id, view.revision)

    assert state_of(settings, request_id) is None


def test_9_27_a_wrong_case_is_fixed_once_and_the_net_goes_to_review(make_settings, tmp_path):
    settings = make_settings()
    request_id = at_s_writing(settings)
    runner = Runner(tmp_path)
    revision = state_of(settings, request_id).revision

    view = net_flow.run_safety_net(settings, request_id, revision, runner)

    assert view.step == "s_review"
    [row] = nets_of(settings, request_id)
    assert [c.id for c in row.net.cases] == ["S-1"]
    assert row.proof["proven"] == ["S-1"] and row.proof["dropped"] == []
    assert row.proof["fix_calls"] == 1 and runner.runs == 2  # wrong at first, right after the fix
    assert not row.accepted and row.record_version == 1
    assert row.fingerprint
    events = events_of(settings, request_id)
    assert "safety_net_written" in events and "safety_net_proved" in events
    assert list_messages(settings.db_path, request_id)[-1].text.startswith(
        "Safety net: 1 test(s) capture today's behaviour. All 1 pass"
    )


def test_9_27_a_case_that_keeps_failing_is_dropped_and_listed_as_not_covered(
    make_settings, tmp_path, monkeypatch
):
    switches(monkeypatch, "net_case_keeps_failing")
    settings = make_settings()
    request_id = at_s_writing(settings)
    runner = Runner(tmp_path)

    view = net_flow.run_safety_net(
        settings, request_id, state_of(settings, request_id).revision, runner
    )

    assert view.step == "s_review"
    [row] = nets_of(settings, request_id)
    assert row.net.cases == [] and row.net.test_code == ""
    assert row.proof["dropped"] == ["S-1"] and row.proof["fix_calls"] == 2
    assert runner.runs == 3  # the first run, and one more after each fix call
    reasons = {item.item: item.reason for item in row.net.not_covered}
    assert reasons["format_expiry"] == DROPPED_REASON
    assert "no test could be made to pass" in list_messages(settings.db_path, request_id)[-1].text


def test_9_28_an_unusable_reply_gives_s_unable_and_try_again_works(
    make_settings, tmp_path, monkeypatch
):
    switches(monkeypatch, "net_unusable")
    settings = make_settings()
    request_id = at_s_writing(settings)
    runner = Runner(tmp_path)

    view = net_flow.run_safety_net(
        settings, request_id, state_of(settings, request_id).revision, runner
    )

    assert view.step == "s_unable" and nets_of(settings, request_id) == []
    assert list_messages(settings.db_path, request_id)[-1].text.startswith(
        "The safety net could not be written."
    )
    assert "safety_net_unable" in events_of(settings, request_id)
    assert runner.runs == 0
    switches(monkeypatch)  # "Try again", and this time the AI answers

    again = net_flow.run_safety_net(settings, request_id, view.revision, runner)

    assert again.step == "s_review" and len(nets_of(settings, request_id)) == 1


def test_a_sandbox_that_did_not_run_is_not_the_codes_fault(make_settings):
    settings = make_settings()
    request_id = at_s_writing(settings)

    def broken(_code, _files):
        return LayerBResult(ran=False, error="The sandbox could not start: no folder.")

    view = net_flow.run_safety_net(
        settings, request_id, state_of(settings, request_id).revision, broken
    )

    assert view.step == "s_unable" and nets_of(settings, request_id) == []
    assert "no folder" in list_messages(settings.db_path, request_id)[-1].text


def test_an_ai_that_cannot_be_reached_for_the_fix_call_gives_s_unable(make_settings, tmp_path):
    settings = make_settings()
    request_id = at_s_writing(settings)

    view = net_flow.run_safety_net(
        settings, request_id, state_of(settings, request_id).revision, Runner(tmp_path),
        client=Flaky(),
    )

    assert view.step == "s_unable" and nets_of(settings, request_id) == []


def test_9_30_a_stale_window_a_wrong_step_and_a_missing_runner_are_refused(
    make_settings, tmp_path
):
    settings = make_settings()
    request_id = at_s_writing(settings)
    revision = state_of(settings, request_id).revision

    with pytest.raises(StaleRevisionError):
        net_flow.run_safety_net(settings, request_id, revision - 1, Runner(tmp_path))
    with pytest.raises(EnhanceError, match="sandbox is not connected"):
        net_flow.run_safety_net(settings, request_id, revision, None)
    done = net_flow.run_safety_net(settings, request_id, revision, Runner(tmp_path))
    with pytest.raises(EnhanceError, match="not available at this step"):
        net_flow.run_safety_net(settings, request_id, done.revision, Runner(tmp_path))
    assert len(nets_of(settings, request_id)) == 1


def test_a_restart_at_s_writing_just_runs_again(make_settings, tmp_path):
    settings = make_settings()
    request_id = at_s_writing(settings)
    # Nothing is saved until the whole run is done, so a stopped run leaves s_writing and no row.
    assert state_of(settings, request_id).step == "s_writing"
    assert nets_of(settings, request_id) == []

    view = net_flow.run_safety_net(
        settings, request_id, state_of(settings, request_id).revision, Runner(tmp_path)
    )

    assert view.step == "s_review"
