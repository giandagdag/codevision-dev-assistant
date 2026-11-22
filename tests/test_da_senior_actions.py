"""Phase 10 step 8: the senior's four actions, the return rules, the chat lock, old rows
(spec sections 9 to 11; tests 10-32, 10-36 to 10-46)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agents import da_senior_actions as senior
from agents import da_tester_review as tester
from agents.da_escalation_flow import escalate
from agents.da_escalation_return import pick_return_status
from agents.da_senior_actions import (
    SeniorActionError,
    chat_lock_for,
    close_escalation,
    keep_finding,
    overrule_finding,
    route_pre_phase_10,
    send_guidance,
    take_over,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_state, save_approach_state
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_build import (
    close_build_run,
    ensure_build_tables,
    insert_build_run,
    read_build_state,
    save_build_state,
)
from db_table_functions.db_tbl_da_escalation import read_escalations, read_open_escalation
from db_table_functions.db_tbl_da_handoff import HandoffLockedError, refuse_if_locked
from db_table_functions.db_tbl_da_refine import add_build_result, read_tested
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_tester import insert_review, read_actions, read_reviews
from db_table_functions.db_tbl_da_understand import StaleRevisionError, read_messages
from pydantic_classes.da_build_models import BuildRun, BuildState
from pydantic_classes.da_escalation_models import TriggerDecision
from pydantic_classes.da_tester_models import CHECK_NAMES, CheckResult, Finding, ReviewRecord
from tests.da_build_play import event_types, ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
REASON = "The rule does not apply to this batch job."


@pytest.fixture
def settings(make_settings):
    return make_settings()


def finding(finding_id, severity):
    return Finding(
        finding_id=finding_id, check=4, severity=severity, file="src/a.py", line=3,
        quote="x = 1", cites="AC-1", message="Problem.",
    )  # fmt: skip


def seed(settings, from_status="NOT_PASSING", severities=("must_fix",), trigger="dispute"):
    """A request escalated from `from_status`, with a finished build and one review, the way
    the real flows leave it: status ESCALATION_REQUIRED, approach and build step `escalated`."""
    request_id, _ = ready_with_workspace(settings)
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_audit_table(conn)
        conn.execute("BEGIN IMMEDIATE")
        run = BuildRun(request_id=request_id, build_number=1, approach_version=1, started_at=NOW)
        insert_build_run(conn, run)
        close_build_run(
            conn, request_id, 1, ended_at=NOW, rounds_used=2, result_status=from_status,
            label="Not passing", stop_reason="",
        )  # fmt: skip
        state = BuildState(request_id=request_id, build_number=1, step="escalated")
        save_build_state(conn, state, 0, NOW)
        review = ReviewRecord(
            request_id=request_id, build_number=1, round=2, review_number=1, result="done",
            checks=[CheckResult(number=n, name=t, state="passed") for n, t in CHECK_NAMES.items()],
            findings=[finding(f"F-{i + 1}", sev) for i, sev in enumerate(severities)],
        )  # fmt: skip
        insert_review(conn, review, NOW)
        add_build_result(conn, request_id, True, NOW)
        add_build_result(conn, request_id, True, NOW)
        conn.execute("UPDATE da_requests SET status = ? WHERE request_id = ?",
                     (from_status, request_id))  # fmt: skip
        insert_audit_event(conn, request_id, "developer", "escalated", {"step": "b_done"}, NOW)
        decision = TriggerDecision(trigger=trigger, fire=True, reason="Disputed Must fix: F-1")
        escalate(conn, request_id, decision, NOW, "Disputed Must fix: F-1")
        approach = read_approach_state(conn, request_id)
        approach.step, approach.open_item = "escalated", "Disputed Must fix: F-1"
        save_approach_state(conn, approach, approach.revision, NOW)
        conn.execute("UPDATE da_requests SET status = 'ESCALATION_REQUIRED' WHERE request_id = ?",
                     (request_id,))  # fmt: skip
    return request_id


def row_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_open_escalation(conn, request_id)


def status_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_request(conn, request_id).status


def chat_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return [m.text for m in read_messages(conn, request_id)]


# --- 10-36 Overrule ---


def test_10_36_overruling_the_only_must_fix_changes_the_label_not_the_status(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)

    overrule_finding(settings, row.escalation_id, row.revision, "ann", "F-1", REASON, NOW)

    with open_db(settings.db_path) as conn:
        action = read_actions(conn, request_id, 1)[-1]
    assert (action.action, action.actor, action.reason) == ("overruled", "senior:ann", REASON)
    events = event_types(settings, request_id)
    assert "finding_overruled" in events and "label_changed" in events
    assert status_of(settings, request_id) == "ESCALATION_REQUIRED"
    assert row_of(settings, request_id).revision == row.revision + 1
    assert "The label is now Ready with warnings." in chat_of(settings, request_id)[-1]


def test_overrule_needs_twenty_characters_and_an_open_finding(settings):
    request_id = seed(settings, severities=("must_fix", "fyi"))
    row = row_of(settings, request_id)

    with pytest.raises(SeniorActionError, match="20"):
        overrule_finding(settings, row.escalation_id, row.revision, "ann", "F-1", "too short", NOW)
    with pytest.raises(SeniorActionError, match="F-2"):  # an FYI is not overrulable
        overrule_finding(settings, row.escalation_id, row.revision, "ann", "F-2", REASON, NOW)
    overrule_finding(settings, row.escalation_id, row.revision, "ann", "F-1", REASON, NOW)
    fresh = row_of(settings, request_id)
    with pytest.raises(SeniorActionError, match="already overruled"):
        overrule_finding(settings, fresh.escalation_id, fresh.revision, "ann", "F-1", REASON, NOW)


def test_g5_19_keep_finding_leaves_the_label_and_accepting_both_changes_it(settings):
    request_id = seed(settings, severities=("must_fix", "must_fix"))
    row = row_of(settings, request_id)

    with pytest.raises(SeniorActionError, match="20"):
        keep_finding(settings, row.escalation_id, row.revision, "ann", "F-1", "short", NOW)
    keep_finding(settings, row.escalation_id, row.revision, "ann", "F-1", REASON, NOW)
    with open_db(settings.db_path) as conn:
        actions = read_actions(conn, request_id, 1)
        review = read_reviews(conn, request_id, 1)[-1]
    assert (actions[-1].action, actions[-1].actor) == ("dispute_kept", "senior:ann")
    assert tester.finding_state("F-1", 1, actions)[0] == "kept"
    assert "finding_kept" in event_types(settings, request_id)

    fresh = row_of(settings, request_id)
    overrule_finding(settings, fresh.escalation_id, fresh.revision, "ann", "F-2", REASON, NOW)
    with open_db(settings.db_path) as conn:
        actions = read_actions(conn, request_id, 1)
    assert tester.compute_label(review.findings, [], "done", 1, actions) == "Not passing"
    fresh = row_of(settings, request_id)
    overrule_finding(settings, fresh.escalation_id, fresh.revision, "ann", "F-1", REASON, NOW)
    with open_db(settings.db_path) as conn:
        actions = read_actions(conn, request_id, 1)
    assert tester.compute_label(review.findings, [], "done", 1, actions) == "Ready with warnings"


# --- 10-46 stale ---


def test_10_46_an_old_revision_is_refused_for_every_action(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    take_over(settings, row.escalation_id, row.revision, "ann", NOW)  # revision moves on

    with pytest.raises(StaleRevisionError):
        send_guidance(settings, row.escalation_id, row.revision, "bob", "Try again.", NOW)
    with pytest.raises(StaleRevisionError):
        overrule_finding(settings, row.escalation_id, row.revision, "bob", "F-1", REASON, NOW)
    with pytest.raises(StaleRevisionError):
        close_escalation(settings, row.escalation_id, row.revision, "bob", "returned", "ok", NOW)


# --- 10-37 guidance (the row and the chat; the prompt block is step 9) ---


def test_10_37_guidance_is_saved_shown_as_a_senior_line_and_unlocks_the_chat(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    with open_db(settings.db_path) as conn:
        assert chat_lock_for(conn, request_id).locked

    send_guidance(settings, row.escalation_id, row.revision, "ann", "Use the batch limit.", NOW)

    saved = row_of(settings, request_id)
    assert [g.text for g in saved.guidance] == ["Use the batch limit."]
    assert saved.guidance[0].used_in == ""
    assert "Senior ann: Use the batch limit." in chat_of(settings, request_id)
    assert "guidance_sent" in event_types(settings, request_id)
    with open_db(settings.db_path) as conn:
        assert not chat_lock_for(conn, request_id).locked
    assert saved.outcome == "open"


def test_guidance_has_one_to_two_thousand_characters(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    for bad in ("", "  ", "x" * 2001):
        with pytest.raises(SeniorActionError):
            send_guidance(settings, row.escalation_id, row.revision, "ann", bad, NOW)


# --- 10-38 take over ---


def test_10_38_a_second_senior_cannot_take_over(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    take_over(settings, row.escalation_id, row.revision, "ann", NOW)
    again = row_of(settings, request_id)

    with pytest.raises(SeniorActionError, match="Taken over by ann"):
        take_over(settings, again.escalation_id, again.revision, "bob", NOW)
    assert again.taken_over_by == "ann"
    assert "Senior ann: ann has taken over this request." in chat_of(settings, request_id)


# --- 10-39, 10-40 Return ---


def test_10_39_return_to_not_passing_resets_the_count_and_clears_the_open_item(settings):
    request_id = seed(settings, from_status="NOT_PASSING")
    row = row_of(settings, request_id)

    close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", "Fix F-1.", NOW)

    assert status_of(settings, request_id) == "NOT_PASSING"
    with open_db(settings.db_path) as conn:
        assert read_tested(conn, request_id)["not_passing_in_a_row"] == 0
        assert read_approach_state(conn, request_id).open_item == ""
        assert read_approach_state(conn, request_id).step == "done"
        assert read_build_state(conn, request_id).step == "b_done"
        closed = read_escalations(conn, request_id)[-1]
    assert (closed.outcome, closed.closed_by, closed.close_note) == ("returned", "ann", "Fix F-1.")
    assert "escalation_closed" in event_types(settings, request_id)
    assert any("Returned this request to you" in line for line in chat_of(settings, request_id))


def test_a_returned_overruled_must_fix_lands_at_ready_for_review(settings):
    request_id = seed(settings, from_status="NOT_PASSING")
    row = row_of(settings, request_id)
    overrule_finding(settings, row.escalation_id, row.revision, "ann", "F-1", REASON, NOW)
    row = row_of(settings, request_id)

    close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", "Done.", NOW)

    assert status_of(settings, request_id) == "READY_FOR_REVIEW"


def test_another_must_fix_left_keeps_it_at_not_passing(settings):
    request_id = seed(settings, from_status="NOT_PASSING", severities=("must_fix", "must_fix"))
    row = row_of(settings, request_id)
    overrule_finding(settings, row.escalation_id, row.revision, "ann", "F-1", REASON, NOW)
    row = row_of(settings, request_id)

    close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", "Done.", NOW)

    assert status_of(settings, request_id) == "NOT_PASSING"


def test_10_40_return_to_the_approach_restores_its_step(settings):
    request_id = seed(settings, from_status="APPROACH_PROPOSED", severities=(), trigger="get_help")
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        insert_audit_event(conn, request_id, "developer", "escalated", {"step": "tests"}, NOW)
    row = row_of(settings, request_id)

    close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", "Go on.", NOW)

    assert status_of(settings, request_id) == "APPROACH_PROPOSED"
    with open_db(settings.db_path) as conn:
        assert read_approach_state(conn, request_id).step == "tests"


# --- 10-41 Abandon ---


def test_10_41_abandon_keeps_the_status_and_locks_every_developer_action(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)

    close_escalation(settings, row.escalation_id, row.revision, "ann", "abandoned", "No.", NOW)

    assert status_of(settings, request_id) == "ESCALATION_REQUIRED"
    with open_db(settings.db_path) as conn:
        assert read_escalations(conn, request_id)[-1].outcome == "abandoned"
        with pytest.raises(HandoffLockedError, match="senior closed"):
            refuse_if_locked(conn, request_id)


def test_a_returned_escalation_does_not_lock(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", "Go.", NOW)
    with open_db(settings.db_path) as conn:
        refuse_if_locked(conn, request_id)  # no error


def test_a_closed_row_cannot_be_acted_on_again(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", "Go.", NOW)
    with pytest.raises(SeniorActionError, match="already closed"):
        take_over(settings, row.escalation_id, row.revision + 1, "ann", NOW)


def test_close_needs_a_note_and_a_known_outcome(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    with pytest.raises(SeniorActionError, match="note"):
        close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", " ", NOW)
    with pytest.raises(SeniorActionError, match="Return"):
        close_escalation(settings, row.escalation_id, row.revision, "ann", "later", "note", NOW)


# --- 10-42 the made-up-status guard ---


def test_10_42_a_made_up_status_is_returned_by_the_guard_and_audited(settings):
    request_id = seed(settings, from_status="NOT_PASSING")
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE da_escalations SET body = replace(body, '\"NOT_PASSING\"', '\"MADE_UP\"')"
        )
    row = row_of(settings, request_id)
    assert row.from_status == "MADE_UP"

    close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", "Go.", NOW)

    assert status_of(settings, request_id) == "NOT_PASSING"  # the finished build's status
    assert any("cannot be resumed" in line for line in chat_of(settings, request_id))


def test_the_guard_order_is_build_then_approach_then_checkpoint():
    assert pick_return_status("MADE_UP", "READY_FOR_REVIEW", True)[0] == "READY_FOR_REVIEW"
    assert pick_return_status("MADE_UP", "", True)[0] == "APPROACH_PROPOSED"
    assert pick_return_status("MADE_UP", "", False)[0] == "READY_FOR_CONFIRMATION"
    for running in ("BUILDING", "TESTER_REVIEW", "REVISION_IN_PROGRESS", "HANDED_OFF"):
        assert pick_return_status(running, "", False)[1]  # a note: it was not resumed
    assert pick_return_status("NOT_PASSING", "", False) == ("NOT_PASSING", "")


# --- 10-43, 10-44 the chat lock ---


def test_10_43_the_waiting_line_names_the_senior_and_lifts_after_close(settings):
    request_id = seed(settings)
    with open_db(settings.db_path) as conn:
        lock = chat_lock_for(conn, request_id)
    assert lock.locked
    assert lock.waiting_line.startswith("Waiting for your senior. Your chat is locked until ")
    row = row_of(settings, request_id)
    close_escalation(settings, row.escalation_id, row.revision, "ann", "returned", "Go.", NOW)
    with open_db(settings.db_path) as conn:
        assert not chat_lock_for(conn, request_id).locked


def test_10_44_with_the_policy_switch_off_the_chat_is_not_locked(settings, monkeypatch):
    request_id = seed(settings)
    policy = SimpleNamespace(escalation_lock_chat=False)
    off = SimpleNamespace(rulebook=SimpleNamespace(policy=policy))
    monkeypatch.setattr(senior, "version_on", lambda conn, number: off)
    with open_db(settings.db_path) as conn:
        assert not chat_lock_for(conn, request_id).locked


# --- 10-32 rows for requests escalated before this phase ---


def test_10_32_an_old_escalation_gets_a_routed_row_once(settings):
    request_id, _ = ready_with_workspace(settings)
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_audit_table(conn)
        conn.execute("BEGIN IMMEDIATE")
        insert_audit_event(
            conn, request_id, "system", "status_changed",
            {"from": "READY_TO_BUILD", "to": "ESCALATION_REQUIRED"}, NOW,
        )  # fmt: skip
        conn.execute("UPDATE da_requests SET status = 'ESCALATION_REQUIRED' WHERE request_id = ?",
                     (request_id,))  # fmt: skip

    assert route_pre_phase_10(settings, NOW) == 1
    assert route_pre_phase_10(settings, NOW) == 0

    row = row_of(settings, request_id)
    assert row.from_status == "READY_TO_BUILD"
    assert row.triggers == ["get_help"]
    assert "escalation_routed" in event_types(settings, request_id)
