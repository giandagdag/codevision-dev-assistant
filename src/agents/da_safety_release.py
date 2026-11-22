"""Fix G5 P4 (Admin side): see the requests the safety check stopped, and Release or Keep stopped.

AS400 picture: a job held in a queue. Only an operator (Admin) may release it. Release moves the
request back to the status and step it had before the stop, and writes `safety_released`, so the
safety check does not stop the same request again. Every decision is audited twice: on the
request, and in the Admin audit log.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from agents.da_admin_audit import add_admin_event
from agents.da_safety_check import EVENT_RELEASED, EVENT_STOP
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_audit import (
    ensure_audit_table,
    insert_audit_event,
    list_audit_events,
)
from db_table_functions.db_tbl_da_requests import list_requests, read_request, update_request
from db_table_functions.db_tbl_da_understand import (
    ensure_understand_tables,
    list_messages,
    read_session,
    save_session,
)
from pydantic_classes.da_models import STATUS_STOPPED

EVENT_KEPT = "safety_kept"
TITLE = "Request stopped by the safety check"
NOTE_NEEDED = "Write a note first: say why you release this request."
NOT_STOPPED = "This request is not stopped (someone else may have released it)."
ADMIN_RELEASED = "safety_released"
ADMIN_KEPT = "safety_kept"


class ReleaseError(Exception):
    """The release was refused; the message is plain words for the Admin."""


@dataclass(frozen=True)
class StoppedRequest:
    request_id: str
    text: str  # what the developer typed
    reason: str  # the AI's one line, or the words the word check found
    stopped_at: datetime


def list_stopped(settings) -> list[StoppedRequest]:
    """Every request that is STOPPED now, oldest first. Read only."""
    rows = []
    for request in list_requests(settings.db_path):
        if request.status != STATUS_STOPPED:
            continue
        event = _last_event(settings, request.request_id, EVENT_STOP)
        details = event.details if event else {}
        said = [m.text for m in list_messages(settings.db_path, request.request_id)
                if m.speaker == "developer"]
        reason = details.get("ai_reason") or ", ".join(details.get("words", []))
        stamp = event.timestamp if event else request.updated_at
        rows.append(StoppedRequest(request.request_id, said[-1] if said else "", reason, stamp))
    return rows


def _last_event(settings, request_id: str, kind: str):
    found = [e for e in list_audit_events(settings.db_path, request_id) if e.event_type == kind]
    return found[-1] if found else None


def release(settings, request_id: str, admin: str, note: str, now: datetime | None = None) -> None:
    """Move a STOPPED request back to where it was. A note is required."""
    note = (note or "").strip()
    if not note:
        raise ReleaseError(NOTE_NEEDED)
    now = now or datetime.now(UTC)
    stop = _last_event(settings, request_id, EVENT_STOP)
    with open_db(settings.db_path) as conn:
        # Set up tables before the lock: setting up a table ends any open transaction.
        ensure_understand_tables(conn)
        ensure_audit_table(conn)
        begin_write(conn)
        request = read_request(conn, request_id)
        session = read_session(conn, request_id)
        if request is None or session is None or request.status != STATUS_STOPPED or stop is None:
            raise ReleaseError(NOT_STOPPED)
        back = stop.details["previous_status"]
        update_request(conn, request_id, now=now, status=back)
        insert_audit_event(
            conn, request_id, "system", "status_changed",
            {"from": STATUS_STOPPED, "to": back}, now,
        )
        insert_audit_event(
            conn, request_id, "system", EVENT_RELEASED, {"admin": admin, "note": note}, now
        )
        session.step = stop.details["previous_step"]
        save_session(conn, session, session.revision, now)
    add_admin_event(ADMIN_RELEASED, admin, f"Released {request_id}: {note}", now=now)


def keep_stopped(
    settings, request_id: str, admin: str, note: str = "", now: datetime | None = None
) -> None:
    """Admin looked and leaves it stopped. Only audit lines are written."""
    now = now or datetime.now(UTC)
    note = (note or "").strip()
    with open_db(settings.db_path) as conn:
        ensure_audit_table(conn)
        details = {"admin": admin, "note": note}
        insert_audit_event(conn, request_id, "system", EVENT_KEPT, details, now)
    add_admin_event(ADMIN_KEPT, admin, f"Kept {request_id} stopped. {note}".strip(), now=now)
