import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
    add_message,
    ensure_understand_tables,
    get_confirmed_record,
    get_session,
    insert_confirmed_record,
    insert_session,
    list_messages,
    save_session,
)
from pydantic_classes.da_request_record_models import RequestRecord, UnderstandSession

T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 25, 9, 5, tzinfo=UTC)


@pytest.fixture
def request_id(db_path, published_rulebook):
    return create_request(db_path, "New change request", "dev-0001", now=T0).request_id


@pytest.fixture
def session(db_path, request_id):
    session = UnderstandSession(
        request_id=request_id,
        record=RequestRecord(request_id=request_id, rulebook_version=1),
    )
    with open_db(db_path) as conn:
        ensure_understand_tables(conn)
        insert_session(conn, session, T0)
    return session


def raw_sql(db_path, statement):
    """Run SQL directly, skipping all our functions, as a person with a database tool could."""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(statement)
        conn.commit()


# --- sessions ---


def test_new_session_starts_at_revision_1(db_path, session):
    loaded = get_session(db_path, session.request_id)

    assert loaded == session
    assert loaded.revision == 1


def test_save_moves_to_the_next_revision(db_path, session):
    changed = session.model_copy(update={"step": "optional"})
    with open_db(db_path) as conn:
        saved = save_session(conn, changed, base_revision=1, now=T1)

    assert saved.revision == 2
    assert get_session(db_path, session.request_id).step == "optional"


def test_stale_revision_is_refused_and_nothing_is_written(db_path, session):
    with open_db(db_path) as conn:
        save_session(conn, session.model_copy(update={"step": "optional"}), 1, T1)

    with pytest.raises(StaleRevisionError, match=STALE_MESSAGE):
        with open_db(db_path) as conn:
            add_message(conn, session.request_id, "developer", "From an old window", T1)
            save_session(conn, session.model_copy(update={"step": "correction"}), 1, T1)

    assert get_session(db_path, session.request_id).step == "optional"
    assert list_messages(db_path, session.request_id) == []


def test_unknown_session_is_none(db_path, request_id):
    assert get_session(db_path, request_id) is None


# --- chat messages ---


def test_messages_list_in_the_order_they_were_added(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_understand_tables(conn)
        add_message(conn, request_id, "developer", "First", T0)
        add_message(conn, request_id, "assistant", "Second, same time", T0)
        add_message(conn, request_id, "system", "Third", T1)

    texts = [message.text for message in list_messages(db_path, request_id)]

    assert texts == ["First", "Second, same time", "Third"]


@pytest.mark.parametrize(
    "statement",
    ["UPDATE da_chat_messages SET text = 'changed'", "DELETE FROM da_chat_messages"],
)
def test_chat_messages_cannot_be_edited_or_deleted_with_raw_sql(db_path, request_id, statement):
    with open_db(db_path) as conn:
        ensure_understand_tables(conn)
        add_message(conn, request_id, "developer", "Original", T0)

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        raw_sql(db_path, statement)

    assert [m.text for m in list_messages(db_path, request_id)] == ["Original"]


# --- confirmed records ---


def confirm(db_path, request_id):
    record = RequestRecord(request_id=request_id, rulebook_version=1, title="Add Excel")
    with open_db(db_path) as conn:
        ensure_understand_tables(conn)
        insert_confirmed_record(conn, record, "dev-0001", T1)
    return record


def test_confirmed_record_is_saved_and_read_back(db_path, request_id):
    record = confirm(db_path, request_id)

    assert get_confirmed_record(db_path, request_id) == record
    assert get_confirmed_record(db_path, request_id, version=2) is None


def test_same_version_cannot_be_confirmed_twice(db_path, request_id):
    confirm(db_path, request_id)

    with pytest.raises(UnderstandError, match="already confirmed"):
        confirm(db_path, request_id)


@pytest.mark.parametrize(
    "statement",
    ["UPDATE da_request_records SET record = '{}'", "DELETE FROM da_request_records"],
)
def test_record_v1_cannot_be_edited_or_deleted_with_raw_sql(db_path, request_id, statement):
    record = confirm(db_path, request_id)

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        raw_sql(db_path, statement)

    assert get_confirmed_record(db_path, request_id) == record
