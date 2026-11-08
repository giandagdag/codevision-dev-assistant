"""The lane actions of Refine (Phase 8 spec sections 4 and 5): suggest a lane, start it, revise the
record (requirement lane), confirm or cancel.

Same pattern as the build flow (rule F1): read with no lock, do the slow AI call outside any
transaction, then ONE write transaction holds state, rows, audit events and chat together. The
Refine state has its own revision, so a window that is out of date is refused.

AS400 picture: a change request amendment. The lane click opens the amendment
(REVISION_IN_PROGRESS), the checkpoint is the reviewer's margin diff, Confirm v2 signs it and
Cancel withdraws it.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from agents.da_build_flow import _require_request
from agents.da_llm_client import LLMClient, LLMClientError, get_llm_client
from agents.da_refine_agent import (
    LANE_ROLE,
    REVISION_ROLE,
    RefineContext,
    revise_record,
    suggest_lane,
)
from agents.da_refine_checks import (
    apply_revision,
    cap_message,
    diff_records,
    refine_cap_reached,
)
from agents.da_understand_checks import developer_message_problem
from configs.da_config import ConfigError
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_approach import (
    read_approach_state,
    read_approach_versions,
    read_latest_plan,
)
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_build import ensure_build_tables, read_build_run, read_build_state
from db_table_functions.db_tbl_da_refine import (
    RefineError,
    close_refine,
    insert_refine,
    read_all_records,
    read_refine_revision,
    read_refine_state,
    save_refine_state,
)
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request, update_request
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
from db_table_functions.db_tbl_da_tester import read_reviews
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    add_message,
    insert_confirmed_record,
    read_confirmed_record,
)
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables
from pydantic_classes.da_models import (
    STATUS_CONFIRMED,
    STATUS_NOT_PASSING,
    STATUS_READY,
    STATUS_READY_FOR_REVIEW,
    STATUS_REVISION,
    Actor,
    Request,
)
from pydantic_classes.da_refine_models import (
    LANES,
    LaneSuggestion,
    RecordDiff,
    RefineRow,
    RefineSource,
    RefineState,
)
from pydantic_classes.da_request_record_models import Speaker

LANE_LABELS = {
    "requirement": "Requirement change",
    "approach": "Approach change",
    "bug": "Bug",
}
CANCEL_LABEL = "Cancel"
CONFIRM_V2_LABEL = "Confirm v2"
CANCEL_REVISION_LABEL = "Cancel revision"
CORRECT_LABEL = "Correct something"
NO_SUGGESTION_LINE = "I could not suggest a lane. Pick one."
PICK_LINE = "Pick the lane that fits. You decide."
SOURCES: tuple[str, ...] = ("feedback", "finding", "failed_check", "added_test")

# Steps (RefineState.step) in the order a lane goes through them.
STEP_START = "start"
STEP_LANE_CHOICE = "lane_choice"
STEP_REQ_REVISE = "req_revise"  # the lane is chosen, the revision call has not given a result yet
STEP_REQ_CHECKPOINT = "req_checkpoint"  # the diff is shown, Confirm v2 or Cancel revision
STEP_REQ_DISCOVER = "req_discover"  # v2 is saved; Discover runs on it (step 7b)
STEP_APPROACH = "approach_start"
STEP_APPROACH_REFUSED = "approach_refused"  # the reply changed a criterion; switch or cancel
STEP_BUG = "bug_start"
STEP_BUG_CONFIRM = "bug_confirm"  # the repro test fails today; Yes, this is the bug / No
STEP_BUG_HELP = "bug_help"  # the tries are used up; Get help is offered (step 12)
STEP_BUG_REBUILD = "bug_rebuild"  # the test is appended; the fix round comes next
# Steps where Cancel still gives everything back (nothing is saved for the new version yet).
CANCEL_STEPS = (
    STEP_BUG_CONFIRM,
    STEP_BUG_HELP,
    STEP_LANE_CHOICE,
    STEP_REQ_REVISE,
    STEP_REQ_CHECKPOINT,
    STEP_APPROACH,
    STEP_APPROACH_REFUSED,
    STEP_BUG,
)


@dataclass
class RefineTx:
    """One Refine action's work inside its write transaction. The state is saved at the end."""

    conn: sqlite3.Connection
    request: Request
    state: RefineState
    now: datetime

    def say(self, speaker: Speaker, text: str) -> None:
        add_message(self.conn, self.request.request_id, speaker, text, self.now)

    def audit(self, actor: Actor, event_type: str, details: dict | None = None) -> None:
        insert_audit_event(self.conn, self.request.request_id, actor, event_type, details, self.now)

    def move_to(self, status: str) -> None:
        old = self.request.status
        self.request = update_request(
            self.conn, self.request.request_id, now=self.now, status=status
        )
        self.audit("system", "status_changed", {"from": old, "to": status})

    def set(self, **changes) -> None:
        self.state = self.state.model_copy(update=changes)


