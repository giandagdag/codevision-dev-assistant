"""The read-only "Cited" counts for the Admin console (Phase 11b, spec section 7).

A thin wrapper: the SQL lives in db_tbl_da_tester.count_kept_cites. Only findings the Tester kept
count, so a finding thrown out by the quote check never raises a rule's number. Phase 11c reuses
this for "Rules cited" on the Overview. Plain code, no AI.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from db_table_functions.da_db import open_db, to_db_time
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_tester import count_kept_cites

FIRES_AMBER_ABOVE = 50  # percent: a rule that fires this often may be too strict or badly worded


def fires_in(db_path: Path, now: datetime | None = None) -> dict[str, int]:
    """{rule_id: percent of the last 30 days' Tester reviews with a kept finding citing it}.

    Empty when there were no reviews. A rule never cited is not in the answer."""
    since = to_db_time((now or datetime.now(UTC)) - timedelta(days=30))
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        total = conn.execute(
            "SELECT COUNT(*) FROM da_tester_reviews WHERE created_at >= ?", (since,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT cites,"
            " COUNT(DISTINCT request_id || '/' || build_number || '/' || review_number)"
            " FROM da_tester_findings WHERE kept = 1 AND cites <> '' AND created_at >= ?"
            " GROUP BY cites",
            (since,),
        ).fetchall()
    return {r[0]: round(100 * r[1] / total) for r in rows} if total else {}


def cited_counts(db_path: Path) -> dict[str, int]:
    """{rule_id: how many kept findings cite it}. A rule never cited is simply not in the answer."""
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        return count_kept_cites(conn)
