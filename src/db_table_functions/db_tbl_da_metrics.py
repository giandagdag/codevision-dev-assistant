"""Read-only queries behind the Admin console's health numbers (Phase 11c, spec section 12).

SELECT only: nothing here writes. Like a logical file (LF) over the physical files that the earlier
phases built: it selects and groups rows, and leaves the meaning to agents/da_admin_metrics.py.

Every function takes `since`: the window start as database time text (da_db.to_db_time), or None for
all time. All times are stored as fixed-width UTC text, so a plain `>=` compares them correctly.
"""

import sqlite3

# Audit event types that mean "the developer pressed Get help" (screens write different ones).
STATUS_EVENT = "status_changed"
HELP_EVENTS = ("escalated", "discovery_escalated")
BUILD_KINDS = ("build", "rebuild")  # a "check" run has no Generator, so no first round to judge


def _window(column: str, since: str | None) -> tuple[str, tuple]:
    """A WHERE fragment (starting with AND) and its parameters for the time window."""
    if since is None:
        return "", ()
    return f" AND {column} >= ?", (since,)


def request_rows(conn: sqlite3.Connection, since: str | None) -> list[sqlite3.Row]:
    """Each request created in the window with its Enhance state JSON (None when it has none)."""
    clause, params = _window("r.created_at", since)
    return conn.execute(
        "SELECT r.request_id, e.state AS enhance_state FROM da_requests r"
        " LEFT JOIN da_enhance_state e ON e.request_id = r.request_id"
        f" WHERE 1 = 1{clause}",
        params,
    ).fetchall()


def closed_build_rows(conn: sqlite3.Connection, since: str | None) -> list[sqlite3.Row]:
    """Closed builds (build or rebuild) with their round 1 layers (None when round 1 has no row)."""
    clause, params = _window("b.ended_at", since)
    marks = ", ".join("?" for _ in BUILD_KINDS)
    return conn.execute(
        "SELECT b.request_id, b.build_number, b.rounds_used, r.layer_a, r.layer_b"
        " FROM da_build_runs b LEFT JOIN da_build_rounds r"
        "   ON r.request_id = b.request_id AND r.build_number = b.build_number AND r.round = 1"
        f" WHERE b.ended_at IS NOT NULL AND b.kind IN ({marks}){clause}",
        (*BUILD_KINDS, *params),
    ).fetchall()


def highest_record_versions(conn: sqlite3.Connection, since: str | None) -> list[int]:
    """For each request with a confirmed record in the window: its highest record version."""
    clause, params = _window("confirmed_at", since)
    rows = conn.execute(
        "SELECT MAX(version) AS top FROM da_request_records"
        f" WHERE 1 = 1{clause} GROUP BY request_id",
        params,
    ).fetchall()
    return [row["top"] for row in rows]


def scanned_file_counts(conn: sqlite3.Connection, since: str | None) -> tuple[int, int]:
    """(distinct request+path pairs scanned, distinct requests with at least one)."""
    clause, params = _window("created_at", since)
    row = conn.execute(
        "SELECT COUNT(DISTINCT request_id || char(31) || path) AS files,"
        " COUNT(DISTINCT request_id) AS requests FROM da_workspace_files"
        f" WHERE kind = 'scanned'{clause}",
        params,
    ).fetchone()
    return row["files"], row["requests"]


def help_event_rows(conn: sqlite3.Connection, since: str | None) -> list[sqlite3.Row]:
    """Audit rows that may be a Get help: the status moves and the escalation events."""
    clause, params = _window("timestamp", since)
    marks = ", ".join("?" for _ in HELP_EVENTS)
    return conn.execute(
        "SELECT request_id, event_type, details FROM da_audit_events"
        f" WHERE (event_type = ? OR event_type IN ({marks})){clause}",
        (STATUS_EVENT, *HELP_EVENTS, *params),
    ).fetchall()


def kept_findings_by_check_and_severity(
    conn: sqlite3.Connection, since: str | None
) -> list[sqlite3.Row]:
    """Kept Tester findings counted per (check number, severity). Rejected ones never count."""
    clause, params = _window("created_at", since)
    return conn.execute(
        "SELECT check_number, severity, COUNT(*) AS total FROM da_tester_findings"
        f" WHERE kept = 1{clause} GROUP BY check_number, severity",
        params,
    ).fetchall()


def review_counts(conn: sqlite3.Connection, since: str | None) -> tuple[int, int]:
    """(all Tester reviews, reviews that ended "unable" to assess)."""
    clause, params = _window("created_at", since)
    row = conn.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(result = 'unable'), 0) AS unable"
        f" FROM da_tester_reviews WHERE 1 = 1{clause}",
        params,
    ).fetchone()
    return row["total"], row["unable"]
