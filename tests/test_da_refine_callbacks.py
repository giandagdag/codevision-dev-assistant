"""The Refine clicks on the screen (Phase 8 step 16b). The functions are called directly, as the
Phase 7 callback tests do; no browser."""

import pytest
from dash import Dash, no_update

from agents import da_build_flow as flow
from agents import da_build_runner as build_runner
from agents import da_refine_actions as actions
from agents import da_refine_flow as rflow
from agents import da_refine_lanes as lanes
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from callbacks.screen_callbacks import da_refine_callbacks as rcb
from db_table_functions.db_tbl_da_refine import RefineError
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE
from layouts import da_build_panel as bp
from layouts import da_developer_assistant_page as page
from tests.da_build_play import MODIFY, request_status
from tests.da_refine_play import written_request
from tests.da_tree import by_id, components
from tests.da_workspace_play import facts_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def submitted(monkeypatch):
    """The build runner is not started in these tests; its calls are recorded."""
    calls = []
    monkeypatch.setattr(build_runner, "submit_build", lambda s, r, *a: calls.append(r))
    return calls


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def state_of(tree) -> dict:
    return dict(by_id(tree, page.STATE_ID).data)


def refine_keys(tree) -> list[str]:
    return [
        b.id["index"]
        for b in components(tree, "Button")
        if isinstance(getattr(b, "id", None), dict) and b.id.get("type") == page.REFINE_TYPE
    ]


def click(settings, tree, key, refresh=0):
    """One Refine button click on the page as drawn: the state is the one the page holds."""
    trigger = {"type": page.REFINE_TYPE, "index": key}
    return rcb.handle_refine_button(settings, trigger, 1, state_of(tree), refresh)


def test_written_request_state_carries_the_refine_revision_and_flag(settings):
    request_id, _ = written_request(settings)

    state = state_of(draw(request_id))

    assert state["refine"] is True and state["refine_revision"] == 0 and state["build"] is True


def test_send_at_b_written_goes_to_the_lane_choice_and_the_buttons_are_the_lanes(settings):
    request_id, _ = written_request(settings)
    tree = draw(request_id)

    result = cb.perform_action(settings, cb.SEND_ID, "The upload is wrong", state_of(tree), 0)

    assert result == (1, no_update, "")
    assert lanes.get_refine_state(settings, request_id).step == "lane_choice"
    tree = draw(request_id)
    assert refine_keys(tree) == ["lane_bug", "lane_requirement", "lane_approach", "cancel"]
    assert state_of(tree)["refine_revision"] == 1


def test_a_lane_button_runs_the_lane_and_the_next_screen_has_the_next_buttons(settings):
    request_id, _ = written_request(settings)
    cb.perform_action(settings, cb.SEND_ID, "The upload is wrong", state_of(draw(request_id)), 0)

    result = click(settings, draw(request_id), "lane_bug")

    assert result == (1, "")
    assert request_status(settings, request_id) == "REVISION_IN_PROGRESS"
    tree = draw(request_id)
    assert refine_keys(tree) == ["repro_yes", "repro_no", "help", "cancel"]  # B2 S2: Cancel is drawn last
    assert by_id(tree, cb.TEXT_ID).disabled  # no typing at the repro confirmation


def test_an_old_window_is_refused_with_the_stale_message_and_nothing_changes(settings):
    request_id, _ = written_request(settings)
    cb.perform_action(settings, cb.SEND_ID, "The upload is wrong", state_of(draw(request_id)), 0)
    old = draw(request_id)
    click(settings, old, "lane_bug")

    result = click(settings, old, "cancel")  # the same window clicks again

    assert result == (no_update, STALE_MESSAGE)
    assert request_status(settings, request_id) == "REVISION_IN_PROGRESS"


def test_check_my_edits_starts_the_runner_and_the_page_polls(settings, submitted):
    request_id, folder = written_request(settings)
    folder.edit(MODIFY, "# my own note\n" + folder.files[MODIFY])
    rflow.rescan(
        settings, request_id, facts_of(settings, request_id, folder),
        flow.get_revision(settings, request_id),
    )
    tree = draw(request_id)
    assert "check_edits" in refine_keys(tree)

    result = click(settings, tree, "check_edits")

    assert result == (1, "") and submitted == [request_id]
    tree = draw(request_id)
    assert by_id(tree, bp.POLL_ID).disabled is False  # the page redraws itself while it runs
    assert refine_keys(tree) == []  # no Refine buttons while the build runs


def test_a_problem_the_developer_can_read_is_shown_not_raised(settings):
    request_id, _ = written_request(settings)
    tree = draw(request_id)

    result = click(settings, tree, "restore")  # only one build exists

    assert result[0] is no_update and "no earlier version" in result[1]


def test_a_click_on_a_page_without_refine_state_does_nothing(settings):
    from dash.exceptions import PreventUpdate

    with pytest.raises(PreventUpdate):
        rcb.handle_refine_button(settings, {"type": page.REFINE_TYPE, "index": "cancel"}, 1, {}, 0)
    with pytest.raises(PreventUpdate):
        rcb.handle_refine_button(settings, {"type": page.REFINE_TYPE, "index": "cancel"}, 0,
                                 {"refine": True}, 0)


