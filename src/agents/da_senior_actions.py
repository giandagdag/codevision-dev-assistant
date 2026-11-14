"""What a senior can do with an open escalation (Phase 10 spec section 9): overrule a finding, send
guidance, take over, close. Plus the chat lock (section 11) and the routing of escalations that
were opened before this phase (test 10-32). Plain code, no AI.

Every action is ONE write transaction that checks the escalation row's own revision, so an old
window is refused with the stale message (test 10-46). AS400 picture: the help-desk operator
works the message queue; each reply is logged and the job is released back to its owner.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from agents import da_tester_review as tester
from agents.da_escalation_flow import route_request
from agents.da_escalation_return import restore_flow_steps, return_status_for
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_approach import read_approach_state
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_build import ensure_build_tables, read_build_state
from db_table_functions.db_tbl_da_escalation import (
    insert_escalation,
    read_escalation,
    read_escalations,
    read_open_escalation,
    update_escalation,
)
from db_table_functions.db_tbl_da_refine import add_build_result
from db_table_functions.db_tbl_da_requests import read_request, update_request
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables, version_on
from db_table_functions.db_tbl_da_tester import insert_action, read_actions, read_reviews
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
    add_message,
    ensure_understand_tables,
)
from pydantic_classes.da_escalation_models import UNASSIGNED, EscalationRow, Guidance
from pydantic_classes.da_models import STATUS_ESCALATION
from pydantic_classes.da_tester_models import ACCEPT_MAX_CHARS, FindingAction

OVERRULE_MIN_CHARS = 20
GUIDANCE_MAX_CHARS = 2000
NOTE_MAX_CHARS = 500
OVERRULE_REASON_MESSAGE = (
    f"Please write a reason of {OVERRULE_MIN_CHARS} to {ACCEPT_MAX_CHARS} characters."
)
CLOSED_MESSAGE = "This escalation is already closed."
SENIOR_PREFIX = "Senior "  # chat lines from a senior start with this, so the screen can mark them


class SeniorActionError(UnderstandError):
    """A senior action that is not possible now (the message is shown to him)."""


@dataclass
class ChatLock:
    """The developer's composer while a row is open (spec section 11)."""

    locked: bool = False
    waiting_line: str = ""


# --- the four actions ---


def overrule_finding(
    settings, escalation_id: int, base_revision: int, senior_id: str, finding_id: str,
    reason: str, now: datetime | None = None,
) -> None:  # fmt: skip
    """Overrule one open Must fix or Should fix of the newest review. The label is worked out
    again by plain code; the status does not change here (Close does that)."""
    text = " ".join((reason or "").split())
    if not OVERRULE_MIN_CHARS <= len(text) <= ACCEPT_MAX_CHARS:
        raise SeniorActionError(OVERRULE_REASON_MESSAGE)
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        row = _open_row(conn, escalation_id, base_revision)
        number = _build_number(conn, row.request_id)
        reviews = read_reviews(conn, row.request_id, number) if number else []
        if not reviews:
            raise SeniorActionError("There is no Tester review to overrule a finding in.")
        review, actions = reviews[-1], read_actions(conn, row.request_id, number)
        item = _open_finding(review, finding_id, actions)
        before = _label(review, actions)
        action = FindingAction(
            request_id=row.request_id, build_number=number, review_number=review.review_number,
            finding_id=item.finding_id, action="overruled", reason=text,
            actor=f"senior:{senior_id}",
        )  # fmt: skip
        insert_action(conn, action, now)
        actions.append(action)
        after = _label(review, actions)
        update_escalation(conn, row, base_revision, now)
        details = {"finding": finding_id, "reason": text}
        _audit(conn, row, "finding_overruled", senior_id, details, now)
        line = f"Overruled {finding_id}: {text}."
        if after != before:
            _audit(conn, row, "label_changed", senior_id, {"from": before, "to": after}, now)
            line += f" The label is now {after}."
        _say(conn, row, senior_id, line, now)


