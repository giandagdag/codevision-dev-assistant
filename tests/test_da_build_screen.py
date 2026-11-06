"""The Build and Tests tabs and the chat buttons on screen (rows 6-1, 6-42, spec section 12)."""

import pytest
from dash.exceptions import PreventUpdate

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_build_runner as runner
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE, StaleRevisionError
from layouts import da_build_panel as bp
from layouts import da_developer_assistant_page as page
from layouts import da_workspace_panel as panel
from tests.da_build_play import ready_with_workspace
from tests.da_tree import all_text, by_id, components
from tests.da_workspace_play import good_folder, pick, ready_to_build_id

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def ready(settings):
    return ready_with_workspace(settings)


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def labels(tree, kind=None):
    return [
        all_text(b)
        for b in components(tree, "Button")
        if kind is None or (isinstance(getattr(b, "id", None), dict) and b.id.get("type") == kind)
    ]


def tab(tree, name):
    return [t for t in components(tree, "TabsTab") if all_text(t) == name][0]


def start(settings, request_id):
    return flow.start_build(settings, request_id, flow.get_revision(settings, request_id))


def ctx_data(tree):
    return by_id(tree, panel.WS_CTX_ID).data


def test_6_1_build_is_an_active_button_only_when_the_workspace_is_ready(settings, ready):
    request_id, _ = ready
    other = ready_to_build_id(settings)  # READY_TO_BUILD but no folder chosen yet

    ready_tree, blocked_tree = draw(request_id), draw(other)

    build = by_id(ready_tree, panel.ws_button_id("build", "bar"))
    assert build is not None and not getattr(build, "disabled", False)
    assert "Build" in labels(ready_tree, panel.WS_BTN_TYPE)
    assert by_id(blocked_tree, panel.ws_button_id("build", "bar")) is None
    assert "Build" not in labels(blocked_tree, panel.WS_BTN_TYPE)
    assert (
        ctx_data(ready_tree)["build_revision"] == 0 and ctx_data(ready_tree)["auto_write"] is False
    )


def test_a_running_build_draws_the_blue_banner_progress_stop_and_a_live_poll(settings, ready):
    request_id, _ = ready
    start(settings, request_id)

    tree = draw(request_id)

    state = by_id(tree, page.STATE_ID).data
    assert state["build"] is True and state["revision"] == flow.get_revision(settings, request_id)
    assert "Round 1 of 3. Running on the server. You can leave this page" in all_text(
        by_id(tree, bp.BANNER_ID)
    )
    assert labels(tree, page.CHOICE_TYPE) == ["Cancel build"]
    poll = by_id(tree, bp.POLL_ID)
    assert (poll.interval, poll.disabled) == (3000, False)
    assert "BUILDING" in all_text(by_id(tree, "da-build-chat-status"))
    assert not tab(tree, "Build").disabled


def test_after_the_build_the_poll_is_off_and_the_page_asks_for_the_automatic_write(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)

    tree = draw(request_id)

    assert by_id(tree, bp.POLL_ID).disabled is True
    assert "Built, not written yet. Open this request with your workspace allowed." in all_text(
        by_id(tree, bp.BANNER_ID)
    )
    data = ctx_data(tree)
    assert data["auto_write"] is True and data["build_step"] == "b_done"
    assert data["build_revision"] == flow.get_revision(settings, request_id)
    reconnect = by_id(tree, panel.ws_button_id("reconnect", "bar"))
    assert reconnect.style == {"display": "none"}  # the browser shows it only when it must
    assert "READY FOR REVIEW" in all_text(by_id(tree, "da-build-chat-status"))


def test_f7_there_is_no_manual_rescan_button_while_building_or_after_the_build(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    running = draw(request_id)
    loop.run_build(settings, request_id)
    done = draw(request_id)

    for tree in (running, done):
        every = labels(tree)
        assert "Re-scan" not in every  # Phase 8 (Refine) brings it back after a build
        assert "Change folder" not in every and "Change" not in every


def test_6_42_the_written_tab_says_try_it_yourself_and_has_no_run_the_tests_line(settings, ready):
    request_id, folder = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)
    job = flow.prepare_write(settings, request_id, flow.get_revision(settings, request_id))
    revision = flow.get_revision(settings, request_id)
    flow.save_write(settings, request_id, folder.run_job(job), revision)

    tree = draw(request_id)

    turn = all_text(by_id(tree, bp.TURN_ID))
    assert "Your turn" in turn
    assert "Try it yourself: start CodeVision on your laptop and test the change by hand." in turn
    # F7: there is no working Re-scan after a build in Phase 6 (that is Phase 8, Refine).
    assert "Re-scan" not in turn and "Edit anything" not in turn
    assert "Tell me if a requirement is missing." in turn
    assert "run the tests" not in all_text(tree).lower()
    table = all_text(by_id(tree, bp.FILES_ID))
    assert "src/agents/excel_processor.py" in table and table.count("Written") == 2
    summary = all_text(by_id(tree, bp.SUMMARY_ID))
    assert "Rounds used: 2 of 3" in summary and "Tests passing: 9 of 9" in summary
    assert "Time taken:" in summary
    assert "Ready with warnings. The code files are in your folder." in all_text(
        by_id(tree, bp.BANNER_ID)
    )
    assert all("tests/" not in text for text in [table])


