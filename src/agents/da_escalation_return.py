"""Where a request goes when a senior returns it (Phase 10 spec section 10). Plain code, no AI.

Two parts: `pick_return_status` is pure (facts in, status out) and `restore_flow_steps` puts the
flow states back from "escalated" to the step the developer was at. AS400 picture: the help-desk
puts the job back on the job queue it came from.
"""

import json
import sqlite3
from datetime import datetime
from typing import get_args

from agents import da_tester_review as tester
from db_table_functions.db_tbl_da_approach import read_approach_state, save_approach_state
from db_table_functions.db_tbl_da_build import read_build_runs, read_build_state, save_build_state
from db_table_functions.db_tbl_da_enhance import read_enhance_state, save_enhance_state
from db_table_functions.db_tbl_da_tester import read_actions, read_reviews
from pydantic_classes.da_enhance_models import EnhanceStep
from pydantic_classes.da_escalation_models import EscalationRow
from pydantic_classes.da_models import (
    ALLOWED_MOVES,
    STATUS_APPROACH_PROPOSED,
    STATUS_BUILDING,
    STATUS_ESCALATION,
    STATUS_HANDED_OFF,
    STATUS_NOT_PASSING,
    STATUS_READY,
    STATUS_READY_FOR_REVIEW,
    STATUS_REVISION,
    STATUS_TESTER_REVIEW,
    STATUSES,
)

LABEL_NOT_PASSING = "Not passing"
# These three end their run when the request is escalated, so there is nothing to resume.
NOT_RESUMABLE = (STATUS_BUILDING, STATUS_TESTER_REVIEW, STATUS_REVISION)
APPROACH_RESUME_STEPS = ("review", "limit_reason", "tests_pending", "tests")
LABEL_STATUSES = (STATUS_READY_FOR_REVIEW, STATUS_NOT_PASSING)


def pick_return_status(
    from_status: str, finished_build_status: str, has_approach: bool
) -> tuple[str, str]:
    """(status to return to, audit note). The stored `from_status` when it can be resumed, else the
    section 10 guard: a finished build, else the approach, else the Understand checkpoint."""
    resumable = (
        from_status in STATUSES
        and from_status not in NOT_RESUMABLE
        and from_status not in (STATUS_ESCALATION, STATUS_HANDED_OFF)
        and from_status in ALLOWED_MOVES[STATUS_ESCALATION]
    )
    if resumable:
        return from_status, ""
    if finished_build_status in LABEL_STATUSES:
        target = finished_build_status
    elif has_approach:
        target = STATUS_APPROACH_PROPOSED
    else:
        target = STATUS_READY
    note = f"The status {from_status} cannot be resumed, so the request returned to {target}."
    return target, note


def finished_build_status(conn: sqlite3.Connection, request_id: str) -> str:
    """The status the newest finished build ended in, or "" when no build has finished."""
    for run in reversed(read_build_runs(conn, request_id)):
        if run.result_status in LABEL_STATUSES:
            return run.result_status
    return ""


def label_after_overrule(conn: sqlite3.Connection, request_id: str) -> str:
    """The label of the newest review once the senior's overrules are counted, or "" when there is
    no review or no overrule (then the stored status is used unchanged)."""
    state = read_build_state(conn, request_id)
    if state is None or state.build_number == 0:
        return ""
    reviews = read_reviews(conn, request_id, state.build_number)
    actions = read_actions(conn, request_id, state.build_number)
    if not reviews or not any(a.action == "overruled" for a in actions):
        return ""
    review = reviews[-1]
    return tester.compute_label(
        review.findings, list(review.zone_warnings), review.result, review.review_number, actions
    )


def return_status_for(conn: sqlite3.Connection, row: EscalationRow) -> tuple[str, str]:
    """Section 10 in one place: Dispute return, then the made-up-status guard."""
    target, note = pick_return_status(
        row.from_status,
        finished_build_status(conn, row.request_id),
        read_approach_state(conn, row.request_id) is not None,
    )
    if not note and target in LABEL_STATUSES:
        label = label_after_overrule(conn, row.request_id)
        if label:  # a Must fix was overruled: the new label decides, not the old status
            target = STATUS_NOT_PASSING if label == LABEL_NOT_PASSING else STATUS_READY_FOR_REVIEW
    return target, note


def _last_escalated_step(conn: sqlite3.Connection, request_id: str) -> str:
    row = conn.execute(
        "SELECT details FROM da_audit_events WHERE request_id = ? AND event_type = 'escalated'"
        " ORDER BY event_id DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    if row is None:
        return ""
    return str(json.loads(row["details"]).get("step", ""))


def restore_flow_steps(
    conn: sqlite3.Connection, request_id: str, target: str, now: datetime
) -> None:
    """Take the flows out of "escalated". The step comes from the last `escalated` audit event;
    a step that does not belong to that flow falls back to its finished step. Open items are
    cleared (spec section 10)."""
    step = _last_escalated_step(conn, request_id)
    approach = read_approach_state(conn, request_id)
    if approach is not None and (approach.step == "escalated" or approach.open_item):
        if approach.step == "escalated":
            back_at = target == STATUS_APPROACH_PROPOSED and step in APPROACH_RESUME_STEPS
            approach.step = step if back_at else "done"
        approach.open_item = ""
        save_approach_state(conn, approach, approach.revision, now)
    build = read_build_state(conn, request_id)
    if build is not None and build.step == "escalated":
        done = "b_done" if target in LABEL_STATUSES else "start"
        save_build_state(conn, build.model_copy(update={"step": done}), build.revision, now)
    enhance = _enhance_state(conn, request_id)
    if enhance is not None and enhance.step == "escalated":
        back = step if step in get_args(EnhanceStep) and step != "escalated" else "e_find"
        changed = enhance.model_copy(update={"step": back, "open_item": ""})
        save_enhance_state(conn, changed, enhance.revision, now)


def _enhance_state(conn: sqlite3.Connection, request_id: str):
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'da_enhance_state'"
    ).fetchone()
    return read_enhance_state(conn, request_id) if exists else None