def send_guidance(
    settings, escalation_id: int, base_revision: int, senior_id: str, text: str,
    now: datetime | None = None,
) -> None:  # fmt: skip
    """Save guidance on the row and show it in the developer's chat. It goes once into the next
    AI call of the flow the request returns to (step 9). With the chat lock on, it unlocks."""
    clean = (text or "").strip()
    if not 1 <= len(clean) <= GUIDANCE_MAX_CHARS:
        raise SeniorActionError(f"Please write guidance of 1 to {GUIDANCE_MAX_CHARS} characters.")
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        row = _open_row(conn, escalation_id, base_revision)
        note = Guidance(text=clean, sent_by=senior_id, sent_at=now)
        changed = row.model_copy(update={"guidance": [*row.guidance, note]})
        update_escalation(conn, changed, base_revision, now)
        _audit(conn, row, "guidance_sent", senior_id, {"chars": len(clean)}, now)
        _say(conn, row, senior_id, clean, now)


def take_over(
    settings, escalation_id: int, base_revision: int, senior_id: str, now: datetime | None = None
) -> None:
    """Record who is working on it. Nothing else changes; a second senior is refused."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        row = _open_row(conn, escalation_id, base_revision)
        if row.taken_over_by:
            raise SeniorActionError(f"Taken over by {row.taken_over_by}.")
        changed = row.model_copy(update={"taken_over_by": senior_id})
        update_escalation(conn, changed, base_revision, now)
        _audit(conn, row, "escalation_taken_over", senior_id, {}, now)
        line = f"{senior_id} has taken over this request."
        add_message(conn, row.request_id, "assistant", line, now)


def close_escalation(
    settings, escalation_id: int, base_revision: int, senior_id: str, outcome: str, note: str,
    now: datetime | None = None,
) -> None:  # fmt: skip
    """Close the row: `returned` sends the request back (section 10), `abandoned` locks it."""
    clean = " ".join((note or "").split())
    if not 1 <= len(clean) <= NOTE_MAX_CHARS:
        raise SeniorActionError(f"Please write a note of 1 to {NOTE_MAX_CHARS} characters.")
    if outcome not in ("returned", "abandoned"):
        raise SeniorActionError("Choose Return to developer or Abandon request.")
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        row = _open_row(conn, escalation_id, base_revision)
        closed = row.model_copy(
            update={"outcome": outcome, "close_note": clean, "closed_by": senior_id}
        )
        update_escalation(conn, closed, base_revision, now)
        details = {"outcome": outcome, "note": clean}
        if outcome == "abandoned":
            _audit(conn, row, "escalation_closed", senior_id, details, now)
            _say(conn, row, senior_id, f"Closed this request: {clean}", now)
            return
        target, guard_note = return_status_for(conn, row)
        _return(conn, row, target, senior_id, now)
        details |= {"to": target} | ({"guard": guard_note} if guard_note else {})
        _audit(conn, row, "escalation_closed", senior_id, details, now)
        _say(conn, row, senior_id, f"Returned this request to you: {clean}", now)
        if guard_note:
            add_message(conn, row.request_id, "assistant", guard_note, now)


# --- the chat lock (section 11) ---


def chat_lock_for(conn: sqlite3.Connection, request_id: str) -> ChatLock:
    """Locked while a row is open, the policy switch is on and no guidance has been sent."""
    row = read_open_escalation(conn, request_id) if _has_table(conn, "da_escalations") else None
    request = read_request(conn, request_id)
    if row is None or request is None or row.guidance:
        return ChatLock()
    version = version_on(conn, request.rulebook_version) if request.rulebook_version else None
    if version is not None and not version.rulebook.policy.escalation_lock_chat:
        return ChatLock()
    who = "your senior" if row.senior_label == UNASSIGNED else row.senior_label
    return ChatLock(
        locked=True,
        waiting_line=f"Waiting for your senior. Your chat is locked until {who} replies.",
    )


def get_chat_lock(settings, request_id: str) -> ChatLock:
    with open_db(settings.db_path) as conn:
        ensure_rulebook_tables(conn)
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        return chat_lock_for(conn, request_id)


# --- escalations opened before this phase (10-32) ---


def route_pre_phase_10(settings, now: datetime | None = None) -> int:
    """Make a row for every ESCALATION_REQUIRED request that has none at all. Returns how many.
    Called when the inbox loads. The status before comes from the audit trail."""
    now = now or datetime.now(UTC)
    made = 0
    with _write(settings.db_path) as conn:
        found = conn.execute(
            "SELECT request_id FROM da_requests WHERE status = ?", (STATUS_ESCALATION,)
        ).fetchall()
        for item in found:
            request_id = item["request_id"]
            if read_escalations(conn, request_id):
                continue
            _route_old(conn, request_id, now)
            made += 1
    return made


def _route_old(conn: sqlite3.Connection, request_id: str, now: datetime) -> None:
    route = route_request(conn, request_id)
    approach = read_approach_state(conn, request_id)
    open_item = approach.open_item if approach and approach.open_item else "Get help"
    row = EscalationRow(
        request_id=request_id, triggers=["get_help"], reasons=[open_item], open_item=open_item,
        from_status=_status_before(conn, request_id), capability=route.capability,
        other_capabilities=route.other_capabilities, senior_label=route.senior_label,
        backup_label=route.backup_label,
    )  # fmt: skip
    saved = insert_escalation(conn, row, now)
    _audit(conn, saved, "escalation_routed", "system", {"senior": saved.senior_label}, now)


def _status_before(conn: sqlite3.Connection, request_id: str) -> str:
    found = conn.execute(
        "SELECT details FROM da_audit_events WHERE request_id = ? AND event_type = 'status_changed'"
        " ORDER BY event_id DESC",
        (request_id,),
    ).fetchall()
    for item in found:
        details = json.loads(item["details"])
        if details.get("to") == STATUS_ESCALATION:
            return str(details.get("from", ""))
    return ""


# --- helpers ---


def _return(conn, row: EscalationRow, target: str, senior_id: str, now: datetime) -> None:
    old = STATUS_ESCALATION
    update_request(conn, row.request_id, now=now, status=target)
    _audit(conn, row, "status_changed", senior_id, {"from": old, "to": target}, now)
    restore_flow_steps(conn, row.request_id, target, now)
    # The senior has looked, so trigger 1 needs two more NOT_PASSING in a row (section 10).
    add_build_result(conn, row.request_id, False, now)


def _open_row(conn, escalation_id: int, base_revision: int) -> EscalationRow:
    row = read_escalation(conn, escalation_id)
    if row is None:
        raise SeniorActionError("There is no such escalation.")
    if row.outcome != "open":
        raise SeniorActionError(CLOSED_MESSAGE)
    if row.revision != base_revision:
        raise StaleRevisionError(STALE_MESSAGE)
    return row


def _build_number(conn, request_id: str) -> int:
    state = read_build_state(conn, request_id)
    return state.build_number if state else 0


def _open_finding(review, finding_id: str, actions):
    for item in review.findings:
        if item.finding_id == finding_id and item.kept and item.severity != "fyi":
            held = tester.finding_state(finding_id, review.review_number, actions)[0]
            if held in ("accepted", "overruled"):
                raise SeniorActionError(f"{finding_id} is already {held}.")
            return item
    raise SeniorActionError(f"There is no open Must fix or Should fix {finding_id} to overrule.")


def _label(review, actions) -> str:
    return tester.compute_label(
        review.findings, list(review.zone_warnings), review.result, review.review_number, actions
    )


def _audit(conn, row: EscalationRow, event: str, who: str, details: dict, now: datetime) -> None:
    if who == "system":
        insert_audit_event(conn, row.request_id, "system", event, details, now)
    else:  # the senior's ID goes into the details, as the actor is only the word "senior"
        insert_audit_event(conn, row.request_id, "senior", event, {"senior": who, **details}, now)


def _say(conn, row: EscalationRow, senior_id: str, text: str, now: datetime) -> None:
    add_message(conn, row.request_id, "assistant", f"{SENIOR_PREFIX}{senior_id}: {text}", now)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return found is not None


@contextmanager
def _write(db_path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Tables first: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_audit_table(conn)
        ensure_understand_tables(conn)
        ensure_build_tables(conn)  # the tester, refine, enhance, handoff and escalation tables
        begin_write(conn)
        yield conn
