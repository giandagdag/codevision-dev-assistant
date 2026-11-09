"""Get help inside a Refine lane (Phase 8 spec section 10, test 8-36).

Same idea as the build's Get help (rule B6): the request goes to ESCALATION_REQUIRED with a named
open item, here `Escalated in Refine: <step>`. AS400 picture: a message to the help desk queue
with the job step written on it. The inbox itself comes in Phase 10.
"""

from datetime import UTC, datetime

from agents.da_approach_flow import HELP_BUTTON
from agents.da_refine_lanes import (
    STEP_LANE_CHOICE,
    STEP_START,
    RefineTx,
    _load_state,
    _save,
    _write,
)
from db_table_functions.db_tbl_da_approach import read_approach_state, save_approach_state
from db_table_functions.db_tbl_da_refine import RefineError, close_refine
from db_table_functions.db_tbl_da_requests import read_request
from pydantic_classes.da_models import STATUS_ESCALATION, STATUS_REVISION
from pydantic_classes.da_refine_models import RefineState

ESCALATED_PREFIX = "Escalated in Refine: "
STEP_ESCALATED = "escalated"
HELP_LINE = "A senior developer will pick this up. (The escalations inbox comes in Phase 10.)"


def request_help(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Get help at any lane step. Only while a lane is open (status REVISION_IN_PROGRESS)."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = read_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        if request is None or request.status != STATUS_REVISION:
            raise RefineError("Get help in Refine is only possible while a lane is open.")
        if state.step in (STEP_START, STEP_LANE_CHOICE):
            raise RefineError("Pick a lane first, or use Cancel.")
        approach_state = read_approach_state(conn, request_id)
        if approach_state is None:
            raise RefineError("There is no approach to escalate.")
        step = state.step
        open_item = f"{ESCALATED_PREFIX}{step}"
        tx = RefineTx(conn, request, state, now)
        tx.say("developer", HELP_BUTTON)
        tx.audit(
            "developer",
            "escalated",
            {"step": step, "lane": state.chosen_lane, "open_item": open_item},
        )
        close_refine(
            conn,
            request_id,
            state.refine_number,
            result="escalated",
            record_version_after=request.version,
            approach_version_after=0,
            build_number=0,
            repro_passed_today=state.repro_passed_today,
            now=now,
        )
        approach_revision = approach_state.revision
        approach_state.step = "escalated"
        approach_state.open_item = open_item
        save_approach_state(conn, approach_state, approach_revision, now)
        tx.move_to(STATUS_ESCALATION)
        tx.say("assistant", HELP_LINE)
        tx.set(step=STEP_ESCALATED, pending_feedback="", pending_record=None, repro=None)
        return _save(tx, base_revision)
