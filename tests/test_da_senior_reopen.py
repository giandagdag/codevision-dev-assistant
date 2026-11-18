"""B2 step 6 (S7f): a senior returns a request with 1 to 5 more decision rounds."""

from datetime import UTC, datetime

import pytest

from agents.da_senior_actions import SeniorActionError
from agents.da_senior_reopen import reopen_decisions
from agents.da_understand_flow import SEND_SENIOR_OPTION, choose_option, get_understand_view
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_escalation import read_open_escalation
from db_table_functions.db_tbl_da_understand import get_session, save_session
from tests.da_stub_client import StubClient, stub_reply
from tests.test_da_understand_flow import GOOD_Q1, answer, choose, limit_five, start
from tests.test_da_understand_limit_buttons import ask

pytestmark = pytest.mark.usefixtures("published_rulebook", "limit_five")
limit_five = limit_five  # noqa: PLW0127


@pytest.fixture
def settings(make_settings):
    return make_settings()


def escalated(settings, extra_questions):
    """Five decisions answered, then the extra ones past the limit, then Send to my senior."""
    view = start(settings)
    five = [ask(f"Decision {n}?") for n in range(5)]
    view = answer(settings, view, client=StubClient(stub_reply(GOOD_Q1["updates"], five)))
    for _ in range(5):
        view = choose(settings, view, "Yes")
    more = [ask(q) for q in extra_questions]
    view = answer(settings, view, client=StubClient(stub_reply({}, more)))
    view = choose_option(settings, view.request.request_id, SEND_SENIOR_OPTION, view.revision)
    with open_db(settings.db_path) as conn:
        return view.request.request_id, read_open_escalation(conn, view.request.request_id)


def test_reopen_adds_rounds_for_this_request_and_asks_the_next_decision(settings):
    request_id, row = escalated(settings, ["Extra one?", "Extra two?"])

    reopen_decisions(settings, row.escalation_id, row.revision, "senior-1", 1, "Go on")

    session = get_session(settings.db_path, request_id)
    assert session.extra_decision_rounds == 1  # 5 (this test's policy) + 1 = 6 for this request
    assert session.step == "decision"
    assert [d.question for d in session.pending_decisions] == ["Extra one?"]
    assert session.pending_decisions[0].options == ["Yes", "No"]
    assert [d.question for d in session.aside_decisions] == ["Extra two?"]
    assert session.record.open_items == ["Needs a senior decision: Extra two?"]
    assert session.needs_senior is True
    view = get_understand_view(settings, request_id)
    assert view.request.status == "DECISION_REQUIRED"
    assert view.choices == ["Yes", "No", "I need help deciding"]
    events = [e.event_type for e in list_audit_events(settings.db_path, request_id)]
    assert "decision_limit_raised" in events


def test_enough_rounds_bring_every_waiting_decision_back(settings):
    request_id, row = escalated(settings, ["Extra one?", "Extra two?"])

    reopen_decisions(settings, row.escalation_id, row.revision, "senior-1", 5, "Go on")

    session = get_session(settings.db_path, request_id)
    assert len(session.pending_decisions) == 2
    assert session.aside_decisions == []
    assert session.needs_senior is False
    assert session.record.open_items == []


@pytest.mark.parametrize("rounds", [0, 6])
def test_rounds_outside_1_to_5_are_refused(settings, rounds):
    request_id, row = escalated(settings, ["Extra one?"])

    with pytest.raises(SeniorActionError, match="1 to 5"):
        reopen_decisions(settings, row.escalation_id, row.revision, "senior-1", rounds, "No")

    assert get_session(settings.db_path, request_id).extra_decision_rounds == 0


def test_a_request_not_waiting_at_the_limit_is_refused_and_nothing_is_written(settings):
    request_id, row = escalated(settings, ["Extra one?"])
    with open_db(settings.db_path) as conn:
        session = get_session(settings.db_path, request_id)
        session.step = "correction"  # for example a request that moved on to Build
        save_session(conn, session, session.revision, datetime.now(UTC))

    with pytest.raises(SeniorActionError, match="not waiting at the decision limit"):
        reopen_decisions(settings, row.escalation_id, row.revision, "senior-1", 2, "Go on")

    assert get_session(settings.db_path, request_id).extra_decision_rounds == 0
    events = [e.event_type for e in list_audit_events(settings.db_path, request_id)]
    assert "decision_limit_raised" not in events


def test_a_missing_note_changes_nothing(settings):
    request_id, row = escalated(settings, ["Extra one?"])

    with pytest.raises(SeniorActionError, match="note"):
        reopen_decisions(settings, row.escalation_id, row.revision, "senior-1", 2, "  ")

    assert get_session(settings.db_path, request_id).extra_decision_rounds == 0
