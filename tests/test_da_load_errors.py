"""Fix NP step 2: whose fault is a test file that cannot load (NP-1 loop part, NP-2, NP-3)."""

import dataclasses

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_sandbox, da_sandbox_python
from agents.da_check_words import is_system_message
from agents.da_load_errors import classify_load_error, is_system_pause, pause_text
from pydantic_classes.da_build_models import LayerBResult, LoadError
from tests.da_build_play import (
    CREATE,
    RecordingFactory,
    build_state,
    chat,
    ready_with_workspace,
    rounds_of,
)

pytestmark = pytest.mark.usefixtures("published_rulebook")

PLANNED = [CREATE, "src/agents/upload_validator.py"]


@pytest.fixture
def src(tmp_path):
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "upload_validator.py").write_text("")
    return tmp_path


def error(message, kind="import", error_type="ModuleNotFoundError", tail=()):
    return LoadError(kind=kind, error_type=error_type, message=message, traceback_tail=list(tail))


# --- the decision, in plain code ---


def test_a_library_the_server_lacks_is_missing_library(src):
    fault, module = classify_load_error(error("No module named 'openpyxl'"), src, PLANNED)
    assert (fault, module) == ("missing_library", "openpyxl")


def test_a_wrong_path_to_a_planned_file_is_planned_code(src):
    """The test imports `excel_processor` but the file sits under agents/."""
    fault, _ = classify_load_error(error("No module named 'excel_processor'"), src, PLANNED)
    assert fault == "planned_code"


def test_a_missing_name_inside_a_known_folder_is_planned_code(src):
    fault, _ = classify_load_error(error("No module named 'agents.nothing'"), src, PLANNED)
    assert fault == "planned_code"


def test_a_wrong_function_name_is_planned_code(src):
    message = "cannot import name 'convert' from 'agents.excel_processor' (x.py)"
    fault, _ = classify_load_error(error(message, error_type="ImportError"), src, PLANNED)
    assert fault == "planned_code"


def test_a_set_up_error_is_a_frozen_test_problem(src):
    fault, _ = classify_load_error(error("no data", kind="set_up"), src, PLANNED)
    assert fault == "frozen_test"


def test_a_set_up_error_inside_the_written_code_is_planned_code(src):
    tail = ['  File "/tmp/da_sandbox_x/src/agents/excel_processor.py", line 4', "ValueError: bad"]
    fault, _ = classify_load_error(
        error("bad", kind="set_up", error_type="ValueError", tail=tail), src, PLANNED
    )
    assert fault == "planned_code"


def test_another_error_is_planned_code_only_when_a_planned_file_is_in_the_trace(src):
    in_trace = ['  File "/tmp/x/src/agents/excel_processor.py", line 3', "NameError: oops"]
    other = error("oops", error_type="NameError", tail=in_trace)
    assert classify_load_error(other, src, PLANNED)[0] == "planned_code"
    own = error("bad", error_type="SyntaxError", tail=['  File "tests/t.py", line 1'])
    assert classify_load_error(own, src, PLANNED)[0] == "frozen_test"


def test_only_server_and_frozen_test_faults_pause_the_build():
    def result(fault):
        return LayerBResult(load_error=error("x").model_copy(update={"fault": fault}))

    assert is_system_pause(result("missing_library")) and is_system_pause(result("frozen_test"))
    assert not is_system_pause(result("planned_code")) and not is_system_pause(result(""))
    assert not is_system_pause(None) and not is_system_pause(LayerBResult())
    text = pause_text(result("missing_library"))
    assert is_system_message(text)
    assert text.startswith("The Developer Assistant's Python is missing")
    assert pause_text(result("missing_library"), "CodeVision's Python").startswith(
        "CodeVision's Python is missing `a library`."  # G3-8
    )
    # a paused build saved before Fix G3 still counts as the Developer Assistant's problem
    assert is_system_message("The server's Python is missing `openpyxl`. This needs the team.")


