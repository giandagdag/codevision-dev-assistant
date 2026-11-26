"""Fix G9 T4 and T5 (G9-10, G9-11): the requirement is the referee when a frozen test keeps failing
the same way."""

import pytest

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_test_expectations as expectations
from pydantic_classes.da_build_models import LayerBResult, RoundRecord, TestOutcome
from tests.da_build_play import (
    RecordingFactory,
    event_types,
    ready_with_workspace,
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


def _build(settings, request_id, monkeypatch, factory):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"always_fail"}))
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    return loop.run_build(settings, request_id, factory)


def _after_round_two(monkeypatch, bad_once: bool):
    """The first expectation check after round 2 says 'invented' (bad_once), or never."""
    state = {"two_done": False, "spent": False}
    original = loop._Run._one_round

    def spy(self, number, contract, tests):
        passed = original(self, number, contract, tests)
        state["two_done"] = state["two_done"] or number == 2
        return passed

    def check(code, wanted):
        if bad_once and state["two_done"] and not state["spent"]:
            state["spent"] = True
            return {name: ["Invented words here"] for name in _methods(code)}
        return {}

    monkeypatch.setattr(loop._Run, "_one_round", spy)
    monkeypatch.setattr(expectations, "invented_by_method", check)


def _methods(code):
    import ast

    return [n.name for n in ast.walk(ast.parse(code)) if isinstance(n, ast.FunctionDef)]


def test_g9_10_an_unbacked_test_is_rewritten_once_and_the_round_is_not_counted(
    settings, request_id, monkeypatch
):
    _after_round_two(monkeypatch, bad_once=True)

    _build(settings, request_id, monkeypatch, RecordingFactory())

    rounds = rounds_of(settings, request_id)
    assert [r.referee_only for r in rounds] == [False, False, True, False]
    assert "test_rewritten_by_referee" in event_types(settings, request_id)
    assert run_row(settings, request_id).rounds_used == 3  # the referee run used no round


def test_g9_11_a_backed_test_sends_the_code_back_with_the_expected_value(
    settings, request_id, monkeypatch
):
    _after_round_two(monkeypatch, bad_once=False)
    factory = RecordingFactory()

    _build(settings, request_id, monkeypatch, factory)

    assert not any(r.referee_only for r in rounds_of(settings, request_id))
    assert "test_rewritten_by_referee" not in event_types(settings, request_id)
    assert "Change the code, not the test." in factory.code_calls()[-1]


def _run(*results):
    return LayerBResult(tests=[TestOutcome(name=n, result=r, message=m) for n, r, m in results])


def test_the_same_actual_value_twice_is_stuck_and_a_new_value_is_progress():
    older = _run(("test_a", "fail", "'x' != 'y'"), ("test_b", "fail", "1 != 2"))
    newer = _run(("test_a", "fail", "'x' != 'y'"), ("test_b", "fail", "1 != 3"))

    assert expectations.same_failures(older, newer) == {"test_a": "'x' != 'y'"}
    assert expectations.same_failures(None, newer) == {}


def test_an_old_round_record_reads_as_a_normal_round():
    assert RoundRecord.model_fields["referee_only"].default is False
