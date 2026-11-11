"""Phase 9 step 15: the safety net in a requirement-lane Refine (test 9-44). The re-marking is
plain code; made-up cases and a real accepted net on the made-up program. No AI is called."""

from datetime import UTC, datetime

import pytest

from agents import da_safety_net_flow as net_flow
from agents.da_enhance_refine import carry_net_forward, remark_net
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_enhance import (
    ensure_enhance_tables,
    read_accepted_net,
    read_enhance_state,
    read_latest_safety_net,
)
from db_table_functions.db_tbl_da_understand import list_messages, read_confirmed_record
from pydantic_classes.da_enhance_models import NotCovered, SafetyCase, SafetyNet
from pydantic_classes.da_refine_models import CriterionChange, RecordDiff
from pydantic_classes.da_request_record_models import MustNotChange, RequestRecord
from tests import da_play
from tests.test_da_safety_net_flow import Runner, at_s_writing

pytestmark = pytest.mark.usefixtures("published_rulebook")


def case(number, mark=None):
    return SafetyCase(
        id=f"S-{number}", today_behaviour="Shows the date.", function="format_expiry",
        expected_to_change=mark,
    )


def diff(*changes):
    return RecordDiff(
        from_version=1, to_version=2,
        criteria=[CriterionChange(id=i, change=c) for i, c in changes],
    )


def record(**update):
    return RequestRecord(
        request_id="CVDA-2026-0001", rulebook_version=1, version=2, kind="enhance",
        functions_in_scope=["format_expiry"], **update,
    )


# --- the pure part ---


def test_9_44_a_removed_criterion_clears_the_mark_and_a_changed_one_is_flagged():
    net = SafetyNet(cases=[case(1, "AC-1"), case(2, "AC-2"), case(3, "AC-3"), case(4)])

    result = remark_net(net, diff(("AC-1", "removed"), ("AC-2", "changed")), record())

    marks = {c.id: c.expected_to_change for c in result.net.cases}
    assert marks == {"S-1": None, "S-2": "AC-2", "S-3": "AC-3", "S-4": None}
    assert result.remarks == [("S-1", "AC-1", "removed"), ("S-2", "AC-2", "changed")]
    assert result.needs_review


def test_9_44_an_added_criterion_needs_no_look_and_the_tests_are_not_touched():
    net = SafetyNet(cases=[case(1, "AC-1")], test_code="class T: pass\n")

    result = remark_net(net, diff(("AC-2", "added")), record())

    assert not result.needs_review
    assert result.net.test_code == net.test_code
    assert result.net.cases == net.cases


def test_9_44_a_new_must_not_change_item_is_listed_as_not_covered():
    net = SafetyNet(
        cases=[case(1)], not_covered=[NotCovered(item="NC-1", reason="Could not be tested.")]
    )
    new = record(must_not_change=[MustNotChange(id="NC-1", text="Keep the format.")])
    assert not remark_net(net, diff(), new).new_uncovered  # NC-1 was already listed

    newer = record(
        must_not_change=[
            MustNotChange(id="NC-1", text="Keep the format."),
            MustNotChange(id="NC-2", text="Keep the sort order."),
        ]
    )
    result = remark_net(net, diff(), newer)

    assert result.new_uncovered == ["NC-2"]
    assert result.needs_review


# --- carried to the new record version ---


def accepted_net_request(settings, tmp_path):
    request_id = at_s_writing(settings)
    with open_db(settings.db_path) as conn:
        revision = read_enhance_state(conn, request_id).revision
    net_flow.run_safety_net(settings, request_id, revision, Runner(tmp_path))
    with open_db(settings.db_path) as conn:
        revision = read_enhance_state(conn, request_id).revision
    net_flow.accept_safety_net(settings, request_id, revision)
    return request_id


def carry(settings, request_id, **update):
    with open_db(settings.db_path) as conn:
        old = read_confirmed_record(conn, request_id, 1)
    new = old.model_copy(update={"version": 2, **update})
    with open_db(settings.db_path) as conn:
        ensure_enhance_tables(conn)  # the real write helper does this before it takes the lock
        begin_write(conn)
        return old, carry_net_forward(conn, old, new, diff(), datetime.now(UTC))


def test_9_44_nothing_to_look_at_the_carried_net_is_accepted_at_once(make_settings, tmp_path):
    settings = make_settings()
    request_id = accepted_net_request(settings, tmp_path)

    _old, result = carry(settings, request_id)

    assert result is not None and not result.needs_review
    with open_db(settings.db_path) as conn:
        carried = read_accepted_net(conn, request_id, 2)
        assert carried is not None
        assert carried.net.test_code == read_accepted_net(conn, request_id, 1).net.test_code
        assert read_enhance_state(conn, request_id).step == "s_accepted"
    assert "safety_net_carried" in [
        e.event_type for e in list_audit_events(settings.db_path, request_id)
    ]


def test_9_44_a_new_must_not_change_item_waits_for_his_look_then_can_be_accepted(
    make_settings, tmp_path
):
    settings = make_settings()
    request_id = accepted_net_request(settings, tmp_path)
    extra = [MustNotChange(id="NC-9", text="Keep the sort order.")]

    _old, result = carry(settings, request_id, must_not_change=extra)

    assert result.new_uncovered == ["NC-9"]
    with open_db(settings.db_path) as conn:
        assert read_accepted_net(conn, request_id, 2) is None
        waiting = read_latest_safety_net(conn, request_id)
        assert waiting.record_version == 2 and not waiting.accepted
        state = read_enhance_state(conn, request_id)
        assert state.step == "s_review"
    assert "NC-9 is not covered" in list_messages(settings.db_path, request_id)[-1].text

    net_flow.accept_safety_net(settings, request_id, state.revision)

    with open_db(settings.db_path) as conn:
        assert read_accepted_net(conn, request_id, 2) is not None


def test_9_44_a_request_without_a_net_is_left_alone(make_settings):
    settings = make_settings()
    request_id = da_play.to_confirmed(settings).request.request_id

    _old, result = carry(settings, request_id)

    assert result is None
