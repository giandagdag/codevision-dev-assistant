"""The Tester's three tables: save, read back, append-only (Phase 7 spec section 12)."""

import sqlite3
from datetime import UTC, datetime

import pytest

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_tester import (
    count_unable_reviews,
    insert_action,
    insert_review,
    next_review_number,
    read_actions,
    read_reviews,
)
from pydantic_classes.da_tester_models import (
    CHECK_NAMES,
    CheckResult,
    Finding,
    FindingAction,
    ReviewRecord,
)
from tests.da_build_play import ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def review(request_id, number=1, result="done", label="Ready with warnings"):
    return ReviewRecord(
        request_id=request_id,
        build_number=1,
        round=2,
        review_number=number,
        model="fake-model",
        calls=1,
        prompt_chars=1234,
        attempts=1,
        result=result,
        checks=[CheckResult(number=n, name=t, state="passed") for n, t in CHECK_NAMES.items()],
        zone_warnings=["Touches the Login zone."],
        label=label,
        findings=[
            Finding(
                finding_id="F-1",
                check=5,
                severity="should_fix",
                file="src/a.py",
                line=3,
                quote="x = 1",
                cites="AC-1",
                message="Extra.",
            ),
            Finding(
                finding_id="F-2",
                check=4,
                severity="must_fix",
                kept=False,
                reject_reason="The quote is not in the file.",
            ),
        ],
    )


def test_a_review_and_its_findings_are_saved_and_read_back(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        insert_review(conn, review(request_id), NOW)
        saved = read_reviews(conn, request_id, 1)

    assert len(saved) == 1
    got = saved[0]
    assert (got.model, got.calls, got.prompt_chars, got.label) == (
        "fake-model",
        1,
        1234,
        "Ready with warnings",
    )
    assert [c.number for c in got.checks] == [1, 2, 3, 4, 5, 6, 7]
    assert got.zone_warnings == ["Touches the Login zone."]
    assert [(f.finding_id, f.kept) for f in got.findings] == [("F-1", True), ("F-2", False)]
    assert got.findings[1].reject_reason == "The quote is not in the file."


def test_review_numbers_count_up_per_build(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        assert next_review_number(conn, request_id, 1) == 1
        insert_review(conn, review(request_id, 1), NOW)
        assert next_review_number(conn, request_id, 1) == 2
        assert next_review_number(conn, request_id, 2) == 1


def test_unable_reviews_are_counted_for_phase_10(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        insert_review(conn, review(request_id, 1, "unable", "Unable to assess"), NOW)
        insert_review(conn, review(request_id, 2), NOW)

        assert count_unable_reviews(conn, request_id) == 1


def test_actions_are_saved_in_order(settings, request_id):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        for action in ("accepted", "reopened"):
            insert_action(
                conn,
                FindingAction(
                    request_id=request_id,
                    build_number=1,
                    review_number=1,
                    finding_id="F-1",
                    action=action,
                    reason="because I said so",
                ),
                NOW,
            )

        assert [a.action for a in read_actions(conn, request_id, 1)] == ["accepted", "reopened"]


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE da_tester_reviews SET label = 'x'",
        "DELETE FROM da_tester_reviews",
        "UPDATE da_tester_findings SET message = 'x'",
        "DELETE FROM da_tester_findings",
        "UPDATE da_tester_finding_actions SET reason = 'x'",
        "DELETE FROM da_tester_finding_actions",
    ],
)
def test_the_tester_tables_are_append_only(settings, request_id, sql):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        insert_review(conn, review(request_id), NOW)
        insert_action(
            conn,
            FindingAction(
                request_id=request_id,
                build_number=1,
                review_number=1,
                finding_id="F-1",
                action="accepted",
                reason="a long enough reason",
            ),
            NOW,
        )

        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute(sql)


def test_ensure_build_tables_creates_the_tester_tables(settings):
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        names = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert {"da_tester_reviews", "da_tester_findings", "da_tester_finding_actions"} <= names
