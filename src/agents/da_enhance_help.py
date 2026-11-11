"""Get help at a Phase 9 step (spec section 2, test 9-45).

Same idea as Get help in Refine: the request goes to ESCALATION_REQUIRED with a named open item,
`Escalated in Enhance: <step>`. AS400 picture: a message to the help desk queue with the job step
written on it. The inbox itself comes in Phase 10.
"""

from datetime import UTC, datetime

from agents.da_approach_flow import HELP_BUTTON
from agents.da_enhance_flow import EnhanceView, _load_state, _Tx, _view, _write_transaction
from db_table_functions.db_tbl_da_enhance import EnhanceError, save_enhance_state
from db_table_functions.db_tbl_da_requests import read_request, update_request
from pydantic_classes.da_models import (
    STATUS_APPROACH_PROPOSED,
    STATUS_CLARIFICATION,
    STATUS_DECISION_REQUIRED,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_DRAFT,
    STATUS_ESCALATION,
    STATUS_READY,
    STATUS_READY_TO_BUILD,
)

ESCALATED_PREFIX = "Escalated in Enhance: "
HELP_LINE = "A senior developer will pick this up. (The escalations inbox comes in Phase 10.)"
# Where Get help is offered, and the statuses the request can have at that step. The safety net
# being written (s_writing) is left out: a run is in progress, and "Try again" appears if it stops.
# A request switched from card 1 keeps card 1's status; a re-check of main (section 5 step 8) can
# leave it at APPROACH_PROPOSED or READY_TO_BUILD.
FIND_STATUSES = (
    STATUS_DRAFT,
    STATUS_CLARIFICATION,
    STATUS_DECISION_REQUIRED,
    STATUS_READY,
    STATUS_APPROACH_PROPOSED,
    STATUS_READY_TO_BUILD,
)
HELP_STATUS = {
    "e_find": FIND_STATUSES,
    "e_pick": FIND_STATUSES,
    "e_stale": FIND_STATUSES,
    "e_fresh": FIND_STATUSES,
    "s_unable": (STATUS_DISCOVERY_CONFIRMED,),
    "s_review": (STATUS_DISCOVERY_CONFIRMED,),
}


def request_help(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> EnhanceView:
    """Get help at any Phase 9 step that offers it. A stale window is refused first."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, tuple(HELP_STATUS))
    open_item = f"{ESCALATED_PREFIX}{state.step}"
    with _write_transaction(settings.db_path) as conn:
        request = read_request(conn, request_id)
        if request is None or request.status not in HELP_STATUS[state.step]:
            raise EnhanceError("Get help is not available at this point of the request.")
        tx = _Tx(conn, request_id, now)
        tx.say("developer", HELP_BUTTON)
        tx.audit("developer", "escalated", {"step": state.step, "open_item": open_item})
        update_request(conn, request_id, now=now, status=STATUS_ESCALATION)
        tx.say("assistant", HELP_LINE)
        save_enhance_state(
            conn, state.model_copy(update={"step": "escalated", "open_item": open_item}),
            base_revision, now,
        )
    return _view(settings, request_id)
