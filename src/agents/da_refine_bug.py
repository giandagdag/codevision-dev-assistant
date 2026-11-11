"""The bug lane of Refine, first half (Phase 8 spec section 7, steps 1 to 4): the Tester writes one
test that shows the bug, plain code proves in the sandbox that it FAILS on his current files, and
one click ("Yes, this is the bug") appends it to the frozen test set as a new version.

The fix round (step 5) is the next step of the build; this file stops at `bug_rebuild`.

What the Tester sees: the record, the contract names, this criterion's cases and his words. Never
code (D-G). What the sandbox runs: the test set so far plus the new method, against his latest text
of every planned file (the last scan).

AS400 picture: before the fix, the tester files a failing test case against the program as it is.
Only when the case really fails does the programmer sign it as the bug to fix.
"""

import sqlite3
from datetime import UTC, datetime

from agents.da_approach_checks import normalise_path
from agents.da_build_flow import STARTED_MESSAGE, BuildTx, _approach_of, planned_paths_of
from agents.da_build_flow import _save as build_save
from agents.da_build_loop import resolve_reference_dir
from agents.da_llm_client import LLMClient
from agents.da_refine_agent import REPRO_ROLE, write_repro_test
from agents.da_refine_lanes import (
    STEP_BUG,
    STEP_BUG_CONFIRM,
    STEP_BUG_HELP,
    STEP_BUG_REBUILD,
    RefineTx,
    _call,
    _context,
    _load_state,
    _require_step,
    _save,
    _write,
)
from agents.da_refine_merge import MergeError, append_test_method
from agents.da_sandbox import run_tests
from agents.da_understand_checks import developer_message_problem
from agents.da_workspace_checks import fingerprint
from configs.da_config import ConfigError
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import (
    ensure_build_tables,
    insert_build_run,
    next_build_number,
    read_build_state,
    read_frozen_files,
)
from db_table_functions.db_tbl_da_refine import (
    RefineError,
    insert_test_set,
    next_test_set_version,
    read_latest_test_set,
    read_test_sets,
)
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request, read_request
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables, read_file_versions
from pydantic_classes.da_build_models import BuildRun, Contract, LayerBResult
from pydantic_classes.da_models import STATUS_BUILDING
from pydantic_classes.da_refine_models import STEP_BUG_FIXING, PendingRepro, RefineState, TestSet

YES_LABEL = "Yes, this is the bug"
NO_LABEL = "No, describe again"
PASSES_TODAY_LINE = (
    "This test passes on your current code, so it does not show the bug. "
    "Describe it again, or pick another lane."
)
FAILURE_LIMIT = 300


# --- 1. write the test and prove it fails today ---


def start_repro(
    settings,
    request_id: str,
    base_revision: int,
    description: str = "",
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> RefineState:
    """One Tester call, then one sandbox run. A test that fails today is shown for his click. One
    that passes today uses a try (`refine_repro_max_attempts`); then Get help is offered. Never
    a build round."""
    now = now or datetime.now(UTC)
    if description:
        problem = developer_message_problem(description)
        if problem:
            raise RefineError(problem)
        description = description.strip()
    work = _read_work(settings, request_id, base_revision)
    feedback = f"{work.state.pending_feedback}\n{description}" if description else (
        work.state.pending_feedback
    )
    reply, why, tests_text, proof = _write_and_prove(settings, work, feedback, client)
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_BUG)
        tx = RefineTx(conn, work.request, state, now)
        if description:
            tx.say("developer", description)
            tx.set(pending_feedback=feedback)
        if reply is None or proof is None:
            tx.audit("system", "repro_test_unusable", {"why": why})
            tx.say("assistant", f"I could not write a test for this. {why} Describe it again.")
            return _save(tx, base_revision)
        tx.audit("system", "repro_test_written", {"case": work.case_id})
        failure = _failure_of(proof, reply.method)
        if failure is None:
            return _passes_today(tx, work, base_revision)
        repro = PendingRepro(
            case_id=work.case_id,
            criterion_id=reply.criterion_id,
            given=reply.given,
            expect=reply.expect,
            method=reply.method,
            failure=failure,
        )
        tx.say("assistant", _confirm_text(repro))
        tx.set(step=STEP_BUG_CONFIRM, repro=repro)
        return _save(tx, base_revision)


