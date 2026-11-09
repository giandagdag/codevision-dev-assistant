"""Fix my edit and My edit is right (Phase 8 step 16a; tests 8-6 buttons and 8-8)."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_refine_edit as edit
from agents import da_refine_flow as rflow
from agents import da_refine_lanes as lanes
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import read_build_run
from db_table_functions.db_tbl_da_refine import RefineError, read_refines
from pydantic_classes.da_models import STATUS_BUILDING, STATUS_REVISION
from tests.da_approach_play import events_of
from tests.da_build_play import MODIFY, chat, request_status
from tests.da_refine_play import lane_reply, rev, written_request
from tests.da_stub_client import StubClient
from tests.da_workspace_play import facts_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def not_passing(settings):
    """A request whose check run on a broken edit ended NOT_PASSING."""
    request_id, folder = written_request(settings)
    folder.edit(MODIFY, "def validate(path):\n    return False\n")
    revision = flow.get_revision(settings, request_id)
    rflow.rescan(settings, request_id, facts_of(settings, request_id, folder), revision)
    rflow.start_check(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    assert request_status(settings, request_id) == "NOT_PASSING"
    return request_id


def test_fix_my_edit_starts_a_rebuild_at_once_with_source_failed_check(settings):
    request_id = not_passing(settings)

    state = edit.fix_edit(settings, request_id, rev(settings, request_id))

    assert state.step == "bug_fixing" and state.chosen_lane == "bug"
    assert request_status(settings, request_id) == STATUS_BUILDING
    with open_db(settings.db_path) as conn:
        row = read_refines(conn, request_id)[-1]
        assert read_build_run(conn, request_id, 3).kind == "rebuild"
    assert row.source == "failed_check" and row.chosen_lane == "bug"
    assert row.feedback.startswith("My edit failed")
    started = events_of(settings, request_id, "refine_started")[-1].details
    assert started["from"] == "failed_check"
    moves = events_of(settings, request_id, "status_changed")
    assert STATUS_REVISION in [e.details["to"] for e in moves]


def test_fix_my_edit_is_refused_when_the_status_is_not_not_passing(settings):
    request_id, _ = written_request(settings)  # READY_FOR_REVIEW

    with pytest.raises(RefineError):
        edit.fix_edit(settings, request_id, rev(settings, request_id))


def test_fix_my_edit_is_refused_with_an_old_window(settings):
    request_id = not_passing(settings)
    old = rev(settings, request_id)
    lanes.suggest(settings, request_id, "x is wrong", old, StubClient(lane_reply("bug")))

    with pytest.raises(Exception, match="another window|updated"):
        edit.fix_edit(settings, request_id, old)


def test_8_8_my_edit_is_right_starts_the_requirement_lane_with_text_pre_filled(settings):
    request_id = not_passing(settings)

    state = edit.edit_right(
        settings, request_id, rev(settings, request_id), StubClient(lane_reply("requirement"))
    )

    assert state.step == "req_revise" and state.chosen_lane == "requirement"
    assert request_status(settings, request_id) == STATUS_REVISION
    assert "is intended" in state.pending_feedback and "expects the old behaviour" in (
        state.pending_feedback
    )
    assert state.pending_source == "failed_check"
    with open_db(settings.db_path) as conn:
        assert read_refines(conn, request_id)[-1].source == "failed_check"
    assert "is intended" in chat(settings, request_id, "developer")[-2]


def test_my_edit_is_right_is_refused_when_nothing_failed(settings):
    request_id, _ = written_request(settings)

    with pytest.raises(RefineError):
        edit.edit_right(
            settings, request_id, rev(settings, request_id), StubClient(lane_reply("requirement"))
        )
