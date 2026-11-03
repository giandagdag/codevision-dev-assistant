"""The ways out of a blocked check, and the cancelled picker (rows 5-19 to 5-21; W5, W6, P14)."""

from datetime import UTC, datetime

import pytest

from agents import da_approach_flow as approach_flow
from agents import da_workspace_flow as flow
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_state, save_approach_state
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_workspace import WorkspaceError, read_workspace_state
from tests.da_approach_play import event_types, events_of
from tests.da_discover_play import moves
from tests.da_workspace_play import good_folder, pick, ready_to_build_id, texts

pytestmark = pytest.mark.usefixtures("published_rulebook")

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_to_build_id(settings)


@pytest.fixture
def blocked(settings, request_id):
    folder = good_folder()
    del folder.files["src/callbacks/da_calls.py"]
    view, _ = pick(settings, request_id, folder)
    assert view.step == "ws_blocked"
    return view


def test_5_19_change_the_approach_reopens_the_approach_change_box(settings, request_id, blocked):
    before = approach_flow.get_approach_view(settings, request_id)

    view = flow.change_approach(settings, request_id, blocked.revision)

    after = approach_flow.get_approach_view(settings, request_id)
    assert view.request.status == "APPROACH_PROPOSED"
    assert after.step == "change" and after.text_prompt.startswith("What should change?")
    assert after.change_count == before.change_count + 1  # 5-19: the counter goes up
    assert events_of(settings, request_id, "approach_reopened")[0].details["change_count"] == 1
    assert ("READY_TO_BUILD", "APPROACH_PROPOSED") in moves(settings, request_id)
    assert view.step == "start"  # the workspace starts over for the changed plan
    assert texts(view, "assistant")[-1].startswith("What should change?")


def test_5_19_the_change_is_not_counted_a_second_time_when_the_text_is_sent(
    settings, request_id, blocked
):
    from tests.da_approach_play import Tweaked

    flow.change_approach(settings, request_id, blocked.revision)
    state = approach_flow.get_approach_view(settings, request_id)

    after = approach_flow.submit_text(
        settings, request_id, "Please use a different folder", state.revision,
        generator=Tweaked("change"),
    )

    assert state.change_count == 1 and after.change_count == 1
    assert after.approach.approach_version == 3  # a new approach version was made


def test_change_the_approach_is_not_offered_after_three_changes(settings, request_id, blocked):
    with open_db(settings.db_path) as conn:
        state = read_approach_state(conn, request_id)
        state.change_count = 3
        save_approach_state(conn, state, state.revision, NOW)

    view = flow.get_workspace_view(settings, request_id)

    assert [key for key, _ in view.buttons] == ["help"]
    assert "all 3 changes" in view.note
    with pytest.raises(WorkspaceError, match="all 3 changes"):
        flow.change_approach(settings, request_id, blocked.revision)


def test_5_20_get_help_escalates_with_the_exact_open_item(settings, request_id, blocked):
    view = flow.request_help(settings, request_id, blocked.revision)

    assert view.request.status == "ESCALATION_REQUIRED"
    assert view.open_item == "Escalated in Workspace: ws_blocked"
    approach = approach_flow.get_approach_view(settings, request_id)
    assert approach.step == "escalated"
    assert approach.open_item == "Escalated in Workspace: ws_blocked"
    assert events_of(settings, request_id, "escalated")[-1].details["step"] == "ws_blocked"
    assert ("READY_TO_BUILD", "ESCALATION_REQUIRED") in moves(settings, request_id)


def test_get_help_keeps_the_workspace_step_at_ws_blocked(settings, request_id, blocked):
    flow.request_help(settings, request_id, blocked.revision)

    with open_db(settings.db_path) as conn:
        state = read_workspace_state(conn, request_id)

    assert state.step == "ws_blocked"  # not lost, not replaced by "escalated"
    assert state.last_check.blockers[0].code == "B1"


def test_p14_a_failure_midway_saves_nothing(settings, request_id, blocked, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(flow, "save_approach_state", boom)
    revision = blocked.revision

    for action in (flow.change_approach, flow.request_help):
        with pytest.raises(RuntimeError):
            action(settings, request_id, revision)

    with open_db(settings.db_path) as conn:
        assert read_request(conn, request_id).status == "READY_TO_BUILD"
        assert read_approach_state(conn, request_id).step == "done"
        assert read_workspace_state(conn, request_id).revision == revision
    assert "approach_reopened" not in event_types(settings, request_id)
    assert "escalated" not in event_types(settings, request_id)
    assert texts(flow.get_workspace_view(settings, request_id))[-1].startswith("B1:")


def test_exits_are_only_possible_from_a_blocked_check(settings, request_id):
    folder = good_folder()
    view, _ = pick(settings, request_id, folder)

    with pytest.raises(WorkspaceError):
        flow.change_approach(settings, request_id, view.revision)
    with pytest.raises(WorkspaceError):
        flow.request_help(settings, request_id, view.revision)


def test_5_21_a_cancelled_picker_leaves_a_chat_line_and_nothing_else(settings, request_id):
    view = flow.picker_cancelled(settings, request_id, 0)

    assert view.step == "start" and view.revision == 0
    assert texts(view, "assistant")[-1] == "No folder chosen."
    assert [e for e in event_types(settings, request_id) if e.startswith("workspace")] == []
    with open_db(settings.db_path) as conn:
        assert read_workspace_state(conn, request_id) is None
