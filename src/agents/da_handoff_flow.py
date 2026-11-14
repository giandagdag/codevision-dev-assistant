"""The Handoff actions the screen calls (Phase 10 spec sections 2 to 4).

Same pattern as Build and Refine: read with no lock, the browser's file read happens outside any
transaction, then ONE write transaction holds the state, the rows, the audit events and the chat
lines together (rule B3). Handoff has its own revision for the stale-window check.

AS400 picture: the promotion request. First the clerk ticks the checklist (ready_for_handoff),
then compares the member in the library with the one that was tested (final_check), and only
then is the object promoted and locked.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from agents.da_handoff_checks import compare_fingerprints, findings_check, folder_blockers
from agents.da_handoff_facts import gather_summary_facts
from agents.da_handoff_summary import build_summary
from agents.da_tester_flow import DONE_STEPS, get_tester_view
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_approach import read_approach_state, save_approach_state
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_build import ensure_build_tables, read_build_state
from db_table_functions.db_tbl_da_enhance import ensure_enhance_tables
from db_table_functions.db_tbl_da_handoff import (
    HandoffLockedError,
    get_last_tested_fingerprints,
    insert_handoff,
    read_handoff,
    read_handoff_state,
    refuse_if_locked,
    save_handoff_state,
)
from db_table_functions.db_tbl_da_refine import read_tested
from db_table_functions.db_tbl_da_requests import (
    get_rulebook_for_request,
    insert_request,
    read_request,
    update_request,
)
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
    add_message,
)
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables
from pydantic_classes.da_handoff_models import (
    ESCALATION_OPEN_MESSAGE,
    HandoffRow,
    HandoffState,
    HandoffView,
)
from pydantic_classes.da_models import (
    STATUS_ESCALATION,
    STATUS_HANDED_OFF,
    STATUS_NOT_PASSING,
    STATUS_READY_FOR_REVIEW,
    Request,
)

READY_LABEL = "Ready for handoff"
HELP_LABEL = "Get help"
ESCALATED_PREFIX = "Escalated in Handoff: "
NOT_PASSING_LINE = "Handoff needs a passing build. Refine, or Get help."
NOT_READY_MESSAGE = "Handoff is only possible when the request is READY FOR REVIEW."
WRONG_STEP_MESSAGE = "That is not possible at this step of the Handoff."
DONE_LINE = (
    "Handed off. The request is locked. Copy the PR summary from the Audit tab into your pull "
    "request."
)


class HandoffError(UnderstandError):
    """A Handoff action that is not possible now (the message is shown to the developer)."""


# --- reading ---


def get_handoff_view(settings, request_id: str) -> HandoffView:
    """Everything the screen needs about Handoff, read with no lock."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        request = read_request(conn, request_id)
        state = read_handoff_state(conn, request_id) or HandoffState(request_id=request_id)
        row = read_handoff(conn, request_id)
    status = request.status if request else ""
    return HandoffView(
        state=state,
        handoff=row,
        can_start=status == STATUS_READY_FOR_REVIEW
        and state.step in ("h_start", "h_blocked_findings"),
        locked=status == STATUS_HANDED_OFF,
    )


# --- actions ---


