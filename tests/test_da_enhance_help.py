"""Phase 9 step 15: Get help at the Phase 9 steps (test 9-45) and the stale refusal on every
action (test 9-46). No real AI: made-up code, the scripted fake client."""

import pytest

from agents import da_enhance_flow as enhance
from agents import da_safety_net_flow as net_flow
from agents.da_enhance_help import ESCALATED_PREFIX, request_help
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_enhance import EnhanceError, read_enhance_state
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from tests.test_da_safety_net_flow import Runner, at_s_writing

pytestmark = pytest.mark.usefixtures("published_rulebook")


def status_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_request(conn, request_id).status


def state_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_enhance_state(conn, request_id)


def at_review(settings, tmp_path):
    request_id = at_s_writing(settings)
    runner = Runner(tmp_path)
    net_flow.run_safety_net(settings, request_id, state_of(settings, request_id).revision, runner)
    return request_id


def test_9_45_get_help_while_finding_the_program(make_settings):
    settings = make_settings()
    started = enhance.start_enhance_request(settings)

    view = request_help(settings, started.request_id, started.revision)

    assert status_of(settings, started.request_id) == "ESCALATION_REQUIRED"
    assert view.step == "escalated"
    assert state_of(settings, started.request_id).open_item == f"{ESCALATED_PREFIX}e_find"
    [event] = [
        e for e in list_audit_events(settings.db_path, started.request_id)
        if e.event_type == "escalated"
    ]
    assert event.details["open_item"] == "Escalated in Enhance: e_find"


def test_9_45_get_help_at_the_safety_net_review(make_settings, tmp_path):
    settings = make_settings()
    request_id = at_review(settings, tmp_path)
    assert state_of(settings, request_id).step == "s_review"

    request_help(settings, request_id, state_of(settings, request_id).revision)

    assert status_of(settings, request_id) == "ESCALATION_REQUIRED"
    assert state_of(settings, request_id).open_item == "Escalated in Enhance: s_review"


def test_9_45_get_help_twice_is_refused(make_settings):
    settings = make_settings()
    started = enhance.start_enhance_request(settings)
    view = request_help(settings, started.request_id, started.revision)

    with pytest.raises(EnhanceError, match="not available"):
        request_help(settings, started.request_id, view.revision)


def test_9_45_get_help_while_the_net_is_being_written_is_refused(make_settings):
    settings = make_settings()
    request_id = at_s_writing(settings)
    assert state_of(settings, request_id).step == "s_writing"

    with pytest.raises(EnhanceError, match="not available"):
        request_help(settings, request_id, state_of(settings, request_id).revision)
    assert status_of(settings, request_id) == "DISCOVERY_CONFIRMED"


def test_9_46_every_phase_9_action_refuses_an_old_revision(make_settings, tmp_path):
    settings = make_settings()
    request_id = at_review(settings, tmp_path)
    old = state_of(settings, request_id).revision - 1  # a window that was open before the review

    actions = [
        lambda: request_help(settings, request_id, old),
        lambda: net_flow.accept_safety_net(settings, request_id, old),
        lambda: net_flow.mark_expected_change(settings, request_id, "S-1", "AC-1", old),
        lambda: net_flow.correct_safety_net(settings, request_id, "Check the dates too.", old),
        lambda: net_flow.run_safety_net(settings, request_id, old, Runner(tmp_path)),
        lambda: enhance.find_program(settings, request_id, "limits", old),
    ]
    for action in actions:
        with pytest.raises(StaleRevisionError):
            action()
    assert state_of(settings, request_id).step == "s_review"
