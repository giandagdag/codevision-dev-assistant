"""Fix G9 F5: rule conflicts and gaps at the v2 checkpoint, with the same five buttons as
Understand. The check result sits on the Refine state next to the proposed record; a button
changes the proposed record (or asks a senior), then the check runs again.

AS400 picture: the same function keys as the order-entry screen, now on the change screen.
"""

from datetime import UTC, datetime

from agents import da_understand_rules as rules
from agents.da_escalation_flow import escalate as open_escalation
from agents.da_escalation_flow import request_triggers
from agents.da_escalation_triggers import rule_exception
from agents.da_llm_client import LLMClient
from agents.da_refine_lanes import (
    STEP_REQ_CHECKPOINT,
    RefineTx,
    _load_state,
    _require_request,
    _require_step,
    _save,
    _write,
    check_record,
)
from agents.da_understand_checks import developer_message_problem
from agents.da_understand_flow import EXCEPTION_OFF_MESSAGE
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_escalation import read_open_escalation, update_escalation
from db_table_functions.db_tbl_da_refine import RefineError
from pydantic_classes.da_escalation_models import ExceptionAsk
from pydantic_classes.da_models import STATUS_ESCALATION, STATUS_REVISION
from pydantic_classes.da_refine_models import RefineState
from pydantic_classes.da_request_record_models import LIST_LENGTH_LIMIT

KEY_PREFIX = "rc:"  # then the action and the number, for example "rc:use:1"
ACTIONS = {
    "use": rules.USE_WORDING_PREFIX,
    "change": rules.CHANGE_MYSELF_PREFIX,
    "ask": rules.ASK_EXCEPTION_PREFIX,
    "add": rules.ADD_CRITERION_PREFIX,
    "no": rules.NOT_NEEDED_PREFIX,
}
AGAIN_KEY = f"{KEY_PREFIX}again"


def open_items(state: RefineState) -> tuple[list, list]:
    """(conflicts, gaps) still open: a conflict a senior allowed (RX-n) is not one any more."""
    if state.pending_record is None:
        return [], []
    conflicts = rules.without_excepted(state.pending_record, state.check_conflicts)
    return conflicts, list(state.check_gaps)


def rule_buttons(state: RefineState) -> list[tuple[str, str]]:
    """(key, label) per open item, numbered like the Understand screen: gaps after conflicts."""
    conflicts, gaps = open_items(state)
    out: list[tuple[str, str]] = []

    def add(action: str, number: int) -> None:
        out.append((f"{KEY_PREFIX}{action}:{number}", f"{ACTIONS[action]}{number}"))

    for number, conflict in enumerate(conflicts, 1):
        if conflict.fix.strip():
            add("use", number)
        add("change", number)
        add("ask", number)
    for number, gap in enumerate(gaps, len(conflicts) + 1):
        if gap.suggested_criterion.strip():
            add("add", number)
        add("change", number)
        add("no", number)
    if state.check_failed:
        out.append((AGAIN_KEY, rules.TRY_AGAIN_OPTION))
    return out


def rule_note(state: RefineState) -> str:
    """The items in words for the note above the buttons ("" when nothing is open)."""
    conflicts, gaps = open_items(state)
    lines = rules.conflict_lines(conflicts) + rules.gap_lines(gaps)
    if state.check_failed:
        lines.append(rules.COULD_NOT_RUN)
    return "\n".join(lines)


