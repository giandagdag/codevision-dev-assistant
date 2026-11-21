"""Fix G5 part 1: a request the safety check stops writes no criteria and becomes STOPPED."""

from datetime import UTC, datetime

import pytest

from agents import da_understand_flow as flow
from agents.da_llm_client import LLMClientError, LLMReply
from agents.da_safety_check import EVENT_STOP, STOP_LINE, WHAT_DESTRUCTIVE, WHAT_OTHER
from agents.da_understand_flow import create_understand_request, submit_form
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_handoff import refuse_if_locked
from db_table_functions.db_tbl_da_understand import get_session
from pydantic_classes.da_handoff_models import STOPPED_MESSAGE
from tests.da_play import ANSWERS

pytestmark = pytest.mark.usefixtures("published_rulebook")

T0 = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
DELETE_ALL = "I need a program to delete all database tables"


class _Ai:
    def __init__(self, text=None, fail=False):
        self.text, self.fail = text, fail

    def complete(self, prompt, system=None):
        if self.fail:
            raise LLMClientError("down")
        return LLMReply(text=self.text, provider="fake", model="m")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def no_interpreter(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No criteria may be written for a stopped request.")

    monkeypatch.setattr(flow, "interpret", forbidden)


def _submit(settings, opening, reason, optional=""):
    view = create_understand_request(settings, opening, now=T0)
    answers = [reason, *ANSWERS[1:], optional]
    return submit_form(settings, view.request.request_id, answers, view.revision, now=T0)


def _events(settings, view, kind):
    return [e for e in list_audit_events(settings.db_path, view.request.request_id)
            if e.event_type == kind]


def test_g5_1_delete_all_tables_with_a_grudge_is_stopped(settings, no_interpreter):
    view = _submit(settings, DELETE_ALL, "I hate my boss")

    assert view.request.status == "STOPPED"
    assert view.input_mode == "stopped"
    assert view.progress_text == "Stopped by the safety check"
    assert view.messages[-1].speaker == "assistant"
    assert view.messages[-1].text == STOP_LINE.format(what=WHAT_DESTRUCTIVE)
    (event,) = _events(settings, view, EVENT_STOP)
    assert event.details["kind"] == "both"
    assert {"hate", "boss"} <= set(event.details["words"])
    assert event.details["previous_status"] == "CLARIFICATION_IN_PROGRESS"
    assert event.details["previous_step"] == "form"
    assert DELETE_ALL not in str(event.details)


def test_g5_2_a_grudge_on_a_harmless_request_stops_even_when_the_ai_says_ok(
    settings, no_interpreter
):
    view = _submit(settings, "A monthly loan report", "to get back at my manager")

    assert view.request.status == "STOPPED"
    assert view.messages[-1].text == STOP_LINE.format(what=WHAT_OTHER)
    assert _events(settings, view, EVENT_STOP)[0].details["ai_verdict"] == "ok"


def test_the_ai_can_stop_a_request_the_words_did_not(settings, monkeypatch, no_interpreter):
    ai = _Ai('{"verdict": "stop", "reason": "looks like sabotage"}')
    monkeypatch.setattr("agents.da_safety_check.get_safety_client", lambda s: ai)

    view = _submit(settings, "A monthly loan report", "the audit team is annoying")

    assert view.request.status == "STOPPED"
    assert _events(settings, view, EVENT_STOP)[0].details["ai_reason"] == "looks like sabotage"


def test_a_harmless_request_is_not_stopped(settings):
    view = _submit(settings, "A monthly loan report", "The report is needed each month")

    assert view.request.status != "STOPPED"
    assert not _events(settings, view, EVENT_STOP)


def test_g5_4_a_failed_ai_call_with_destructive_words_does_not_stop_but_is_not_silent(
    settings, monkeypatch
):
    monkeypatch.setattr("agents.da_safety_check.get_safety_client", lambda s: _Ai(fail=True))

    view = _submit(settings, DELETE_ALL, "clean-up")

    # Destructive without intent goes to the P5 checks (step 5), never straight on silently.
    assert view.request.status != "STOPPED"


def test_a_stopped_request_refuses_every_developer_action(settings, no_interpreter):
    view = _submit(settings, DELETE_ALL, "I hate my boss")

    with open_db(settings.db_path) as conn, pytest.raises(Exception, match="stopped") as error:
        refuse_if_locked(conn, view.request.request_id)
    assert str(error.value) == STOPPED_MESSAGE
    assert get_session(settings.db_path, view.request.request_id).step == "stopped"
