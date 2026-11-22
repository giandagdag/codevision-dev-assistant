"""Fix G5 P5 and P6: destructive work needs four things; a senior decides what is missing."""

import json
from datetime import UTC, datetime

import pytest

from agents import da_understand_flow as flow
from agents.da_destructive import Q_BACKUP, Q_NAMES, Q_REASON, missing_questions
from agents.da_llm_client import LLMReply
from agents.da_understand_checks import is_never_assumed
from agents.da_understand_flow import create_understand_request, submit_form
from db_table_functions.db_tbl_da_understand import get_session
from pydantic_classes.da_request_record_models import AcceptanceCriterion, RequestRecord
from tests.da_play import ANSWERS

pytestmark = pytest.mark.usefixtures("published_rulebook")

T0 = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
CLEAN_UP = "Delete the two old work tables LOAN_TMP and LOAN_OLD"


def _record(**changes) -> RequestRecord:
    base = {"request_id": "CVDA-2026-0001", "rulebook_version": 1}
    return RequestRecord(**(base | changes))


def _backup_criterion() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id="AC-1", kind="success", given="Both tables exist",
        when="The clean-up runs", then="A backup of both tables is saved before they are dropped",
    )


def test_all_four_items_present_leaves_nothing_to_ask():
    record = _record(
        reason="The tables are no longer used by any report",
        in_scope=["Table LOAN_TMP", "Table LOAN_OLD"],
        acceptance_criteria=[_backup_criterion()],
    )

    assert missing_questions(record) == []


def test_each_missing_item_is_asked():
    assert missing_questions(_record()) == [Q_REASON, Q_NAMES, Q_BACKUP]


def test_all_is_not_a_name():
    record = _record(reason="x", in_scope=["All tables"], acceptance_criteria=[_backup_criterion()])

    assert missing_questions(record) == [Q_NAMES]


def test_the_questions_are_never_assumed():
    assert all(is_never_assumed(q) for q in (Q_REASON, Q_NAMES, Q_BACKUP))
    assert flow._assumable([Q_REASON, Q_NAMES, Q_BACKUP, "Which colour?"]) == ["Which colour?"]


def _submit(settings, opening, reason, client=None):
    view = create_understand_request(settings, opening, now=T0)
    answers = [reason, *ANSWERS[1:], ""]
    return submit_form(settings, view.request.request_id, answers, view.revision, client, T0)


def test_g5_destructive_work_with_the_fake_script_goes_to_a_senior_for_what_is_missing(
    make_settings,
):
    settings = make_settings()

    view = _submit(settings, "Delete all rows of the old work tables", "They are no longer used")

    session = get_session(settings.db_path, view.request.request_id)
    assert view.request.status != "STOPPED"
    assert session.record.destructive
    assert session.needs_senior
    assert any(Q_BACKUP in item for item in session.record.open_items)


class _TwoTables:
    """A reply that already holds all four items: the planned clean-up of 2 named tables."""

    model = "m"

    def complete(self, prompt, system=None):
        reply = {
            "updates": {
                "title": "Remove two old work tables",
                "objective": "Remove LOAN_TMP and LOAN_OLD after a backup",
                "reason": "No report reads them any more",
                "current_behaviour": "Both tables hold old rows",
                "expected_behaviour": "Both tables are gone and a backup exists",
                "inputs": "The names of two tables",
                "outputs": "A backup file and a log line",
                "functional_flow": ["Save a backup of both tables", "Drop both tables"],
                "in_scope": ["Table LOAN_TMP", "Table LOAN_OLD"],
            },
            "ambiguities": [],
            "hint": "",
            "acceptance_criteria": [
                {"kind": "success", "given": "Both tables exist", "when": "The clean-up runs",
                 "then": "A backup of both tables is saved before they are dropped"},
            ],
        }
        return LLMReply(text=json.dumps(reply), provider="fake", model="m")


class _Review:
    """The safety AI says "review": destructive, but maybe fine."""

    def complete(self, prompt, system=None):
        return LLMReply(text='{"verdict": "review", "reason": "removes data"}',
                        provider="fake", model="m")


def test_g5_a_planned_clean_up_with_all_items_continues_with_the_zone_flag(
    make_settings, monkeypatch
):
    settings = make_settings()
    monkeypatch.setattr("agents.da_safety_check.get_safety_client", lambda s: _Review())

    view = _submit(settings, CLEAN_UP, "No report reads them any more", client=_TwoTables())

    session = get_session(settings.db_path, view.request.request_id)
    assert view.request.status != "STOPPED"
    assert session.record.destructive
    assert not session.needs_senior and not session.record.open_items