# --- reading ---


def get_refine_revision(settings, request_id: str) -> int:
    """0 means this request has never been refined. The screen sends this with every action."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        return read_refine_revision(conn, request_id)


def get_refine_state(settings, request_id: str) -> RefineState | None:
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        return read_refine_state(conn, request_id)


def get_pending_diff(settings, request_id: str) -> RecordDiff | None:
    """The diff the checkpoint shows (confirmed version to the proposed one), or None."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        state = read_refine_state(conn, request_id)
        if state is None or state.pending_record is None:
            return None
        request = _require_request(conn, request_id)
        old = read_confirmed_record(conn, request_id, request.version)
        return diff_records(old, state.pending_record) if old else None


# --- 1. suggest a lane (section 4) ---


def suggest(
    settings,
    request_id: str,
    feedback: str,
    base_revision: int,
    client: LLMClient | None = None,
    source: RefineSource = "feedback",
    now: datetime | None = None,
) -> RefineState:
    """He typed feedback and pressed Refine. One AI call suggests a lane; he always decides."""
    now = now or datetime.now(UTC)
    problem = developer_message_problem(feedback)
    if problem:
        raise RefineError(problem)
    feedback = feedback.strip()
    context, from_status = _read_context(settings, request_id, base_revision, new_refine=True)
    result, error = _call(settings, LANE_ROLE, client, lambda c: suggest_lane(c, context, feedback))
    suggestion: LaneSuggestion | None = result.value if result is not None else None
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_idle_or_choosing(conn, request, state)
        tx = RefineTx(conn, request, state, now)
        tx.say("developer", feedback)
        if suggestion is None:
            why = error or (result.message if result else "")
            attempts = result.attempts if result is not None else 0
            tx.audit("system", "lane_unusable", {"attempt": attempts, "why": why})
            tx.say("assistant", NO_SUGGESTION_LINE)
        else:
            tx.audit(
                "system",
                "lane_suggested",
                {"lane": suggestion.lane, "criterion": suggestion.criterion_id or ""},
            )
            tx.say("assistant", f"{suggestion.reason} {PICK_LINE}")
        tx.set(
            step=STEP_LANE_CHOICE,
            pending_feedback=feedback,
            pending_source=source,
            suggested_lane=suggestion.lane if suggestion else "",
            suggested_reason=suggestion.reason if suggestion else "",
            suggested_criterion=(suggestion.criterion_id or "") if suggestion else "",
            lane_unusable=suggestion is None,
            from_status=from_status,
            pending_record=None,
        )
        return _save(tx, base_revision)


# --- 2. choose the lane (section 4, step 6) ---


