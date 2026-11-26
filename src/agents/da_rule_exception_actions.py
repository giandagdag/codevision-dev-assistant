"""Fix G9 U6: what a senior does with a "rule exception" escalation: Approve or Reject.

Approve writes one `RX-n` line per ask into the request's record and returns the request to its
step. Reject returns it with the conflict still open. Plain code, no AI. AS400 picture: the
operator signs a waiver on the message and releases the job back to its owner.
"""

from datetime import UTC, datetime

from agents.da_escalation_return import restore_flow_steps, return_status_for
from agents.da_senior_actions import (
    NOTE_MAX_CHARS,
    SeniorActionError,
    _audit,
    _open_row,
    _say,
    _write,
)
from agents.da_understand_rules import exception_line
from db_table_functions.db_tbl_da_escalation import update_escalation
from db_table_functions.db_tbl_da_requests import update_request
from db_table_functions.db_tbl_da_understand import read_session, save_session
from pydantic_classes.da_escalation_models import EscalationRow
from pydantic_classes.da_models import STATUS_ESCALATION

APPROVE_LABEL = "Approve exception"
REJECT_LABEL = "Reject exception"
NOT_AN_EXCEPTION = "This escalation is not an exception request."
NOTE_MESSAGE = f"Please write a note of 1 to {NOTE_MAX_CHARS} characters."


def approve_exception(
    settings, escalation_id: int, base_revision: int, senior_id: str, note: str,
    now: datetime | None = None,
) -> None:  # fmt: skip
    """Record `RX-n` for every ask on the row, then close the row as returned."""
    _decide(settings, escalation_id, base_revision, senior_id, note, True, now)


def reject_exception(
    settings, escalation_id: int, base_revision: int, senior_id: str, note: str,
    now: datetime | None = None,
) -> None:  # fmt: skip
    """Return the request; the conflicts stay open for the developer."""
    _decide(settings, escalation_id, base_revision, senior_id, note, False, now)


def _decide(settings, escalation_id, base_revision, senior_id, note, approve, now) -> None:
    clean = " ".join((note or "").split())
    if not 1 <= len(clean) <= NOTE_MAX_CHARS:
        raise SeniorActionError(NOTE_MESSAGE)
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        row = _open_row(conn, escalation_id, base_revision)
        if not row.exception_asks:
            raise SeniorActionError(NOT_AN_EXCEPTION)
        verdict = "approved" if approve else "rejected"
        if approve:
            _write_exceptions(conn, row, senior_id, now)
        closed = row.model_copy(
            update={"outcome": "returned", "close_note": clean, "closed_by": senior_id}
        )
        update_escalation(conn, closed, base_revision, now)
        target, _note = return_status_for(conn, row)
        update_request(conn, row.request_id, now=now, status=target)
        moved = {"from": STATUS_ESCALATION, "to": target}
        _audit(conn, row, "status_changed", senior_id, moved, now)
        restore_flow_steps(conn, row.request_id, target, now)
        asked = ", ".join(f"{a.rule} for {a.criterion}" for a in row.exception_asks)
        _audit(conn, row, "rule_exception", senior_id, {"verdict": verdict, "asked": asked}, now)
        _say(conn, row, senior_id, f"Exception {verdict} ({asked}): {clean}", now)


def _write_exceptions(conn, row: EscalationRow, senior_id: str, now: datetime) -> None:
    session = read_session(conn, row.request_id)
    if session is None:
        raise SeniorActionError("There is no request record to write the exception into.")
    record = session.record
    for ask in row.exception_asks:
        line = exception_line(record, ask.rule, ask.criterion, senior_id, ask.reason)
        record = record.model_copy(update={"exceptions": [*record.exceptions, line]})
    session.record = record
    session.step = "checkpoint"  # Proceed again: the gate re-checks all
    save_session(conn, session, session.revision, now)
