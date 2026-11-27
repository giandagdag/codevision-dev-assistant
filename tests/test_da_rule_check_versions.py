"""Fix G9 step 6: the rule check before a new version, and old requests (U8, U9, G9-6)."""

import json

import pytest

from agents import da_refine_lanes as lanes
from agents import da_understand_flow as flow
from agents.da_llm_client import LLMClientError, LLMReply
from agents.da_rule_check_agent import COULD_NOT_RUN
from agents.da_understand_flow import OLDER_REQUEST_NOTE
from db_table_functions.da_db import open_db
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
