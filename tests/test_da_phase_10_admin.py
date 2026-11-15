"""Phase 10 step 10a: the Admin numbers are real and the form has the two new fields
(spec sections 12 and 13; tests 10-31 Needs attention, 10-47 part 2, 10-48, 10-49)."""

from datetime import UTC, datetime, timedelta

import pytest

from agents.da_admin_forms import (
    ADVANCED_LIMIT_FIELDS,
    LOCK_CHAT_SWITCH,
    TAB_BUILD,
    rulebook_from_form,
)
from agents.da_admin_metrics import NO_DATA, WINDOW_ALL, health_report
from agents.da_admin_overview import (
    LEVEL_INFO,
    LEVEL_RED,
    escalation_items,
    open_escalations,
)
from db_table_functions.da_db import open_db, to_db_time
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_escalation import insert_escalation, update_escalation
from db_table_functions.db_tbl_da_requests import create_request, update_request
from layouts.da_admin_page import build_view
from pydantic_classes.da_escalation_models import EscalationRow
from tests.test_da_admin_page import all_text, walk

pytestmark = pytest.mark.usefixtures("published_rulebook")
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def new_request(db_path, title="A made-up change"):
    return create_request(db_path, title, "dev-0001", now=NOW).request_id


def add_handoff(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        conn.execute(
            "INSERT INTO da_handoffs (request_id, record_version, approach_version,"
            " last_tested_build, last_tested_kind, summary_text, handed_off_by, created_at)"
            " VALUES (?, 1, 1, 1, 'build', 'Summary.', 'dev-0001', ?)",
            (request_id, to_db_time(NOW)),
        )


def add_escalation(db_path, request_id, trigger, opened, closed=None, senior="senior-0001"):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        row = EscalationRow(
            request_id=request_id, triggers=[trigger], reasons=["Because."], from_status="DRAFT",
            senior_label=senior,
        )  # fmt: skip
        saved = insert_escalation(conn, row, opened)
        if closed:
            done = saved.model_copy(update={"outcome": "returned"})
            update_escalation(conn, done, saved.revision, closed)


# --- 10-48 ---


def test_10_48_handoffs_and_escalations_are_real_numbers(db_path):
    ids = [new_request(db_path, f"Change {n}") for n in range(4)]
    add_handoff(db_path, ids[0])
    add_handoff(db_path, ids[1])
    add_escalation(db_path, ids[0], "get_help", NOW - timedelta(days=3))  # open 3 days
    add_escalation(db_path, ids[1], "dispute", NOW - timedelta(hours=10), NOW - timedelta(hours=4))
    add_escalation(db_path, ids[2], "get_help", NOW - timedelta(hours=8), NOW - timedelta(hours=4))

    report = health_report(db_path, WINDOW_ALL, NOW)

    assert report.handoffs.value == 2
    assert report.handoffs.note == "2 of 4 requests (50%)"
    assert report.escalations.value == 3
    assert dict(report.escalations.items) == {
        "Get help": 2, "Dispute": 1, "Cap hit twice": 0, "Out of scope": 0,
        "Tester unable twice": 0,
    }  # fmt: skip
    assert "open 1, closed 2" in report.escalations.text
    assert "5.0 hours" in report.escalations.text  # (6 h + 4 h) / 2
    for metric in report.all_metrics:
        assert "Get help only" not in metric.note and "Phase 10" not in metric.text


def test_10_48_an_empty_database_says_no_data_yet_for_both(db_path):
    report = health_report(db_path, WINDOW_ALL, NOW)
    assert report.handoffs.text == NO_DATA and report.escalations.text == NO_DATA


def test_requests_but_no_handoff_or_escalation_is_not_dressed_as_a_result(db_path):
    new_request(db_path)
    report = health_report(db_path, WINDOW_ALL, NOW)
    assert report.handoffs.text == NO_DATA
    assert report.escalations.text == "0"


def test_the_window_leaves_out_older_rows(db_path):
    request_id = new_request(db_path)
    add_escalation(db_path, request_id, "get_help", NOW - timedelta(days=90))
    report = health_report(db_path, "30d", NOW)
    assert report.escalations.value == 0


# --- 10-49 ---


def test_10_49_an_old_escalation_without_a_row_is_counted_as_get_help_from_the_audit(db_path):
    request_id = new_request(db_path)
    with open_db(db_path) as conn:
        ensure_audit_table(conn)
        update_request(conn, request_id, now=NOW, status="ESCALATION_REQUIRED")
        insert_audit_event(
            conn, request_id, "system", "status_changed",
            {"from": "DRAFT", "to": "ESCALATION_REQUIRED"}, NOW,
        )  # fmt: skip

    report = health_report(db_path, WINDOW_ALL, NOW)

    assert report.escalations.value == 1
    assert dict(report.escalations.items)["Get help"] == 1
    assert "1 from before Phase 10" in report.escalations.text


def test_a_request_with_a_row_is_not_counted_twice(db_path):
    request_id = new_request(db_path)
    with open_db(db_path) as conn:
        ensure_audit_table(conn)
        update_request(conn, request_id, now=NOW, status="ESCALATION_REQUIRED")
        insert_audit_event(
            conn, request_id, "system", "status_changed",
            {"from": "DRAFT", "to": "ESCALATION_REQUIRED"}, NOW,
        )  # fmt: skip
    add_escalation(db_path, request_id, "get_help", NOW)

    assert health_report(db_path, WINDOW_ALL, NOW).escalations.value == 1


# --- Needs attention (10-31, second half) ---


def row(senior="senior-0001", opened=NOW):
    return EscalationRow(
        request_id="CVDA-2026-0001", from_status="DRAFT", senior_label=senior, opened_at=opened
    )


def test_10_31_an_escalation_without_a_named_senior_is_a_needs_attention_line():
    items = escalation_items([row("Unassigned"), row()], 14, NOW)

    assert [(i.level, i.text) for i in items] == [
        (LEVEL_INFO, "1 escalation has no named senior.")
    ]


def test_several_unnamed_and_stale_escalations_are_counted_in_words():
    old = NOW - timedelta(days=20)
    rows = [row("Unassigned", old), row("Unassigned", old), row(opened=old)]

    items = escalation_items(rows, 14, NOW)

    assert [(i.level, i.text) for i in items] == [
        (LEVEL_INFO, "2 escalations have no named senior."),
        (LEVEL_RED, "3 escalations open longer than 14 days."),
    ]


def test_no_escalations_adds_no_line():
    assert escalation_items([], 14, NOW) == []


def test_only_open_rows_are_read_for_the_overview(make_settings):
    settings = make_settings()
    request_id = new_request(settings.db_path)
    add_escalation(settings.db_path, request_id, "get_help", NOW)
    other = new_request(settings.db_path, "Second")
    add_escalation(settings.db_path, other, "dispute", NOW, NOW)

    rows = open_escalations(settings)

    assert [r.request_id for r in rows] == [request_id]


# --- 10-47 part 2: the form and the screen ---


def test_10_47_the_build_tab_has_the_sixth_switch_and_the_advanced_limit(published_rulebook):
    view = build_view(published_rulebook)

    text = all_text(view)
    assert "Lock the developer's chat during an escalation" in text
    assert "handoff_summary_max_chars" in ADVANCED_LIMIT_FIELDS
    assert "Handoff summary max chars" in text  # plain label, not the field name (AF-2)
    switches = [c for c in walk(view) if type(c).__name__ == "Switch"]
    assert len(switches) == 6


def test_the_sixth_switch_saves_into_the_policy_not_into_the_triggers(seed_rulebook):
    form = {
        "triggers": {
            "cap_hit_twice": True, "out_of_scope": True, "dispute": True,
            "tester_unable_twice": True, "get_help": True, LOCK_CHAT_SWITCH: False,
        },
        "handoff_summary_max_chars": "3000",
    }  # fmt: skip

    saved = rulebook_from_form(seed_rulebook, TAB_BUILD, form)

    assert saved.policy.escalation_lock_chat is False
    assert saved.policy.handoff_summary_max_chars == 3000
    assert [t.name for t in saved.policy.escalation_triggers] == [
        "cap_hit_twice", "out_of_scope", "dispute", "tester_unable_twice", "get_help",
    ]  # fmt: skip


def test_the_summary_limit_has_its_bounds(seed_rulebook):
    from pydantic import ValidationError

    # The Save button turns this into a plain-words problem (save_from_form); here it is raw.
    with pytest.raises(ValidationError, match="500"):
        rulebook_from_form(seed_rulebook, TAB_BUILD, {"handoff_summary_max_chars": "10"})
