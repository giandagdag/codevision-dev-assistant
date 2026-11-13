"""The read-only "Cited" counts for the Admin console (Phase 11b, spec section 7).

A thin wrapper: the SQL lives in db_tbl_da_tester.count_kept_cites. Only findings the Tester kept
count, so a finding thrown out by the quote check never raises a rule's number. Phase 11c reuses
this for "Rules cited" on the Overview. Plain code, no AI.
"""

from pathlib import Path

from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_tester import count_kept_cites


def cited_counts(db_path: Path) -> dict[str, int]:
    """{rule_id: how many kept findings cite it}. A rule never cited is simply not in the answer."""
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        return count_kept_cites(conn)
