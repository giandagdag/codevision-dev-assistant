"""confirm_discovery, escalate_discovery and get_discovery_view (step 11d)."""

import pytest

from agents.da_discover_flow import (
    CONFIRM_OPTION,
    ESCALATE_OPTION,
    HINT_OPTION,
    NOT_PROOF_LIMITATION,
    add_hint_and_search,
    confirm_discovery,
    escalate_discovery,
    get_discovery_view,
    start_discovery,
)
from db_table_functions.db_tbl_da_discovery import DiscoveryError
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE, StaleRevisionError
from tests.da_discover_play import (
    confirmed_id,
    event_types,
    events_of,
    moves,
    record_state,
    set_status,
)
from tests.da_stub_client import StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")

SIMILAR = "SIMILAR_IMPLEMENTATION_FOUND"


class NoHits:
    def search(self, query, mode, filters, top_k):
        return []


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def first_round(settings):
    request_id = confirmed_id(settings)
    return request_id, start_discovery(settings, request_id, 0)


def test_confirm_moves_to_discovery_confirmed_with_audit_and_chat(settings, first_round):
    request_id, view = first_round

    done = confirm_discovery(settings, request_id, view.revision)

    assert done.request.status == "DISCOVERY_CONFIRMED" and done.choices == []
    assert events_of(settings, request_id, "discovery_confirmed")[0].details == {"round": 1}
    assert moves(settings, request_id)[-1] == (SIMILAR, "DISCOVERY_CONFIRMED")
    assert done.messages[-2].speaker == "developer" and done.messages[-2].text == CONFIRM_OPTION
    assert "confirmed after round 1" in done.messages[-1].text
    assert done.revision == view.revision + 1


def test_confirm_after_a_hint_round_names_that_round(settings, first_round):
    request_id, view = first_round
    view = add_hint_and_search(settings, request_id, "batching helper", view.revision)

    done = confirm_discovery(settings, request_id, view.revision)

    assert "after round 2" in done.messages[-1].text


def test_escalate_moves_to_escalation_required_and_carries_the_open_item(settings, first_round):
    request_id, view = first_round
    latest_limitation = view.result.limitations[-1]

    done = escalate_discovery(settings, request_id, view.revision)

    assert done.request.status == "ESCALATION_REQUIRED" and done.choices == []
    expected = f"Escalated in Discover: {latest_limitation}"
    assert done.open_item == expected
    event = events_of(settings, request_id, "discovery_escalated")[0]
    assert event.details == {"round": 1, "open_item": expected}
    assert moves(settings, request_id)[-1] == (SIMILAR, "ESCALATION_REQUIRED")
    assert "senior developer will pick this up" in done.messages[-1].text


def test_escalating_a_no_match_round_names_the_not_proof_limitation(settings):
    request_id = confirmed_id(settings)
    view = start_discovery(settings, request_id, 0, index=NoHits())

    done = escalate_discovery(settings, request_id, view.revision)

    assert done.open_item == f"Escalated in Discover: {NOT_PROOF_LIMITATION}"


def test_escalating_with_no_limitation_says_developer_request(settings):
    request_id = confirmed_id(settings)
    reply = {
        "findings": [
            {
                "kind": "existing_capability",
                "title": "PDF exists",
                "explanation": "Already there.",
                "hit_ids": [1],
                "confidence": "high",
            }
        ],
        "limitations": [],
    }
    view = start_discovery(settings, request_id, 0, client=StubClient(reply))

    done = escalate_discovery(settings, request_id, view.revision)

    assert done.open_item == "Escalated in Discover: developer request"


def test_the_view_shows_the_choices_for_each_status(settings, first_round):
    request_id, view = first_round

    assert view.outcome == SIMILAR and view.status_label == "SIMILAR IMPLEMENTATION FOUND"
    assert view.choices == [CONFIRM_OPTION, HINT_OPTION, ESCALATE_OPTION]
    assert view.can_hint and view.cap_message == "" and view.open_item == ""
    assert (view.rounds_used, view.max_rounds) == (1, 3)
    assert view.record.version == 1 and view.record.request_id == request_id


def test_the_view_before_any_round_has_no_result_and_no_choices(settings):
    request_id = confirmed_id(settings)

    view = get_discovery_view(settings, request_id)

    assert view.result is None and view.choices == [] and view.rounds_used == 0
    assert view.revision == 0 and view.outcome == "CONFIRMED_FOR_DISCOVERY"


def test_the_view_of_an_unconfirmed_or_unknown_request_is_refused(settings):
    with pytest.raises(DiscoveryError, match="does not exist"):
        get_discovery_view(settings, "CVDA-2026-9999")


@pytest.mark.parametrize("action", [confirm_discovery, escalate_discovery])
def test_finishing_actions_are_refused_from_the_wrong_status(settings, action):
    request_id = confirmed_id(settings)

    with pytest.raises(DiscoveryError, match="cannot be"):
        action(settings, request_id, 0)

    set_status(settings, request_id, "SEARCHING")
    with pytest.raises(DiscoveryError, match="cannot be"):
        action(settings, request_id, 0)


@pytest.mark.parametrize("action", [confirm_discovery, escalate_discovery])
def test_finishing_actions_are_refused_twice(settings, first_round, action):
    request_id, view = first_round
    action(settings, request_id, view.revision)

    with pytest.raises(DiscoveryError, match="cannot be"):
        action(settings, request_id, view.revision + 1)


@pytest.mark.parametrize("action", [confirm_discovery, escalate_discovery])
def test_finishing_actions_refuse_a_stale_window_and_write_nothing(settings, first_round, action):
    request_id, view = first_round
    add_hint_and_search(settings, request_id, "batching helper", view.revision)
    before = event_types(settings, request_id)

    with pytest.raises(StaleRevisionError, match=STALE_MESSAGE):
        action(settings, request_id, view.revision)  # the old revision

    assert event_types(settings, request_id) == before
    assert get_discovery_view(settings, request_id).outcome == SIMILAR


def test_record_v1_and_the_session_are_byte_identical_after_every_discover_action(settings):
    request_id = confirmed_id(settings)
    before = record_state(settings, request_id)

    view = start_discovery(settings, request_id, 0)
    assert record_state(settings, request_id) == before
    view = add_hint_and_search(settings, request_id, "batching helper", view.revision)
    assert record_state(settings, request_id) == before
    confirm_discovery(settings, request_id, view.revision)
    assert record_state(settings, request_id) == before


def test_record_v1_is_unchanged_after_an_escalation(settings, first_round):
    request_id, view = first_round
    before = record_state(settings, request_id)

    escalate_discovery(settings, request_id, view.revision)

    assert record_state(settings, request_id) == before
