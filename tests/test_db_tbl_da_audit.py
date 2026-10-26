import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

import pytest

from db_table_functions import db_tbl_da_audit
from db_table_functions.db_tbl_da_audit import (
    UnknownRequestError,
    add_audit_event,
    list_audit_events,
)
from db_table_functions.db_tbl_da_requests import create_request

T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


@pytest.fixture
def request_id(db_path, published_rulebook):
    return create_request(db_path, "Change A", "dev-0001", now=T0).request_id


def test_event_is_saved_and_read_back(db_path, request_id):
    add_audit_event(db_path, request_id, "developer", "request_created", {"note": "hi"}, now=T0)

    events = list_audit_events(db_path, request_id)

    assert len(events) == 1
    assert events[0].actor == "developer"
    assert events[0].event_type == "request_created"
    assert events[0].details == {"note": "hi"}
    assert events[0].timestamp == T0


def test_events_come_back_in_time_order(db_path, request_id):
    # Added out of order on purpose.
    add_audit_event(db_path, request_id, "system", "second", now=T0 + timedelta(minutes=5))
    add_audit_event(db_path, request_id, "developer", "first", now=T0)

    types = [event.event_type for event in list_audit_events(db_path, request_id)]

    assert types == ["first", "second"]


def test_events_with_same_timestamp_keep_insert_order(db_path, request_id):
    for event_type in ["one", "two", "three"]:
        add_audit_event(db_path, request_id, "system", event_type, now=T0)

    types = [event.event_type for event in list_audit_events(db_path, request_id)]

    assert types == ["one", "two", "three"]


def test_only_this_requests_events_are_listed(db_path, request_id):
    other_id = create_request(db_path, "Change B", "dev-0002", now=T0).request_id
    add_audit_event(db_path, request_id, "developer", "mine", now=T0)
    add_audit_event(db_path, other_id, "developer", "theirs", now=T0)

    types = [event.event_type for event in list_audit_events(db_path, request_id)]

    assert types == ["mine"]


def test_event_for_unknown_request_is_refused(db_path):
    with pytest.raises(UnknownRequestError, match="CVDA-2026-9999 does not exist"):
        add_audit_event(db_path, "CVDA-2026-9999", "system", "orphan", now=T0)


def test_details_that_cannot_be_saved_give_plain_message(db_path, request_id):
    with pytest.raises(ValueError, match="cannot be saved"):
        add_audit_event(db_path, request_id, "system", "bad", {"when": T0}, now=T0)

    assert list_audit_events(db_path, request_id) == []


def test_module_offers_no_edit_or_delete_function():
    public_names = [name for name in dir(db_tbl_da_audit) if not name.startswith("_")]

    for word in ("update", "edit", "delete", "remove"):
        assert not any(word in name.lower() for name in public_names)


def test_database_refuses_to_edit_an_audit_event(db_path, request_id):
    add_audit_event(db_path, request_id, "developer", "request_created", now=T0)

    # Go around our functions on purpose, as careless future code might.
    with closing(sqlite3.connect(db_path)) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="cannot be edited"):
            conn.execute("UPDATE da_audit_events SET event_type = 'changed'")

    assert list_audit_events(db_path, request_id)[0].event_type == "request_created"


def test_database_refuses_to_delete_an_audit_event(db_path, request_id):
    add_audit_event(db_path, request_id, "developer", "request_created", now=T0)

    with closing(sqlite3.connect(db_path)) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            conn.execute("DELETE FROM da_audit_events")

    assert len(list_audit_events(db_path, request_id)) == 1


def test_details_that_refer_to_themselves_give_the_plain_message(db_path, request_id):
    # Parked item P3, fixed in Phase 2A.
    details = {}
    details["self"] = details

    with pytest.raises(ValueError, match="hold a value that cannot be saved"):
        add_audit_event(db_path, request_id, "system", "x", details)
