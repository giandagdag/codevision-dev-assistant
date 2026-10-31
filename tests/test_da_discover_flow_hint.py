"""add_hint_and_search, the round cap and the stale check (step 11c)."""

import pytest

from agents.da_discover_flow import (
    HINT_OPTION,
    add_hint_and_search,
    get_discovery_view,
    start_discovery,
)
from db_table_functions.db_tbl_da_discovery import DiscoveryError, get_results
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    list_messages,
)
from tests.da_discover_play import confirmed_id, event_types, moves, record_state
from tests.da_stub_client import StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")

SIMILAR = "SIMILAR_IMPLEMENTATION_FOUND"
HINT = "batching helper"


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def first_round(settings):
    request_id = confirmed_id(settings)
    return request_id, start_discovery(settings, request_id, 0)


def test_hint_round_on_the_demo_record_gives_ai_findings_and_similar_found(settings, first_round):
    request_id, view = first_round

    second = add_hint_and_search(settings, request_id, HINT, view.revision)

    assert second.request.status == SIMILAR
    assert second.result.round == 2 and second.rounds_used == 2
    assert second.result.summary_source == "ai"
    assert second.result.hint == HINT
    assert second.revision == 2
    assert any(h.symbol == "make_batches" for h in second.result.hits)
    assert len(get_results(settings.db_path, request_id)) == 2


def test_hint_queries_are_added_to_the_round(settings, first_round):
    request_id, view = first_round

    second = add_hint_and_search(settings, request_id, HINT, view.revision)

    assert f"exact: {HINT}" in second.result.queries
    assert f"meaning: {HINT}" in second.result.queries


def test_audit_starts_with_the_hint_and_the_moves_go_outcome_searching_outcome(
    settings, first_round
):
    request_id, view = first_round
    before = len(event_types(settings, request_id))

    add_hint_and_search(settings, request_id, HINT, view.revision)

    assert event_types(settings, request_id)[before:] == [
        "discovery_hint_added",
        "discovery_started",
        "status_changed",
        "status_changed",
        "discovery_completed",
    ]
    assert moves(settings, request_id)[-2:] == [(SIMILAR, "SEARCHING"), ("SEARCHING", SIMILAR)]
    chat = [m.text for m in list_messages(settings.db_path, request_id)]
    assert f"{HINT_OPTION}: {HINT}" in chat


def test_record_v1_is_unchanged_after_a_hint_round(settings, first_round):
    request_id, view = first_round
    before = record_state(settings, request_id)

    add_hint_and_search(settings, request_id, HINT, view.revision)

    assert record_state(settings, request_id) == before


@pytest.mark.parametrize(
    ("hint", "message"),
    [
        ("", "Please type a message"),
        ("use sk-abcdefghijklmnopqrstuvwxyz123456", "API key"),
        ("password = hunter2hunter2", "password or key"),
        ("def check(x):\n    return x", "Code cannot be used"),
        ("```look```", "Code cannot be used"),
        ("x" * 301, "300"),
    ],
)
def test_bad_hints_are_refused_and_nothing_is_written(settings, first_round, hint, message):
    request_id, view = first_round
    def state():
        return event_types(settings, request_id), get_discovery_view(settings, request_id).revision

    before = state()

    with pytest.raises(DiscoveryError, match=message):
        add_hint_and_search(settings, request_id, hint, view.revision)

    assert state() == before
    assert len(get_results(settings.db_path, request_id)) == 1


def test_the_third_round_is_the_last_and_a_fourth_is_refused(settings, first_round):
    request_id, view = first_round
    view = add_hint_and_search(settings, request_id, "one", view.revision)
    assert view.can_hint and HINT_OPTION in view.choices
    view = add_hint_and_search(settings, request_id, "two", view.revision)

    assert view.rounds_used == 3 and not view.can_hint
    assert HINT_OPTION not in view.choices and len(view.choices) == 2
    assert "all 3 search rounds" in view.cap_message
    with pytest.raises(DiscoveryError, match="limit of 3 search rounds"):
        add_hint_and_search(settings, request_id, "three", view.revision)
    assert len(get_results(settings.db_path, request_id)) == 3


def test_the_cap_follows_the_setting(make_settings):
    settings = make_settings(discovery_max_rounds=1)
    request_id = confirmed_id(settings)
    view = start_discovery(settings, request_id, 0)

    assert not view.can_hint and view.cap_message
    with pytest.raises(DiscoveryError, match="limit of 1 search rounds"):
        add_hint_and_search(settings, request_id, HINT, view.revision)


def test_a_stale_window_is_refused_and_nothing_is_written(settings, first_round):
    request_id, view = first_round
    add_hint_and_search(settings, request_id, "one", view.revision)

    with pytest.raises(StaleRevisionError, match=STALE_MESSAGE):
        add_hint_and_search(settings, request_id, "two", view.revision)  # the old revision

    assert len(get_results(settings.db_path, request_id)) == 2


def test_a_hint_needs_a_finished_round_first(settings):
    request_id = confirmed_id(settings)

    with pytest.raises(DiscoveryError, match="cannot be searched"):
        add_hint_and_search(settings, request_id, HINT, 0)


def test_a_hint_round_with_a_bad_ai_is_saved_as_plain_results(settings, first_round):
    request_id, view = first_round

    second = add_hint_and_search(
        settings, request_id, HINT, view.revision, client=StubClient("nope", "nope again")
    )

    assert second.result.summary_source == "fallback" and second.result.round == 2
    assert second.request.status in (SIMILAR, "NO_RELIABLE_MATCH")
