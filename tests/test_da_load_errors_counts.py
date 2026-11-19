"""Fix NP step 4: honest counts (NP-4) and a Resume that does not pile up rows (NP-5)."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_load_errors import load_failed_text
from layouts.da_build_panel import _layer_b_state
from pydantic_classes.da_build_models import (
    LayerAResult,
    LayerBResult,
    LoadError,
    RoundRecord,
    TestOutcome,
)
from tests.da_build_play import RecordingFactory, progress_of, ready_with_workspace, rounds_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


def failed_load(count=6, fault="missing_library"):
    rows = [TestOutcome(name=f"t{i}", result="not_run") for i in range(count)]
    error = LoadError(kind="import", error_type="ModuleNotFoundError", fault=fault)
    return LayerBResult(tests=rows, load_error=error)


def test_a_load_error_counts_no_test_as_run():
    result = failed_load()
    assert load_failed_text(result) == "0 of 6 ran: the test file could not load"
    assert result.ran_count == 0
    assert _layer_b_state(result)[0] == "0 of 6 ran: the test file could not load"


def a_record():
    return RoundRecord(
        request_id="CVDA-2026-0001", build_number=1, round=1, layer_a=LayerAResult(),
        layer_b=failed_load(fault="planned_code"),
    )  # fmt: skip


def test_the_banner_and_a_failed_check_run_do_not_say_zero_tests_failed():
    """Review round 2: the red banner and the Check-my-edits message use the load-error words."""
    record = a_record()
    banner = flow._failed_banner(record, 6, 3)
    assert "0 of 6 ran: the test file could not load" in banner and "tests failed" not in banner

    said = []

    @contextmanager
    def turn():
        yield None

    stub = SimpleNamespace(_turn=turn, _close=lambda tx, *args: said.append(args[-1]))
    loop._Run._finish_check_failed(stub, record)
    assert "0 of 6 ran: the test file could not load" in said[0] and "breaks" not in said[0]


def test_the_final_sentence_says_the_file_still_could_not_load():
    text = loop._finish_text(False, 3, "Not passing", [a_record()], 6)
    assert "still could not load" in text and "test(s) still fail" not in text


def test_a_normal_result_is_counted_as_before():
    result = LayerBResult(tests=[TestOutcome(name="a", result="pass")])
    assert load_failed_text(result) is None
    assert _layer_b_state(result)[0] == "1 of 1 passed"


def test_np5_resume_twice_leaves_one_layer_a_and_one_layer_b_line(make_settings, monkeypatch):
    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]
    real = loop.run_tests

    def runner(*args, **kwargs):
        result = real(*args, **kwargs)
        result.tests = [t.model_copy(update={"result": "not_run"}) for t in result.tests]
        result.load_error = LoadError(
            kind="import", error_type="ModuleNotFoundError", message="No module named 'openpyxl'"
        )
        return result

    monkeypatch.setattr(loop, "run_tests", runner)
    factory = RecordingFactory()
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id, factory) == "interrupted"
    for _ in range(2):
        flow.try_again(settings, request_id, flow.get_revision(settings, request_id))
        assert loop.run_build(settings, request_id, factory) == "interrupted"

    lines = [p.text for p in progress_of(settings, request_id)]
    assert len([t for t in lines if t.startswith("Layer A")]) == 1
    assert len([t for t in lines if t.startswith("Layer B")]) == 1
    assert "0 of" in next(t for t in lines if t.startswith("Layer B"))
    assert len(rounds_of(settings, request_id)) == 3  # the audit trail keeps every run
