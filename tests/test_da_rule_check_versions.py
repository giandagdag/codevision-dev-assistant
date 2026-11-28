"""Fix G9 step 6: the rule check before a new version, and old requests (U8, U9, G9-6)."""

import json

import pytest

from agents import da_refine_lanes as lanes
from agents import da_refine_rules as rules
from agents import da_understand_flow as flow
from agents.da_llm_client import LLMClientError, LLMReply
from agents.da_refine_actions import get_refine_bar
from agents.da_rule_check_agent import COULD_NOT_RUN
from agents.da_rule_exception_actions import approve_exception
from agents.da_understand_flow import OLDER_REQUEST_NOTE
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_escalation import read_open_escalation
from db_table_functions.db_tbl_da_refine import RefineError
from tests import da_play
from tests.da_refine_play import lane_reply, rev, written_request
from tests.da_stub_client import StubClient
from tests.test_da_refine_lanes import CHANGE_AND_ADD

pytestmark = pytest.mark.usefixtures("published_rulebook")


class RuleClient:
    model = "fake"

    def __init__(self, conflict=True, fail=False):
        self.conflict, self.fail = conflict, fail

    def complete(self, prompt, system=None):
        if self.fail:
            raise LLMClientError("down")
        found = [{"criterion": "AC-1", "rule": "CV-PY-001", "why": "Not plain", "fix": "x"}]
        text = json.dumps({"conflicts": found if self.conflict else []})
        return LLMReply(text=text, provider="fake", model="fake")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def _at_v2_checkpoint(settings):
    request_id, _ = written_request(settings)
    lanes.suggest(
        settings, request_id, "Reject big files", rev(settings, request_id),
        StubClient(lane_reply("requirement")),
    )  # fmt: skip
    lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))
    lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(CHANGE_AND_ADD))
    return request_id


def test_g9_6_a_conflict_stops_the_new_version_and_nothing_is_saved(settings):
    request_id = _at_v2_checkpoint(settings)

    with pytest.raises(RefineError) as error:
        lanes.confirm_revision(
            settings, request_id, rev(settings, request_id), client=RuleClient()
        )

    assert "CV-PY-001" in str(error.value)
    state = lanes.confirm_revision(
        settings, request_id, rev(settings, request_id), client=RuleClient(conflict=False)
    )
    assert state.step != "req_checkpoint"  # the second try, with no conflict, went through


def test_f1d_a_gap_stops_the_new_version_too(settings):
    request_id = _at_v2_checkpoint(settings)

    class GapClient(RuleClient):
        def complete(self, prompt, system=None):
            gap = {"case": "no arguments", "question": "What then?", "suggested_criterion": "g"}
            return LLMReply(text=json.dumps({"conflicts": [], "uncovered": [gap]}),
                            provider="fake", model="fake")  # fmt: skip

    with pytest.raises(RefineError) as error:
        lanes.confirm_revision(
            settings, request_id, rev(settings, request_id), client=GapClient()
        )

    assert "Gap: no arguments. What then?" in str(error.value)


def test_a_failed_check_blocks_the_new_version(settings):
    request_id = _at_v2_checkpoint(settings)

    with pytest.raises(RefineError) as error:
        lanes.confirm_revision(
            settings, request_id, rev(settings, request_id), client=RuleClient(fail=True)
        )

    assert COULD_NOT_RUN in str(error.value)


def test_an_older_request_shows_that_the_check_did_not_run(settings):
    view = da_play.to_checkpoint(settings)
    done = flow.choose_option(settings, view.request.request_id, flow.PROCEED_OPTION, view.revision)
    assert done.rule_check_note == ""  # the check ran at Confirm

    with open_db(settings.db_path) as conn:
        # The audit trail is append-only; the trigger goes only to act out an old database.
        conn.execute("DROP TRIGGER da_audit_events_no_delete")
        conn.execute("DELETE FROM da_audit_events WHERE event_type = 'rule_check'")
        conn.commit()

    again = flow.get_understand_view(settings, view.request.request_id)
    assert again.rule_check_note == OLDER_REQUEST_NOTE


# --- F5: the same buttons in the v2 lane ---


class GapClient(RuleClient):
    gap = {
        "case": "empty file", "question": "What then?",
        "suggested_criterion": "Given an empty file, when it is read, then it is refused",
    }  # fmt: skip

    def complete(self, prompt, system=None):
        text = json.dumps({"conflicts": [], "uncovered": [self.gap]})
        return LLMReply(text=text, provider="fake", model="fake")


def _bar(settings, request_id):
    return get_refine_bar(settings, request_id)


