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


def test_typed_answer_over_300_characters_is_refused_at_a_decision(settings):
    view = da_play.to_decision(settings)
    result = send(settings, view, "x" * 301)
    assert result == (no_update, no_update, flow.CUSTOM_TOO_LONG)


def test_typed_answer_at_a_decision_is_saved_and_redraws(settings):
    view = da_play.to_decision(settings)
    result = send(settings, view, "Only the first sheet")
    assert result == (1, no_update, "")
    after = flow.get_understand_view(settings, view.request.request_id)
    assert after.record.decisions[0].choice == "Only the first sheet"


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
    draw, action, enter = app._callback_list[:3]  # the Workspace hops come after these
    assert draw["prevent_initial_call"] is False  # it must draw on first load
    assert action["prevent_initial_call"] is True
    # Busy mode: Send spins, the text box and Skip cannot be used a second time.
    assert action["running"]["running"] == {
        "da-send.loading": True,
        "da-text.readOnly": True,
        "da-skip.disabled": True,
        "da-busy.style": {"display": "block"},
    }
    assert action["running"]["runningOff"]["da-busy.style"] == {"display": "none"}
    assert {v for k, v in action["running"]["runningOff"].items() if k != "da-busy.style"} == {
        False
    }
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


# --- Discover (Phase 3, spec 3.8) ---


def discover_state(request_id, revision=0):
    return {"request_id": request_id, "revision": revision, "discover": True}


def discovery_view(settings, request_id):
    from agents import da_discover_flow as discover

    return discover.get_discovery_view(settings, request_id)


@pytest.fixture
def confirmed_id(settings):
    return da_play.to_confirmed(settings).request.request_id


def test_a_confirmed_request_is_drawn_as_the_discover_workspace(settings, confirmed_id):
    tree = cb.show_page(f"?request={confirmed_id}", 0)

    text = all_text(tree)
    assert by_id(tree, page.STATE_ID).data["discover"] is True
    assert page.PROCEED_DISCOVERY_OPTION in text
    assert "CONFIRMED FOR DISCOVERY" in text


def test_a_request_still_being_clarified_is_drawn_as_the_understand_workspace(settings):
    view = da_play.start(settings)

    tree = cb.show_page(f"?request={view.request.request_id}", 0)

    assert "discover" not in by_id(tree, page.STATE_ID).data


def test_proceed_to_discovery_runs_the_round_and_asks_for_a_redraw(settings, confirmed_id):
    result = cb.perform_action(
        settings, choice(0), None, discover_state(confirmed_id), 5
    )

    assert result == (6, no_update, "")
    view = discovery_view(settings, confirmed_id)
    assert view.request.status == "SIMILAR_IMPLEMENTATION_FOUND" and view.result.round == 1
    tree = cb.show_page(f"?request={confirmed_id}", 6)
    assert by_id(tree, page.STATE_ID).data["revision"] == 1
    assert "Round 1 of 3" in all_text(tree)


def test_send_in_discover_is_the_hint_and_searches_again(settings, confirmed_id):
    cb.perform_action(
        settings, choice(0), None, discover_state(confirmed_id), 0
    )

    result = cb.perform_action(
        settings, page.SEND_ID, "batching helper", discover_state(confirmed_id, 1), 1
    )

    assert result == (2, no_update, "")
    view = discovery_view(settings, confirmed_id)
    assert view.result.round == 2 and view.result.hint == "batching helper"


def test_a_hint_with_a_secret_shows_a_plain_message_and_writes_nothing(settings, confirmed_id):
    cb.perform_action(
        settings, choice(0), None, discover_state(confirmed_id), 0
    )

    hint = "key sk-abcdefghijklmnopqrstuvwxyz123456"
    refresh, search, message = cb.perform_action(
        settings, page.SEND_ID, hint, discover_state(confirmed_id, 1), 1
    )

    assert refresh is no_update and search is no_update
    assert "API key" in message
    assert discovery_view(settings, confirmed_id).rounds_used == 1


def test_confirm_button_calls_the_flow(settings, confirmed_id):
    cb.perform_action(
        settings, choice(0), None, discover_state(confirmed_id), 0
    )

    cb.perform_action(
        settings, choice(0), None, discover_state(confirmed_id, 1), 1
    )

    assert discovery_view(settings, confirmed_id).request.status == "DISCOVERY_CONFIRMED"


def test_escalate_button_calls_the_flow(settings, confirmed_id):
    cb.perform_action(
        settings, choice(0), None, discover_state(confirmed_id), 0
    )

    escalate = choice(1)
    cb.perform_action(settings, escalate, None, discover_state(confirmed_id, 1), 1)

    view = discovery_view(settings, confirmed_id)
    assert view.request.status == "ESCALATION_REQUIRED" and view.open_item


def test_a_stale_discover_window_is_refused_and_nothing_is_written(settings, confirmed_id):
    cb.perform_action(
        settings, choice(0), None, discover_state(confirmed_id), 0
    )

    result = cb.perform_action(
        settings, choice(0), None, discover_state(confirmed_id, 0), 1
    )

    assert result == (no_update, no_update, STALE_MESSAGE)
    assert discovery_view(settings, confirmed_id).request.status == "SIMILAR_IMPLEMENTATION_FOUND"


def test_a_discover_choice_with_no_button_behind_it_gets_the_stale_message(settings, confirmed_id):
    result = cb.perform_action(settings, choice(5), None, discover_state(confirmed_id), 0)

    assert result == (no_update, no_update, STALE_MESSAGE)
    assert discovery_view(settings, confirmed_id).request.status == "CONFIRMED_FOR_DISCOVERY"


def test_codevision_search_provider_shows_the_not_configured_message(
    make_settings, published_rulebook, settings, confirmed_id
):
    work = make_settings(search_provider="codevision")

    result = cb.perform_action(
        work, choice(0), None, discover_state(confirmed_id), 0
    )

    assert result == (no_update, no_update, "CodeVision search is not configured yet.")


def test_the_same_buttons_in_an_understand_workspace_still_call_the_understand_engine(settings):
    view = da_play.to_decision(settings)

    cb.perform_action(settings, choice(0), None, state_of(view), 0)

    after = flow.get_understand_view(settings, view.request.request_id)
    assert after.request.status != "DECISION_REQUIRED"


def test_a_request_saved_before_2d_shows_a_plain_page_and_stays_in_the_list(settings):
    """2D-5: no crash, no stack trace, still listed, nothing deleted."""
    import json
    import sqlite3
    from contextlib import closing

    view = da_play.start(settings)
    rid = view.request.request_id
    with closing(sqlite3.connect(settings.db_path)) as conn:
        (raw,) = conn.execute("SELECT session FROM da_understand_sessions").fetchone()
        data = json.loads(raw)
        data["record"]["success_scenarios"] = ["A workbook is ingested"]
        conn.execute("UPDATE da_understand_sessions SET session = ?", (json.dumps(data),))
        conn.commit()

    text = all_text(cb.show_page(f"?request={rid}", 0))

    assert f"Request {rid} was saved before the Understand update (2D)" in text
    assert "cannot be opened." in text
    assert "Please start a new request." in text
    assert "Back to Home" in text
    assert rid in all_text(cb.show_page("", 0))  # still in "My recent requests"