def perform_rule_button(
    settings,
    request_id: str,
    base_revision: int,
    key: str,
    text: str = "",
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> None:
    """One of the five buttons (or Try again) at the v2 checkpoint."""
    now = now or datetime.now(UTC)
    action, _, number = key.removeprefix(KEY_PREFIX).partition(":")
    with open_db(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_REQ_CHECKPOINT)
    record = state.pending_record
    if record is None:
        raise RefineError("There is no proposed change.")
    if action == "ask":
        return _ask_exception(settings, request_id, base_revision, state, number, text, now)
    label = f"{ACTIONS.get(action, '')}{number}".strip() if number else rules.TRY_AGAIN_OPTION
    audit: tuple[str, dict] | None = None
    conflicts, gaps = open_items(state)
    if action == "change":
        _say_only(settings, request_id, base_revision, label, rules.CHANGE_MYSELF_MESSAGE, now)
        return
    if action == "use":
        conflict = _pick(conflicts, number, 0)
        record, field = rules.with_wording(record, conflict)
        audit = ("wording_used", {"criterion": conflict.criterion, "field": field})
    elif action == "add":
        gap = _pick(gaps, number, len(conflicts))
        record = _or_refused(lambda: rules.with_gap_criterion(record, gap))
        audit = ("gap_criterion_added", {"case": gap.case})
    elif action == "no":
        gap = _pick(gaps, number, len(conflicts))
        reason = _reason(text, rules.NOT_NEEDED_NEEDS_REASON)
        if len(record.out_of_scope) >= LIST_LENGTH_LIMIT:
            raise RefineError(rules.NO_ROOM_MESSAGE)
        line = rules.not_needed_line(gap, reason)
        record = record.model_copy(update={"out_of_scope": [*record.out_of_scope, line]})
        audit = ("gap_not_needed", {"case": gap.case, "reason": reason})
    elif action != "again":
        raise RefineError("That is not one of the choices.")
    found = check_record(settings, request_id, record, client)  # no lock during the AI call
    with _write(settings.db_path) as conn:
        tx = _tx(conn, request_id, base_revision, now)
        tx.say("developer", label)
        if audit:
            tx.audit("developer", *audit)
        tx.set(pending_record=record, **found)
        _save(tx, base_revision)


def _pick(items: list, number: str, skip: int):
    """The item a numbered button stands for (gaps are numbered after the conflicts)."""
    if not number.isdigit() or not 1 <= int(number) - skip <= len(items):
        raise RefineError("That is not one of the choices.")
    return items[int(number) - skip - 1]


def _or_refused(make):
    try:
        return make()
    except ValueError as error:
        raise RefineError(str(error)) from error


def _reason(text: str, needs_reason: str) -> str:
    reason = " ".join((text or "").split())
    if len(reason) < rules.EXCEPTION_MIN_CHARS:
        raise RefineError(needs_reason)
    problem = developer_message_problem(reason)
    if problem:
        raise RefineError(problem)
    return reason[:500]


def _tx(conn, request_id: str, base_revision: int, now: datetime) -> RefineTx:
    request = _require_request(conn, request_id)
    return RefineTx(conn, request, _load_state(conn, request_id, base_revision), now)


def _say_only(settings, request_id: str, base_revision: int, said: str, answer: str, now) -> None:
    with _write(settings.db_path) as conn:
        tx = _tx(conn, request_id, base_revision, now)
        tx.say("developer", said)
        tx.say("assistant", answer)
        _save(tx, base_revision)


def _ask_exception(settings, request_id, base_revision, state, number, text, now) -> None:
    """Ask the capability's senior to allow one conflict. Approve writes RX-n into the proposed
    record (da_rule_exception_actions); the request waits in ESCALATION_REQUIRED meanwhile."""
    conflicts, _gaps = open_items(state)
    conflict = _pick(conflicts, number, 0)
    reason = _reason(text, rules.EXCEPTION_NEEDS_REASON)
    line = f"{conflict.criterion} may break {conflict.rule}: {reason}"
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        if request.status != STATUS_REVISION:
            raise RefineError("An exception can only be asked while the change is open.")
        tx = _tx(conn, request_id, base_revision, now)
        decision = rule_exception(request_triggers(conn, request_id), line)
        tx.say("developer", f"{rules.ASK_EXCEPTION_PREFIX}{number}: {reason}")
        result = open_escalation(conn, request_id, decision, now, line)
        if result.opened or result.reason_added:
            row = read_open_escalation(conn, request_id)
            ask = ExceptionAsk(criterion=conflict.criterion, rule=conflict.rule, reason=reason)
            asks = [*row.exception_asks, ask]
            changed = row.model_copy(update={"exception_asks": asks})
            update_escalation(conn, changed, row.revision, now)
            details = {"rule": conflict.rule, "for": conflict.criterion}
            tx.audit("developer", "rule_exception_asked", details)
        if result.opened:
            tx.move_to(STATUS_ESCALATION)
            tx.say("assistant", "A senior developer will look at your exception request.")
        elif decision.switched_off:
            tx.say("assistant", EXCEPTION_OFF_MESSAGE)
        _save(tx, base_revision)
