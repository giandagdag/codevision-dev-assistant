"""Fix G9 step 3: conflicts block Confirm; the two wording buttons and Try again (U5)."""

import json

import pytest

from agents import da_understand_flow as flow
from agents.da_llm_client import LLMClientError, LLMReply
from agents.da_understand_rules import (
    CHANGE_MYSELF_PREFIX,
    TRY_AGAIN_OPTION,
    USE_WORDING_PREFIX,
)
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_understand import UnderstandError, get_session
from tests import da_play

pytestmark = pytest.mark.usefixtures("published_rulebook")

FIX = "It prints the text NO INPUT PROVIDED as one plain sentence saying what to do"


class RuleClient:
    """Answers the rule check: the conflict, until the criterion has the suggested wording."""

    model = "fake"

    def __init__(self, criterion, fail=False):
        self.criterion, self.fail, self.calls = criterion, fail, 0

    def complete(self, prompt, system=None):
        self.calls += 1
        if self.fail:
            raise LLMClientError("down")
        found = [] if FIX in prompt else [
            {"criterion": self.criterion, "rule": "CV-PY-001", "why": "Not a plain sentence",
             "fix": FIX}
        ]  # fmt: skip
        return LLMReply(text=json.dumps({"conflicts": found}), provider="fake", model="fake")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def _checkpoint(settings):
    view = da_play.to_checkpoint(settings)
    return view, view.record.acceptance_criteria[1].id


def _proceed(settings, view, client):
    return flow.choose_option(
        settings, view.request.request_id, flow.PROCEED_OPTION, view.revision, client=client
    )


def test_confirm_is_refused_and_the_chat_names_the_conflict(settings):
    """G9-1."""
    view, criterion = _checkpoint(settings)

    after = _proceed(settings, view, RuleClient(criterion))

    assert after.request.status != "CONFIRMED_FOR_DISCOVERY"
    chat = after.messages[-1].text
    for part in (criterion, "CV-PY-001", "Error messages are plain sentences",
                 "Not a plain sentence", "Suggested wording: " + FIX):  # fmt: skip
        assert part in chat
    assert after.choices[:2] == [f"{USE_WORDING_PREFIX}1", f"{CHANGE_MYSELF_PREFIX}1"]
    with pytest.raises(UnderstandError):
        flow.choose_option(settings, after.request.request_id, flow.PROCEED_OPTION, after.revision)


def test_use_the_suggested_wording_runs_the_check_again_then_confirm_works(settings):
    """G9-2."""
    view, criterion = _checkpoint(settings)
    client = RuleClient(criterion)
    after = _proceed(settings, view, client)

    after = flow.choose_option(
        settings, after.request.request_id, f"{USE_WORDING_PREFIX}1", after.revision, client=client
    )

    changed = {c.id: c for c in after.record.acceptance_criteria}[criterion]
    assert changed.then == FIX
    assert client.calls == 2
    assert after.input_mode == "choices"  # back at the checkpoint
    done = _proceed(settings, after, client)
    assert done.request.status == "CONFIRMED_FOR_DISCOVERY"
    events = [e.event_type for e in list_audit_events(settings.db_path, done.request.request_id)]
    assert "rule_wording_used" in events
    assert events.count("rule_check") == 2  # the second Proceed reuses the fresh check


def test_change_it_myself_only_explains(settings):
    view, criterion = _checkpoint(settings)
    after = _proceed(settings, view, RuleClient(criterion))

    again = flow.choose_option(
        settings, after.request.request_id, f"{CHANGE_MYSELF_PREFIX}1", after.revision
    )

    assert again.record == after.record
    assert "Type the new wording" in again.messages[-1].text


def test_a_failed_check_blocks_confirm_until_try_again_works(settings):
    view, criterion = _checkpoint(settings)

    after = _proceed(settings, view, RuleClient(criterion, fail=True))

    assert "The rule and gap check could not run: Try again" in after.messages[-1].text
    assert TRY_AGAIN_OPTION in after.choices
    ok = flow.choose_option(
        settings, after.request.request_id, TRY_AGAIN_OPTION, after.revision,
        client=RuleClient(criterion),
    )  # fmt: skip
    assert "CV-PY-001" in ok.messages[-1].text  # now it ran and found the conflict


def test_no_conflicts_confirms_straight_away(settings):
    view, _ = _checkpoint(settings)

    done = flow.choose_option(settings, view.request.request_id, flow.PROCEED_OPTION, view.revision)

    assert done.request.status == "CONFIRMED_FOR_DISCOVERY"
    assert get_session(settings.db_path, done.request.request_id).rule_check_state == "ok"