def choose_lane(
    settings, request_id: str, lane: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """His click starts the lane: REVISION_IN_PROGRESS, a Refine row, audit `refine_started`."""
    now = now or datetime.now(UTC)
    if lane not in LANES:
        raise RefineError("Pick one of the three lanes.")
    # Read before the write lock is taken: a second connection must not wait for our own lock.
    policy = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        if state.step != STEP_LANE_CHOICE:
            raise RefineError("Type your feedback and press Refine first.")
        build = _require_refinable(conn, request)
        if refine_cap_reached(state.refine_count, policy.refine_max_per_request):
            raise RefineError(cap_message(state.refine_count))
        number = state.refine_number + 1
        record = read_confirmed_record(conn, request_id, request.version)
        tx = RefineTx(conn, request, state, now)
        insert_refine(
            conn,
            RefineRow(
                request_id=request_id,
                refine_number=number,
                source=state.pending_source,
                feedback=state.pending_feedback,
                suggested_lane=state.suggested_lane,
                reason=state.suggested_reason,
                chosen_lane=lane,  # type: ignore[arg-type]
                from_status=request.status,
                record_version_before=record.version if record else request.version,
                approach_version_before=build.approach_version,
            ),
            now,
        )
        tx.say("developer", LANE_LABELS[lane])
        tx.move_to(STATUS_REVISION)
        tx.audit(
            "developer",
            "refine_started",
            {"refine": number, "suggested": state.suggested_lane, "chosen": lane},
        )
        first = {"requirement": STEP_REQ_REVISE, "approach": STEP_APPROACH, "bug": STEP_BUG}[lane]
        tx.set(
            step=first,
            refine_number=number,
            refine_count=state.refine_count + 1,
            chosen_lane=lane,
            from_status=request.status,
            repro=None,
            repro_tries=0,
            repro_passed_today=0,
        )
        return _save(tx, base_revision)


# --- 3. requirement lane: the revision call and its checkpoint (section 5) ---


def revise(
    settings,
    request_id: str,
    base_revision: int,
    correction: str = "",
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> RefineState:
    """Ask for the changes only (D-C), apply them in plain code, and show the diff. Also used by
    Correct something at the checkpoint: the correction is added to his first words."""
    now = now or datetime.now(UTC)
    if correction:
        problem = developer_message_problem(correction)
        if problem:
            raise RefineError(problem)
        correction = correction.strip()
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        request = _require_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_REQ_REVISE, STEP_REQ_CHECKPOINT)
        rulebook = get_rulebook_for_request(settings.db_path, request_id).rulebook
        context = _context(conn, request, rulebook)
        versions = read_all_records(conn, request_id)
    feedback = f"{state.pending_feedback}\n{correction}" if correction else state.pending_feedback
    result, error = _call(
        settings, REVISION_ROLE, client, lambda c: revise_record(c, context, feedback)
    )
    proposed, problems = None, []
    if result is not None and result.ok:
        proposed, problems = apply_revision(context.record, result.value, versions)
        if proposed is not None and diff_records(context.record, proposed).empty:
            proposed, problems = None, ["That does not change the request."]
    else:
        problems = [error or (result.message if result else "")]
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_REQ_REVISE, STEP_REQ_CHECKPOINT)
        tx = RefineTx(conn, request, state, now)
        if correction:
            tx.say("developer", correction)
            # Keep it, so a second correction still carries the first one.
            tx.set(pending_feedback=feedback)
        if proposed is None:
            detail = " ".join(p for p in problems if p) or "The answer was not usable."
            tx.say(
                "assistant", f"I could not work out the change. {detail} Say it again, or cancel."
            )
            tx.set(step=STEP_REQ_REVISE, pending_record=None)
        else:
            diff = diff_records(context.record, proposed)
            tx.say("assistant", checkpoint_text(diff))
            tx.set(step=STEP_REQ_CHECKPOINT, pending_record=proposed)
        return _save(tx, base_revision)


def checkpoint_text(diff: RecordDiff) -> str:
    """The checkpoint in words: what changed from vN to v(N+1)."""
    lines = [f"Here is what changes in version {diff.to_version}:"]
    lines += [f"- {item.field} changes." for item in diff.fields]
    verbs = {"added": "is added", "changed": "changes", "removed": "is removed"}
    lines += [f"- {item.id} {verbs[item.change]}." for item in diff.criteria]
    lines.append(f"Press {CONFIRM_V2_LABEL}, or {CANCEL_REVISION_LABEL}, or type a correction.")
    return "\n".join(lines)


