"""Phase 10 step 1: Handoff's tables, the new request column and the new rulebook fields."""

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from da_load_starter_rulebook import SEED_RULEBOOK_FILE
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_handoff import (
    insert_handoff,
    read_handoff,
    read_handoff_state,
    save_handoff_state,
)
from db_table_functions.db_tbl_da_requests import (
    create_request,
    ensure_request_tables,
    get_request,
    insert_request,
)
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_handoff_models import HandoffRow, HandoffState
from pydantic_classes.da_rulebook_models import Rulebook

pytestmark = pytest.mark.usefixtures("published_rulebook")
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


@pytest.fixture
def request_id(db_path):
    return create_request(db_path, "Add a limit check", "dev-home-01", NOW).request_id


def make_row(request_id: str) -> HandoffRow:
    return HandoffRow(
        request_id=request_id,
        record_version=2,
        approach_version=1,
        last_tested_build=3,
        last_tested_kind="build",
        summary_text="CVDA made-up summary",
        handed_off_by="dev-home-01",
    )


def test_handoff_state_has_its_own_revision_and_refuses_a_stale_save(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        assert read_handoff_state(conn, request_id) is None
        saved = save_handoff_state(conn, HandoffState(request_id=request_id), 0, NOW)
        again = save_handoff_state(conn, saved.model_copy(update={"step": "h_checking"}), 1, NOW)

        assert (saved.revision, again.revision) == (1, 2)
        assert read_handoff_state(conn, request_id).step == "h_checking"
        with pytest.raises(StaleRevisionError):
            save_handoff_state(conn, again, 1, NOW)
        with pytest.raises(StaleRevisionError):
            save_handoff_state(conn, again, 0, NOW)


def test_a_request_is_handed_off_once(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        insert_handoff(conn, make_row(request_id), NOW)

        assert read_handoff(conn, request_id).summary_text == "CVDA made-up summary"
        with pytest.raises(sqlite3.IntegrityError):
            insert_handoff(conn, make_row(request_id), NOW)


def test_handoffs_are_append_only(db_path, request_id):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        insert_handoff(conn, make_row(request_id), NOW)

        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE da_handoffs SET summary_text = 'changed'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM da_handoffs")


def test_a_new_request_has_no_follow_link_and_a_follow_up_keeps_it(db_path, request_id):
    assert get_request(db_path, request_id).follows_request_id is None
    with open_db(db_path) as conn:
        ensure_request_tables(conn)
        begin_write(conn)
        follow = insert_request(conn, "More limits", "dev-home-01", NOW, request_id)

    assert follow.follows_request_id == request_id
    assert get_request(db_path, follow.request_id).follows_request_id == request_id


def test_an_older_requests_table_gets_the_follow_column(tmp_path):
    old = tmp_path / "old.db"
    with open_db(old) as conn:
        conn.execute(
            "CREATE TABLE da_requests (request_id TEXT PRIMARY KEY, title TEXT NOT NULL,"
            " developer_id TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL, rulebook_version INTEGER)"
        )
        ensure_request_tables(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(da_requests)")}

    assert "follows_request_id" in columns


def test_a_rulebook_saved_before_phase_10_loads_with_the_defaults():
    data = json.loads(SEED_RULEBOOK_FILE.read_text(encoding="utf-8"))
    del data["policy"]["escalation_lock_chat"]
    del data["policy"]["handoff_summary_max_chars"]

    policy = Rulebook.model_validate(data).policy

    assert policy.escalation_lock_chat is True
    assert policy.handoff_summary_max_chars == 6000
