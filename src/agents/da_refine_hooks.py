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
from db_table_functions.db_tbl_da_approach import (
    read_approach_state,
    read_approach_versions,
    read_latest_plan,
)
from db_table_functions.db_tbl_da_audit import insert_audit_event
from db_table_functions.db_tbl_da_build import (
    ensure_build_tables,
    read_build_state,
    save_build_state,
)
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
# Approach lane: the new approach version is shown; accept it, then the test plan (spec section 6).
STEP_APPROACH_PLAN = "approach_plan"

DROPPED_FILES_LINE = (
    "These files are no longer in the plan. Delete them yourself if you do not need them: {paths}."
)


@dataclass
class RevisionPlan:
    """What changed in the record, in the words the test plan needs."""

    refine_number: int
    # None for the approach lane: the record did not change.
    diff: RecordDiff | None
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


def _approach_lane_plan(conn: sqlite3.Connection, request_id: str) -> RevisionPlan | None:
    """The approach lane at its test plan step, in the shape finish_revision needs."""
    state = read_refine_state(conn, request_id)
    if state is None or state.step != STEP_APPROACH_PLAN:
        return None
    rows = [r for r in read_refines(conn, request_id) if r.refine_number == state.refine_number]
    if not rows:
        return None
    return RevisionPlan(
        refine_number=state.refine_number,
        diff=None,
        old_approach_version=rows[0].approach_version_before,
    )


def revision_plan_of(db_path: Path, request_id: str) -> RevisionPlan | None:
    """The same, on its own read connection (for the part that runs before an AI call)."""
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        return read_revision_plan(conn, request_id)


def approach_lane_keeps_plan(conn: sqlite3.Connection, request_id: str) -> bool | None:
    """None unless an approach lane waits for its test plan. Otherwise True when the design
    decisions are the same as the ones the current test plan was written from: the Tester is
    then not asked again and the plan is carried over to the new approach version (8-20)."""
    state = read_refine_state(conn, request_id)
    if state is None or state.step != STEP_APPROACH_PLAN:
        return None
    plan = read_latest_plan(conn, request_id)
    approach_state = read_approach_state(conn, request_id)
    if plan is None or approach_state is None:
        return False
    versions = read_approach_versions(conn, request_id)
    written_from = next((v for v in versions if v.approach_version == plan.approach_version), None)
    if written_from is None:
        return False
    return _decision_key(written_from.decisions) == _decision_key(approach_state.decisions)


def approach_lane_plan_of(db_path: Path, request_id: str) -> bool | None:
    """The same, on its own read connection (for the part that runs before an AI call)."""
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        return approach_lane_keeps_plan(conn, request_id)


def _decision_key(decisions) -> list[tuple[str, str]]:
    return [(item.question, item.choice) for item in decisions]


def finish_revision(conn: sqlite3.Connection, request_id: str, now: datetime) -> None:
    """Called inside Accept test plan, in its write transaction, once the gate has passed.

    Closes the Refine, lists the files the new plan dropped (never deleted), and sends the
    workspace back to its first step so the folder check runs again on the new file plan.
    Works for the requirement lane and for the approach lane.
    """
    plan = read_revision_plan(conn, request_id)
    if plan is None:
        plan = _approach_lane_plan(conn, request_id)
    if plan is None:
        return
    request = read_request(conn, request_id)
    approaches = read_approach_versions(conn, request_id)
    newest = approaches[-1]
    old = next((v for v in approaches if v.approach_version == plan.old_approach_version), None)
    lane = "requirement" if plan.diff is not None else "approach"
    close_refine(
        conn,
        request_id,
        plan.refine_number,
        result=lane,
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
    # The earlier build is finished and written. A new approach version needs a new build (spec
    # section 5, step 10), and Build only starts from the step `start`. The build number goes on
    # counting, and every earlier build stays in the Versions list.
    build = read_build_state(conn, request_id)
    if build is not None and build.step == "b_written":
        fresh = {"step": "start", "write_state": "not_written", "message": "", "return_status": ""}
        save_build_state(conn, build.model_copy(update=fresh), build.revision, now)
    state = read_refine_state(conn, request_id)
    insert_audit_event(
        conn, request_id, "system", f"refine_{lane}_ready", {"refine": plan.refine_number}, now
    )
    done = {"step": "start", "chosen_lane": "", "pending_feedback": "", "pending_record": None}
    save_refine_state(conn, state.model_copy(update=done), state.revision, now)