def test_the_requirement_lane_shows_refine_buttons_on_the_discover_screen(settings):
    request_id, _ = written_request(settings)
    cb.perform_action(settings, cb.SEND_ID, "Reject files over 5 MB", state_of(draw(request_id)), 0)
    click(settings, draw(request_id), "lane_requirement")  # the revision call runs by itself
    tree = draw(request_id)
    assert refine_keys(tree) == ["confirm_v2", "help", "cancel"]
    assert not by_id(tree, cb.TEXT_ID).disabled  # a correction may be typed
    send = [b for b in components(tree, "Button") if getattr(b, "id", None) == cb.SEND_ID]
    assert send and send[0].children == "Correct something"

    click(settings, tree, "confirm_v2")  # Discover runs by itself on the new version

    tree = draw(request_id)
    # On the Discover screen, status SIMILAR_FOUND: the three Phase 3 buttons (F4)
    assert refine_keys(tree) == ["findings_ok", "findings_escalate"]
    assert state_of(tree)["refine"] is True and state_of(tree)["discover"] is True
    assert not by_id(tree, cb.TEXT_ID).disabled  # "Something's missing" is the text box + Send

    click(settings, tree, "findings_ok")  # the revision approach starts by itself

    assert lanes.get_refine_state(settings, request_id).step == "req_plan"
    tree = draw(request_id)
    assert refine_keys(tree) == []  # the Phase 4 buttons take over
    assert state_of(tree).get("refine") is not True


def test_every_refine_button_the_page_can_draw_is_a_registered_callback_input(settings):
    request_id, _ = written_request(settings)
    app = Dash(__name__, suppress_callback_exceptions=True)
    cb.register_da_developer_assistant_page_callbacks(app)
    registered = " ".join(str(c["inputs"]) for c in app._callback_list)
    assert page.REFINE_TYPE in registered
    assert bp.ADD_CASE_TYPE in registered and "da-conflict-pick" in registered

    seen = set()
    cb.perform_action(settings, cb.SEND_ID, "The upload is wrong", state_of(draw(request_id)), 0)
    for step_tree in (draw(request_id),):
        seen |= set(refine_keys(step_tree))
    click(settings, draw(request_id), "lane_bug")
    seen |= set(refine_keys(draw(request_id)))
    for key in seen:
        assert key in actions.HANDLERS, key
    # Every drawn pattern id type has an Input; the Refine ones are the three below.
    for type_name in (page.REFINE_TYPE, bp.ADD_CASE_TYPE):
        assert type_name in registered


def test_fix_it_calls_the_refine_action_with_the_finding_id(settings, monkeypatch):
    calls = []

    def fake_run(s, key, state, text="", arg=""):
        calls.append((key, arg))
        return ""

    monkeypatch.setattr(cb, "run_refine", fake_run)
    state = {"request_id": "CVDA-2026-0001", "revision": 3, "build": True, "refine_revision": 2}

    result = cb.perform_finding_action(settings, "fixit:F-1", {}, state, 4)

    assert result == (5, "") and calls == [("fixit", "F-1")]


def test_fix_it_does_nothing_when_the_page_has_no_refine_state(settings, monkeypatch):
    monkeypatch.setattr(cb, "run_refine", lambda *a, **k: pytest.fail("must not be called"))
    state = {"request_id": "CVDA-2026-0001", "revision": 3, "build": True}

    with pytest.raises(cb.PreventUpdate):
        cb.perform_finding_action(settings, "fixit:F-1", {}, state, 4)


def test_a_conflict_pick_passes_the_place_and_the_choice_with_the_build_revision(
    settings, monkeypatch
):
    seen = []
    monkeypatch.setattr(rcb, "perform_pick", lambda *args: seen.append(args))
    trigger = {"type": "da-conflict-pick", "path": "src/a.py", "conflict": "C-1", "choice": "mine"}
    state = {"request_id": "CVDA-2026-0001", "revision": 6, "build": True}

    result = rcb.handle_conflict_pick(settings, trigger, 1, state, 0)

    assert result == (1, "")
    assert seen == [(settings, "CVDA-2026-0001", "src/a.py", "C-1", "mine", 6)]


def test_add_a_test_case_runs_the_tester_and_waits_for_his_click(settings):
    request_id, _ = written_request(settings)
    tree = draw(request_id)

    fields = {"criterion": "AC-1", "text": "A file with spaces in its name"}
    result = rcb.handle_add_case(settings, fields, state_of(tree), 0)

    assert result == (1, "")
    assert lanes.get_refine_state(settings, request_id).step in ("own_confirm", "own_fails")
    assert refine_keys(draw(request_id))[0] in ("own_add", "own_bug")


def test_add_a_test_case_form_is_drawn_on_the_tests_tab_at_b_written(settings):
    request_id, _ = written_request(settings)

    tree = draw(request_id)

    assert by_id(tree, bp.ADD_CASE_ID) is not None
    ids = [getattr(c, "id", None) for c in components(tree)]
    assert {"type": bp.ADD_CASE_TYPE, "index": "go"} in ids
    assert {"type": bp.ADD_CASE_FIELD_TYPE, "index": "text"} in ids


def test_a_refine_error_is_a_shown_error(settings):
    assert RefineError.__mro__[1].__name__ == "UnderstandError"
    assert rcb.SHOWN_ERRORS is actions.SHOWN_CHAIN_ERRORS