def test_the_failure_report_table_and_the_regenerated_file_note(settings, ready, monkeypatch):
    request_id, _ = ready
    start(settings, request_id)
    seen = []
    original = loop._Run._one_round

    def spy(self, number, contract, tests):
        passed = original(self, number, contract, tests)
        if number == 1:
            seen.append(draw(request_id))
        return passed

    monkeypatch.setattr(loop._Run, "_one_round", spy)

    loop.run_build(settings, request_id)

    tree = seen[0]
    banner = all_text(by_id(tree, bp.BANNER_ID))
    assert "Round 1 of 3: 3 of 9 tests failed." in banner
    assert (
        "Only excel_processor.py is regenerated. Tests stay frozen. 1 shared budget of 3 rounds."
        in banner
    )
    failures = all_text(by_id(tree, bp.FAILURES_ID))
    for expected in ("T-2", "T-5", "T-8", "AC-2", "AC-4", "AC-7"):
        assert expected in failures
    assert by_id(tree, bp.POLL_ID).disabled is False  # b_round_failed still polls
    layers = all_text(by_id(tree, bp.LAYERS_ID))
    assert "Does it run?" in layers and "Does it behave?" in layers
    assert "Matches the agreement?" in layers and "Coming in Phase 7" in layers
    assert "6 of 9 passed" in layers


def test_the_progress_list_has_the_frozen_tests_line_and_layer_c_coming_in_phase_7(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)

    progress = all_text(by_id(draw(request_id), bp.PROGRESS_ID))

    assert "Tester wrote 9 tests (frozen)" in progress
    assert "Layer B: 9 of 9 tests passed (time limit 60 seconds per run)" in progress
    assert "Layer C: independent Tester review (coming in Phase 7)" in progress


def test_the_tests_tab_lists_the_frozen_tests_and_says_they_stay_on_the_server(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)

    tree = draw(request_id)

    assert not tab(tree, "Tests").disabled
    listing = all_text(by_id(tree, bp.TESTS_LIST_ID))
    assert "T-1" in listing and "T-9" in listing and "AC-3" in listing and "Passed" in listing
    assert all_text(by_id(tree, "da-tests-note")) == (
        "These tests run on the CodeVision server. They are not copied to your folder."
    )
    code = all_text(by_id(tree, bp.TESTS_CODE_ID))
    assert "def test_t1_ac1_" in code  # View test code shows the frozen file, read only
    assert "View test code" in all_text(tree)


def test_the_tests_tab_is_empty_before_the_first_build(settings, ready):
    assert tab(draw(ready[0]), "Tests").disabled


def test_a_paused_build_draws_try_again_stop_and_get_help_with_the_poll_off(
    settings, ready, monkeypatch
):
    request_id, _ = ready
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"no_answer"}))
    start(settings, request_id)
    loop.run_build(settings, request_id)

    tree = draw(request_id)

    assert labels(tree, page.CHOICE_TYPE) == ["Resume build", "Cancel build", "Get help"]
    assert by_id(tree, bp.POLL_ID).disabled is True
    assert "The build paused:" in all_text(by_id(tree, bp.BANNER_ID))


def test_a_stopped_write_offers_the_browser_button_re_scan_and_build_again(settings, ready):
    request_id, folder = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)
    folder.edit("src/agents/upload_validator.py", "# changed by the developer\n")
    job = flow.prepare_write(settings, request_id, flow.get_revision(settings, request_id))
    revision = flow.get_revision(settings, request_id)
    flow.save_write(settings, request_id, folder.run_job(job), revision)

    tree = draw(request_id)

    assert by_id(tree, panel.ws_button_id("rebuild", "bar")) is not None
    assert "Re-scan and build again" in labels(tree, panel.WS_BTN_TYPE)
    assert labels(tree, page.CHOICE_TYPE) == ["Get help"]


