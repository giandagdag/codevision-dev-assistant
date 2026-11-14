"""Phase 10 step 4: the Handoff flow and the lock (spec sections 2 to 4), fake provider only."""

from datetime import UTC, datetime

import pytest

from agents import da_build_flow as build_flow
from agents import da_build_loop as loop
from agents import da_handoff_flow as flow
from agents import da_tester_flow as tester_flow
from agents import da_workspace_flow as workspace_flow
from agents.da_handoff_facts import _accepted_approach
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_escalation import (
    insert_escalation,
    read_open_escalation,
    update_escalation,
)
from db_table_functions.db_tbl_da_handoff import (
    HandoffLockedError,
    get_last_tested_fingerprints,
    read_handoff,
)
from db_table_functions.db_tbl_da_requests import get_request
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_escalation_models import EscalationRow
from pydantic_classes.da_handoff_models import LOCKED_MESSAGE
from tests.da_build_play import chat, event_types, ready_with_workspace, request_status

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


@pytest.fixture
def built_open(make_settings, published_rulebook):
    """A request built with the fake provider, at READY_FOR_REVIEW. The fake Tester leaves one
    Should fix open, which Handoff must refuse."""
    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]
    build_flow.start_build(settings, request_id, build_flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    return settings, request_id


@pytest.fixture
def built(built_open):
    """The same request with its open Should fix accepted (with a reason)."""
    settings, request_id = built_open
    reason = "Made-up reason: the team agreed to leave this as it is for now."
    for row in tester_flow.get_tester_view(settings, request_id).rows:
        if row.state == "open" and row.finding.severity == "should_fix":
            revision_now = build_flow.get_revision(settings, request_id)
            tester_flow.accept_finding(
                settings, request_id, revision_now, row.finding.finding_id, reason
            )
    return settings, request_id


def test_an_open_should_fix_blocks_handoff_and_names_the_finding(built_open):
    settings, request_id = built_open

    state = flow.ready_for_handoff(settings, request_id, 0, NOW)

    assert state.step == "h_blocked_findings"
    assert state.blockers[0].text == (
        "F-1 (Should fix) is still open: Fix it or Accept, with reason."
    )
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    assert "handoff_blocked" in event_types(settings, request_id)


def revision(settings, request_id) -> int:
    return flow.get_handoff_view(settings, request_id).state.revision


def prints_of(settings, request_id) -> dict[str, str]:
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        return get_last_tested_fingerprints(conn, request_id)


def to_checking(settings, request_id):
    state = flow.ready_for_handoff(settings, request_id, revision(settings, request_id), NOW)
    assert state.step == "h_checking", state.blockers
    return state


def test_a_clean_request_passes_both_checks_and_is_handed_off(built):
    settings, request_id = built
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    state = to_checking(settings, request_id)

    done = flow.final_check(
        settings, request_id, state.revision, prints_of(settings, request_id), NOW
    )

    assert done.step == "h_done"
    assert request_status(settings, request_id) == "HANDED_OFF"
    types = event_types(settings, request_id)
    assert "handoff_checked" in types and "handed_off" in types
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        row = read_handoff(conn, request_id)
    assert row.summary_text.startswith(request_id)
    assert "tests/" not in row.summary_text
    assert flow.get_handoff_view(settings, request_id).locked


def test_a_changed_file_writes_nothing_but_the_state_audit_and_chat(built):
    settings, request_id = built
    state = to_checking(settings, request_id)
    seen = {path: "changed-" + fp for path, fp in prints_of(settings, request_id).items()}

    blocked = flow.final_check(settings, request_id, state.revision, seen, NOW)

    assert blocked.step == "h_blocked_folder"
    assert {item.result for item in blocked.checks} == {"changed"}
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        assert read_handoff(conn, request_id) is None
    assert any("Changed since the last test" in line for line in chat(settings, request_id))
    # He can fix the folder and check again from the blocked step.
    again = flow.final_check(
        settings, request_id, blocked.revision, prints_of(settings, request_id), NOW
    )
    assert again.step == "h_done"


def test_a_missing_file_blocks_and_extra_files_are_ignored(built):
    settings, request_id = built
    state = to_checking(settings, request_id)
    seen = prints_of(settings, request_id)
    gone = sorted(seen)[0]
    del seen[gone]
    seen["not_planned.py"] = "whatever"

    blocked = flow.final_check(settings, request_id, state.revision, seen, NOW)

    assert [c.path for c in blocked.checks if c.result == "missing"] == [gone]
    assert "not_planned.py" not in [c.path for c in blocked.checks]


def test_a_stale_window_is_refused(built):
    settings, request_id = built
    state = to_checking(settings, request_id)
    with pytest.raises(StaleRevisionError):
        flow.ready_for_handoff(settings, request_id, state.revision - 1, NOW)
    with pytest.raises(StaleRevisionError):
        flow.final_check(settings, request_id, state.revision + 5, {}, NOW)
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"


def test_final_check_needs_ready_for_handoff_first(built):
    settings, request_id = built
    with pytest.raises(flow.HandoffError):
        flow.final_check(settings, request_id, 0, prints_of(settings, request_id), NOW)


def test_blocked_findings_write_only_state_audit_and_chat(built, monkeypatch):
    settings, request_id = built
    from agents.da_handoff_checks import UNABLE_TEXT
    from pydantic_classes.da_handoff_models import Blocker

    monkeypatch.setattr(
        flow, "findings_check", lambda *a, **k: [Blocker(kind="label", text=UNABLE_TEXT)]
    )

    state = flow.ready_for_handoff(settings, request_id, 0, NOW)

    assert state.step == "h_blocked_findings"
    assert state.blockers[0].text == UNABLE_TEXT
    assert "handoff_blocked" in event_types(settings, request_id)
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    assert UNABLE_TEXT in chat(settings, request_id)[-1]


def test_every_developer_action_is_refused_after_handoff(built):
    settings, request_id = built
    state = to_checking(settings, request_id)
    flow.final_check(settings, request_id, state.revision, prints_of(settings, request_id), NOW)
    build_rev = build_flow.get_revision(settings, request_id)

    for action in (
        lambda: build_flow.request_help(settings, request_id, build_rev),
        lambda: build_flow.start_build(settings, request_id, build_rev),
        lambda: build_flow.stop_build(settings, request_id, build_rev),
        lambda: build_flow.change_approach(settings, request_id, build_rev),
        lambda: tester_flow.accept_finding(settings, request_id, build_rev, "F-1", "x" * 40),
        lambda: workspace_flow.change_approach(settings, request_id, 0),
        lambda: flow.request_help(settings, request_id, revision(settings, request_id)),
        lambda: flow.ready_for_handoff(settings, request_id, revision(settings, request_id)),
    ):
        with pytest.raises((HandoffLockedError, flow.HandoffError)) as caught:
            action()
        assert str(caught.value) == LOCKED_MESSAGE

    # Reading stays open.
    assert build_flow.get_state(settings, request_id).build_number >= 1
    assert flow.get_handoff_view(settings, request_id).handoff is not None


def test_a_follow_up_request_links_to_the_handed_off_one(built):
    settings, request_id = built
    with pytest.raises(flow.HandoffError):
        flow.start_follow_up(settings, request_id, "dev-home-01", NOW)
    state = to_checking(settings, request_id)
    flow.final_check(settings, request_id, state.revision, prints_of(settings, request_id), NOW)

    follow = flow.start_follow_up(settings, request_id, "dev-home-01", NOW)

    assert get_request(settings.db_path, follow.request_id).follows_request_id == request_id
    assert follow.status == "DRAFT"
    assert "follow_up_started" in event_types(settings, request_id)


def test_get_help_in_handoff_names_the_step(built):
    settings, request_id = built
    state = flow.request_help(settings, request_id, 0, NOW)

    assert state.step == "h_start"
    assert request_status(settings, request_id) == "ESCALATION_REQUIRED"
    assert "escalated" in event_types(settings, request_id)


def test_an_open_escalation_blocks_handoff(built):
    settings, request_id = built
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        row = EscalationRow(request_id=request_id, from_status="READY_FOR_REVIEW")
        insert_escalation(conn, row, NOW)

    with pytest.raises(flow.HandoffError, match="A senior is looking"):
        flow.ready_for_handoff(settings, request_id, 0, NOW)

    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        open_row = read_open_escalation(conn, request_id)
        closed = open_row.model_copy(update={"outcome": "returned"})
        update_escalation(conn, closed, open_row.revision, NOW)

    assert flow.ready_for_handoff(settings, request_id, 0, NOW).step != "h_blocked_findings"


def test_a_check_my_edits_run_hands_off_the_edited_text(built):
    """10-8: after his edit is the last tested text, the folder with that text passes."""
    settings, request_id = built
    prints = prints_of(settings, request_id)
    state = to_checking(settings, request_id)
    # The folder still holds the (unedited) tested text, so the same prints pass.
    assert flow.final_check(settings, request_id, state.revision, prints, NOW).step == "h_done"
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        assert _accepted_approach(conn, request_id) is not None
