"""Save and read Approach (spec section 10). Three tables, created with CREATE TABLE IF NOT EXISTS.

- da_approach_versions: one row per approach version, append-only (the database refuses edits).
- da_test_plans: one row per test plan version, append-only.
- da_approach_state: the working state, one row per request, with its own revision number so a
  save from an old window is refused (the same idea as Discover's revision).

Like Discover's storage, every write function takes the caller's connection, so the flow can save
versions, state, status, audit events and chat lines in one transaction.
"""

import json
import sqlite3
from datetime import datetime

from db_table_functions.da_db import add_column_if_missing, to_db_time
from db_table_functions.db_tbl_da_discovery import ensure_discovery_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
)
from pydantic_classes.da_approach_models import (
    ApproachReply,
    ApproachState,
    ApproachVersion,
    TestCase,
    TestPlanVersion,
)

# The triggers are SQLite-only: CodeVision's database will need its own equivalent.
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_approach_versions (
    request_id       TEXT NOT NULL REFERENCES da_requests (request_id),
    approach_version INTEGER NOT NULL,
    source           TEXT NOT NULL,
    record_version   INTEGER NOT NULL,
    rulebook_version INTEGER NOT NULL,
    discovery_round  INTEGER NOT NULL,
    plan             TEXT NOT NULL,
    decisions        TEXT NOT NULL,
    warnings         TEXT NOT NULL,
    zones            TEXT NOT NULL,
    model            TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (request_id, approach_version)
);

