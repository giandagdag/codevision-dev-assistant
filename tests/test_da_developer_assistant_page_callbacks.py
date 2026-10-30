from types import SimpleNamespace

import pytest
from dash import Dash, no_update
from dash.exceptions import PreventUpdate

from agents import da_understand_flow as flow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE
from layouts import da_developer_assistant_page as page
from tests import da_play
from tests.da_stub_client import StubClient, stub_reply
from tests.da_tree import all_text, by_id


@pytest.fixture
def settings(make_settings, published_rulebook, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


def state_of(view):
    return {"request_id": view.request.request_id, "revision": view.revision}


def send(settings, view, text="my answer"):
    return cb.perform_action(settings, page.SEND_ID, text, state_of(view), 0)


def choice(index):
    return {"type": page.CHOICE_TYPE, "index": index}


# Made-up options with the characters that broke ids: curly quote, long dash, accent, emoji.
TRICKY_OPTIONS = [
    "Keep the user\u2019s old file \u2014 convert later",
    "Caf\u00e9 sheets only",
    "Skip hidden sheets \U0001F4CA",
]


def to_tricky_decision(settings):
    """A material decision whose options hold the awkward characters (stub interpreter reply)."""
    ambiguity = {"text": "Which way should we go?", "material": True, "options": TRICKY_OPTIONS}
    reply = stub_reply({"title": "Add Excel uploads"}, [ambiguity])
    view = flow.create_understand_request(settings, "Can we support Excel uploads?")
    return flow.submit_answer(
        settings, view.request.request_id, "Because users ask", view.revision,
        client=StubClient(reply),
    )


def test_the_whole_scripted_conversation_runs_through_the_buttons(settings):
    # First message: no request yet, so the screen is told to open the new one.
    refresh, search, message = cb.perform_action(
        settings, page.SEND_ID, "Can we support Excel uploads?", {"request_id": None}, 0
    )
    assert refresh is no_update and message == ""
    request_id = search.removeprefix("?request=")
    view = flow.get_understand_view(settings, request_id)

    for text in da_play.ANSWERS:
        refresh, search, message = send(settings, view, text)
        assert (refresh, search, message) == (1, no_update, "")
        view = flow.get_understand_view(settings, request_id)
    assert view.input_mode == "choices"  # the decision locks the text box

    cb.perform_action(settings, choice(0), None, state_of(view), 1)
    view = flow.get_understand_view(settings, request_id)
    assert view.can_skip
    cb.perform_action(settings, page.SKIP_ID, None, state_of(view), 2)
    view = flow.get_understand_view(settings, request_id)
    proceed = view.choices.index(flow.PROCEED_OPTION)
    cb.perform_action(settings, choice(proceed), None, state_of(view), 3)

    view = flow.get_understand_view(settings, request_id)
    assert view.request.status == "CONFIRMED_FOR_DISCOVERY"
    assert view.progress_text == "Confirmed and saved as version 1"

    home = all_text(cb.show_page("", 4))
    assert request_id in home and "CONFIRMED FOR DISCOVERY" in home


def test_show_page_draws_home_new_and_one_request(settings):
    view = da_play.start(settings)
    assert "My recent requests" in all_text(cb.show_page(None, 0))
    new = cb.show_page("?new=1", 0)
    assert by_id(new, page.STATE_ID).data["request_id"] is None
    drawn = cb.show_page(f"?request={view.request.request_id}", 0)
    assert by_id(drawn, page.STATE_ID).data == state_of(view)


def test_reloading_mid_conversation_shows_the_same_thing(settings):
    view = da_play.answer(settings, da_play.start(settings), da_play.ANSWERS[0])
    url = f"?request={view.request.request_id}"
    first, second = cb.show_page(url, 0), cb.show_page(url, 7)
    assert all_text(first) == all_text(second)
    assert "1 of 4 mandatory questions answered" in all_text(first)


def test_busy_database_on_home_gives_a_plain_message(settings, monkeypatch):
    def busy(_settings):
        raise cb.DatabaseBusyError("The database is busy. Please try again.")

    monkeypatch.setattr(cb, "list_my_requests", busy)
    assert "database is busy" in all_text(cb.show_page("", 0))


def test_unknown_request_gives_a_plain_message(settings):
    tree = cb.show_page("?request=CVDA-2026-9999", 0)
    assert "does not exist" in all_text(tree)
    assert by_id(tree, "da-back-home") is not None


def test_stale_window_is_refused_and_nothing_is_written(settings):
    view = da_play.start(settings)
    old_state = state_of(view)
    da_play.answer(settings, view, da_play.ANSWERS[0])  # "another window" saved first
    before = flow.get_understand_view(settings, view.request.request_id)

    result = cb.perform_action(settings, page.SEND_ID, "late answer", old_state, 0)

    assert result == (no_update, no_update, STALE_MESSAGE)
    after = flow.get_understand_view(settings, view.request.request_id)
    assert after.messages == before.messages and after.revision == before.revision


def test_a_message_with_a_key_is_refused_and_not_saved(settings):
    view = da_play.start(settings)
    result = send(settings, view, "my key is sk-ant-api03-" + "a" * 40)
    assert result[0] is no_update and result[2] != ""
    after = flow.get_understand_view(settings, view.request.request_id)
    assert after.messages == view.messages


def test_text_is_refused_while_a_decision_waits(settings):
    view = da_play.to_decision(settings)
    result = send(settings, view)
    assert result == (
        no_update,
        no_update,
        "A decision is waiting. Please choose one of the options first.",
    )


def test_help_choice_shows_decision_required_then_choosing_resumes(settings):
    view = da_play.to_decision(settings)
    help_button = view.choices.index(flow.HELP_OPTION)
    cb.perform_action(settings, choice(help_button), None, state_of(view), 0)
    view = flow.get_understand_view(settings, view.request.request_id)
    assert view.request.status == "DECISION_REQUIRED"
    assert "DECISION REQUIRED" in all_text(cb.show_page(f"?request={view.request.request_id}", 0))
    cb.perform_action(settings, choice(0), None, state_of(view), 1)
    view = flow.get_understand_view(settings, view.request.request_id)
    assert view.request.status == "CLARIFICATION_IN_PROGRESS"


@pytest.mark.parametrize("index", range(len(TRICKY_OPTIONS)))
def test_each_button_picks_its_own_option_even_with_awkward_characters(settings, index):
    view = to_tricky_decision(settings)
    assert view.choices[:-1] == TRICKY_OPTIONS  # the buttons, in order (Help is added last)

    result = cb.perform_action(settings, choice(index), None, state_of(view), 0)

    assert result == (1, no_update, "")
    after = flow.get_understand_view(settings, view.request.request_id)
    assert after.record.decisions[0].choice == TRICKY_OPTIONS[index]


def test_a_button_index_with_nothing_behind_it_gets_the_stale_message(settings):
    view = da_play.to_decision(settings)
    for index in (len(view.choices), 99, -1):
        result = cb.perform_action(settings, choice(index), None, state_of(view), 0)
        assert result == (no_update, no_update, STALE_MESSAGE)
    after = flow.get_understand_view(settings, view.request.request_id)
    assert after.messages == view.messages and after.revision == view.revision


def test_a_choice_from_an_old_window_gets_the_stale_message(settings):
    view = da_play.to_decision(settings)
    old_state = state_of(view)
    da_play.choose(settings, view, view.choices[1])  # "another window" chose first

    result = cb.perform_action(settings, choice(0), None, old_state, 0)

    assert result == (no_update, no_update, STALE_MESSAGE)
    after = flow.get_understand_view(settings, view.request.request_id)
    assert after.record.decisions[0].choice == view.choices[1]


def test_no_rulebook_gives_a_plain_message(make_settings, monkeypatch):
    settings = make_settings()  # nothing published
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    result = cb.perform_action(settings, page.SEND_ID, "hello", {"request_id": None}, 0)
    assert result[0] is no_update and "No rulebook has been published" in result[2]


def test_onprem_shows_its_plain_message_in_the_chat(make_settings, published_rulebook, monkeypatch):
    settings = make_settings(llm_provider="onprem")
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    view = flow.create_understand_request(settings, "Can we support Excel uploads?")
    cb.perform_action(settings, page.SEND_ID, "Because users ask", state_of(view), 0)
    tree = cb.show_page(f"?request={view.request.request_id}", 0)
    assert "DA_ONPREM_URL is missing" in all_text(tree)
    assert page.DEMO_BANNER not in all_text(tree)


def test_nothing_clicked_does_nothing(settings, monkeypatch):
    monkeypatch.setattr(cb, "ctx", SimpleNamespace(triggered_id=None, triggered=[]))
    with pytest.raises(PreventUpdate):
        cb.handle_action(None, [None], None, "", {"request_id": None}, 0)
    # A button that was only redrawn (n_clicks still None) is not a click either.
    monkeypatch.setattr(
        cb,
        "ctx",
        SimpleNamespace(triggered_id=page.SEND_ID, triggered=[{"value": None}]),
    )
    with pytest.raises(PreventUpdate):
        cb.handle_action(None, [None], None, "", {"request_id": None}, 0)


def test_handle_action_passes_a_real_click_on(settings, monkeypatch):
    view = da_play.start(settings)
    monkeypatch.setattr(
        cb, "ctx", SimpleNamespace(triggered_id=page.SEND_ID, triggered=[{"value": 1}])
    )
    result = cb.handle_action(1, [], None, "my answer", state_of(view), 4)
    assert result == (5, no_update, "")


def test_unknown_trigger_does_nothing(settings):
    with pytest.raises(PreventUpdate):
        cb.perform_action(settings, "da-something-else", None, {"request_id": "x"}, 0)


def test_register_attaches_the_callbacks_and_the_busy_state():
    app = Dash(__name__, suppress_callback_exceptions=True)
    cb.register_da_developer_assistant_page_callbacks(app)
    draw, action, enter = app._callback_list
    assert draw["prevent_initial_call"] is False  # it must draw on first load
    assert action["prevent_initial_call"] is True
    # Busy mode: Send spins, the text box and Skip cannot be used a second time.
    assert action["running"]["running"] == {
        "da-send.loading": True,
        "da-text.readOnly": True,
        "da-skip.disabled": True,
    }
    assert set(action["running"]["runningOff"].values()) == {False}
    # Enter-to-send: a browser-side callback that runs after every redraw.
    assert enter["output"] == "da-keys-ready.data"
    assert enter["inputs"][0]["id"] == page.PAGE_CONTENT_ID
    assert enter["clientside_function"]["function_name"]


def test_enter_script_has_every_guard():
    # These are string checks only: the real proof is the browser check in the review notes.
    js = cb.ENTER_TO_SEND_JS
    assert "'da-text'" in js and "getElementById('da-send')" in js and "send.click()" in js
    for guard in (
        "event.key !== 'Enter'",
        "event.shiftKey",  # Shift+Enter stays a new line
        "event.isComposing",
        "box.disabled",  # locked choices, waiting, done
        "box.readOnly",  # a reply is running
        "send.disabled",
        "data-loading",
    ):
        assert guard in js
    assert "window.daEnterToSend" in js  # one listener for the whole page
