"""Fix G9 finish F1: the gap check in the rule check call (G9-9, 9b, 9c, 9d)."""

import json

import pytest

from agents import da_understand_flow as flow
from agents.da_llm_client import LLMClientError, LLMReply
from agents.da_rule_check_agent import COULD_NOT_RUN
from agents.da_rule_conflicts import keep_real_gaps
from agents.da_understand_rules import (
    ADD_CRITERION_PREFIX,
    CHANGE_MYSELF_PREFIX,
    NOT_NEEDED_PREFIX,
)
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file
from db_table_functions.db_tbl_da_understand import UnderstandError
from pydantic_classes.da_request_record_models import AcceptanceCriterion, RequestRecord
from pydantic_classes.da_rule_conflict_models import Gap
from tests import da_play

pytestmark = pytest.mark.usefixtures("published_rulebook")

SUGGESTED = "Given no arguments, when the tool runs, then it prints NO INPUT PROVIDED"
GAP = {"case": "no arguments", "question": "What should it do with no arguments?",
       "suggested_criterion": SUGGESTED}  # fmt: skip


class GapClient:
    """Answers the rule check: the gap, until a criterion or an out-of-scope line names it."""

    model = "fake"

    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def complete(self, prompt, system=None):
        self.calls += 1
        if self.fail:
            raise LLMClientError("down")
        gaps = [] if "NO INPUT PROVIDED" in prompt else [GAP]
        reply = {"conflicts": [], "uncovered": gaps}
        return LLMReply(text=json.dumps(reply), provider="fake", model="fake")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def _proceed(settings, view, client):
    return flow.choose_option(
        settings, view.request.request_id, flow.PROCEED_OPTION, view.revision, client=client
    )


def _refused(settings):
    client = GapClient()
    view = da_play.to_checkpoint(settings)
    return _proceed(settings, view, client), client


def test_g9_9_an_open_gap_refuses_confirm_and_the_chat_shows_it(settings):
    after, _ = _refused(settings)

    assert after.request.status != "CONFIRMED_FOR_DISCOVERY"
    assert "Gap: no arguments. What should it do with no arguments?" in after.messages[-1].text
    assert after.choices[:3] == [
        f"{ADD_CRITERION_PREFIX}1", f"{CHANGE_MYSELF_PREFIX}1", f"{NOT_NEEDED_PREFIX}1"
    ]  # fmt: skip


def test_g9_9b_add_this_criterion_runs_the_check_again_then_confirm_works(settings):
    after, client = _refused(settings)
    before = len(after.record.acceptance_criteria)

    after = flow.choose_option(
        settings, after.request.request_id, f"{ADD_CRITERION_PREFIX}1", after.revision,
        client=client,
    )  # fmt: skip

    added = after.record.acceptance_criteria[-1]
    assert len(after.record.acceptance_criteria) == before + 1
    assert added.id == f"AC-{before + 1}" and added.then == "it prints NO INPUT PROVIDED"
    assert client.calls == 2
    done = _proceed(settings, after, client)
    assert done.request.status == "CONFIRMED_FOR_DISCOVERY"


def test_g9_9c_not_needed_with_a_reason_is_recorded_and_confirm_works(settings):
    after, client = _refused(settings)
    request_id = after.request.request_id
    with pytest.raises(UnderstandError):  # the reason lives in the box
        flow.choose_option(settings, request_id, f"{NOT_NEEDED_PREFIX}1", after.revision)
    with pytest.raises(UnderstandError):  # too short
        flow.gap_not_needed(settings, request_id, f"{NOT_NEEDED_PREFIX}1", "no", after.revision)

    after = flow.gap_not_needed(
        settings, request_id, f"{NOT_NEEDED_PREFIX}1", "the menu never calls it that way",
        after.revision,
    )  # fmt: skip

    assert "Not needed: no arguments: the menu never calls it that way" in after.record.out_of_scope
    events = [e.event_type for e in list_audit_events(settings.db_path, request_id)]
    assert "gap_not_needed" in events
    audited = [e.details for e in list_audit_events(settings.db_path, request_id)
               if e.event_type == "gap_not_needed"]  # fmt: skip
    assert audited[0]["gap"] == "1" and "case" not in audited[0]  # the number, not the AI's words
    assert _proceed(settings, after, client).request.status == "CONFIRMED_FOR_DISCOVERY"


