"""Save and read Enhance (Phase 9 spec section 14). CREATE TABLE IF NOT EXISTS.

- da_enhance_state: one row per request, with its own revision for the stale check (F1).
- da_enhance_candidates: append-only, one row per Find round.
- da_freshness_checks: append-only, one row per check (an override is a new row).
- da_safety_nets: append-only. Accepting appends a copy with accepted = 1.
- da_unassigned_files: one OPEN row per path; updated only to resolve it.

Every write function takes the caller's connection, so a flow can save state, rows, audit events
and chat lines in ONE transaction. AS400 picture: a journaled file, where history is only added to.
"""

import json
import sqlite3
from datetime import datetime

from db_table_functions.da_db import to_db_time
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
)
from pydantic_classes.da_enhance_models import (
    Candidate,
    EnhanceState,
    FreshnessCheckRow,
    FreshnessResult,
    SafetyNet,
    SafetyNetRow,
    UnassignedFile,
)

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_enhance_state (
    request_id TEXT PRIMARY KEY REFERENCES da_requests (request_id),
    state      TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS da_enhance_candidates (
    request_id TEXT NOT NULL REFERENCES da_requests (request_id),
    find_round INTEGER NOT NULL,
    candidates TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, find_round)
);

CREATE TRIGGER IF NOT EXISTS da_enhance_candidates_no_update
BEFORE UPDATE ON da_enhance_candidates
BEGIN
    SELECT RAISE(ABORT, 'Candidate rows are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_enhance_candidates_no_delete
BEFORE DELETE ON da_enhance_candidates
BEGIN
    SELECT RAISE(ABORT, 'Candidate rows are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_freshness_checks (
    request_id     TEXT NOT NULL REFERENCES da_requests (request_id),
    check_number   INTEGER NOT NULL,
    record_version INTEGER NOT NULL,
    result         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (request_id, check_number)
);

CREATE TRIGGER IF NOT EXISTS da_freshness_checks_no_update
BEFORE UPDATE ON da_freshness_checks
BEGIN
    SELECT RAISE(ABORT, 'Freshness checks are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_freshness_checks_no_delete
BEFORE DELETE ON da_freshness_checks
BEGIN
    SELECT RAISE(ABORT, 'Freshness checks are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_safety_nets (
    request_id     TEXT NOT NULL REFERENCES da_requests (request_id),
    net_version    INTEGER NOT NULL,
    record_version INTEGER NOT NULL,
    net            TEXT NOT NULL,
    fingerprint    TEXT NOT NULL,
    proof          TEXT NOT NULL,
    accepted       INTEGER NOT NULL,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (request_id, net_version)
);

CREATE TRIGGER IF NOT EXISTS da_safety_nets_no_update
BEFORE UPDATE ON da_safety_nets
BEGIN
    SELECT RAISE(ABORT, 'Safety nets are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_safety_nets_no_delete
BEFORE DELETE ON da_safety_nets
BEGIN
    SELECT RAISE(ABORT, 'Safety nets are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_unassigned_files (
    unassigned_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    path             TEXT NOT NULL,
    picked_capability TEXT NOT NULL,
    request_id       TEXT NOT NULL REFERENCES da_requests (request_id),
    state            TEXT NOT NULL,
    resolved_by      TEXT NOT NULL,
    resolved_at      TEXT,
    created_at       TEXT NOT NULL,
    resolved_capability TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS da_unassigned_one_open_per_path
ON da_unassigned_files (path) WHERE state = 'open';

CREATE TRIGGER IF NOT EXISTS da_unassigned_resolved_no_update
BEFORE UPDATE ON da_unassigned_files
WHEN OLD.state != 'open'
BEGIN
    SELECT RAISE(ABORT, 'A resolved Unassigned row cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_unassigned_no_delete
BEFORE DELETE ON da_unassigned_files
BEGIN
    SELECT RAISE(ABORT, 'Unassigned rows cannot be deleted.');
END;
"""


class EnhanceError(UnderstandError):
    """An Enhance action was refused. The message says why in plain words."""


def ensure_enhance_tables(conn: sqlite3.Connection) -> None:
    """Called by ensure_build_tables, after da_requests exists."""
    conn.executescript(_CREATE_TABLES_SQL)
    # Phase 11b: a database made before this column existed gets it added (nullable, so old rows
    # stay valid). Like adding a field to a physical file with CHGPF.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(da_unassigned_files)")}
    if "resolved_capability" not in columns:
        conn.execute("ALTER TABLE da_unassigned_files ADD COLUMN resolved_capability TEXT")


# --- the working state ---


def read_enhance_revision(conn: sqlite3.Connection, request_id: str) -> int:
    """0 means no Enhance state yet for this request."""
    row = conn.execute(
        "SELECT revision FROM da_enhance_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    return row["revision"] if row else 0


def read_enhance_state(conn: sqlite3.Connection, request_id: str) -> EnhanceState | None:
    row = conn.execute(
        "SELECT state, revision FROM da_enhance_state WHERE request_id = ?", (request_id,)
    ).fetchone()
    if row is None:
        return None
    return EnhanceState.model_validate(json.loads(row["state"]) | {"revision": row["revision"]})


def save_enhance_state(
    conn: sqlite3.Connection, state: EnhanceState, base_revision: int, now: datetime
) -> EnhanceState:
    """Save as revision base_revision + 1; refused if the stored revision moved on. Base 0 means
    the first save. Check and save are one statement, so nothing can slip in between."""
    text = state.model_dump_json(exclude={"revision"})
    if base_revision == 0:
        try:
            conn.execute(
                "INSERT INTO da_enhance_state (request_id, state, revision, updated_at)"
                " VALUES (?, ?, 1, ?)",
                (state.request_id, text, to_db_time(now)),
            )
        except sqlite3.IntegrityError as error:
            if "UNIQUE" not in str(error):
                raise  # for example an unknown request: not a stale save
            raise StaleRevisionError(STALE_MESSAGE) from error
        return state.model_copy(update={"revision": 1})
    cursor = conn.execute(
        "UPDATE da_enhance_state SET state = ?, revision = ?, updated_at = ?"
        " WHERE request_id = ? AND revision = ?",
        (text, base_revision + 1, to_db_time(now), state.request_id, base_revision),
    )
    if cursor.rowcount != 1:
        raise StaleRevisionError(STALE_MESSAGE)
    return state.model_copy(update={"revision": base_revision + 1})


def list_requests_at_step(conn: sqlite3.Connection, step: str) -> list[str]:
    """Request IDs whose Enhance step is `step` (used at start-up to find cut-off safety nets)."""
    rows = conn.execute("SELECT request_id, state FROM da_enhance_state ORDER BY request_id")
    return [row["request_id"] for row in rows if json.loads(row["state"]).get("step") == step]


# --- Find rounds ---


def insert_candidates(
    conn: sqlite3.Connection,
    request_id: str,
    find_round: int,
    candidates: list[Candidate],
    now: datetime,
) -> None:
    """Append one Find round. A second save of the same round is refused."""
    try:
        conn.execute(
            "INSERT INTO da_enhance_candidates (request_id, find_round, candidates, created_at)"
            " VALUES (?, ?, ?, ?)",
            (
                request_id,
                find_round,
                json.dumps([item.model_dump() for item in candidates]),
                to_db_time(now),
            ),
        )
    except sqlite3.IntegrityError as error:
        if "UNIQUE" not in str(error):
            raise
        raise EnhanceError(f"Find round {find_round} is already saved.") from error


def read_candidates(conn: sqlite3.Connection, request_id: str) -> list[list[Candidate]]:
    """Every Find round, oldest first, each a list of candidates."""
    rows = conn.execute(
        "SELECT candidates FROM da_enhance_candidates WHERE request_id = ? ORDER BY find_round",
        (request_id,),
    ).fetchall()
    return [[Candidate.model_validate(item) for item in json.loads(row[0])] for row in rows]


# --- freshness checks ---


def next_check_number(conn: sqlite3.Connection, request_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(check_number), 0) AS top FROM da_freshness_checks"
        " WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row["top"] + 1


def insert_freshness_check(
    conn: sqlite3.Connection,
    request_id: str,
    record_version: int,
    result: FreshnessResult,
    now: datetime,
) -> FreshnessCheckRow:
    number = next_check_number(conn, request_id)
    conn.execute(
        "INSERT INTO da_freshness_checks (request_id, check_number, record_version, result,"
        " created_at) VALUES (?, ?, ?, ?, ?)",
        (request_id, number, record_version, result.model_dump_json(), to_db_time(now)),
    )
    return FreshnessCheckRow(
        request_id=request_id,
        check_number=number,
        record_version=record_version,
        result=result,
        created_at=now,
    )


def read_freshness_checks(conn: sqlite3.Connection, request_id: str) -> list[FreshnessCheckRow]:
    rows = conn.execute(
        "SELECT * FROM da_freshness_checks WHERE request_id = ? ORDER BY check_number",
        (request_id,),
    ).fetchall()
    return [
        FreshnessCheckRow(
            request_id=row["request_id"],
            check_number=row["check_number"],
            record_version=row["record_version"],
            result=FreshnessResult.model_validate_json(row["result"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


def read_latest_freshness(conn: sqlite3.Connection, request_id: str) -> FreshnessCheckRow | None:
    found = read_freshness_checks(conn, request_id)
    return found[-1] if found else None


# --- safety nets ---


def next_net_version(conn: sqlite3.Connection, request_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(net_version), 0) AS top FROM da_safety_nets WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row["top"] + 1


def insert_safety_net(
    conn: sqlite3.Connection, item: SafetyNetRow, now: datetime
) -> SafetyNetRow:
    conn.execute(
        "INSERT INTO da_safety_nets (request_id, net_version, record_version, net, fingerprint,"
        " proof, accepted, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.request_id,
            item.net_version,
            item.record_version,
            item.net.model_dump_json(),
            item.fingerprint,
            json.dumps(item.proof),
            1 if item.accepted else 0,
            to_db_time(now),
        ),
    )
    return item.model_copy(update={"created_at": now})


def read_safety_nets(conn: sqlite3.Connection, request_id: str) -> list[SafetyNetRow]:
    rows = conn.execute(
        "SELECT * FROM da_safety_nets WHERE request_id = ? ORDER BY net_version", (request_id,)
    ).fetchall()
    return [
        SafetyNetRow(
            request_id=row["request_id"],
            net_version=row["net_version"],
            record_version=row["record_version"],
            net=SafetyNet.model_validate_json(row["net"]),
            fingerprint=row["fingerprint"],
            proof=json.loads(row["proof"]),
            accepted=bool(row["accepted"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


def read_latest_safety_net(conn: sqlite3.Connection, request_id: str) -> SafetyNetRow | None:
    found = read_safety_nets(conn, request_id)
    return found[-1] if found else None


def read_accepted_net(
    conn: sqlite3.Connection, request_id: str, record_version: int
) -> SafetyNetRow | None:
    """The accepted net in force for one record version: the latest accepted row of it."""
    found = [
        item
        for item in read_safety_nets(conn, request_id)
        if item.accepted and item.record_version == record_version
    ]
    return found[-1] if found else None


# --- the Unassigned queue ---


def add_unassigned(
    conn: sqlite3.Connection, path: str, picked_capability: str, request_id: str, now: datetime
) -> UnassignedFile:
    """Open a row for a file in no capability. A second request on the same path links to the
    row that is already open (one open row per path), and the first pick stays."""
    existing = _open_row(conn, path)
    if existing is not None:
        return existing
    conn.execute(
        "INSERT INTO da_unassigned_files (path, picked_capability, request_id, state,"
        " resolved_by, created_at) VALUES (?, ?, ?, 'open', '', ?)",
        (path, picked_capability, request_id, to_db_time(now)),
    )
    return _open_row(conn, path)  # type: ignore[return-value]


def resolve_unassigned(
    conn: sqlite3.Connection,
    unassigned_id: int,
    state: str,
    resolved_by: str,
    now: datetime,
    resolved_capability: str = "",
) -> None:
    """Close an open row as `confirmed`, `changed` or `rejected` (Phase 11's Admin screen).

    resolved_capability is the capability Admin moved the file to (state `changed`); empty when
    the developer's pick stands or the file is rejected (it belongs in no capability)."""
    if state not in ("confirmed", "changed", "rejected"):
        raise EnhanceError("An Unassigned row is resolved as confirmed, changed or rejected.")
    cursor = conn.execute(
        "UPDATE da_unassigned_files SET state = ?, resolved_by = ?, resolved_at = ?,"
        " resolved_capability = ? WHERE unassigned_id = ? AND state = 'open'",
        (state, resolved_by, to_db_time(now), resolved_capability or None, unassigned_id),
    )
    if cursor.rowcount != 1:
        raise EnhanceError("That Unassigned row is not open.")


def list_unassigned(conn: sqlite3.Connection, state: str = "open") -> list[UnassignedFile]:
    """Read only. Phase 11 shows this list to Admin."""
    rows = conn.execute(
        "SELECT * FROM da_unassigned_files WHERE state = ? ORDER BY unassigned_id", (state,)
    ).fetchall()
    return [_to_unassigned(row) for row in rows]


def list_resolved(conn: sqlite3.Connection, limit: int = 50) -> list[UnassignedFile]:
    """The last `limit` resolved rows (confirmed and changed), newest first. Read only."""
    rows = conn.execute(
        "SELECT * FROM da_unassigned_files WHERE state != 'open'"
        " ORDER BY resolved_at DESC, unassigned_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_to_unassigned(row) for row in rows]


def _open_row(conn: sqlite3.Connection, path: str) -> UnassignedFile | None:
    row = conn.execute(
        "SELECT * FROM da_unassigned_files WHERE path = ? AND state = 'open'", (path,)
    ).fetchone()
    return _to_unassigned(row) if row else None


def _to_unassigned(row: sqlite3.Row) -> UnassignedFile:
    resolved = row["resolved_at"]
    return UnassignedFile(
        unassigned_id=row["unassigned_id"],
        path=row["path"],
        picked_capability=row["picked_capability"],
        request_id=row["request_id"],
        state=row["state"],
        resolved_by=row["resolved_by"],
        resolved_at=datetime.fromisoformat(resolved) if resolved else None,
        resolved_capability=row["resolved_capability"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
    )
