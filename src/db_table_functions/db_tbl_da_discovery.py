"""Save and read Discover's search rounds (spec 3.6, decision D-D).

Two tables:
- da_discovery_results: one row per round, append-only (the database itself refuses edits and
  deletes), like a journaled file keyed to the request. Request record v1 is never touched.
- da_discovery_state: just the discovery revision number per request. A save from an old window
  is refused, the same way Understand's save is (planning decision 2).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from db_table_functions.da_db import open_db, to_db_time
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
    ensure_understand_tables,
)
from pydantic_classes.da_discovery_models import DiscoveryResult, Finding, SearchHit
from pydantic_classes.da_enhance_models import ImpactResult

# The triggers are SQLite-only: CodeVision's database will need its own equivalent.
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_discovery_results (
    request_id       TEXT NOT NULL REFERENCES da_requests (request_id),
    round            INTEGER NOT NULL,
    record_version   INTEGER NOT NULL,
    rulebook_version INTEGER NOT NULL,
    search_provider  TEXT NOT NULL,
    queries          TEXT NOT NULL,
    hits             TEXT NOT NULL,
    findings         TEXT NOT NULL,
    limitations      TEXT NOT NULL,
    summary_source   TEXT NOT NULL,
    model            TEXT NOT NULL,
    hint             TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (request_id, round)
);

CREATE TRIGGER IF NOT EXISTS da_discovery_results_no_update
BEFORE UPDATE ON da_discovery_results
BEGIN
    SELECT RAISE(ABORT, 'Discovery results are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_discovery_results_no_delete
BEFORE DELETE ON da_discovery_results
BEGIN
    SELECT RAISE(ABORT, 'Discovery results are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_discovery_state (
    request_id TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    revision   INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class DiscoveryError(UnderstandError):
    """A Discover action was refused. The message says why in plain words."""


def ensure_discovery_tables(conn: sqlite3.Connection) -> None:
    # These tables point at da_requests, which the Understand tables set up first.
    ensure_understand_tables(conn)
    conn.executescript(_CREATE_TABLES_SQL)
    _add_impact_column(conn)


def _add_impact_column(conn: sqlite3.Connection) -> None:
    """Phase 9: da_discovery_results gets a nullable `impact` column (JSON). An older database
    gets it here. The append-only trigger only blocks UPDATE, so ALTER is fine. Old rows read as
    no impact."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(da_discovery_results)")}
    if "impact" not in columns:
        conn.execute("ALTER TABLE da_discovery_results ADD COLUMN impact TEXT")


def insert_result(conn: sqlite3.Connection, result: DiscoveryResult, now: datetime) -> None:
    """Append one round. A second save of the same round is refused."""
    try:
        conn.execute(
            "INSERT INTO da_discovery_results (request_id, round, record_version,"
            " rulebook_version, search_provider, queries, hits, findings, limitations,"
            " summary_source, model, hint, created_at, impact)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result.request_id,
                result.round,
                result.record_version,
                result.rulebook_version,
                result.search_provider,
                json.dumps(result.queries),
                json.dumps([hit.model_dump() for hit in result.hits]),
                json.dumps([finding.model_dump() for finding in result.findings]),
                json.dumps(result.limitations),
                result.summary_source,
                result.model,
                result.hint,
                to_db_time(now),
                result.impact.model_dump_json() if result.impact else None,
            ),
        )
    except sqlite3.IntegrityError as error:
        if "UNIQUE" not in str(error):
            raise  # for example an unknown request: not a duplicate round
        raise DiscoveryError(
            f"Round {result.round} of request {result.request_id} is already saved and "
            "cannot be saved again."
        ) from error


def read_results(conn: sqlite3.Connection, request_id: str) -> list[DiscoveryResult]:
    rows = conn.execute(
        "SELECT * FROM da_discovery_results WHERE request_id = ? ORDER BY round", (request_id,)
    ).fetchall()
    return [_to_result(row) for row in rows]


def read_latest_result(conn: sqlite3.Connection, request_id: str) -> DiscoveryResult | None:
    row = conn.execute(
        "SELECT * FROM da_discovery_results WHERE request_id = ? ORDER BY round DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return _to_result(row) if row else None


def count_rounds(conn: sqlite3.Connection, request_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM da_discovery_results WHERE request_id = ?", (request_id,)
    ).fetchone()
    return row["n"]


def get_results(db_path: Path, request_id: str) -> list[DiscoveryResult]:
    """Every saved round of a request, oldest first."""
    with open_db(db_path) as conn:
        ensure_discovery_tables(conn)
        return read_results(conn, request_id)


def read_escalation_open_item(conn: sqlite3.Connection, request_id: str) -> str:
    """The open item the latest discovery_escalated audit event carries, or empty (spec 3.5)."""
    row = conn.execute(
        "SELECT details FROM da_audit_events WHERE request_id = ? AND event_type ="
        " 'discovery_escalated' ORDER BY event_id DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return json.loads(row["details"]).get("open_item", "") if row else ""


def read_discovery_revision(conn: sqlite3.Connection, request_id: str) -> int:
    """The discovery revision. 0 means Discover has not started for this request."""
    row = conn.execute(
        "SELECT revision FROM da_discovery_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    return row["revision"] if row else 0


def bump_discovery_revision(
    conn: sqlite3.Connection, request_id: str, base_revision: int, now: datetime
) -> int:
    """Save revision base_revision + 1 and return it. Refused if the stored revision is no
    longer base_revision (another window acted first). The check and the save are one
    statement, so no other save can slip in between; the caller's transaction then rolls back."""
    if base_revision == 0:
        try:
            conn.execute(
                "INSERT INTO da_discovery_state (request_id, revision, updated_at)"
                " VALUES (?, 1, ?)",
                (request_id, to_db_time(now)),
            )
        except sqlite3.IntegrityError as error:
            raise StaleRevisionError(STALE_MESSAGE) from error
        return 1
    cursor = conn.execute(
        "UPDATE da_discovery_state SET revision = ?, updated_at = ?"
        " WHERE request_id = ? AND revision = ?",
        (base_revision + 1, to_db_time(now), request_id, base_revision),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return base_revision + 1


def _to_result(row: sqlite3.Row) -> DiscoveryResult:
    return DiscoveryResult(
        request_id=row["request_id"],
        round=row["round"],
        record_version=row["record_version"],
        rulebook_version=row["rulebook_version"],
        search_provider=row["search_provider"],
        queries=json.loads(row["queries"]),
        hits=[SearchHit.model_validate(item) for item in json.loads(row["hits"])],
        findings=[Finding.model_validate(item) for item in json.loads(row["findings"])],
        limitations=json.loads(row["limitations"]),
        summary_source=row["summary_source"],
        model=row["model"],
        hint=row["hint"],
        impact=ImpactResult.model_validate_json(row["impact"]) if row["impact"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )
