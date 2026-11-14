"""Phase 10 step 7: the shared escalate helper and the hooks that use it (spec sections 7 and 8)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agents import da_build_flow as build_flow
from agents import da_build_loop as loop
from agents import da_handoff_flow as handoff_flow
from agents.da_build_loop import _Run
from agents.da_escalation_flow import escalate, request_triggers
from agents.da_escalation_triggers import dispute, get_help
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import ensure_audit_table
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_escalation import read_escalations, read_open_escalation
from db_table_functions.db_tbl_da_requests import create_request, read_request
from pydantic_classes.da_rulebook_models import EscalationTrigger
from tests.da_build_play import chat, event_types, ready_with_workspace, request_status

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
NAMES = ("cap_hit_twice", "out_of_scope", "dispute", "tester_unable_twice", "get_help")
ALL_ON = [EscalationTrigger(name=name, on=True) for name in NAMES]
ALL_OFF = [EscalationTrigger(name=name, on=False) for name in NAMES]


@pytest.fixture
def request_id(db_path, published_rulebook):
    created = create_request(db_path, "Add a limit check", "dev-home-01", NOW).request_id
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        ensure_audit_table(conn)
    return created


def run(db_path, request_id, decision, open_item=""):
    with open_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return escalate(conn, request_id, decision, NOW, open_item)


def test_the_pinned_switches_are_read_on_the_callers_connection(db_path, request_id):
    with open_db(db_path) as conn:
        names = [item.name for item in request_triggers(conn, request_id)]
    assert sorted(names) == sorted(NAMES)


def test_a_fired_trigger_opens_one_row_with_the_status_it_came_from(db_path, request_id):
    decision = get_help(ALL_ON, "Build", "b_unable")

    result = run(db_path, request_id, decision, "Escalated in Build: b_unable")

    assert result.opened
    with open_db(db_path) as conn:
        row = read_open_escalation(conn, request_id)
    assert row.triggers == ["get_help"]
    assert row.open_item == "Escalated in Build: b_unable"
    assert row.from_status == "DRAFT"
    assert row.senior_label == "Unassigned"  # no approach yet, so no capability


def test_a_second_trigger_adds_a_reason_instead_of_a_second_row(db_path, request_id):
    run(db_path, request_id, get_help(ALL_ON, "Build", "b_unable"))

    result = run(db_path, request_id, dispute(ALL_ON, "F-2"))

    assert result.reason_added and not result.opened
    with open_db(db_path) as conn:
        rows = read_escalations(conn, request_id)
    assert len(rows) == 1
    assert rows[0].triggers == ["get_help", "dispute"]
    assert len(rows[0].reasons) == 2


def test_a_switched_off_trigger_writes_no_row_and_audits(db_path, request_id):
    result = run(db_path, request_id, dispute(ALL_OFF, "F-2"))

    assert result.switched_off
    with open_db(db_path) as conn:
        assert read_escalations(conn, request_id) == []
    events = event_types(_settings(db_path), request_id)
    assert "escalation_switched_off" in events


def test_a_quiet_decision_does_nothing(db_path, request_id):
    from agents.da_escalation_triggers import cap_hit_twice

    result = run(db_path, request_id, cap_hit_twice(ALL_ON, 1, 1, 0))
    assert not (result.opened or result.switched_off or result.reason_added)


def test_nothing_fires_at_handed_off(db_path, request_id):
    with open_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE da_requests SET status = 'HANDED_OFF' WHERE request_id = ?",
                     (request_id,))  # fmt: skip
    result = run(db_path, request_id, get_help(ALL_ON, "Handoff", "h_start"))
    assert not result.opened


def _settings(db_path):
    class Fake:
        pass

    fake = Fake()
    fake.db_path = db_path
    return fake


# --- the build-loop hooks (triggers 1 and 4), called with a small stand-in for the run ---


def stand_in(db_path, request_id, triggers):
    """What the two hook methods read from the run: request id and the pinned switches."""
    policy = SimpleNamespace(escalation_triggers=triggers)
    return SimpleNamespace(request_id=request_id, inp=SimpleNamespace(policy=policy))


def hook_tx(conn, request_id):
    request = read_request(conn, request_id)
    state = SimpleNamespace(build_number=2)
    moves = []
    tx = SimpleNamespace(
        conn=conn, now=NOW, state=state, request=request, move_to=moves.append
    )
    return tx, moves


def test_two_not_passing_builds_open_a_row_and_move_to_a_senior(db_path, request_id):
    with open_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        tx, moves = hook_tx(conn, request_id)
        _Run._cap_hit_twice(stand_in(db_path, request_id, ALL_ON), tx, 1)  # count 1: quiet
        assert moves == [] and read_open_escalation(conn, request_id) is None
        _Run._cap_hit_twice(stand_in(db_path, request_id, ALL_ON), tx, 2)
        row = read_open_escalation(conn, request_id)
    assert moves == ["ESCALATION_REQUIRED"]
    assert row.triggers == ["cap_hit_twice"]
    assert row.fired_count == 2
    assert row.reasons == ["Round cap hit twice: builds 1 and 2"]


def test_cap_hit_twice_with_the_switch_off_leaves_the_status(db_path, request_id):
    with open_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        tx, moves = hook_tx(conn, request_id)
        _Run._cap_hit_twice(stand_in(db_path, request_id, ALL_OFF), tx, 2)
        assert read_open_escalation(conn, request_id) is None
    assert moves == []
    assert "escalation_switched_off" in event_types(_settings(db_path), request_id)


def test_a_count_of_three_does_not_fire_again_after_the_row_at_two(db_path, request_id):
    with open_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        tx, moves = hook_tx(conn, request_id)
        run_self = stand_in(db_path, request_id, ALL_ON)
        _Run._cap_hit_twice(run_self, tx, 2)
        _Run._cap_hit_twice(run_self, tx, 3)
        assert len(read_escalations(conn, request_id)) == 1
    assert moves == ["ESCALATION_REQUIRED"]  # the second call found a count below 2 + 2


# --- the hooks ---


@pytest.fixture
def built(make_settings, published_rulebook):
    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]
    build_flow.start_build(settings, request_id, build_flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    return settings, request_id


def test_get_help_in_handoff_opens_a_row_and_moves(built):
    settings, request_id = built

    handoff_flow.request_help(settings, request_id, 0, NOW)

    assert request_status(settings, request_id) == "ESCALATION_REQUIRED"
    with open_db(settings.db_path) as conn:
        row = read_open_escalation(conn, request_id)
    assert row.triggers == ["get_help"]
    assert row.from_status == "READY_FOR_REVIEW"
    assert row.open_item.startswith("Escalated in Handoff: ")
    assert any("has been asked to look" in line for line in chat(settings, request_id))
    assert "escalation_opened" in event_types(settings, request_id)


def test_get_help_with_the_switch_off_does_not_move(built, monkeypatch):
    settings, request_id = built
    monkeypatch.setattr(handoff_flow, "request_triggers", lambda conn, rid: ALL_OFF)

    handoff_flow.request_help(settings, request_id, 0, NOW)

    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    with open_db(settings.db_path) as conn:
        assert read_escalations(conn, request_id) == []
    assert "escalation_switched_off" in event_types(settings, request_id)
    assert any("Ask your senior directly" in line for line in chat(settings, request_id))