def _passes_today(tx: RefineTx, work: _Work, base_revision: int) -> RefineState:
    tries = tx.state.repro_tries + 1
    passed = tx.state.repro_passed_today + 1
    tx.audit("system", "repro_test_passed_today", {"attempt": tries})
    tx.set(repro_tries=tries, repro_passed_today=passed)
    if tries >= work.max_tries:
        tx.say("assistant", f"{PASSES_TODAY_LINE} I could not get a test that fails. Get help.")
        tx.set(step=STEP_BUG_HELP)
    else:
        tx.say("assistant", PASSES_TODAY_LINE)
    return _save(tx, base_revision)


def _confirm_text(repro: PendingRepro) -> str:
    return (
        f"Here is a test for {repro.criterion_id} ({repro.case_id}, tag Bug).\n"
        f"Given: {repro.given}\nExpect: {repro.expect}\n"
        f"Today it fails with: {repro.failure}\n"
        f"Press {YES_LABEL}, or {NO_LABEL}."
    )


# --- 2. his click ---


def confirm_repro(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Yes, this is the bug: the method is appended as a new test set version. The earlier methods
    stay byte for byte the same. The fix round follows (next step)."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_BUG_CONFIRM)
        repro = state.repro
        build = read_build_state(conn, request_id)
        if repro is None or build is None:
            raise RefineError("There is no test to confirm.")
        request = _request_of(conn, request_id)
        version = append_repro(conn, request_id, build.approach_version, repro, now)
        tx = RefineTx(conn, request, state, now)
        tx.say("developer", YES_LABEL)
        tx.audit(
            "developer",
            "repro_test_confirmed",
            {"case": repro.case_id, "criterion": repro.criterion_id, "test_set": version},
        )
        tx.say("assistant", f"The test is saved as test set version {version}. I will fix it.")
        tx.set(step=STEP_BUG_REBUILD)
        return _save(tx, base_revision)


def append_repro(
    conn: sqlite3.Connection, request_id: str, approach_version: int, repro: PendingRepro, now
) -> int:
    """Append the confirmed method to the frozen test set as a new version; the earlier methods stay
    byte for byte the same. Returns the new test set version."""
    base = _base_test_text(conn, request_id, approach_version)
    try:
        text = append_test_method(base, repro.method)
    except MergeError as error:
        raise RefineError(str(error)) from error
    version = next_test_set_version(conn, request_id)
    insert_test_set(
        conn,
        TestSet(
            request_id=request_id,
            test_set_version=version,
            approach_version=approach_version,
            added_case_ids=[repro.case_id],
            text=text,
            fingerprint=fingerprint(text),
        ),
        now,
    )
    return version


def reject_repro(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """No, describe again: nothing is saved, the tries start again, and he types more."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_BUG_CONFIRM, STEP_BUG_HELP)
        tx = RefineTx(conn, _request_of(conn, request_id), state, now)
        tx.say("developer", NO_LABEL)
        case = state.repro.case_id if state.repro else ""
        tx.audit("developer", "repro_test_rejected", {"case": case})
        tx.say("assistant", "Describe the bug again in your own words.")
        tx.set(step=STEP_BUG, repro=None, repro_tries=0)
        return _save(tx, base_revision)


# --- 3. the fix build (section 7, step 5) ---


def start_bug_fix(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """After the confirm: a new build number with a fresh budget, kind `rebuild`. The build loop
    (run by the caller) writes only the traced file and never changes the tests.
    REVISION_IN_PROGRESS goes to BUILDING; the loop ends the Refine when the build ends."""
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_BUG_REBUILD)
        request = begin_rebuild(conn, _request_of(conn, request_id), now)
        tx = RefineTx(conn, request, state, now)
        tx.set(step=STEP_BUG_FIXING)
        return _save(tx, base_revision)


def begin_rebuild(conn: sqlite3.Connection, request, now: datetime):
    """The shared start of a fix build: a new build number, kind `rebuild`, status BUILDING.
    Returns the request as it is after the move."""
    request_id = request.request_id
    build = read_build_state(conn, request_id)
    number = next_build_number(conn, request_id)
    insert_build_run(
        conn,
        BuildRun(
            request_id=request_id,
            build_number=number,
            approach_version=build.approach_version,
            started_at=now,
            kind="rebuild",
        ),
    )
    build_tx = BuildTx(conn, request, build, now)
    build_tx.say("assistant", STARTED_MESSAGE)
    build_tx.move_to(STATUS_BUILDING)
    build_tx.audit("system", "build_started", {"build": number, "kind": "rebuild"})
    build_tx.set(
        build_number=number,
        step="b_running",
        current_round=0,
        write_state="not_written",
        message="",
    )
    build_save(build_tx, build.revision)
    return build_tx.request


# --- helpers ---


class _Work:
    """Everything the Tester call and the proof need, read once with no lock held."""

    def __init__(self, **values):
        self.__dict__.update(values)


def _read_work(
    settings, request_id: str, base_revision: int, steps=(STEP_BUG,), criterion: str = ""
) -> _Work:
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_workspace_tables(conn)
        conn.execute("BEGIN")
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, *steps)
        request = _request_of(conn, request_id)
        rulebook = get_rulebook_for_request(settings.db_path, request_id).rulebook
        context = _context(conn, request, rulebook)
        build = read_build_state(conn, request_id)
        frozen = read_frozen_files(conn, request_id, build.approach_version)
        if "contract" not in frozen or "test" not in frozen:
            raise RefineError("The build has no saved contract and tests to work from.")
        approach = _approach_of(conn, request_id, build)
        code = {}
        for path in planned_paths_of(approach):
            versions = read_file_versions(conn, request_id, path)
            if versions:
                code[path] = versions[-1].text
        base = _base_test_text(conn, request_id, build.approach_version)
        used = [i for s in read_test_sets(conn, request_id) for i in s.added_case_ids]
    return _Work(
        state=state,
        request=request,
        context=context,
        contract=Contract.model_validate_json(frozen["contract"].text),
        code=code,
        base_tests=base,
        case_id=_next_case_id([c.test_id for c in context.cases] + used),
        criterion_id=criterion or _criterion_of(state, context),
        policy=rulebook.policy,
        max_tries=rulebook.policy.refine_repro_max_attempts,
        request_id=request_id,
    )


def _base_test_text(conn: sqlite3.Connection, request_id: str, approach_version: int) -> str:
    latest = read_latest_test_set(conn, request_id, approach_version)
    if latest is not None:
        return latest.text
    return read_frozen_files(conn, request_id, approach_version)["test"].text


def _request_of(conn: sqlite3.Connection, request_id: str):
    return read_request(conn, request_id)


def _next_case_id(ids: list[str]) -> str:
    numbers = [int(i.split("-")[1]) for i in ids if i.startswith("T-") and i[2:].isdigit()]
    return f"T-{max(numbers, default=0) + 1}"


def _criterion_of(state: RefineState, context) -> str:
    """The criterion the lane suggestion named, or the first one when none was named."""
    ids = [c.id for c in context.record.acceptance_criteria]
    if state.suggested_criterion in ids:
        return state.suggested_criterion
    if not ids:
        raise RefineError("The request has no acceptance criterion to test.")
    return ids[0]


def _write_and_prove(
    settings, work: _Work, feedback: str, client: LLMClient | None, own_test: bool = False
):
    """(reply, why, tests text, sandbox result). The reply is None when no usable test came. With
    `own_test`, a reply with a `question` (too vague) comes back with no tests and no proof."""
    result, error = _call(
        settings,
        REPRO_ROLE,
        client,
        lambda c: write_repro_test(
            c, work.context.record, work.contract, work.context.cases, work.policy,
            work.criterion_id, work.case_id, feedback, own_test,
        ),
    )
    if result is None or not result.ok:
        why = error or (result.message if result else "") or "The answer was not usable."
        return None, why, "", None
    reply = result.value
    if reply.question:
        return reply, "", "", None
    try:
        tests = append_test_method(work.base_tests, reply.method)
    except MergeError as error:
        return None, str(error), "", None
    proof = _run_proof(settings, work, tests)
    if not proof.ran:
        return None, proof.error, tests, None
    return reply, "", tests, proof


def _run_proof(settings, work: _Work, tests: str) -> LayerBResult:
    reference = resolve_reference_dir(settings)
    if reference is None:
        raise ConfigError("The sandbox needs DA_SANDBOX_SOURCE_DIR to prove the test.")
    return run_tests(
        reference,
        {normalise_path(p): t for p, t in work.code.items()},
        work.request_id.lower().replace("-", "_"),
        tests,
        exclude=work.policy.build_sandbox_exclude,
        timeout_seconds=work.policy.build_test_timeout_seconds,
    )


def _failure_of(proof: LayerBResult, method: str) -> str | None:
    """How the new test failed today, in one short line; None when it passed (or never ran)."""
    name = method.split("(")[0].replace("def ", "").strip()
    for item in proof.tests:
        if item.name.endswith(name) and item.result in ("fail", "error"):
            line = item.message or (item.traceback_tail[-1] if item.traceback_tail else "")
            return (line.strip() or "the test failed")[:FAILURE_LIMIT]
    return None