def _keys(settings, request_id):
    return [key for key, _label in _bar(settings, request_id).buttons]


def _press(settings, request_id, key, text="", client=None):
    rules.perform_rule_button(settings, request_id, rev(settings, request_id), key, text, client)


def _audited(settings, request_id, event_type):
    return [e.details for e in list_audit_events(settings.db_path, request_id)
            if e.event_type == event_type]  # fmt: skip


def _blocked(settings, request_id, client):
    with pytest.raises(RefineError):
        lanes.confirm_revision(settings, request_id, rev(settings, request_id), client=client)


def test_f5_g9_6_a_conflict_shows_its_buttons_and_wording_clears_it(settings):
    request_id = _at_v2_checkpoint(settings)
    _blocked(settings, request_id, RuleClient())

    assert _keys(settings, request_id)[:3] == ["rc:use:1", "rc:change:1", "rc:ask:1"]
    assert "CV-PY-001" in _bar(settings, request_id).note

    _press(settings, request_id, "rc:use:1", client=RuleClient(conflict=False))

    state = lanes.get_refine_state(settings, request_id)
    assert state.check_conflicts == []
    assert state.pending_record.acceptance_criteria[0].then == "x"
    assert not [k for k in _keys(settings, request_id) if k.startswith("rc:")]


def test_f5_a_gap_gets_add_change_and_not_needed(settings):
    request_id = _at_v2_checkpoint(settings)
    _blocked(settings, request_id, GapClient())
    assert _keys(settings, request_id)[:3] == ["rc:add:1", "rc:change:1", "rc:no:1"]

    before = len(lanes.get_refine_state(settings, request_id).pending_record.acceptance_criteria)
    _press(settings, request_id, "rc:add:1", client=RuleClient(conflict=False))
    after = lanes.get_refine_state(settings, request_id).pending_record
    assert len(after.acceptance_criteria) == before + 1
    assert _audited(settings, request_id, "gap_criterion_added") == [{"gap": "1"}]  # no AI words


def test_f5_not_needed_wants_a_reason_and_records_the_line(settings):
    request_id = _at_v2_checkpoint(settings)
    _blocked(settings, request_id, GapClient())
    with pytest.raises(RefineError):
        _press(settings, request_id, "rc:no:1", "short", RuleClient(conflict=False))

    reason = "files are never empty here"
    _press(settings, request_id, "rc:no:1", reason, RuleClient(conflict=False))

    state = lanes.get_refine_state(settings, request_id)
    assert state.check_gaps == []
    assert any(x.startswith("Not needed: empty file") for x in state.pending_record.out_of_scope)
    assert _audited(settings, request_id, "gap_not_needed") == [{"gap": "1", "reason": reason}]


def test_f5_change_it_myself_only_says_where_to_type(settings):
    request_id = _at_v2_checkpoint(settings)
    _blocked(settings, request_id, RuleClient())

    _press(settings, request_id, "rc:change:1")

    assert lanes.get_refine_state(settings, request_id).check_conflicts  # still open


def test_f5_ask_for_an_exception_then_approve_writes_rx_into_the_new_version(settings):
    request_id = _at_v2_checkpoint(settings)
    _blocked(settings, request_id, RuleClient())
    with pytest.raises(RefineError):
        _press(settings, request_id, "rc:ask:1", "short")

    _press(settings, request_id, "rc:ask:1", "the batch job needs this")

    with open_db(settings.db_path) as conn:
        row = read_open_escalation(conn, request_id)
    assert [(a.criterion, a.rule) for a in row.exception_asks] == [("AC-1", "CV-PY-001")]
    approve_exception(settings, row.escalation_id, row.revision, "senior1", "ok")

    state = lanes.get_refine_state(settings, request_id)
    assert state.step == "req_checkpoint"
    assert state.pending_record.exceptions[0].startswith("RX-1: CV-PY-001 allowed for AC-1")
    assert "CV-PY-001" not in _bar(settings, request_id).note  # the conflict is allowed now


def test_f5_a_failed_check_offers_try_again(settings):
    request_id = _at_v2_checkpoint(settings)
    _blocked(settings, request_id, RuleClient(fail=True))
    assert _keys(settings, request_id)[0] == "rc:again"

    _press(settings, request_id, "rc:again", client=RuleClient(conflict=False))
    assert not lanes.get_refine_state(settings, request_id).check_failed


def test_f5_an_old_state_row_reads_with_no_items():
    from pydantic_classes.da_refine_models import RefineState

    state = RefineState.model_validate({"request_id": "CVDA-2026-0001"})
    assert (state.check_conflicts, state.check_gaps, state.check_failed) == ([], [], False)
