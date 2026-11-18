"""B2 S7f: a senior returns a request at the decision limit and gives it 1 to 5 more decision
rounds, for that request only. Plain code, no AI. AS400 picture: the help desk raises the job's
own limit and puts it back on its queue; the library defaults are not touched."""

from datetime import UTC, datetime

from agents.da_inbox import get_inbox_row
from agents.da_senior_actions import (
    NOTE_MAX_CHARS,
    SeniorActionError,
    _audit,
    _open_row,
    _write,
    close_escalation,
)
from agents.da_understand_flow import SENIOR_PREFIX
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from db_table_functions.db_tbl_da_rulebook import RulebookError
from db_table_functions.db_tbl_da_understand import read_session, save_session
from pydantic_classes.da_rulebook_models import DEFAULT_MAX_MATERIAL_DECISIONS

MIN_ROUNDS, MAX_ROUNDS = 1, 5
NOT_AT_LIMIT_MESSAGE = "This request is not waiting at the decision limit."
ROUNDS_MESSAGE =f"Choose {MIN_ROUNDS} to {MAX_ROUNDS} more decision rounds."


def reopen_decisions(
    settings, escalation_id: int, base_revision: int, senior_id: str, rounds: int, note: str,
    now: datetime | None = None,
) -> None:  # fmt: skip
    """Raise this request's decision limit by `rounds`, put the waiting decisions back so the next
    one is really asked, then close the row as `returned`. The session is saved first, so a
    failure never leaves a returned request that is stuck."""
    if not MIN_ROUNDS <= rounds <= MAX_ROUNDS:
        raise SeniorActionError(ROUNDS_MESSAGE)
    if not 1 <= len(" ".join((note or "").split())) <= NOTE_MAX_CHARS:
        raise SeniorActionError(f"Please write a note of 1 to {NOTE_MAX_CHARS} characters.")
    now = now or datetime.now(UTC)
    found = get_inbox_row(settings, escalation_id)
    if found is None:
        raise SeniorActionError("There is no such escalation.")
    limit = _policy_limit(settings, found.request_id)  # read before the write lock opens
    with _write(settings.db_path) as conn:
        row = _open_row(conn, escalation_id, base_revision)
        session = read_session(conn, row.request_id)
        if session is None:
            raise SeniorActionError("This request has no Understand step to reopen.")
        if session.step != "senior" or not session.needs_senior:
            raise SeniorActionError(NOT_AT_LIMIT_MESSAGE)  # only a request waiting at the limit
        session.extra_decision_rounds += rounds
        room = limit + session.extra_decision_rounds - session.material_decisions_asked
        back = session.aside_decisions[: max(room, 0)]
        session.aside_decisions = session.aside_decisions[len(back) :]
        asked = {SENIOR_PREFIX + item.question for item in back}
        session.record = session.record.model_copy(
            update={"open_items": [i for i in session.record.open_items if i not in asked]}
        )
        session.pending_decisions = [*session.pending_decisions, *back]
        session.material_decisions_asked += len(back)
        session.decisions_announced = 0
        session.needs_senior = bool(session.aside_decisions)
        session.step = _step_after(session)
        save_session(conn, session, session.revision, now)
        _audit(
            conn, row, "decision_limit_raised", senior_id,
            {"rounds": rounds, "extra_total": session.extra_decision_rounds,
             "restored": len(back)}, now,
        )  # fmt: skip
    close_escalation(settings, escalation_id, base_revision, senior_id, "returned", note, now)


def _step_after(session) -> str:
    if session.pending_decisions:
        return "decision"
    return "senior" if session.needs_senior else "correction"


def _policy_limit(settings, request_id: str) -> int:
    try:
        pinned = get_rulebook_for_request(settings.db_path, request_id)
    except RulebookError:
        return DEFAULT_MAX_MATERIAL_DECISIONS
    return pinned.rulebook.policy.max_material_decisions
