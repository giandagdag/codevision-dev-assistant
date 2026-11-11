"""Add a test case (Phase 8 spec section 11, D-N): he types a case in plain language for one
criterion, the Tester writes the method, plain code runs it on his current files.

Passes today: he confirms, it is appended (tag Yours) and a check run follows, so the label
covers it. Fails today: "Treat it as a bug?" with Yes, fix it (the bug lane from its fix build on,
this test is the repro) or Drop this test. It counts in the Refine cap only as a bug lane.

AS400 picture: the tester adds a case to the test deck. If the program already passes it, the case
joins the deck. If it fails, he may open a defect on it, or tear the case up.
"""

from datetime import UTC, datetime

from agents.da_llm_client import LLMClient
from agents.da_refine_bug import (
    _failure_of,
    _read_work,
    _request_of,
    _write_and_prove,
    append_repro,
)
from agents.da_refine_checks import cap_message, refine_cap_reached
from agents.da_refine_lanes import (
    STEP_BUG_REBUILD,
    STEP_START,
    RefineTx,
    _load_state,
    _require_refinable,
    _require_step,
    _save,
    _write,
)
from agents.da_understand_checks import developer_message_problem
from db_table_functions.db_tbl_da_build import read_build_state
from db_table_functions.db_tbl_da_refine import RefineError, insert_refine
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from db_table_functions.db_tbl_da_understand import read_confirmed_record
from pydantic_classes.da_models import STATUS_REVISION
from pydantic_classes.da_refine_models import PendingRepro, RefineRow, RefineState

STEP_OWN_CONFIRM = "own_confirm"  # the new test passes today; add it or drop it
STEP_OWN_FAILS = "own_fails"  # the new test fails today; treat it as a bug or drop it
ADD_LABEL = "Add this test"
YES_FIX_LABEL = "Yes, fix it"
DROP_LABEL = "Drop this test"
VAGUE_PREFIX = "Describe the case more:"
FAILS_LINE ="Your new test fails on the current code. Treat it as a bug?"


def add_test_case(
    settings,
    request_id: str,
    base_revision: int,
    criterion_id: str,
    description: str,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> RefineState:
    """One Tester call, one sandbox run. Nothing is appended before his click."""
    now = now or datetime.now(UTC)
    problem = developer_message_problem(description)
    if problem:
        raise RefineError(problem)
    description = description.strip()
    work = _read_work(settings, request_id, base_revision, (STEP_START,), criterion_id)
    if criterion_id not in [c.id for c in work.context.record.acceptance_criteria]:
        raise RefineError("Pick one of the acceptance criteria of this request.")
    reply, why, _, proof = _write_and_prove(settings, work, description, client, own_test=True)
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_START)
        request = _request_of(conn, request_id)
        _require_refinable(conn, request)
        tx = RefineTx(conn, request, state, now)
        tx.say("developer", f"Add a test case for {criterion_id}: {description}")
        if reply is not None and reply.question:
            # Too vague is an answer: nothing is run or stored, and no case ID is used up.
            tx.audit("system", "own_test_vague", {"question": reply.question})
            tx.say("assistant", f"{VAGUE_PREFIX} {reply.question}")
            return _save(tx, base_revision)
        if reply is None or proof is None:
            tx.audit("system", "own_test_unusable", {"why": why})
            tx.say("assistant", f"I could not write that test. {why} Describe it again.")
            return _save(tx, base_revision)
        failure = _failure_of(proof, reply.method)
        repro = PendingRepro(
            case_id=work.case_id,
            criterion_id=criterion_id,
            given=reply.given,
            expect=reply.expect,
            method=reply.method,
            failure=failure or "",
        )
        tx.audit("system", "own_test_written", {"case": work.case_id, "fails": failure is not None})
        head = f"Test {repro.case_id} for {criterion_id} (tag Yours).\nGiven: {repro.given}\n"
        head += f"Expect: {repro.expect}\n"
        if failure is None:
            tx.say("assistant", f"{head}It passes today. Press {ADD_LABEL}, or {DROP_LABEL}.")
            tx.set(step=STEP_OWN_CONFIRM, repro=repro)
        else:
            tx.say(
                "assistant",
                f"{head}Today it fails with: {failure}\n{FAILS_LINE} "
                f"Press {YES_FIX_LABEL}, or {DROP_LABEL}.",
            )
            tx.set(step=STEP_OWN_FAILS, repro=repro)
        return _save(tx, base_revision)


def confirm_own_test(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Add this test: appended as a new test set version. The caller then starts the check run
    (`start_check(..., after_new_test=True)`), so the label covers the new case."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_OWN_CONFIRM)
        build = read_build_state(conn, request_id)
        if state.repro is None or build is None:
            raise RefineError("There is no test to add.")
        version = append_repro(conn, request_id, build.approach_version, state.repro, now)
        tx = RefineTx(conn, _request_of(conn, request_id), state, now)
        tx.say("developer", ADD_LABEL)
        tx.audit(
            "developer",
            "own_test_added",
            {"case": state.repro.case_id, "tag": "yours", "test_set": version},
        )
        tx.say("assistant", f"The test is saved as test set version {version}. I will run it now.")
        tx.set(step=STEP_START, repro=None)
        return _save(tx, base_revision)


def treat_as_bug(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Yes, fix it: a bug lane Refine starts (source `added_test`) with this test as the repro.
    The caller then runs `start_bug_fix`."""
    now = now or datetime.now(UTC)
    policy = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_OWN_FAILS)
        request = _request_of(conn, request_id)
        build = _require_refinable(conn, request)
        if refine_cap_reached(state.refine_count, policy.refine_max_per_request):
            raise RefineError(cap_message(state.refine_count))
        repro = state.repro
        if repro is None:
            raise RefineError("There is no test to fix.")
        number = state.refine_number + 1
        record = read_confirmed_record(conn, request_id, request.version)
        insert_refine(
            conn,
            RefineRow(
                request_id=request_id,
                refine_number=number,
                source="added_test",
                feedback=repro.given,
                chosen_lane="bug",
                from_status=request.status,
                record_version_before=record.version if record else request.version,
                approach_version_before=build.approach_version,
            ),
            now,
        )
        version = append_repro(conn, request_id, build.approach_version, repro, now)
        tx = RefineTx(conn, request, state, now)
        tx.say("developer", YES_FIX_LABEL)
        tx.move_to(STATUS_REVISION)
        started = {"refine": number, "chosen": "bug", "from": "added_test"}
        tx.audit("developer", "refine_started", started)
        tx.audit("developer", "repro_test_confirmed", {"case": repro.case_id, "test_set": version})
        tx.say("assistant", f"The test is saved as test set version {version}. I will fix it.")
        tx.set(
            step=STEP_BUG_REBUILD,
            refine_number=number,
            refine_count=state.refine_count + 1,
            chosen_lane="bug",
            from_status=request.status,
            repro_tries=0,
            repro_passed_today=0,
        )
        return _save(tx, base_revision)


def drop_own_test(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Drop this test: nothing is saved, no Refine is counted."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_OWN_CONFIRM, STEP_OWN_FAILS)
        tx = RefineTx(conn, _request_of(conn, request_id), state, now)
        tx.say("developer", DROP_LABEL)
        case = state.repro.case_id if state.repro else ""
        tx.audit("developer", "own_test_dropped", {"case": case})
        tx.say("assistant", "The test is dropped. Nothing was changed.")
        tx.set(step=STEP_START, repro=None)
        return _save(tx, base_revision)
