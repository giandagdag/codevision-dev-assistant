"""Get help in a lane and the stale check on Refine actions (Phase 8 step 12, tests 8-36, 8-37)."""

import pytest

from agents import da_refine_bug as bug
from agents import da_refine_lanes as lanes
from agents.da_refine_help import request_help
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_state
from db_table_functions.db_tbl_da_refine import RefineError, read_refines
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_models import STATUS_ESCALATION, STATUS_REVISION
from tests.da_approach_play import events_of
from tests.da_build_play import request_status
from tests.da_refine_play import lane_reply, rev, written_request
from tests.da_stub_client import StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def in_lane(settings):
    """A request with the bug lane open (step bug_start, status REVISION_IN_PROGRESS)."""
    request_id, _ = written_request(settings)
    lanes.suggest(
        settings, request_id, "It breaks", rev(settings, request_id), StubClient(lane_reply("bug"))
    )
    lanes.choose_lane(settings, request_id, "bug", rev(settings, request_id))
    return request_id


def test_8_36_get_help_in_a_lane_escalates_with_the_step_named(settings, in_lane):
    state = request_help(settings, in_lane, rev(settings, in_lane))

    assert request_status(settings, in_lane) == STATUS_ESCALATION
    assert state.step == "escalated"
    with open_db(settings.db_path) as conn:
        assert read_approach_state(conn, in_lane).open_item == "Escalated in Refine: bug_start"
        assert read_refines(conn, in_lane)[0].result == "escalated"
    assert events_of(settings, in_lane, "escalated")[0].details["step"] == "bug_start"


def test_get_help_at_the_checkpoint_names_that_step(settings):
    request_id, _ = written_request(settings)
    lanes.suggest(
        settings,
        request_id,
        "Change it",
        rev(settings, request_id),
        StubClient(lane_reply("requirement")),
    )
    lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))
    assert request_status(settings, request_id) == STATUS_REVISION

    request_help(settings, request_id, rev(settings, request_id))

    with open_db(settings.db_path) as conn:
        item = read_approach_state(conn, request_id).open_item
    assert item.startswith("Escalated in Refine: req_")


def test_get_help_is_refused_when_no_lane_is_open(settings):
    request_id, _ = written_request(settings)

    with pytest.raises(RefineError):
        request_help(settings, request_id, rev(settings, request_id))


def test_8_37_every_refine_action_refuses_an_old_revision(settings, in_lane):
    old = rev(settings, in_lane) - 1
    actions = [
        lambda: lanes.cancel(settings, in_lane, old),
        lambda: request_help(settings, in_lane, old),
        lambda: bug.reject_repro(settings, in_lane, old),
        lambda: bug.confirm_repro(settings, in_lane, old),
        lambda: lanes.confirm_revision(settings, in_lane, old),
        lambda: lanes.choose_lane(settings, in_lane, "bug", old),
    ]
    for action in actions:
        with pytest.raises(StaleRevisionError):
            action()
    assert request_status(settings, in_lane) == STATUS_REVISION
