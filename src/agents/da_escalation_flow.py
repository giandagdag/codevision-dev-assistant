"""The ONE shared escalate helper (Phase 10 spec sections 7 and 8, step 7).

Every Get help button, Dispute and the automatic triggers go through here, inside the caller's
write transaction. The helper writes the escalation row, the audit line and one chat line. It does
NOT move the request's status or touch the flow state: each flow keeps doing that itself (it knows
its own steps). A caller reads `result.opened` and `result.switched_off` to decide what to do.

AS400 picture: the one program every job calls to put a message on the help-desk message queue.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from agents.da_escalation_routing import route_for
from agents.da_escalation_triggers import (
    DISPUTE_OFF_MESSAGE,
    GET_HELP_OFF_MESSAGE,
    add_reason,
    status_blocks_triggers,
)
from db_table_functions.db_tbl_da_audit import insert_audit_event
from db_table_functions.db_tbl_da_escalation import (
    ensure_escalation_table_in_transaction,
    insert_escalation,
    read_open_escalation,
    update_escalation,
)
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_rulebook import active_version_on, version_on
from db_table_functions.db_tbl_da_understand import add_message
from pydantic_classes.da_escalation_models import UNASSIGNED, EscalationRow, Route, TriggerDecision
from pydantic_classes.da_models import STATUS_HANDED_OFF
from pydantic_classes.da_rulebook_models import EscalationTrigger

OFF_MESSAGES = {"get_help": GET_HELP_OFF_MESSAGE, "dispute": DISPUTE_OFF_MESSAGE}
AUTOMATIC_LINES = {
    "cap_hit_twice": "Two builds in a row did not pass.",
    "out_of_scope": "This looks outside what this tool may change.",
    "tester_unable_twice": "The Tester could not assess this request twice.",
}


@dataclass
class EscalationResult:
    """`opened`: a new row was written. `reason_added`: an open row got one more reason.
    `switched_off`: the trigger's switch is off, nothing was written but the audit line and chat."""

    opened: bool = False
    reason_added: bool = False
    switched_off: bool = False
    row: EscalationRow | None = None


def request_triggers(conn: sqlite3.Connection, request_id: str) -> list[EscalationTrigger]:
    """The switches of the rulebook version this request is PINNED to (read on the caller's
    connection, so no second lock is needed)."""
    request = read_request(conn, request_id)
    version = version_on(conn, request.rulebook_version) if request else None
    return version.rulebook.policy.escalation_triggers if version else []


def escalate(
    conn: sqlite3.Connection,
    request_id: str,
    decision: TriggerDecision,
    now: datetime,
    open_item: str = "",
) -> EscalationResult:
    """Act on one trigger decision. Rules: X1 (one open row, extra reasons are added), X4 (nothing
    fires at HANDED_OFF or at ESCALATION_REQUIRED with no open row), D-I (a switched-off trigger
    only audits and tells the developer)."""
    request = read_request(conn, request_id)
    if request is None or request.status == STATUS_HANDED_OFF:
        return EscalationResult()
    ensure_escalation_table_in_transaction(conn)
    if decision.switched_off:
        return _switched_off(conn, request_id, decision, now)
    if not decision.fire:
        return EscalationResult()
    open_row = read_open_escalation(conn, request_id)
    if open_row is not None:
        return _add_reason(conn, open_row, decision, now)
    if status_blocks_triggers(request.status):
        return EscalationResult()
    row = _new_row(conn, request_id, request.status, decision, open_item, now)
    saved = insert_escalation(conn, row, now)
    insert_audit_event(
        conn, request_id, "system", "escalation_opened",
        {
            "trigger": decision.trigger,
            "senior": saved.senior_label,
            "from_status": saved.from_status,
            "reason": decision.reason,
        },
        now,
    )  # fmt: skip
    add_message(conn, request_id, "assistant", _senior_line(decision.trigger, saved), now)
    return EscalationResult(opened=True, row=saved)


def _switched_off(conn, request_id: str, decision: TriggerDecision, now: datetime):
    insert_audit_event(
        conn, request_id, "system", "escalation_switched_off",
        {"trigger": decision.trigger, "reason": decision.reason}, now,
    )  # fmt: skip
    line = OFF_MESSAGES.get(decision.trigger)
    if line:  # the automatic triggers stay silent: the developer pressed nothing
        add_message(conn, request_id, "assistant", line, now)
    return EscalationResult(switched_off=True)


def _add_reason(conn, open_row: EscalationRow, decision: TriggerDecision, now: datetime):
    changed = add_reason(open_row, decision.trigger, decision.reason)
    saved = update_escalation(conn, changed, open_row.revision, now)
    insert_audit_event(
        conn, open_row.request_id, "system", "escalation_reason_added",
        {"trigger": decision.trigger, "reason": decision.reason}, now,
    )  # fmt: skip
    return EscalationResult(reason_added=True, row=saved)


def _new_row(conn, request_id, from_status, decision, open_item, now) -> EscalationRow:
    route = route_request(conn, request_id)
    return EscalationRow(
        request_id=request_id,
        triggers=[decision.trigger],
        reasons=[decision.reason],
        open_item=open_item or decision.reason,
        from_status=from_status,
        capability=route.capability,
        other_capabilities=route.other_capabilities,
        senior_label=route.senior_label,
        backup_label=route.backup_label,
        fired_count=decision.count,
    )


def route_request(conn: sqlite3.Connection, request_id: str) -> Route:
    """Section 8: capability from the confirmed target (enhancement) or the planned files, then the
    senior from the ACTIVE rulebook (a senior who left should not keep getting escalations)."""
    active = active_version_on(conn)
    if active is None:
        return Route()
    capabilities = active.rulebook.policy.capabilities
    return route_for(capabilities, _target_capability(conn, request_id), _planned(conn, request_id))


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return found is not None


def _target_capability(conn: sqlite3.Connection, request_id: str) -> str:
    if not _has_table(conn, "da_enhance_state"):
        return ""
    from db_table_functions.db_tbl_da_enhance import read_enhance_state

    state = read_enhance_state(conn, request_id)
    if state is None or not state.targets:
        return ""
    return state.targets[0].capability


def _planned(conn: sqlite3.Connection, request_id: str) -> list[str]:
    if not _has_table(conn, "da_approach_versions"):
        return []
    from agents.da_handoff_facts import _accepted_approach

    approach = _accepted_approach(conn, request_id)
    return [item.path for item in approach.plan.files] if approach else []


def _senior_line(trigger: str, row: EscalationRow) -> str:
    who = "nobody is named yet" if row.senior_label == UNASSIGNED else row.senior_label
    asked = f"Your senior ({who}) has been asked to look at this request."
    lead = AUTOMATIC_LINES.get(trigger, "")
    return f"{lead} {asked}".strip()