# --- the buttons ---


def choice(index):
    return {"type": page.CHOICE_TYPE, "index": index}


def test_the_stop_button_calls_stop_build(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    state = by_id(draw(request_id), page.STATE_ID).data

    refresh, _, message = cb.perform_action(settings, choice(0), None, state, 3)

    assert (refresh, message) == (4, "")
    assert flow.get_state(settings, request_id).step == "start"


def test_try_again_resumes_and_hands_the_build_to_the_runner(settings, ready, monkeypatch):
    request_id, _ = ready
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"no_answer"}))
    start(settings, request_id)
    loop.run_build(settings, request_id)
    submitted = []
    monkeypatch.setattr(runner, "submit_build", lambda s, rid, *a: submitted.append(rid))
    state = by_id(draw(request_id), page.STATE_ID).data

    cb.perform_action(settings, choice(0), None, state, 0)  # Resume build

    assert flow.get_state(settings, request_id).step == "b_running"
    assert submitted == [request_id]


def test_an_old_window_or_a_missing_button_is_refused_with_the_stale_message(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    state = by_id(draw(request_id), page.STATE_ID).data

    old = cb.perform_action(settings, choice(0), None, {**state, "revision": 0}, 0)
    none = cb.perform_action(settings, choice(5), None, state, 0)

    assert old[2] == STALE_MESSAGE and none[2] == STALE_MESSAGE
    assert flow.get_state(settings, request_id).step == "b_running"  # nothing was stopped


def test_the_poll_redraws_only_for_a_build_page(settings, ready):
    assert cb.poll_build(1, {"build": True, "request_id": "x"}, 7) == 8
    for args in ((0, {"build": True}, 1), (1, {}, 1), (1, None, 1), (None, {"build": True}, 1)):
        with pytest.raises(PreventUpdate):
            cb.poll_build(*args)
    assert isinstance(StaleRevisionError, type) and pick and good_folder  # imports in use


# --- Phase 6 fixes, section 6 ---


def code_badge(tree):
    return all_text(by_id(tree, "da-code-badge"))


def test_f9c_the_chat_badge_follows_the_real_write_state(settings, ready):
    request_id, folder = ready
    assert code_badge(draw(request_id)) == "No code is written yet"
    start(settings, request_id)
    loop.run_build(settings, request_id)
    # Built, but nothing is in the folder yet: still "no code".
    assert code_badge(draw(request_id)) == "No code is written yet"

    job = flow.prepare_write(settings, request_id, flow.get_revision(settings, request_id))
    revision = flow.get_revision(settings, request_id)
    flow.save_write(settings, request_id, folder.run_job(job), revision)

    assert code_badge(draw(request_id)) == "Code is written to your folder"


def test_f9c_a_not_passing_build_that_was_written_also_changes_the_badge(
    settings, ready, monkeypatch
):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"always_fail"}))
    request_id, folder = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)
    job = flow.prepare_write(settings, request_id, flow.get_revision(settings, request_id))
    revision = flow.get_revision(settings, request_id)
    flow.save_write(settings, request_id, folder.run_job(job), revision)

    tree = draw(request_id)

    assert "NOT PASSING" in all_text(by_id(tree, "da-build-chat-status"))
    assert code_badge(tree) == "Code is written to your folder"


def test_f9b_the_tests_tab_says_why_no_test_has_a_result(settings, ready, monkeypatch):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"bad_edit", "always_fail"}))
    request_id, _ = ready
    start(settings, request_id)
    loop.run_build(settings, request_id)

    view = flow.get_build_view(settings, request_id)
    tab_text = all_text(bp.tests_tab(view))

    assert view.tests_not_run is True
    assert "Not run: the code checks (Layer A) failed first. See the Build tab." in tab_text


def test_f9b_the_line_is_absent_when_the_tests_ran_or_no_round_finished(settings, ready):
    request_id, _ = ready
    start(settings, request_id)
    before_round = flow.get_build_view(settings, request_id)
    loop.run_build(settings, request_id)
    after = flow.get_build_view(settings, request_id)

    assert before_round.tests_not_run is False and after.tests_not_run is False
    assert "Not run:" not in all_text(bp.tests_tab(after))
    assert "Not run:" not in all_text(bp.tests_tab(before_round))
