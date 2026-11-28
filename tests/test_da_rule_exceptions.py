"""Fix G9 step 4: Ask for an exception, then the senior approves or rejects (U6, G9-3)."""

import json

import pytest

from agents import da_understand_flow as flow
from agents.da_llm_client import LLMReply
from agents.da_rule_exception_actions import approve_exception, reject_exception
from agents.da_senior_actions import SeniorActionError
from agents.da_understand_rules import ASK_EXCEPTION_PREFIX, excepted_pairs
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_escalation import ensure_escalation_tables, read_escalations
from db_table_functions.db_tbl_da_understand import UnderstandError, get_session
from tests import da_play

pytestmark = pytest.mark.usefixtures("published_rulebook")

REASON = "The legacy screen needs this exact wording"


class ConflictClient:
    """Always reports one conflict on the second criterion (until an exception allows it)."""

    model = "fake"

    def __init__(self, criterion):
        self.criterion = criterion

    def complete(self, prompt, system=None):
        found = [{"criterion": self.criterion, "rule": "CV-PY-001", "why": "Not plain", "fix": "x"}]
        return LLMReply(text=json.dumps({"conflicts": found}), provider="fake", model="fake")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def _at_conflict(settings):
    view = da_play.to_checkpoint(settings)
    criterion = view.record.acceptance_criteria[1].id
    after = flow.choose_option(
        settings, view.request.request_id, flow.PROCEED_OPTION, view.revision,
        client=ConflictClient(criterion),
    )  # fmt: skip
    return after, criterion


def _rows(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_escalation_tables(conn)
        return read_escalations(conn, request_id)


def _ask(settings, view, text=REASON):
    return flow.ask_for_exception(
        settings, view.request.request_id, f"{ASK_EXCEPTION_PREFIX}1", text, view.revision
    )


def test_the_third_button_is_offered(settings):
    view, _ = _at_conflict(settings)

    assert f"{ASK_EXCEPTION_PREFIX}1" in view.choices


def test_a_short_reason_is_refused_and_nothing_is_written(settings):
    view, _ = _at_conflict(settings)

    with pytest.raises(UnderstandError):
        _ask(settings, view, "too short")

    assert _rows(settings, view.request.request_id) == []


def test_asking_opens_one_inbox_item_and_the_request_waits(settings):
    view, criterion = _at_conflict(settings)

    after = _ask(settings, view)

    row = _rows(settings, view.request.request_id)[0]
    assert row.triggers == ["rule_exception"] and row.outcome == "open"
    assert (row.exception_asks[0].criterion, row.exception_asks[0].rule) == (criterion, "CV-PY-001")
    assert after.request.status == "ESCALATION_REQUIRED"
    events = [e.event_type for e in list_audit_events(settings.db_path, view.request.request_id)]
    assert "rule_exception_asked" in events


def test_approve_writes_an_rx_line_and_the_conflict_stops_blocking(settings):
    view, criterion = _at_conflict(settings)
    _ask(settings, view)
    row = _rows(settings, view.request.request_id)[0]

    approve_exception(settings, row.escalation_id, row.revision, "senior1", "Fine for this screen")

    session = get_session(settings.db_path, view.request.request_id)
    assert session.record.exceptions[0].startswith("RX-1: CV-PY-001 allowed for " + criterion)
    assert "approved by senior1" in session.record.exceptions[0]
    assert (criterion, "CV-PY-001") in excepted_pairs(session.record)
    done = flow.choose_option(
        settings, view.request.request_id, flow.PROCEED_OPTION, session.revision,
        client=ConflictClient(criterion),
    )  # fmt: skip
    assert done.request.status == "CONFIRMED_FOR_DISCOVERY"
    events = [e.event_type for e in list_audit_events(settings.db_path, view.request.request_id)]
    assert "rule_exception" in events


def test_reject_returns_the_request_with_the_conflict_still_open(settings):
    view, _ = _at_conflict(settings)
    _ask(settings, view)
    row = _rows(settings, view.request.request_id)[0]

    reject_exception(settings, row.escalation_id, row.revision, "senior1", "Please reword it")

    session = get_session(settings.db_path, view.request.request_id)
    assert session.record.exceptions == []
    after = flow.get_understand_view(settings, view.request.request_id)
    assert after.request.status != "ESCALATION_REQUIRED"
    assert f"{ASK_EXCEPTION_PREFIX}1" in after.choices


def _add_get_help(settings, request_id):
    from datetime import UTC, datetime

    from agents.da_escalation_flow import escalate
    from pydantic_classes.da_escalation_models import TriggerDecision

    decision = TriggerDecision(trigger="get_help", fire=True, reason="Escalated in Understand")
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        escalate(conn, request_id, decision, datetime.now(UTC))


@pytest.mark.parametrize("verdict", [approve_exception, reject_exception])
def test_a_row_with_another_reason_stays_open_after_the_exception_is_settled(settings, verdict):
    """Finish review 3: only the exception is settled; Get help still waits for the senior."""
    view, _ = _at_conflict(settings)
    _ask(settings, view)
    _add_get_help(settings, view.request.request_id)
    row = _rows(settings, view.request.request_id)[0]
    assert set(row.triggers) == {"rule_exception", "get_help"}

    verdict(settings, row.escalation_id, row.revision, "senior1", "Decided")

    left = _rows(settings, view.request.request_id)[0]
    assert left.outcome == "open" and left.triggers == ["get_help"]
    assert left.exception_asks == [] and len(left.reasons) == 1
    assert "may break" not in left.reasons[0]
    status = flow.get_understand_view(settings, view.request.request_id).request.status
    assert status == "ESCALATION_REQUIRED"
    events = [e.event_type for e in list_audit_events(settings.db_path, view.request.request_id)]
    assert "rule_exception" in events


def test_the_inbox_shows_approve_and_reject_and_the_action_runs(make_settings):
    """Review round 2: the senior can say yes or no on the Inbox screen, not only in code."""
    from agents.da_inbox import get_inbox_row
    from callbacks.screen_callbacks.da_inbox_page_callbacks import run_senior_action
    from layouts.da_inbox_page import MODE_APPROVE, action_bar

    settings = make_settings(senior_ids=("ann",), developer_id="ann")
    view, criterion = _at_conflict(settings)
    _ask(settings, view)
    raw = _rows(settings, view.request.request_id)[0]
    inbox_row = get_inbox_row(settings, raw.escalation_id)
    assert "Approve exception" in str(action_bar(inbox_row, False))
    target = {"escalation_id": raw.escalation_id, "revision": raw.revision,
              "request_id": view.request.request_id}  # fmt: skip

    line = run_senior_action(settings, MODE_APPROVE, target, "ann", "Fine for this screen")

    assert line == f"Exception approved on {view.request.request_id}"
    session = get_session(settings.db_path, view.request.request_id)
    assert (criterion, "CV-PY-001") in excepted_pairs(session.record)


def test_a_note_is_required(settings):
    view, _ = _at_conflict(settings)
    _ask(settings, view)
    row = _rows(settings, view.request.request_id)[0]

    with pytest.raises(SeniorActionError):
        approve_exception(settings, row.escalation_id, row.revision, "senior1", " ")