def confirm_revision(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Confirm v2: save the next record version (same CVDA number) and hand over to Discover."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_REQ_CHECKPOINT)
        record = state.pending_record
        old = read_confirmed_record(conn, request_id, request.version)
        if record is None or old is None:
            raise RefineError("There is no proposed change to confirm.")
        diff = diff_records(old, record)
        insert_confirmed_record(conn, record, request.developer_id, now)
        tx = RefineTx(conn, request, state, now)
        tx.say("developer", CONFIRM_V2_LABEL)
        tx.audit(
            "developer",
            "record_revised",
            {"from": old.version, "to": record.version, "diff": diff.model_dump(mode="json")},
        )
        # Two audited moves: the record is confirmed again, so Discover can start on it.
        tx.move_to(STATUS_READY)
        tx.move_to(STATUS_CONFIRMED)
        tx.request = update_request(conn, request_id, now=now, version=record.version)
        tx.say(
            "assistant",
            f"Version {record.version} is saved. I will search for reusable code again.",
        )
        tx.set(step=STEP_REQ_DISCOVER, pending_record=None)
        return _save(tx, base_revision)


# --- 4. cancel (section 4 and 5, step 5) ---


def cancel(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Cancel, or Cancel revision. Nothing new is saved; the status goes back to where Refine
    started and the audit shows `refine_cancelled`."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, *CANCEL_STEPS)
        tx = RefineTx(conn, request, state, now)
        at_checkpoint = state.step == STEP_REQ_CHECKPOINT
        tx.say("developer", CANCEL_REVISION_LABEL if at_checkpoint else CANCEL_LABEL)
        tx.audit("developer", "refine_cancelled", {"step": state.step, "lane": state.chosen_lane})
        if request.status == STATUS_REVISION:
            close_refine(
                conn,
                request_id,
                state.refine_number,
                result="cancelled",
                record_version_after=request.version,
                approach_version_after=0,
                build_number=0,
                repro_passed_today=state.repro_passed_today,
                now=now,
            )
            tx.move_to(state.from_status or STATUS_READY_FOR_REVIEW)
        tx.say("assistant", "Cancelled. Nothing was changed.")
        tx.set(
            step=STEP_START,
            pending_feedback="",
            suggested_lane="",
            suggested_reason="",
            suggested_criterion="",
            chosen_lane="",
            pending_record=None,
            lane_unusable=False,
            repro=None,
            repro_tries=0,
            repro_passed_today=0,
        )
        return _save(tx, base_revision)


# --- helpers ---


@contextmanager
def _write(db_path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Tables first: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_audit_table(conn)
        ensure_workspace_tables(conn)
        ensure_build_tables(conn)
        begin_write(conn)
        yield conn


def _load_state(conn: sqlite3.Connection, request_id: str, base_revision: int) -> RefineState:
    """The Refine state, after the stale check. A request never refined starts a fresh state."""
    if read_refine_revision(conn, request_id) != base_revision:
        raise StaleRevisionError(STALE_MESSAGE)
    return read_refine_state(conn, request_id) or RefineState(request_id=request_id)


def _save(tx: RefineTx, base_revision: int) -> RefineState:
    tx.state = save_refine_state(tx.conn, tx.state, base_revision, tx.now)
    return tx.state


def _require_step(state: RefineState, *steps: str) -> None:
    if state.step not in steps:
        raise RefineError("That is not possible at this step of the Refine.")


def _require_idle_or_choosing(conn: sqlite3.Connection, request: Request, state: RefineState):
    if state.step not in (STEP_START, STEP_LANE_CHOICE):
        raise RefineError("A Refine is already in progress. Finish or cancel it first.")
    return _require_refinable(conn, request)


def _require_refinable(conn: sqlite3.Connection, request: Request):
    """Refine starts only at `b_written` with READY_FOR_REVIEW or NOT_PASSING (section 2)."""
    build = read_build_state(conn, request.request_id)
    if build is None or build.step != "b_written":
        raise RefineError("This is only possible after a build, when the code is in your folder.")
    if request.status not in (STATUS_READY_FOR_REVIEW, STATUS_NOT_PASSING):
        raise RefineError("This is only possible after a build, when the code is in your folder.")
    return build


def _read_context(
    settings, request_id: str, base_revision: int, new_refine: bool
) -> tuple[RefineContext, str]:
    """Everything the lane call may see. Never the chat, never code."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        request = _require_request(conn, request_id)
        state = _load_state(conn, request_id, base_revision)
        _require_idle_or_choosing(conn, request, state)
        rulebook = get_rulebook_for_request(settings.db_path, request_id).rulebook
        if new_refine and refine_cap_reached(
            state.refine_count, rulebook.policy.refine_max_per_request
        ):
            raise RefineError(cap_message(state.refine_count))
        return _context(conn, request, rulebook), request.status


def _context(conn: sqlite3.Connection, request: Request, rulebook) -> RefineContext:
    request_id = request.request_id
    record = read_confirmed_record(conn, request_id, request.version)
    if record is None:
        raise RefineError("There is no confirmed request record to refine.")
    approach_state = read_approach_state(conn, request_id)
    wanted = approach_state.accepted_approach_version if approach_state else 0
    approach = next(
        (v for v in read_approach_versions(conn, request_id) if v.approach_version == wanted),
        None,
    )
    if approach is None:
        raise RefineError("There is no accepted approach to refine.")
    plan = read_latest_plan(conn, request_id)
    build = read_build_state(conn, request_id)
    run = read_build_run(conn, request_id, build.build_number) if build else None
    reviews = read_reviews(conn, request_id, build.build_number) if build else []
    return RefineContext(
        charter=rulebook.charter,
        record=record,
        approach=approach,
        cases=plan.cases if plan else [],
        policy=rulebook.policy,
        label=run.label if run else "",
        findings=reviews[-1].findings if reviews else [],
    )


def _call(settings, role: str, client: LLMClient | None, ask):
    """Run one AI call. Returns (AIResult or None, error text). A missing setting or an AI that
    does not answer gives no raise: the flow shows the plain message instead."""
    try:
        client = client or get_llm_client(role, settings)  # type: ignore[arg-type]
        return ask(client), ""
    except (ConfigError, LLMClientError) as error:
        return None, str(error)
