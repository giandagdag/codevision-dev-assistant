"""Save and read the Independent Tester's work (Phase 7 spec section 12). Three tables,
CREATE TABLE IF NOT EXISTS, all append-only.

- da_tester_reviews: one row per Layer C review, saved when the review closes (done or unable).
- da_tester_findings: every finding of a review, kept or rejected, with the reason.
- da_tester_finding_actions: what the developer did to a finding. The newest action wins.

Every write function takes the caller's connection, so the loop can save review, findings, state,
audit events and chat lines in ONE transaction (rule T2). Like a review log kept next to the job
log: nothing in it is ever edited, only added to.
"""

import json
import sqlite3
from datetime import datetime

from db_table_functions.da_db import to_db_time
from pydantic_classes.da_tester_models import (
    CheckResult,
    Finding,
    FindingAction,
    ReviewRecord,
)

# The triggers are SQLite-only: CodeVision's database will need its own equivalent.
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_tester_reviews (
    request_id    TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number  INTEGER NOT NULL,
    review_number INTEGER NOT NULL,
    round         INTEGER NOT NULL,
    model         TEXT NOT NULL,
    calls         INTEGER NOT NULL,
    prompt_chars  INTEGER NOT NULL,
    attempts      INTEGER NOT NULL,
    result        TEXT NOT NULL,
    checks        TEXT NOT NULL,
    zone_warnings TEXT NOT NULL,
    label         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (request_id, build_number, review_number)
);