# --- inside the build loop (real sandbox, fake AI) ---


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def inject(monkeypatch, load_error):
    """Run the real sandbox, then make its result look like a file that could not load."""
    real = loop.run_tests

    def runner(*args, **kwargs):
        result = real(*args, **kwargs)
        result.tests = [
            t.model_copy(update={"result": "not_run", "message": "Did not run"})
            for t in result.tests
        ]
        result.load_error = load_error.model_copy()
        return result

    monkeypatch.setattr(loop, "run_tests", runner)


def build(settings, request_id, factory):
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    return loop.run_build(settings, request_id, factory)


def test_np1_a_missing_library_pauses_without_a_round_and_resume_never_calls_the_ai(
    settings, request_id, monkeypatch
):
    inject(monkeypatch, error("No module named 'openpyxl'"))
    factory = RecordingFactory()

    assert build(settings, request_id, factory) == "interrupted"

    said = chat(settings, request_id, "assistant")
    prefix = "The Developer Assistant's Python is missing `openpyxl`."
    assert any(t.startswith(prefix) for t in said)
    assert not any(t.startswith("The build paused:") for t in said)
    calls = len(factory.code_calls())
    for _ in range(2):  # Resume twice: the AI is never asked, no round is used
        flow.try_again(settings, request_id, flow.get_revision(settings, request_id))
        assert loop.run_build(settings, request_id, factory) == "interrupted"
    assert len(factory.code_calls()) == calls
    assert loop._rounds_used(rounds_of(settings, request_id)) == 0
    state = build_state(settings, request_id)
    assert flow.is_system_failure(state)  # NP-8: Get help offers Send to my senior
    assert ("Send to my senior") in [label for _, label in flow._build_buttons(state, False)[0]]


def test_g3_8_with_codevisions_python_set_the_words_name_it(
    settings, request_id, monkeypatch, tmp_path
):
    fake = tmp_path / "python.exe"
    fake.write_text("x")
    settings = dataclasses.replace(settings, codevision_python=str(fake))
    monkeypatch.setattr(da_sandbox_python, "_probe", lambda path, args: "3.14.1")
    # the real sandbox still runs on this app's Python (the fake file cannot start)
    monkeypatch.setattr(da_sandbox, "test_python", lambda s: da_sandbox_python.test_python(None))
    inject(monkeypatch, error("No module named 'openpyxl'"))

    assert build(settings, request_id, RecordingFactory()) == "interrupted"

    said = chat(settings, request_id, "assistant")
    assert any(t.startswith("CodeVision's Python is missing `openpyxl`.") for t in said)
    assert flow.is_system_failure(build_state(settings, request_id))


def test_np2_an_import_of_a_missing_planned_name_is_a_normal_failure(
    settings, request_id, monkeypatch
):
    message = "cannot import name 'convert' from 'agents.excel_processor'"
    tail = ['  File "/tmp/da_sandbox_x/src/agents/excel_processor.py", line 1', "ImportError: x"]
    inject(monkeypatch, error(message, error_type="ImportError", tail=tail))
    factory = RecordingFactory()

    build(settings, request_id, factory)

    rows = rounds_of(settings, request_id)
    assert len(rows) >= 2  # not a pause: the next round ran and used the budget
    assert rows[0].layer_b.load_error.fault == "planned_code"
    assert rows[0].failure_report is not None and rows[0].files_to_fix == [CREATE]
    assert any("cannot import name 'convert'" in p for p in factory.code_calls()[2:])
    said = " ".join(chat(settings, request_id, "assistant"))
    assert "tests failed" not in said and "test(s) still fail" not in said
    assert "the test file could not load" in said
    # Get help after the rounds ran out still tells the senior why
    flow.request_help(settings, request_id, flow.get_revision(settings, request_id))
    assert any("cannot import name 'convert'" in t for t in chat(settings, request_id, "assistant"))


def test_np3_a_set_up_class_error_says_a_frozen_test_cannot_run(settings, request_id, monkeypatch):
    inject(monkeypatch, error("no data file", kind="set_up", error_type="RuntimeError"))
    factory = RecordingFactory()

    assert build(settings, request_id, factory) == "interrupted"

    said = chat(settings, request_id, "assistant")
    assert "A frozen test cannot run: no data file" in said
    assert loop._rounds_used(rounds_of(settings, request_id)) == 0
    assert flow.is_system_failure(build_state(settings, request_id))
