"""Fix NP step 3: the reason is always shown, with <sandbox> instead of any server path
(NP-4, NP-6 reason part, NP-8)."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_check_words import SYSTEM_HELP_LINE
from agents.da_load_errors import hide_sandbox
from layouts import da_build_panel as panel
from pydantic_classes.da_build_models import LoadError
from tests.da_build_play import RecordingFactory, chat, ready_with_workspace
from tests.da_tree import all_text

pytestmark = pytest.mark.usefixtures("published_rulebook")

TAIL = [
    '  File "C:\\Users\\boss\\AppData\\Local\\Temp\\da_sandbox_ab12\\tests\\t\\test_t.py", line 3',
    '  File "/srv/app/da_sandbox_zz/src/agents/excel_processor.py", line 9, in <module>',
    '  File "C:\\Python314\\Lib\\importlib\\__init__.py", line 88, in import_module',
    "ModuleNotFoundError: No module named 'openpyxl'",
]


# --- the hiding itself ---


def test_a_sandbox_path_keeps_only_the_part_from_src_on():
    text = hide_sandbox('File "/srv/app/da_sandbox_zz/src/agents/x.py", line 9')
    assert text == 'File "<sandbox>/src/agents/x.py", line 9'


def test_the_temporary_folder_and_other_paths_are_hidden_and_plain_words_are_not():
    one = hide_sandbox("C:\\Users\\boss\\AppData\\Local\\Temp\\da_sandbox_ab12\\tests\\t\\a.py")
    assert one == "<sandbox>/tests/t/a.py"
    assert hide_sandbox("C:\\Python314\\Lib\\loader.py") == "<sandbox>/loader.py"
    assert hide_sandbox("use and/or here") == "use and/or here"
    assert hide_sandbox("No module named 'openpyxl'") == "No module named 'openpyxl'"


def test_a_line_that_looks_like_a_secret_is_hidden_but_the_others_stay():
    text = hide_sandbox("api_key = abc123\nplain line")
    assert text == "[hidden]\nplain line"


# --- on the screens ---


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def inject(monkeypatch, load_error=None, not_proven=False):
    real = loop.run_tests

    def runner(*args, **kwargs):
        result = real(*args, **kwargs)
        if load_error is not None:
            result.tests = [t.model_copy(update={"result": "not_run"}) for t in result.tests]
            result.load_error = load_error.model_copy()
        if not_proven:
            result.tests[-1] = result.tests[-1].model_copy(
                update={"result": "not_proven", "message": "Not proven: no result recorded"}
            )
        return result

    monkeypatch.setattr(loop, "run_tests", runner)


def start_and_run(settings, request_id):
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    return loop.run_build(settings, request_id, RecordingFactory())


def test_np4_both_tabs_show_the_reason_with_sandbox_instead_of_any_server_path(
    settings, request_id, monkeypatch
):
    error = LoadError(
        kind="import",
        error_type="ModuleNotFoundError",
        message="No module named 'openpyxl'",
        traceback_tail=TAIL,
    )
    inject(monkeypatch, error)
    start_and_run(settings, request_id)
    view = flow.get_build_view(settings, request_id)

    for tab in (panel.build_tab(view), panel.tests_tab(view)):
        text = all_text(tab)
        assert "The test file could not load. ModuleNotFoundError: No module named" in text
        assert "<sandbox>/src/agents/excel_processor.py" in text
        assert "da_sandbox_" not in text and "C:\\" not in text and "/srv/" not in text


def test_np6_a_test_that_truly_reports_nothing_shows_its_reason(settings, request_id, monkeypatch):
    inject(monkeypatch, not_proven=True)
    start_and_run(settings, request_id)
    view = flow.get_build_view(settings, request_id)

    assert "Not proven: no result recorded" in all_text(panel.build_tab(view))
    assert "Not proven: no result recorded" in all_text(panel.tests_tab(view))


def test_np8_get_help_starts_with_the_missing_module_sentence_and_offers_send_to_senior(
    settings, request_id, monkeypatch
):
    error = LoadError(
        kind="import", error_type="ModuleNotFoundError", message="No module named 'openpyxl'",
        traceback_tail=TAIL,
    )
    inject(monkeypatch, error)
    start_and_run(settings, request_id)
    state = flow.get_state(settings, request_id)
    assert ("Send to my senior") in [label for _, label in flow._build_buttons(state, False)[0]]

    flow.request_help(settings, request_id, flow.get_revision(settings, request_id))

    said = chat(settings, request_id, "assistant")
    first = said.index(next(t for t in said if t.startswith("The server's Python is missing")))
    # The sentence comes again at the head of the Get help text, before the trace and the line.
    later = said[first + 1 :]
    again = next(i for i, t in enumerate(later) if t.startswith("The server's Python is missing"))
    assert "<sandbox>" in " ".join(later[again:]) and SYSTEM_HELP_LINE in later[again:]
    assert "da_sandbox_" not in " ".join(said)
