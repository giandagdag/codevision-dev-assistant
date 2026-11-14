"""A senior's guidance, handed once to the next AI call (Phase 10 spec section 9, step 9).

Plain code, no AI of its own, and no new prompt file: the four existing prompt builders (Approach,
the Generator's fix round, the Refine lane suggestion and the Tester review) add the block this
file makes. `take_guidance` reads the guidance a senior sent on a RETURNED escalation, marks it
used (so the call after it gets nothing) and audits `guidance_used`.
AS400 picture: a note pinned to the job ticket that the next operator reads once and initials.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_escalation import mark_guidance_used, read_escalations

HEADING = "Guidance from your senior (advice from a person; the rules above still apply):"

# Where it was used, as written on the row and in the audit trail.
USED_APPROACH = "approach"
USED_FIX_ROUND = "build_fix_round"
USED_REFINE_LANE = "refine_lane"
USED_TESTER_REVIEW = "tester_review"


def guidance_block(text: str) -> str:
    """The block a prompt builder appends. Empty text gives an empty string (nothing changes)."""
    return f"\n\n{HEADING}\n{text.strip()}\n" if text and text.strip() else ""


def take_guidance(
    db_path: Path, request_id: str, used_in: str, now: datetime | None = None
) -> str:
    """The unused guidance of this request's returned escalations, joined; marked used."""
    with open_db(db_path) as conn:
        if not _unused(conn, request_id):
            return ""  # the usual case: no lock taken, no write
    now = now or datetime.now(UTC)
    with open_db(db_path) as conn:
        ensure_audit_table(conn)
        begin_write(conn)
        rows = _unused(conn, request_id)  # read again under the lock: another call may have won
        texts = []
        for row in rows:
            texts += [item.text for item in row.guidance if not item.used_in]
            mark_guidance_used(conn, row, used_in)
        if texts:
            insert_audit_event(
                conn, request_id, "system", "guidance_used",
                {"used_in": used_in, "pieces": len(texts)}, now,
            )  # fmt: skip
    return "\n".join(texts)


def _unused(conn: sqlite3.Connection, request_id: str) -> list:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'da_escalations'"
    ).fetchone()
    if exists is None:
        return []
    return [
        row
        for row in read_escalations(conn, request_id)
        if row.outcome == "returned" and any(not item.used_in for item in row.guidance)
    ]
