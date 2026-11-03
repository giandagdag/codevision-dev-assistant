"""What the screen is told about a build (spec sections 1, 8 and 12)."""

from datetime import UTC, datetime

import pytest

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_state, save_approach_state
from tests.da_build_play import CREATE, MODIFY, ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def ready(settings):
    return ready_with_workspace(settings)


def view(settings, request_id):
    return flow.get_build_view(settings, request_id)


def start(settings, request_id):
    return flow.start_build(settings, request_id, flow.get_revision(settings, request_id))


def write(settings, request_id, folder):
    job = flow.prepare_write(settings, request_id, flow.get_revision(settings, request_id))
    flow.save_write(
        settings, request_id, folder.run_job(job), flow.get_revision(settings, request_id)
    )


def labels(pairs):
    return [label for _, label in pairs]


def test_before_a_build_the_view_is_empty_and_has_no_revision(settings, ready):
    shown = view(settings, ready[0])

    assert (shown.state.step, shown.revision, shown.run) == ("start", 0, None)
    assert shown.buttons == [] and shown.browser_buttons == []
    assert shown.polling is False and shown.auto_write is False and shown.banner_text == ""


def test_6_1_a_running_build_shows_the_blue_banner_the_stop_button_and_polls(settings, ready):
    request_id, _ = ready
    start(settings, request_id)

    shown = view(settings, request_id)

    assert shown.banner_kind == "blue"
    assert shown.banner_text == (
        "Round 1 of 3. Running on the server. You can leave this page and come back."
    )
    assert labels(shown.buttons) == ["Stop build"] and shown.polling is True
    assert shown.time_limit == 60 and shown.max_rounds == 3


def test_6_18_after_a_failed_round_the_banner_is_red_and_names_the_one_file(
    settings, ready, monkeypatch
):
    request_id, _ = ready
    start(settings, request_id)
    seen = []
    original = loop._Run._one_round

    def spy(self, number, contract, tests):
        passed = original(self, number, contract, tests)
        if number == 1:
            seen.append(view(settings, request_id))
        return passed

    monkeypatch.setattr(loop._Run, "_one_round", spy)

    loop.run_build(settings, request_id)

    shown = seen[0]
    assert shown.state.step == "b_round_failed" and shown.polling is True
    assert shown.banner_kind == "red"
    assert shown.banner_text == (
        "Round 1 of 3: 3 of 9 tests failed. Only excel_processor.py is regenerated. "
        "Tests stay frozen. 1 shared budget of 3 rounds."
    )
    results = {t.test_id: t.result for t in shown.tests}
    assert [i for i, r in results.items() if r == "fail"] == ["T-2", "T-5", "T-8"]
    assert shown.rounds[0].failure_report.files_to_fix == [CREATE]


def test_a_finished_build_not_yet_written_says_so_and_asks_the_page_to_write(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)

    shown = view(settings, request_id)

    assert shown.state.step == "b_done" and shown.auto_write is True and shown.polling is False
    assert (
        shown.banner_text
        == "Built, not written yet. Open this request with your workspace allowed."
    )
    assert shown.label == "Ready with warnings" and shown.tests_passing == "9 of 9"
    assert [(r.path, r.status) for r in shown.rows] == [
        (CREATE, "Not written yet"),
        (MODIFY, "Not written yet"),
    ]
    assert labels(shown.buttons) == ["Get help"]


def test_6_42_after_the_write_the_view_is_green_with_written_files_and_no_test_line(
    settings, ready
):
    request_id, folder = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)
    write(settings, request_id, folder)

    shown = view(settings, request_id)

    assert shown.state.step == "b_written" and shown.auto_write is False
    assert (shown.banner_kind, shown.banner_text) == (
        "green",
        "Ready with warnings. The code files are in your folder.",
    )
    assert [r.status for r in shown.rows] == ["Written", "Written"]
    assert [r.action for r in shown.rows] == ["New", "Change"]
    assert shown.run.rounds_used == 2 and shown.seconds_taken >= 0
    assert shown.folder_name == "codevision" and shown.mode == "picker"
    assert "tests" not in shown.banner_text.lower()


def test_a_not_passing_build_is_red_when_written(settings, ready, monkeypatch):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"always_fail"}))
    request_id, folder = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)
    write(settings, request_id, folder)

    shown = view(settings, request_id)

    assert (shown.banner_kind, shown.label) == ("red", "Not passing")
    assert shown.banner_text == "Not passing. The code files are in your folder."


def test_the_tests_tab_data_has_ids_yours_tags_descriptions_and_the_frozen_file(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)

    shown = view(settings, request_id)

    assert len(shown.tests) == 9
    first = shown.tests[0]
    assert (first.test_id, first.criterion_id, first.yours) == ("T-1", "AC-1", False)
    assert first.description.endswith(".") and first.result == "pass"
    assert "def test_t1_ac1_" in shown.test_code


def test_buttons_for_a_paused_build(settings, ready, monkeypatch):
    request_id, _ = ready
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"no_answer"}))
    start(settings, request_id)
    loop.run_build(settings, request_id)

    shown = view(settings, request_id)

    assert shown.banner_kind == "orange" and shown.banner_text.startswith("The build paused:")
    assert labels(shown.buttons) == ["Try again", "Stop build", "Get help"]
    assert shown.polling is False


def test_buttons_for_unable_and_the_change_cap(settings, ready, monkeypatch):
    request_id, _ = ready
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"bad_tests"}))
    start(settings, request_id)
    loop.run_build(settings, request_id)
    assert labels(view(settings, request_id).buttons) == [
        "Try again",
        "Change the approach",
        "Get help",
    ]

    with open_db(settings.db_path) as conn:
        approach = read_approach_state(conn, request_id)
        approach.change_count = 3
        save_approach_state(conn, approach, approach.revision, datetime.now(UTC))

    assert labels(view(settings, request_id).buttons) == ["Try again", "Get help"]


def test_a_stopped_write_offers_re_scan_and_build_again_and_names_the_file(settings, ready):
    request_id, folder = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)
    folder.edit(MODIFY, "def validate(path):\n    return True\n# edited\n")
    write(settings, request_id, folder)

    shown = view(settings, request_id)

    assert shown.state.step == "b_write_stopped" and shown.banner_kind == "orange"
    assert shown.banner_text == (
        f"You changed {MODIFY} while I was building. Nothing after it was written."
    )
    assert labels(shown.browser_buttons) == ["Re-scan and build again"]
    assert labels(shown.buttons) == ["Get help"]
    assert {r.path: r.status for r in shown.rows} == {
        CREATE: "Written",
        MODIFY: "Not written yet",
    }
