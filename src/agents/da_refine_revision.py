"""The requirement lane after Confirm v2 (Phase 8 spec section 5, steps 6 to 9).

Three actions, each one small:
1. `run_discover`: Discover runs again by itself on the new record version.
2. `confirm_findings`: "Findings look right" (the Phase 3 confirm), then the lane goes on.
3. `start_revision_approach`: one Generator call with the accepted approach, the record diff and the
   new Discover round. Saved as a new approach version with source `revision`. The Phase 4 change
   count (G9) is not touched.

From there the Phase 4 steps run as they are (Accept approach, Tester plan, Accept test plan). The
two places that behave differently for a revision are in `da_approach_flow` and use
`da_refine_hooks`: the Tester writes cases for new and changed criteria only, and accepting the
test plan closes the Refine and sends the workspace back to its folder check.

AS400 picture: an amended change request goes through the same review desks again, in the same
order. Nothing is skipped, and the earlier signed version stays on file.
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
from agents.da_discover_flow import add_hint_and_search, confirm_discovery, start_discovery
from agents.da_llm_client import LLMClient
from agents.da_refine_hooks import (
    STEP_REQ_APPROACH,
    STEP_REQ_FINDINGS,
    STEP_REQ_PLAN,
    revision_plan_of,
)
from agents.da_refine_lanes import (
    STEP_REQ_DISCOVER,
    RefineTx,
    _load_state,
    _require_step,
)
from agents.da_search_index import SearchIndex
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import (
    ensure_approach_tables,
    insert_approach_version,
    read_approach_revision,
    save_approach_state,
)
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_discovery import ensure_discovery_tables, read_discovery_revision
from db_table_functions.db_tbl_da_refine import RefineError, save_refine_state
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request, read_request
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE, StaleRevisionError
from pydantic_classes.da_approach_models import CHANGE_LIMIT
from pydantic_classes.da_models import STATUS_APPROACH_PROPOSED, STATUS_DISCOVERY_CONFIRMED
from pydantic_classes.da_refine_models import RecordDiff, RefineState

FINDINGS_LINE = (
    "Discover ran again on the new version. Check the findings, then press Findings look right."
)


def diff_text(diff: RecordDiff) -> str:
    """The record diff in plain words, for the Generator. Short: at most CHANGE_LIMIT characters."""
    lines = [f"The request changed from version {diff.from_version} to version {diff.to_version}."]
    lines += [f"The {item.field} changed to: {item.new}" for item in diff.fields]
    for item in diff.criteria:
        text = item.new or item.old or {}
        said = " ".join(f"{k} {v}" for k, v in text.items() if k != "kind")
        lines.append(f"Criterion {item.id} is {item.change}. {said}".strip())
    return "\n".join(lines)[:CHANGE_LIMIT]


# --- 1. Discover on the new version ---


def run_discover(
    settings,
    request_id: str,
    base_revision: int,
    client: LLMClient | None = None,
    index: SearchIndex | None = None,
    now: datetime | None = None,
) -> RefineState:
    """Discover runs by itself on record v(N+1). If it fails, the lane stays at this step and the
    same action can be tried again (rule F3)."""
    now = now or datetime.now(UTC)
    _check_step(settings, request_id, base_revision, STEP_REQ_DISCOVER)
    discovery_revision = _discovery_revision(settings, request_id)
    start_discovery(settings, request_id, discovery_revision, client, index, now)
    return _move_step(
        settings, request_id, base_revision, STEP_REQ_FINDINGS, "revision_discover_done", now,
        FINDINGS_LINE,
    )


def add_findings_hint(
    settings,
    request_id: str,
    base_revision: int,
    hint: str,
    client: LLMClient | None = None,
    index: SearchIndex | None = None,
    now: datetime | None = None,
) -> RefineState:
    """✏️ Something's missing at the findings step (F4): the Phase 3 hint round, with its round cap
    (a refused round raises the Phase 3 message). The lane stays at the findings step."""
    now = now or datetime.now(UTC)
    state = _check_step(settings, request_id, base_revision, STEP_REQ_FINDINGS)
    add_hint_and_search(
        settings, request_id, hint, _discovery_revision(settings, request_id), client, index, now
    )
    return state


def confirm_findings(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Findings look right: the Phase 3 confirm. The lane then asks for the revision approach."""
    now = now or datetime.now(UTC)
    _check_step(settings, request_id, base_revision, STEP_REQ_FINDINGS)
    confirm_discovery(settings, request_id, _discovery_revision(settings, request_id), now)
    return _move_step(
        settings, request_id, base_revision, STEP_REQ_APPROACH, "revision_findings_confirmed",
        now, "",
    )


