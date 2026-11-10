"""Phase 9 step 18b: the safety net is wired to the screen (code review round 1, Must fix 2).
Click-through tests: they call the page callbacks, not the engine. Made-up data, no real AI."""

import pytest
from dash.exceptions import PreventUpdate

from agents import da_discover_flow as discover
from agents import da_enhance_flow as enhance
from agents import da_safety_net_flow as net_flow
from agents import da_safety_net_runner as net_runner
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from layouts import da_developer_assistant_page as page
from layouts import da_enhance_panel as panel
from tests.test_da_enhance_discover import confirmed_enhance
from tests.test_da_safety_net_flow import (
    Runner,
    at_s_writing,
    events_of,
    nets_of,
    state_of,
)

pytestmark = pytest.mark.usefixtures("published_rulebook")


def choice(index):
    return {"type": page.CHOICE_TYPE, "index": index}


def state_for(settings, request_id):
    view = enhance.get_enhance_view(settings, request_id)
    return {"request_id": request_id, "revision": view.revision, "enhance": view.step}


def click(settings, request_id, label):
    """Press the button with this label, the way handle_action passes it on."""
    view = enhance.get_enhance_view(settings, request_id)
    index = [text for _key, text in panel.enhance_buttons(view)].index(label)
    return cb.perform_action(settings, choice(index), "", state_for(settings, request_id), 0)


def in_review(settings, tmp_path):
    request_id = at_s_writing(settings)
    net_flow.run_safety_net(settings, request_id, state_of(settings, request_id).revision,
                            Runner(tmp_path))
    return request_id


def test_confirming_discovery_starts_the_safety_net_in_the_background(make_settings, monkeypatch):
    settings = make_settings()
    request_id = confirmed_enhance(settings)
    view = discover.start_discovery(settings, request_id, 0)
    started = []
    monkeypatch.setattr(net_runner, "submit_safety_net", lambda *args: started.append(args))
    monkeypatch.setattr(cb, "_start_approach_now", lambda *_: pytest.fail("Approach too early"))

    message = cb._discover_choice(settings, request_id, cb.CONFIRM_KEY, view.revision)

    assert message == ""
    assert state_of(settings, request_id).step == "s_writing"
    assert started == [(settings, request_id, state_of(settings, request_id).revision)]


def test_the_background_thread_runs_the_engine_to_the_review_step(make_settings, tmp_path):
    settings = make_settings()
    request_id = at_s_writing(settings)
    revision = state_of(settings, request_id).revision

    net_runner.submit_safety_net(settings, request_id, revision, runner=Runner(tmp_path)).join()

    assert state_of(settings, request_id).step == "s_review"


def test_a_thread_that_fails_is_logged_and_leaves_the_step_alone(make_settings, monkeypatch):
    settings = make_settings()
    request_id = at_s_writing(settings)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(net_flow, "run_safety_net", boom)
    net_runner.submit_safety_net(settings, request_id, 1).join()

    assert state_of(settings, request_id).step == "s_writing"


def test_the_review_step_offers_continue_get_help_and_the_correct_button(make_settings, tmp_path):
    settings = make_settings()
    request_id = in_review(settings, tmp_path)

    view = enhance.get_enhance_view(settings, request_id)

    labels = [label for _key, label in panel.enhance_buttons(view)]
    assert labels == ["Continue to Approach", "Get help"]


def test_continue_to_approach_accepts_the_net_and_approach_starts_by_itself(
    make_settings, tmp_path, monkeypatch
):
    settings = make_settings()
    request_id = in_review(settings, tmp_path)
    started = []
    monkeypatch.setattr(cb, "_start_approach_now", lambda *args: started.append(args))

    outputs = click(settings, request_id, "Continue to Approach")

    assert outputs[0] == 1 and state_of(settings, request_id).step == "s_accepted"
    assert nets_of(settings, request_id)[-1].accepted
    assert started == [(settings, request_id)]


def test_correct_something_is_the_send_button_at_the_review_step(
    make_settings, tmp_path, monkeypatch
):
    settings = make_settings()
    request_id = in_review(settings, tmp_path)
    monkeypatch.setattr(net_flow, "sandbox_runner", lambda *_: Runner(tmp_path))

    cb.perform_action(settings, page.SEND_ID, "Please also check the expiry date.",
                      state_for(settings, request_id), 0)

    assert "safety_net_corrected" in events_of(settings, request_id)
    assert state_of(settings, request_id).corrections_used == 1


def test_a_refused_correction_shows_its_message_and_writes_nothing(make_settings, tmp_path):
    settings = make_settings()
    request_id = in_review(settings, tmp_path)

    outputs = cb.perform_action(settings, page.SEND_ID, "   ", state_for(settings, request_id), 0)

    assert outputs[0] is cb.no_update and outputs[2]
    assert len(nets_of(settings, request_id)) == 1


def test_try_again_at_s_unable_starts_the_write_in_the_background(make_settings, monkeypatch):
    settings = make_settings()
    request_id = at_s_writing(settings)
    net_flow.recover_interrupted_safety_nets(settings)
    started = []
    monkeypatch.setattr(net_runner, "submit_safety_net", lambda *args: started.append(args))
    view = enhance.get_enhance_view(settings, request_id)
    assert [label for _key, label in panel.enhance_buttons(view)] == ["Try again", "Get help"]

    click(settings, request_id, "Try again")

    assert started == [(settings, request_id, view.revision)]


def test_get_help_works_at_the_review_step(make_settings, tmp_path):
    settings = make_settings()
    request_id = in_review(settings, tmp_path)

    click(settings, request_id, "Get help")

    assert state_of(settings, request_id).step == "escalated"


def test_the_mark_dropdown_changes_one_case_and_a_second_pick_of_it_is_quiet(
    make_settings, tmp_path
):
    settings = make_settings()
    request_id = in_review(settings, tmp_path)
    first = nets_of(settings, request_id)[0].net.cases[0].expected_to_change
    value = panel.MARK_NONE_VALUE if first else "AC-1"
    state = state_for(settings, request_id)

    refresh, message = cb.perform_mark(settings, "S-1", value, state, 0)

    assert (refresh, message) == (1, "")
    assert len(nets_of(settings, request_id)) == 2
    with pytest.raises(PreventUpdate):  # the dropdown also fires when it is redrawn
        cb.perform_mark(settings, "S-1", value, state_for(settings, request_id), 1)


def test_an_old_window_cannot_change_a_mark(make_settings, tmp_path):
    settings = make_settings()
    request_id = in_review(settings, tmp_path)
    state = state_for(settings, request_id)
    state["revision"] -= 1

    refresh, message = cb.perform_mark(settings, "S-1", "AC-1", state, 0)

    assert refresh is cb.no_update and message
    assert len(nets_of(settings, request_id)) == 1


def test_the_safety_net_tab_can_draw_dropdowns_for_the_marks(make_settings, tmp_path):
    settings = make_settings()
    request_id = in_review(settings, tmp_path)
    row = nets_of(settings, request_id)[0]

    tab = panel.safety_net_tab(row, ["AC-1"])

    assert "da-net-mark" in repr(tab) and "Expected to change (AC-1)" in repr(tab)
    assert "da-net-mark" not in repr(panel.safety_net_tab(row))
