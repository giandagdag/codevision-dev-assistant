"""The approach lane of Refine (Phase 8 spec section 6).

Two actions:
1. `start_approach_change`: his feedback goes to the Phase 4 `change` call with the current
   approach. A good reply is saved as a new approach version with source `refine` (the Phase 4
   change count G9 is not touched; the Refine cap counts it instead). If the reply says a
   criterion would have to change, plain code refuses it and points to the requirement lane.
2. `switch_to_requirement`: after that refusal, the same Refine continues as a requirement lane.

From the new version the Phase 4 steps run as they are (Accept approach, test plan, Accept test
plan). The two places that behave differently use `da_refine_hooks`: the Tester is skipped when
the design decisions did not change, and accepting the test plan closes the Refine.

AS400 picture: a change to the program spec (which members, which design) that leaves the
business request alone. If the change touches the request itself, it goes back to the request desk.
"""

from datetime import UTC, datetime

from agents.da_approach_checks import CHANGE
from agents.da_approach_flow import (
    APPROACH_DIVIDER,
    _ask_text,
    _context,
    _failure_text,
    _generate,
    _new_version,
    _proposal_text,
    _snapshot,
    _Turn,
    _write_transaction,
)
from agents.da_llm_client import LLMClient
from agents.da_refine_hooks import STEP_APPROACH_PLAN
from agents.da_refine_lanes import (
    STEP_APPROACH,
    STEP_APPROACH_REFUSED,
    STEP_REQ_REVISE,
    RefineTx,
    _load_state,
    _require_step,
)
from agents.da_refine_revision import _approach_revision, _check_step
from db_table_functions.db_tbl_da_approach import (
    insert_approach_version,
    save_approach_state,
)
from db_table_functions.db_tbl_da_refine import RefineError, save_refine_state
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request, read_request
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE, StaleRevisionError
from pydantic_classes.da_models import STATUS_APPROACH_PROPOSED
from pydantic_classes.da_refine_models import RefineState

SWITCH_LABEL = "Switch to requirement change"
REFUSED_LINE = (
    "This changes the requirement. Use the requirement lane. "
    f"Press {SWITCH_LABEL}, or Cancel."
)


def start_approach_change(
    settings,
    request_id: str,
    base_revision: int,
    generator: LLMClient | None = None,
    now: datetime | None = None,
) -> RefineState:
    """One Generator call, then a new approach version with source `refine`. A failed call or a
    refused reply saves nothing but a chat line; the lane stays where it was."""
    now = now or datetime.now(UTC)
    refine = _check_step(settings, request_id, base_revision, STEP_APPROACH, STEP_APPROACH_REFUSED)
    approach_revision = _approach_revision(settings, request_id)
    snap = _snapshot(settings, request_id, approach_revision)
    if snap.state is None or snap.approach is None:
        raise RefineError("There is no approach to change.")
    pinned = get_rulebook_for_request(settings.db_path, request_id)
    context = _context(
        pinned, snap, decisions=snap.state.decisions, change_text=refine.pending_feedback
    )
    result = _generate(settings, CHANGE, context, generator)
    with _write_transaction(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_APPROACH, STEP_APPROACH_REFUSED)
        tx = RefineTx(conn, read_request(conn, request_id), state, now)
        if not result.ok:
            details = {"problems": result.problems[:5], "lane": "approach"}
            tx.audit("system", "approach_failed", details)
            failed = _failure_text(result, "apply your change")
            tx.say("assistant", f"{failed} Nothing was saved. Press Try again.")
            return save_refine_state(conn, tx.state, base_revision, now)
        if result.reply.changes_criteria:
            tx.audit("system", "approach_refused_criterion", {"refine": state.refine_number})
            tx.say("assistant", REFUSED_LINE)
            tx.set(step=STEP_APPROACH_REFUSED)
            return save_refine_state(conn, tx.state, base_revision, now)
        approach_state = snap.state
        if approach_state.revision != approach_revision:
            raise StaleRevisionError(STALE_MESSAGE)
        version = _new_version(
            snap, pinned, result, CHANGE, snap.approach.approach_version + 1,
            approach_state.decisions, source="refine",
        )
        insert_approach_version(conn, version, now)
        turn = _Turn(conn, tx.request, approach_state, now)
        approach_state.pending_choices = result.reply.design_choices
        approach_state.step = "choices" if approach_state.pending_choices else "review"
        approach_state.limit_reason = ""
        approach_state.open_item = ""
        turn.move_to(STATUS_APPROACH_PROPOSED)
        turn.audit(
            "llm", "approach_refined",
            {"approach_version": version.approach_version, "files": len(version.plan.files),
             "model": version.model, "refine": state.refine_number},
        )
        turn.say("system", APPROACH_DIVIDER)
        turn.say("assistant", _proposal_text(version))
        if approach_state.pending_choices:
            turn.say("assistant", _ask_text(approach_state.pending_choices[0]))
        save_approach_state(conn, approach_state, approach_revision, now)
        tx.set(step=STEP_APPROACH_PLAN)
        return save_refine_state(conn, tx.state, base_revision, now)


def switch_to_requirement(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Switch to requirement change: the same Refine goes on as a requirement lane, with his
    feedback as it was. It is not a new Refine, so the cap is not used again."""
    now = now or datetime.now(UTC)
    with _write_transaction(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_APPROACH_REFUSED)
        tx = RefineTx(conn, read_request(conn, request_id), state, now)
        tx.say("developer", SWITCH_LABEL)
        tx.audit(
            "developer", "lane_switched",
            {"refine": state.refine_number, "from": "approach", "to": "requirement"},
        )
        tx.set(step=STEP_REQ_REVISE, chosen_lane="requirement")
        return save_refine_state(conn, tx.state, base_revision, now)