# --- 2. the revision approach ---


def start_revision_approach(
    settings,
    request_id: str,
    base_revision: int,
    generator: LLMClient | None = None,
    now: datetime | None = None,
) -> RefineState:
    """One Generator call, then a new approach version with source `revision`. A failed call saves
    nothing but a chat line, and the lane stays here ("Try again")."""
    now = now or datetime.now(UTC)
    refine = _check_step(settings, request_id, base_revision, STEP_REQ_APPROACH)
    approach_revision = _approach_revision(settings, request_id)
    snap = _snapshot(settings, request_id, approach_revision)
    not_ready = snap.state is None or snap.approach is None
    if snap.request.status != STATUS_DISCOVERY_CONFIRMED or not_ready:
        raise RefineError("The revision approach can only start after the findings are confirmed.")
    plan = revision_plan_of(settings.db_path, request_id)
    if plan is None:
        raise RefineError("There is no changed record to plan from.")
    pinned = get_rulebook_for_request(settings.db_path, request_id)
    context = _context(
        pinned, snap, decisions=snap.state.decisions, change_text=diff_text(plan.diff)
    )
    result = _generate(settings, CHANGE, context, generator)
    with _write_transaction(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_REQ_APPROACH)
        tx = RefineTx(conn, snap.request, state, now)
        if not result.ok:
            details = {"problems": result.problems[:5], "lane": "requirement"}
            tx.audit("system", "approach_failed", details)
            failed = _failure_text(result, "plan the changed request", "Press Try again.")
            tx.say("assistant", failed)
            return save_refine_state(conn, tx.state, base_revision, now)
        approach_state = snap.state
        if approach_state.revision != approach_revision:
            raise StaleRevisionError(STALE_MESSAGE)
        version = _new_version(
            snap, pinned, result, CHANGE, snap.approach.approach_version + 1,
            approach_state.decisions, source="revision",
        )
        insert_approach_version(conn, version, now)
        turn = _Turn(conn, snap.request, approach_state, now)
        approach_state.pending_choices = result.reply.design_choices
        approach_state.step = "choices" if approach_state.pending_choices else "review"
        approach_state.limit_reason = ""
        approach_state.open_item = ""
        turn.move_to(STATUS_APPROACH_PROPOSED)
        turn.audit(
            "llm", "approach_revised",
            {"approach_version": version.approach_version, "files": len(version.plan.files),
             "model": version.model, "refine": refine.refine_number},
        )
        turn.say("system", APPROACH_DIVIDER)
        turn.say("assistant", _proposal_text(version))
        if approach_state.pending_choices:
            turn.say("assistant", _ask_text(approach_state.pending_choices[0]))
        save_approach_state(conn, approach_state, approach_revision, now)
        tx.set(step=STEP_REQ_PLAN)
        return save_refine_state(conn, tx.state, base_revision, now)


# --- helpers ---


def _check_step(settings, request_id: str, base_revision: int, *steps: str) -> RefineState:
    """Stale check and step check before any slow work. Nothing is written."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        state = _load_state(conn, request_id, base_revision)
    _require_step(state, *steps)
    return state


def _move_step(
    settings, request_id: str, base_revision: int, step: str, event: str, now: datetime, line: str
) -> RefineState:
    with _write_transaction(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        request = read_request(conn, request_id)
        tx = RefineTx(conn, request, state, now)
        tx.audit("system", event, {"step": step})
        if line:
            tx.say("assistant", line)
        tx.set(step=step)
        return save_refine_state(conn, tx.state, base_revision, now)


def _discovery_revision(settings, request_id: str) -> int:
    with open_db(settings.db_path) as conn:
        ensure_discovery_tables(conn)
        return read_discovery_revision(conn, request_id)


def _approach_revision(settings, request_id: str) -> int:
    with open_db(settings.db_path) as conn:
        ensure_approach_tables(conn)
        return read_approach_revision(conn, request_id)
