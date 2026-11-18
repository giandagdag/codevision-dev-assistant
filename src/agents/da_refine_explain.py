"""Explain simply and Help me decide at lane choice (B2 S3, fix batch B2).

AS400 picture: two help keys on the lane screen. Each makes one AI call and prints one message line
(or marks one button); he still presses the lane key himself. A failed call says so and changes
nothing.
"""

from datetime import UTC, datetime

from agents.da_llm_client import LLMClient
from agents.da_refine_agent import LANE_ROLE, explain_lanes, suggest_lane
from agents.da_refine_lanes import (
    LANE_LABELS,
    PICK_LINE,
    STEP_LANE_CHOICE,
    RefineTx,
    _call,
    _load_state,
    _read_context,
    _require_idle_or_choosing,
    _require_request,
    _save,
    _write,
    get_refine_state,
)
from db_table_functions.db_tbl_da_refine import RefineError
from pydantic_classes.da_refine_models import LaneSuggestion, RefineState

EXPLAIN_LABEL = "Explain simply"
DECIDE_LABEL = "Help me decide"
EXPLAIN_FAILED = "The AI could not explain this right now. Nothing was changed. Try again."
DECIDE_FAILED = "The AI could not recommend a lane right now. Nothing was changed. Try again."


def explain_simply(
    settings,
    request_id: str,
    base_revision: int,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> RefineState:
    """One AI call: the three choices in plain words, shown in the chat. Nothing else changes."""
    feedback, context = _prepare(settings, request_id, base_revision)
    result, _ = _call(
        settings, LANE_ROLE, client, lambda c: explain_lanes(c, context, feedback, LANE_LABELS)
    )
    if result is None or result.value is None:
        raise RefineError(EXPLAIN_FAILED)
    return _finish(settings, request_id, base_revision, now, "explain_simple", result.value, None)


def help_decide(
    settings,
    request_id: str,
    base_revision: int,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> RefineState:
    """One AI call: recommend one lane with a reason. The button gets a Suggested tag; no lane
    starts, he still clicks."""
    feedback, context = _prepare(settings, request_id, base_revision)
    result, _ = _call(settings, LANE_ROLE, client, lambda c: suggest_lane(c, context, feedback))
    suggestion: LaneSuggestion | None = result.value if result is not None else None
    if suggestion is None:
        raise RefineError(DECIDE_FAILED)
    return _finish(
        settings, request_id, base_revision, now, "lane_decide_help",
        f"{suggestion.reason} {PICK_LINE}", suggestion,
    )


def _prepare(settings, request_id: str, base_revision: int):
    """The words he typed, and what the AI may see. Refused unless the lane choice is on screen."""
    state = get_refine_state(settings, request_id)
    if state is None or state.step != STEP_LANE_CHOICE:
        raise RefineError("Type your feedback and press Refine first.")
    context, _ = _read_context(settings, request_id, base_revision, new_refine=False)
    return state.pending_feedback, context


def _finish(settings, request_id, base_revision, now, event, line, suggestion):
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_idle_or_choosing(conn, request, state)
        if state.step != STEP_LANE_CHOICE:
            raise RefineError("Type your feedback and press Refine first.")
        tx = RefineTx(conn, request, state, now)
        tx.say("assistant", line)
        details = {"lane": suggestion.lane} if suggestion else {}
        tx.audit("developer", event, details)
        if suggestion:
            tx.set(
                suggested_lane=suggestion.lane,
                suggested_reason=suggestion.reason,
                suggested_criterion=suggestion.criterion_id or "",
                lane_unusable=False,
            )
        return _save(tx, base_revision)
