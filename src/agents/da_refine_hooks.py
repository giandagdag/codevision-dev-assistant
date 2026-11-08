"""What the Approach flow needs to know about a requirement-lane Refine (Phase 8 spec section 5).

Kept apart from `da_refine_revision.py` on purpose: the Approach flow calls these two functions,
and the revision flow calls the Approach flow. Putting the shared part here, with no import of
either flow, keeps the files from importing each other in a circle.

AS400 picture: a small exit program. The main job (Approach) calls it at two fixed points and
carries on without knowing the details.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from agents.da_refine_checks import diff_records
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_versions
from db_table_functions.db_tbl_da_audit import insert_audit_event
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_refine import (
    close_refine,
    read_all_records,
    read_refine_state,
    read_refines,
    save_refine_state,
)
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_understand import add_message
from db_table_functions.db_tbl_da_workspace import read_workspace_state, save_workspace_state
from pydantic_classes.da_refine_models import RecordDiff

# Refine steps of the requirement lane after Confirm v2 (the earlier ones live in da_refine_lanes).
STEP_REQ_FINDINGS = "req_findings"  # Discover ran on the new version; "Findings look right" waits
STEP_REQ_APPROACH = "req_approach"  # findings confirmed; the revision approach is being made
STEP_REQ_PLAN = "req_plan"  # the revision approach is shown; accept it, then the test plan
APPROACH_STEPS = (STEP_REQ_APPROACH, STEP_REQ_PLAN)

DROPPED_FILES_LINE = (
    "These files are no longer in the plan. Delete them yourself if you do not need them: {paths}."
)


@dataclass
class RevisionPlan:
    """What changed in the record, in the words the test plan needs."""

    refine_number: int
    diff: RecordDiff
    # Criteria that need new Tester cases (added and changed).
    needs_cases: list[str] = field(default_factory=list)
    # Criteria whose old cases are dropped (changed and removed).
    dropped: set[str] = field(default_factory=set)
    old_approach_version: int = 0


def read_revision_plan(conn: sqlite3.Connection, request_id: str) -> RevisionPlan | None:
    """None unless a requirement lane is waiting for its approach or test plan."""
    state = read_refine_state(conn, request_id)
    request = read_request(conn, request_id)
    if state is None or request is None or state.step not in APPROACH_STEPS:
        return None
    rows = [r for r in read_refines(conn, request_id) if r.refine_number == state.refine_number]
    versions = {record.version: record for record in read_all_records(conn, request_id)}
    if not rows or rows[0].record_version_before not in versions or request.version not in versions:
        return None
    diff = diff_records(versions[rows[0].record_version_before], versions[request.version])
    return RevisionPlan(
        refine_number=state.refine_number,
        diff=diff,
        needs_cases=[c.id for c in diff.criteria if c.change in ("added", "changed")],
        dropped={c.id for c in diff.criteria if c.change in ("changed", "removed")},
        old_approach_version=rows[0].approach_version_before,
    )


def revision_plan_of(db_path: Path, request_id: str) -> RevisionPlan | None:
    """The same, on its own read connection (for the part that runs before an AI call)."""
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        return read_revision_plan(conn, request_id)


def finish_revision(conn: sqlite3.Connection, request_id: str, now: datetime) -> None:
    """Called inside Accept test plan, in its write transaction, once the gate has passed.

    Closes the Refine, lists the files the new plan dropped (never deleted), and sends the
    workspace back to its first step so the folder check runs again on the new file plan.
    """
    plan = read_revision_plan(conn, request_id)
    if plan is None:
        return
    request = read_request(conn, request_id)
    approaches = read_approach_versions(conn, request_id)
    newest = approaches[-1]
    old = next((v for v in approaches if v.approach_version == plan.old_approach_version), None)
    close_refine(
        conn,
        request_id,
        plan.refine_number,
        result="requirement",
        record_version_after=request.version,
        approach_version_after=newest.approach_version,
        build_number=0,
        repro_passed_today=0,
        now=now,
    )
    if old is not None:
        kept = {item.path for item in newest.plan.files}
        gone = [item.path for item in old.plan.files if item.path not in kept]
        if gone:
            line = DROPPED_FILES_LINE.format(paths=", ".join(gone))
            add_message(conn, request_id, "assistant", line, now)
            insert_audit_event(
                conn, request_id, "system", "files_dropped_from_plan", {"paths": gone}, now
            )
    workspace = read_workspace_state(conn, request_id)
    if workspace is not None:
        save_workspace_state(
            conn, workspace.model_copy(update={"step": "start"}), workspace.revision, now
        )
    state = read_refine_state(conn, request_id)
    insert_audit_event(
        conn, request_id, "system", "refine_requirement_ready", {"refine": plan.refine_number}, now
    )
    done = {"step": "start", "chosen_lane": "", "pending_feedback": "", "pending_record": None}
    save_refine_state(conn, state.model_copy(update=done), state.revision, now)