CREATE TRIGGER IF NOT EXISTS da_tester_reviews_no_update
BEFORE UPDATE ON da_tester_reviews
BEGIN
    SELECT RAISE(ABORT, 'Tester reviews are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_tester_reviews_no_delete
BEFORE DELETE ON da_tester_reviews
BEGIN
    SELECT RAISE(ABORT, 'Tester reviews are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_tester_findings (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number  INTEGER NOT NULL,
    review_number INTEGER NOT NULL,
    finding_id    TEXT NOT NULL,
    check_number  INTEGER NOT NULL,
    severity      TEXT NOT NULL,
    file          TEXT NOT NULL,
    line          INTEGER NOT NULL,
    quote         TEXT NOT NULL,
    cites         TEXT NOT NULL,
    message       TEXT NOT NULL,
    made_by       TEXT NOT NULL,
    kept          INTEGER NOT NULL,
    reject_reason TEXT NOT NULL,
    fixable       INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS da_tester_findings_no_update
BEFORE UPDATE ON da_tester_findings
BEGIN
    SELECT RAISE(ABORT, 'Tester findings are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_tester_findings_no_delete
BEFORE DELETE ON da_tester_findings
BEGIN
    SELECT RAISE(ABORT, 'Tester findings are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_tester_finding_actions (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT NOT NULL REFERENCES da_requests (request_id),
    build_number  INTEGER NOT NULL,
    review_number INTEGER NOT NULL,
    finding_id    TEXT NOT NULL,
    action        TEXT NOT NULL,
    reason        TEXT NOT NULL,
    actor         TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS da_tester_finding_actions_no_update
BEFORE UPDATE ON da_tester_finding_actions
BEGIN
    SELECT RAISE(ABORT, 'Finding actions are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_tester_finding_actions_no_delete
BEFORE DELETE ON da_tester_finding_actions
BEGIN
    SELECT RAISE(ABORT, 'Finding actions are append-only and cannot be deleted.');
END;
"""


def ensure_tester_tables(conn: sqlite3.Connection) -> None:
    """Called by ensure_build_tables, after the build tables (and da_requests) exist."""
    conn.executescript(_CREATE_TABLES_SQL)


def count_kept_cites(conn: sqlite3.Connection, since: str | None = None) -> dict[str, int]:
    """How often each rule ID was cited by a kept finding (rejected findings do not count).

    Read only. The Admin console shows it in the "Cited" column (Phase 11b) and in "Rules cited"
    on the Overview (Phase 11c). `since` is database time text; None means all time."""
    window = "" if since is None else " AND created_at >= ?"
    rows = conn.execute(
        "SELECT cites, COUNT(*) AS total FROM da_tester_findings"
        f" WHERE kept = 1 AND cites <> ''{window} GROUP BY cites",
        () if since is None else (since,),
    ).fetchall()
    return {row["cites"]: row["total"] for row in rows}


# --- reviews ---


def next_review_number(conn: sqlite3.Connection, request_id: str, build_number: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(review_number), 0) AS top FROM da_tester_reviews"
        " WHERE request_id = ? AND build_number = ?",
        (request_id, build_number),
    ).fetchone()
    return row["top"] + 1


def insert_review(conn: sqlite3.Connection, item: ReviewRecord, now: datetime) -> ReviewRecord:
    """Save a closed review and all its findings (kept and rejected) together."""
    conn.execute(
        "INSERT INTO da_tester_reviews (request_id, build_number, review_number, round, model,"
        " calls, prompt_chars, attempts, result, checks, zone_warnings, label, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.request_id,
            item.build_number,
            item.review_number,
            item.round,
            item.model,
            item.calls,
            item.prompt_chars,
            item.attempts,
            item.result,
            json.dumps([check.model_dump() for check in item.checks]),
            json.dumps(item.zone_warnings),
            item.label,
            to_db_time(now),
        ),
    )
    for finding in item.findings:
        _insert_finding(conn, item, finding, now)
    return item.model_copy(update={"created_at": now})


def _insert_finding(
    conn: sqlite3.Connection, review: ReviewRecord, finding: Finding, now: datetime
) -> None:
    conn.execute(
        "INSERT INTO da_tester_findings (request_id, build_number, review_number, finding_id,"
        " check_number, severity, file, line, quote, cites, message, made_by, kept, reject_reason,"
        " fixable, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            review.request_id,
            review.build_number,
            review.review_number,
            finding.finding_id,
            finding.check,
            finding.severity,
            finding.file,
            finding.line,
            finding.quote,
            finding.cites,
            finding.message,
            finding.made_by,
            1 if finding.kept else 0,
            finding.reject_reason,
            1 if finding.fixable else 0,
            to_db_time(now),
        ),
    )


def read_reviews(
    conn: sqlite3.Connection, request_id: str, build_number: int
) -> list[ReviewRecord]:
    """Every closed review of a build, oldest first, each with its findings."""
    rows = conn.execute(
        "SELECT * FROM da_tester_reviews WHERE request_id = ? AND build_number = ?"
        " ORDER BY review_number",
        (request_id, build_number),
    ).fetchall()
    return [_to_review(conn, row) for row in rows]


def unable_review_numbers(conn: sqlite3.Connection, request_id: str) -> list[int]:
    """The review numbers that ended Unable to assess, oldest first (escalation trigger 4)."""
    rows = conn.execute(
        "SELECT review_number FROM da_tester_reviews WHERE request_id = ? AND result = 'unable'"
        " ORDER BY build_number, review_number",
        (request_id,),
    ).fetchall()
    return [row["review_number"] for row in rows]


def count_unable_reviews(conn: sqlite3.Connection, request_id: str) -> int:
    """How many reviews ended Unable to assess (kept for Phase 10, escalation trigger 4)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM da_tester_reviews WHERE request_id = ? AND result = 'unable'",
        (request_id,),
    ).fetchone()
    return row["n"]


# --- actions ---


def insert_action(conn: sqlite3.Connection, item: FindingAction, now: datetime) -> None:
    conn.execute(
        "INSERT INTO da_tester_finding_actions (request_id, build_number, review_number,"
        " finding_id, action, reason, actor, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.request_id,
            item.build_number,
            item.review_number,
            item.finding_id,
            item.action,
            item.reason,
            item.actor,
            to_db_time(now),
        ),
    )


def read_actions(
    conn: sqlite3.Connection, request_id: str, build_number: int
) -> list[FindingAction]:
    rows = conn.execute(
        "SELECT * FROM da_tester_finding_actions WHERE request_id = ? AND build_number = ?"
        " ORDER BY seq",
        (request_id, build_number),
    ).fetchall()
    return [
        FindingAction(
            request_id=row["request_id"],
            build_number=row["build_number"],
            review_number=row["review_number"],
            finding_id=row["finding_id"],
            action=row["action"],
            reason=row["reason"],
            actor=row["actor"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


# --- rows to models ---


def _to_review(conn: sqlite3.Connection, row: sqlite3.Row) -> ReviewRecord:
    found = conn.execute(
        "SELECT * FROM da_tester_findings WHERE request_id = ? AND build_number = ?"
        " AND review_number = ? ORDER BY seq",
        (row["request_id"], row["build_number"], row["review_number"]),
    ).fetchall()
    return ReviewRecord(
        request_id=row["request_id"],
        build_number=row["build_number"],
        round=row["round"],
        review_number=row["review_number"],
        model=row["model"],
        calls=row["calls"],
        prompt_chars=row["prompt_chars"],
        attempts=row["attempts"],
        result=row["result"],
        checks=[CheckResult.model_validate(item) for item in json.loads(row["checks"])],
        zone_warnings=json.loads(row["zone_warnings"]),
        label=row["label"],
        findings=[_to_finding(item) for item in found],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _to_finding(row: sqlite3.Row) -> Finding:
    return Finding(
        finding_id=row["finding_id"],
        check=row["check_number"],
        severity=row["severity"],
        file=row["file"],
        line=row["line"],
        quote=row["quote"],
        cites=row["cites"],
        message=row["message"],
        made_by=row["made_by"],
        kept=bool(row["kept"]),
        reject_reason=row["reject_reason"],
        fixable=bool(row["fixable"]),
    )