CREATE TRIGGER IF NOT EXISTS da_approach_versions_no_update
BEFORE UPDATE ON da_approach_versions
BEGIN
    SELECT RAISE(ABORT, 'Approach versions are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_approach_versions_no_delete
BEFORE DELETE ON da_approach_versions
BEGIN
    SELECT RAISE(ABORT, 'Approach versions are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_test_plans (
    request_id       TEXT NOT NULL REFERENCES da_requests (request_id),
    plan_version     INTEGER NOT NULL,
    approach_version INTEGER NOT NULL,
    cases            TEXT NOT NULL,
    source_of_change TEXT NOT NULL,
    model            TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (request_id, plan_version)
);

CREATE TRIGGER IF NOT EXISTS da_test_plans_no_update
BEFORE UPDATE ON da_test_plans
BEGIN
    SELECT RAISE(ABORT, 'Test plan versions are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_test_plans_no_delete
BEFORE DELETE ON da_test_plans
BEGIN
    SELECT RAISE(ABORT, 'Test plan versions are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_approach_state (
    request_id TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    state      TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class ApproachError(UnderstandError):
    """An Approach action was refused. The message says why in plain words."""


def ensure_approach_tables(conn: sqlite3.Connection) -> None:
    # These tables point at da_requests, which the Understand tables set up first.
    ensure_discovery_tables(conn)
    conn.executescript(_CREATE_TABLES_SQL)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(da_approach_versions)")}
    if "index_build" not in columns:  # Upgrade G5e: old rows read as "not recorded" (NULL)
        add_column_if_missing(conn, "da_approach_versions", "index_build", "INTEGER")


# --- approach versions ---


def insert_approach_version(
    conn: sqlite3.Connection, version: ApproachVersion, now: datetime
) -> None:
    """Append one approach version. A second save of the same version is refused."""
    try:
        conn.execute(
            "INSERT INTO da_approach_versions (request_id, approach_version, source,"
            " record_version, rulebook_version, discovery_round, plan, decisions, warnings,"
            " zones, model, created_at, index_build)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version.request_id,
                version.approach_version,
                version.source,
                version.record_version,
                version.rulebook_version,
                version.discovery_round,
                version.plan.model_dump_json(),
                json.dumps([item.model_dump(mode="json") for item in version.decisions]),
                json.dumps(version.warnings),
                json.dumps(version.zones_touched),
                version.model,
                to_db_time(now),
                version.index_build,
            ),
        )
    except sqlite3.IntegrityError as error:
        if "UNIQUE" not in str(error):
            raise
        raise ApproachError(
            f"Approach v{version.approach_version} of request {version.request_id} is "
            "already saved and cannot be saved again."
        ) from error


def read_approach_versions(conn: sqlite3.Connection, request_id: str) -> list[ApproachVersion]:
    rows = conn.execute(
        "SELECT * FROM da_approach_versions WHERE request_id = ? ORDER BY approach_version",
        (request_id,),
    ).fetchall()
    return [_to_version(row) for row in rows]


def read_latest_approach(conn: sqlite3.Connection, request_id: str) -> ApproachVersion | None:
    row = conn.execute(
        "SELECT * FROM da_approach_versions WHERE request_id = ?"
        " ORDER BY approach_version DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return _to_version(row) if row else None


# --- test plans ---


def insert_test_plan(conn: sqlite3.Connection, plan: TestPlanVersion, now: datetime) -> None:
    try:
        conn.execute(
            "INSERT INTO da_test_plans (request_id, plan_version, approach_version, cases,"
            " source_of_change, model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                plan.request_id,
                plan.plan_version,
                plan.approach_version,
                json.dumps([case.model_dump() for case in plan.cases]),
                plan.source_of_change,
                plan.model,
                to_db_time(now),
            ),
        )
    except sqlite3.IntegrityError as error:
        if "UNIQUE" not in str(error):
            raise
        raise ApproachError(
            f"Test plan v{plan.plan_version} of request {plan.request_id} is already saved "
            "and cannot be saved again."
        ) from error


def read_test_plans(conn: sqlite3.Connection, request_id: str) -> list[TestPlanVersion]:
    rows = conn.execute(
        "SELECT * FROM da_test_plans WHERE request_id = ? ORDER BY plan_version", (request_id,)
    ).fetchall()
    return [_to_plan(row) for row in rows]


def read_latest_plan(conn: sqlite3.Connection, request_id: str) -> TestPlanVersion | None:
    row = conn.execute(
        "SELECT * FROM da_test_plans WHERE request_id = ? ORDER BY plan_version DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return _to_plan(row) if row else None


def highest_test_number(conn: sqlite3.Connection, request_id: str) -> int:
    """The highest T-number used in any saved plan version, so a number is never reused."""
    numbers = [
        int(case.test_id.split("-")[1])
        for plan in read_test_plans(conn, request_id)
        for case in plan.cases
    ]
    return max(numbers, default=0)


# --- the working state ---


def read_approach_revision(conn: sqlite3.Connection, request_id: str) -> int:
    """The approach revision. 0 means Approach has not started for this request."""
    row = conn.execute(
        "SELECT revision FROM da_approach_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    return row["revision"] if row else 0


def read_approach_state(conn: sqlite3.Connection, request_id: str) -> ApproachState | None:
    row = conn.execute(
        "SELECT state, revision FROM da_approach_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    if row is None:
        return None
    return ApproachState.model_validate(json.loads(row["state"]) | {"revision": row["revision"]})


def save_approach_state(
    conn: sqlite3.Connection, state: ApproachState, base_revision: int, now: datetime
) -> ApproachState:
    """Save the state as revision base_revision + 1. Refused if the stored revision is no longer
    base_revision (another window acted first). Base 0 means the first save. The check and the
    save are one statement, so no other save can slip in between; the caller's transaction then
    rolls back and nothing from the action is written."""
    text = state.model_dump_json(exclude={"revision"})
    if base_revision == 0:
        try:
            conn.execute(
                "INSERT INTO da_approach_state (request_id, state, revision, updated_at)"
                " VALUES (?, ?, 1, ?)",
                (state.request_id, text, to_db_time(now)),
            )
        except sqlite3.IntegrityError as error:
            raise StaleRevisionError(STALE_MESSAGE) from error
        return state.model_copy(update={"revision": 1})
    cursor = conn.execute(
        "UPDATE da_approach_state SET state = ?, revision = ?, updated_at = ?"
        " WHERE request_id = ? AND revision = ?",
        (text, base_revision + 1, to_db_time(now), state.request_id, base_revision),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return state.model_copy(update={"revision": base_revision + 1})


# --- what the audit trail says (read-only) ---


def first_call_failed(conn: sqlite3.Connection, request_id: str) -> bool:
    """True while the latest approach audit event is approach_failed (G3: the button reads Try
    again). Once an approach exists the status has moved on and this is no longer asked."""
    row = conn.execute(
        "SELECT event_type FROM da_audit_events WHERE request_id = ?"
        " AND event_type IN ('approach_failed', 'approach_proposed')"
        " ORDER BY event_id DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return row is not None and row["event_type"] == "approach_failed"


def first_call_problems(conn: sqlite3.Connection, request_id: str) -> list[str]:
    """The problems saved with the latest approach_failed event (check sentences only)."""
    row = conn.execute(
        "SELECT details FROM da_audit_events WHERE request_id = ?"
        " AND event_type = 'approach_failed' ORDER BY event_id DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return list(json.loads(row["details"]).get("problems", [])) if row else []


def confirmed_discovery_round(conn: sqlite3.Connection, request_id: str) -> int:
    """The round the developer confirmed in Discover, or 0 if none (gate check 2)."""
    row = conn.execute(
        "SELECT details FROM da_audit_events WHERE request_id = ?"
        " AND event_type = 'discovery_confirmed' ORDER BY event_id DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return json.loads(row["details"]).get("round", 0) if row else 0


def confirmed_round_record_version(
    conn: sqlite3.Connection, request_id: str, discovery_round: int
) -> int | None:
    """The request version a saved Discover round was built from (gate check 2, N2), or None
    if that round is not saved."""
    row = conn.execute(
        "SELECT record_version FROM da_discovery_results WHERE request_id = ? AND round = ?",
        (request_id, discovery_round),
    ).fetchone()
    return row["record_version"] if row else None


# --- rows to models ---


def _to_version(row: sqlite3.Row) -> ApproachVersion:
    return ApproachVersion.model_validate(
        {
            "request_id": row["request_id"],
            "approach_version": row["approach_version"],
            "source": row["source"],
            "record_version": row["record_version"],
            "rulebook_version": row["rulebook_version"],
            "discovery_round": row["discovery_round"],
            "plan": ApproachReply.model_validate_json(row["plan"]),
            "decisions": json.loads(row["decisions"]),
            "warnings": json.loads(row["warnings"]),
            "zones_touched": json.loads(row["zones"]),
            "model": row["model"],
            "index_build": row["index_build"],
            "created_at": datetime.fromisoformat(row["created_at"]),
        }
    )


def _to_plan(row: sqlite3.Row) -> TestPlanVersion:
    return TestPlanVersion(
        request_id=row["request_id"],
        plan_version=row["plan_version"],
        approach_version=row["approach_version"],
        cases=[TestCase.model_validate(item) for item in json.loads(row["cases"])],
        source_of_change=row["source_of_change"],
        model=row["model"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