def test_add_this_criterion_audits_only_the_gap_number(settings):
    after, client = _refused(settings)

    flow.choose_option(
        settings, after.request.request_id, f"{ADD_CRITERION_PREFIX}1", after.revision,
        client=client,
    )  # fmt: skip

    audited = [e.details for e in list_audit_events(settings.db_path, after.request.request_id)
               if e.event_type == "gap_criterion_added"]  # fmt: skip
    assert audited == [{"gap": "1"}]


def test_a_case_dropped_by_t3_is_a_question_on_the_summary_tab(settings):
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_audit import insert_audit_event

    view = da_play.to_checkpoint(settings)
    request_id = view.request.request_id
    assert "Open question" not in flow.get_understand_view(settings, request_id).rule_check_note
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        dropped = {"cases": ["test_ac_2"]}
        insert_audit_event(conn, request_id, "system", "test_case_dropped", dropped)

    note = flow.get_understand_view(settings, request_id).rule_check_note

    assert "Open question" in note and "test_ac_2" in note


def test_the_check_failing_says_so_and_blocks_confirm(settings):
    view = da_play.to_checkpoint(settings)

    after = _proceed(settings, view, GapClient(fail=True))

    assert after.request.status != "CONFIRMED_FOR_DISCOVERY"
    assert COULD_NOT_RUN == "The rule and gap check could not run: Try again"
    assert COULD_NOT_RUN in after.messages[-1].text


def _record(given="A user runs the tool", **changes) -> RequestRecord:
    criterion = AcceptanceCriterion(
        id="AC-1", kind="success", given=given, when="They press go", then="It works"
    )
    base = {"request_id": "CVDA-2026-0001", "rulebook_version": 1,
            "acceptance_criteria": [criterion]}  # fmt: skip
    return RequestRecord(**(base | changes))


def test_g9_9d_a_gap_a_criterion_already_names_is_dropped_by_plain_code():
    rulebook = load_rulebook_file(SEED_RULEBOOK_FILE)
    record = _record(given="The tool is run with NO arguments at all")
    gaps = [Gap("Arguments no", "q", "g"), Gap("empty values", "q", "g")]

    kept = keep_real_gaps(gaps, record, rulebook)

    assert [g.case for g in kept] == ["empty values"]  # case and word order do not matter


def test_g9_9e_a_planned_case_with_no_covering_criterion_is_not_planned():
    from agents.da_tester_agent import write_test_plan
    from tests.da_stub_client import StubClient

    plan = {"cases": [
        {"criterion_id": "AC-1", "given": "A user runs the tool", "expect": "It prints OK text"},
        {"criterion_id": "AC-9", "given": "An empty file", "expect": "It prints an error text"},
    ]}  # fmt: skip

    result = write_test_plan(StubClient(plan), _record(), [], "")

    assert result.ok and result.not_covered == ["An empty file"]
    assert [case.criterion_id for case in result.reply.cases] == ["AC-1"]


def test_a_not_needed_line_and_the_cap_of_five():
    rulebook = load_rulebook_file(SEED_RULEBOOK_FILE)
    record = _record(out_of_scope=["Not needed: empty values: never happens here"])
    gaps = [Gap("empty values", "q", "g")] + [Gap(f"case number {n}x", "q", "g") for n in range(7)]

    kept = keep_real_gaps(gaps, record, rulebook)

    assert len(kept) == 5 and "empty values" not in [g.case for g in kept]