def ready_for_handoff(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> HandoffState:
    """H1 to H3: the plain checks. A blocked answer writes the state, one audit event and the chat
    line, and nothing else. A clean answer moves to h_checking (the browser reads the folder)."""
    now = now or datetime.now(UTC)
    report = get_tester_view(settings, request_id)  # read before the write lock opens
    with _write(settings.db_path) as conn:
        request = _require_open(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_ready(request)
        if state.step not in ("h_start", "h_blocked_findings", "h_blocked_folder"):
            raise HandoffError(WRONG_STEP_MESSAGE)
        _refuse_if_escalated(conn, request_id)
        build = read_build_state(conn, request_id)
        finished = build is not None and build.step in DONE_STEPS
        blockers = findings_check(report.label, report.rows, finished)
        _say(conn, request_id, "developer", READY_LABEL, now)
        if blockers:
            insert_audit_event(
                conn, request_id, "system", "handoff_blocked",
                {"blockers": [item.text for item in blockers]}, now,
            )  # fmt: skip
            _say(conn, request_id, "assistant", "\n".join(item.text for item in blockers), now)
            changes = {"step": "h_blocked_findings", "blockers": blockers, "checks": []}
        else:
            _say(conn, request_id, "assistant", "Checking your folder against the last test.", now)
            changes = {"step": "h_checking", "blockers": [], "checks": []}
        return save_handoff_state(conn, state.model_copy(update=changes), base_revision, now)


def final_check(
    settings,
    request_id: str,
    base_revision: int,
    fingerprints: dict[str, str],
    now: datetime | None = None,
) -> HandoffState:
    """H4/H5. `fingerprints` is what the browser read: path -> fingerprint of each planned file
    it found. If every planned file equals the last tested one, ONE transaction writes the
    handoff row (with the PR summary), the status move, the audit events and the chat lines."""
    now = now or datetime.now(UTC)
    # Read before the write lock opens: the summary length limit of the pinned rulebook.
    policy = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    with _write(settings.db_path) as conn:
        request = _require_open(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_ready(request)
        if state.step not in ("h_checking", "h_blocked_folder"):
            raise HandoffError(WRONG_STEP_MESSAGE)
        _refuse_if_escalated(conn, request_id)
        expected = get_last_tested_fingerprints(conn, request_id)
        approach = read_approach_state(conn, request_id)
        planned = _planned_paths(conn, request_id, expected)
        checks = compare_fingerprints(planned, fingerprints, expected)
        blocked = folder_blockers(checks)
        insert_audit_event(
            conn, request_id, "system", "handoff_checked",
            {"result": "blocked" if blocked else "equal", "paths": len(checks)}, now,
        )  # fmt: skip
        if blocked:
            _say(conn, request_id, "assistant", "\n".join(blocked), now)
            changes = {"step": "h_blocked_folder", "checks": checks}
            return save_handoff_state(conn, state.model_copy(update=changes), base_revision, now)
        max_chars = policy.handoff_summary_max_chars
        return _hand_off(conn, request, state, base_revision, checks, approach, max_chars, now)


def start_follow_up(
    settings, request_id: str, developer_id: str, now: datetime | None = None
) -> Request:
    """A new request that follows a handed-off one. Only the link is kept (nothing is copied)."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        old = read_request(conn, request_id)
        if old is None or old.status != STATUS_HANDED_OFF:
            raise HandoffError("A follow-up can only start from a handed-off request.")
        new = insert_request(conn, f"Follow-up to {old.title}"[:200], developer_id, now, request_id)
        insert_audit_event(
            conn, request_id, "developer", "follow_up_started", {"new_request": new.request_id}, now
        )
        insert_audit_event(
            conn, new.request_id, "system", "follow_up_started", {"follows": request_id}, now
        )
        return new


def request_help(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> HandoffState:
    """Get help inside Handoff (H7): ESCALATION_REQUIRED, open item `Escalated in Handoff: ...`."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_open(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_ready(request)
        approach = read_approach_state(conn, request_id)
        if approach is None:
            raise HandoffError("There is no approach to escalate.")
        open_item = f"{ESCALATED_PREFIX}{state.step}"
        revision = approach.revision
        approach.step = "escalated"
        approach.open_item = open_item
        save_approach_state(conn, approach, revision, now)
        _say(conn, request_id, "developer", HELP_LABEL, now)
        insert_audit_event(
            conn, request_id, "developer", "escalated",
            {"step": state.step, "open_item": open_item}, now,
        )  # fmt: skip
        _move(conn, request, STATUS_ESCALATION, now)
        _say(conn, request_id, "assistant", "A senior developer will pick this up.", now)
        reset = state.model_copy(update={"step": "h_start", "blockers": [], "checks": []})
        return save_handoff_state(conn, reset, base_revision, now)


# --- helpers ---


def _hand_off(conn, request, state, base_revision, checks, approach, max_chars, now):
    request_id = request.request_id
    facts = gather_summary_facts(conn, request_id)
    text = build_summary(facts, max_chars)
    tested = read_tested(conn, request_id)
    insert_handoff(
        conn,
        HandoffRow(
            request_id=request_id,
            record_version=facts.record_version,
            approach_version=approach.accepted_approach_version if approach else 0,
            last_tested_build=facts.build_number,
            last_tested_kind=tested["last_tested_kind"] or "build",
            summary_text=text,
            handed_off_by=request.developer_id,
        ),
        now,
    )
    _move(conn, request, STATUS_HANDED_OFF, now)
    insert_audit_event(
        conn, request_id, "developer", "handed_off",
        {"build": facts.build_number, "summary_chars": len(text)}, now,
    )  # fmt: skip
    _say(conn, request_id, "assistant", DONE_LINE, now)
    changes = {"step": "h_done", "blockers": [], "checks": checks}
    return save_handoff_state(conn, state.model_copy(update=changes), base_revision, now)


def _move(conn: sqlite3.Connection, request: Request, status: str, now: datetime) -> Request:
    moved = update_request(conn, request.request_id, now=now, status=status)
    insert_audit_event(
        conn, request.request_id, "system", "status_changed",
        {"from": request.status, "to": status}, now,
    )  # fmt: skip
    return moved


def _planned_paths(conn, request_id: str, expected: dict[str, str]) -> list[str]:
    """The planned files (R1: planned files only), in plan order. Falls back to the tested files
    when there is no accepted approach row."""
    from agents.da_handoff_facts import _accepted_approach

    approach = _accepted_approach(conn, request_id)
    if approach is None:
        return sorted(expected)
    return [item.path for item in approach.plan.files]


def _refuse_if_escalated(conn: sqlite3.Connection, request_id: str) -> None:
    """H6: an open escalation blocks Handoff. The table arrives with the escalations inbox."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'da_escalations'"
    ).fetchone()
    if exists is None:
        return
    row = conn.execute(
        "SELECT 1 FROM da_escalations WHERE request_id = ? AND status = 'open'", (request_id,)
    ).fetchone()
    if row is not None:
        raise HandoffError(ESCALATION_OPEN_MESSAGE)


def _require_open(conn: sqlite3.Connection, request_id: str) -> Request:
    request = read_request(conn, request_id)
    if request is None:
        raise HandoffError(f"Request {request_id} does not exist.")
    refuse_if_locked(conn, request_id)
    return request


def _require_ready(request: Request) -> None:
    if request.status == STATUS_NOT_PASSING:
        raise HandoffError(NOT_PASSING_LINE)
    if request.status != STATUS_READY_FOR_REVIEW:
        raise HandoffError(NOT_READY_MESSAGE)


def _load_state(conn: sqlite3.Connection, request_id: str, base_revision: int) -> HandoffState:
    state = read_handoff_state(conn, request_id)
    if (state.revision if state else 0) != base_revision:
        raise StaleRevisionError(STALE_MESSAGE)
    return state or HandoffState(request_id=request_id)


def _say(conn, request_id: str, speaker, text: str, now: datetime) -> None:
    add_message(conn, request_id, speaker, text, now)


@contextmanager
def _write(db_path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Tables first: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_audit_table(conn)
        ensure_workspace_tables(conn)
        ensure_build_tables(conn)
        ensure_enhance_tables(conn)
        begin_write(conn)
        yield conn


__all__ = ["HandoffError", "HandoffLockedError"]
