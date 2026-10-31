"""Proceed to Approach and the first Generator call (rows 4-1, 4-2, 4-9 to 4-11, 4-28)."""

import pytest

from agents import da_approach_flow as flow
from agents.da_approach_agent import ScriptedApproachClient
from db_table_functions.db_tbl_da_approach import ApproachError
from db_table_functions.db_tbl_da_requests import get_request
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from tests.da_approach_play import (
    Tweaked,
    discovery_confirmed_id,
    event_types,
    events_of,
    proposed,
    texts,
)
from tests.da_discover_play import moves
from tests.da_stub_client import FailingClient, StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return discovery_confirmed_id(settings)


def test_before_starting_the_only_button_is_proceed(settings, request_id):
    view = flow.get_approach_view(settings, request_id)

    assert view.step == "start" and view.request.status == "DISCOVERY_CONFIRMED"
    assert view.buttons == [("start", "Proceed to Approach")]
    assert view.revision == 0 and not view.failed_first_call
    assert [c.passed for c in view.gate] == [False] * 4  # nothing planned yet


def test_4_1_the_first_call_saves_approach_v1_and_moves_to_approach_proposed(settings, request_id):
    view = proposed(settings, request_id)

    assert view.request.status == "APPROACH_PROPOSED"
    saved = view.approach
    assert (saved.approach_version, saved.source) == (1, "proposal")
    assert (saved.record_version, saved.discovery_round, saved.rulebook_version) == (1, 1, 1)
    assert [f.path for f in saved.plan.files] == [
        "src/agents/excel_processor.py",
        "src/agents/upload_validator.py",
    ]
    assert "approach_proposed" in event_types(settings, request_id)
    assert ("DISCOVERY_CONFIRMED", "APPROACH_PROPOSED") in moves(settings, request_id)
    assert view.revision == 1 and view.step == "choices"


def test_the_chat_gets_a_divider_and_the_summary_and_the_first_question(settings, request_id):
    view = proposed(settings, request_id)

    assert "🧭 Approach" in texts(view, "system")
    assistant = texts(view, "assistant")
    assert any("Approach v1: 2 code files" in text for text in assistant)
    assert "Where does Excel upload live?" in assistant[-1]


def test_a_plan_with_no_choice_goes_straight_to_review(settings, request_id):
    def no_choice(data):
        data["design_choices"] = []

    view = proposed(settings, request_id, no_choice)

    assert view.step == "review"
    assert [label for _, label in view.buttons] == [
        "Accept approach", "Change something", "Get help"
    ]


def test_4_2_a_first_call_that_fails_twice_changes_nothing_and_offers_try_again(
    settings, request_id
):
    view = flow.start_approach(settings, request_id, 0, generator=StubClient("nope", "nope"))

    assert view.request.status == "DISCOVERY_CONFIRMED"
    assert view.step == "start" and view.revision == 0
    assert view.failed_first_call and view.buttons == [("start", "Try again")]
    assert view.approach is None
    assert events_of(settings, request_id, "approach_failed")
    assert "approach_proposed" not in event_types(settings, request_id)
    assert "I couldn't make a plan." in texts(view, "assistant")[-1]
    assert ("DISCOVERY_CONFIRMED", "APPROACH_PROPOSED") not in moves(settings, request_id)


def test_try_again_after_a_failure_works_and_clears_the_label(settings, request_id):
    flow.start_approach(settings, request_id, 0, generator=FailingClient("The AI is down"))

    view = flow.start_approach(settings, request_id, 0, generator=ScriptedApproachClient("propose"))

    assert view.request.status == "APPROACH_PROPOSED" and not view.failed_first_call


def test_an_unreachable_ai_message_reaches_the_chat(settings, request_id):
    view = flow.start_approach(settings, request_id, 0, generator=FailingClient("The AI is down"))

    assert "The AI is down" in texts(view, "assistant")[-1]


def test_a_reply_with_a_bad_path_is_retried_once_and_then_accepted(settings, request_id):
    calls = []

    def bad_then_good(data):
        calls.append(1)
        if len(calls) == 1:
            data["files"][0]["path"] = "../x.py"

    view = proposed(settings, request_id, bad_then_good)

    assert len(calls) == 2 and view.request.status == "APPROACH_PROPOSED"


def test_4_9_a_modify_path_no_hit_has_is_saved_with_a_warning(settings, request_id):
    view = proposed(settings, request_id)

    warnings = view.approach.warnings
    assert any("src/agents/upload_validator.py: Not found in Discover" in w for w in warnings)
    assert view.request.status == "APPROACH_PROPOSED"


def test_4_10_a_login_file_is_saved_with_the_login_zone(settings, request_id):
    def login(data):
        data["files"][1] = {
            "path": "src/layouts/login_page.py", "action": "create",
            "purpose": "Show a login hint", "reuses": [],
        }

    view = proposed(settings, request_id, login)

    assert view.approach.zones_touched == ["Login"]
    assert any(w.startswith("Touches Login.") for w in view.approach.warnings)
    assert view.request.status == "APPROACH_PROPOSED"


def test_4_11_needs_people_is_a_warning_and_does_not_block(settings, request_id):
    def protected(data):
        data["needs_people"] = [{"path": "src/web/web_server.py", "reason": "Add a route"}]

    view = proposed(settings, request_id, protected)

    assert "A person must change src/web/web_server.py: Add a route." in view.approach.warnings
    assert view.step == "choices"


def test_starting_twice_is_refused(settings, request_id):
    view = proposed(settings, request_id)

    with pytest.raises(StaleRevisionError):
        flow.start_approach(settings, request_id, 0, generator=Tweaked("propose"))
    with pytest.raises(ApproachError, match="design choice is waiting"):
        flow.start_approach(settings, request_id, view.revision)


def test_4_28_a_stale_revision_is_refused_and_nothing_is_saved(settings, request_id):
    with pytest.raises(StaleRevisionError):
        flow.start_approach(settings, request_id, 3, generator=Tweaked("propose"))

    assert get_request(settings.db_path, request_id).status == "DISCOVERY_CONFIRMED"


def test_a_request_not_yet_discovery_confirmed_cannot_start(settings):
    from tests.da_play import to_confirmed

    unconfirmed = to_confirmed(settings).request.request_id

    with pytest.raises(ApproachError):
        flow.start_approach(settings, unconfirmed, 0)
