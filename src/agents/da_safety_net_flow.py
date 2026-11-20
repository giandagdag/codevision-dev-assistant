"""The safety-net conversation (Phase 9 spec section 8): write, check, prove in the sandbox, fix
calls and drop; then the review actions (Continue, Correct something, mark a change) and the
recovery after a restart.

Same pattern as the other flows (rules F1 to F3): read with no lock, do the slow work (the Tester
calls and the proof runs) outside any transaction, then save the net row, the state, the chat lines
and the audit events in ONE transaction, with the Enhance state's own revision as the stale check.

The proof run is a `runner`: a function that runs the test file on today's code and gives back a
LayerBResult. Tests hand in a small one; the real one is `sandbox_runner` (the Phase 6 sandbox,
with the baseline laid over the reference copy). AS400 picture: a test pack that is run against the
production library as it is today; a test that fails there is a wrong test, not a wrong program.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from agents.da_build_agent import AIResult, get_build_client
from agents.da_build_loop import resolve_reference_dir
from agents.da_build_runner import safety_net_slot
from agents.da_enhance_agent import NET_ROLE, revise_safety_net, write_safety_net
from agents.da_enhance_flow import (
    EnhanceView,
    _load_state,
    _policy,
    _read,
    _Tx,
    _view,
    _write_transaction,
    baseline_texts,
)
from agents.da_llm_client import LLMClient
from agents.da_safety_net_checks import (
    UNABLE_TEXT,
    complete_not_covered,
    drop_cases,
    failure_report_for_cases,
    proof_split,
)
from agents.da_sandbox import run_tests
from agents.da_understand_checks import developer_message_problem
from agents.da_workspace_checks import fingerprint
from configs.da_config import ConfigError, Settings
from da_logging import get_logger
from db_table_functions.db_tbl_da_discovery import read_latest_result
from db_table_functions.db_tbl_da_enhance import (
    EnhanceError,
    insert_safety_net,
    list_requests_at_step,
    next_net_version,
    read_enhance_state,
    read_latest_safety_net,
    save_enhance_state,
)
from db_table_functions.db_tbl_da_refine import read_all_records
from pydantic_classes.da_build_models import LayerBResult
from pydantic_classes.da_enhance_models import ImpactRow, SafetyNet, SafetyNetRow
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

# Runs a test file on today's code (the baseline over the reference copy): (test code, files) in,
# result out. Part B supplies the sandbox one.
ProofRunner = Callable[[str, dict[str, str]], LayerBResult]

WRITING_STEPS = ("s_writing", "s_unable")
NO_REFERENCE_TEXT = (
    "The safety net cannot be proved here: the server has no reference copy of CodeVision "
    "(DA_SANDBOX_SOURCE_DIR)."
)
NO_RECORD_TEXT = "There is no confirmed request record to write a safety net for."
BUSY_TEXT = "The safety net is already being written for this request. Please wait."
RESTART_TEXT = "The server restarted while the safety net was being written. Press Try again."
STOPPED_TEXT = "The safety net write stopped on an error. Press Try again."
MARK_NONE = ""  # the "After the change" mark for "Must still pass"

# Requests whose safety net is being written or proved right now, in this server (F2).
_busy: set[str] = set()
_busy_lock = threading.Lock()


def is_safety_net_running(request_id: str) -> bool:
    """True while a write, correction or proof for this request runs in this server. The screen
    shows "writing" for it; a step `s_writing` with no run behind it shows Try again (F3)."""
    with _busy_lock:
        return request_id in _busy


@contextmanager
def _one_at_a_time(settings: Settings, request_id: str) -> Iterator[None]:
    """F2: one safety-net write or proof at a time for a request, and it takes a slot of the
    shared pool (it uses the AI and the sandbox like a build)."""
    with _busy_lock:
        if request_id in _busy:
            raise EnhanceError(BUSY_TEXT)
        _busy.add(request_id)
    try:
        with safety_net_slot(settings, request_id):
            yield
    finally:
        with _busy_lock:
            _busy.discard(request_id)


def sandbox_runner(settings: Settings, request_id: str, policy: Policy) -> ProofRunner:
    """The real proof run: the Phase 6 sandbox with the baseline laid over the reference copy
    (spec section 8, step 4), same time limit as a build. No reference copy gives a run that did
    not happen, which is not the test's fault."""

    def run(test_code: str, files: dict[str, str]) -> LayerBResult:
        reference = resolve_reference_dir(settings)
        if reference is None:
            return LayerBResult(ran=False, error=NO_REFERENCE_TEXT)
        return run_tests(
            reference, files, request_id.lower().replace("-", "_"), test_code,
            exclude=policy.build_sandbox_exclude,
            timeout_seconds=policy.build_test_timeout_seconds,
            settings=settings,
        )

    return run


def run_safety_net(
    settings: Settings,
    request_id: str,
    base_revision: int,
    runner: ProofRunner | None = None,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> EnhanceView:
    """Write the net (one Tester call), prove it on today's code, repair what fails (up to
    `safety_net_max_attempts` fix calls), drop what still fails, add what is not covered.
    Allowed at `s_writing` (also after a restart: nothing was saved yet) and at `s_unable` (the
    "Try again" button). Ends at `s_review`, or at `s_unable` when the net could not be made."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, WRITING_STEPS)
    record, record_version, impact = _read_inputs(settings, request_id)
    policy = _policy(settings, request_id)
    files = baseline_texts(settings, request_id)
    runner = runner or sandbox_runner(settings, request_id, policy)
    client_or_error = _tester_client(settings, client)
    if isinstance(client_or_error, AIResult):
        return _save_unable(settings, state, base_revision, client_or_error, now)

    with _one_at_a_time(settings, request_id):  # F2: slow work, outside any transaction
        first = write_safety_net(client_or_error, record, files, impact, policy)
        if first.value is None:
            return _save_unable(settings, state, base_revision, first, now)
        proved = _prove_and_repair(
            client_or_error, runner, record, files, impact, policy, first.value
        )
    if isinstance(proved, AIResult):  # the AI was not reached, or the sandbox did not run
        return _save_unable(settings, state, base_revision, proved, now)
    net, proof, fix_calls = proved
    net = complete_not_covered(net, record)

    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        version = next_net_version(conn, request_id)
        insert_safety_net(
            conn,
            SafetyNetRow(
                request_id=request_id, net_version=version, record_version=record_version,
                net=net, fingerprint=fingerprint(net.test_code), proof=proof,
            ),
            now,
        )
        tx.audit(
            "system", "safety_net_written",
            {"cases": len(proof["proven"]) + len(proof["dropped"]), "attempt": first.attempts,
             "fix_calls": fix_calls},
        )
        tx.audit(
            "system", "safety_net_proved",
            {"passed": len(proof["proven"]), "dropped": len(proof["dropped"])},
        )
        tx.say("assistant", _written_text(net, proof))
        save_enhance_state(conn, state.model_copy(update={"step": "s_review"}), base_revision, now)
    logger.info("Safety net %s written for %s", version, request_id)
    return _view(settings, request_id)


def _read_inputs(
    settings: Settings, request_id: str
) -> tuple[RequestRecord, int, list[ImpactRow]]:
    """The latest confirmed record, its version number, and the impact rows stored with the latest
    Discover round (none when Discover found no callers or the reference copy was unavailable)."""
    with _read(settings.db_path) as conn:
        records = read_all_records(conn, request_id)
        latest = read_latest_result(conn, request_id)
    if not records:
        raise EnhanceError(NO_RECORD_TEXT)
    impact = latest.impact.rows if latest is not None and latest.impact is not None else []
    return records[-1], len(records), impact


def _tester_client(settings: Settings, client: LLMClient | None) -> LLMClient | AIResult:
    """The client, or an AIResult saying why there is none (for example a work server that is
    not configured yet)."""
    if client is not None:
        return client
    try:
        return get_build_client(settings, NET_ROLE)
    except ConfigError as error:
        return AIResult(None, kind="unreachable", message=str(error))


def _prove_and_repair(
    client: LLMClient,
    runner: ProofRunner,
    record: RequestRecord,
    files: dict[str, str],
    impact: list[ImpactRow],
    policy: Policy,
    net: SafetyNet,
) -> tuple[SafetyNet, dict, int] | AIResult:
    """Run the net on today's code. Failing cases get up to `safety_net_max_attempts` fix calls,
    the proven ones kept byte for byte; what still fails is dropped (D-I). Returns (net, proof,
    number of fix calls), or an AIResult when the work cannot go on (sandbox did not run, or the AI
    could not be reached)."""
    fix_calls = 0
    while True:
        result = runner(net.test_code, files)  # slow
        if not result.ran:
            return AIResult(None, kind="no_sandbox", message=result.error or NO_REFERENCE_TEXT)
        proven, failing = proof_split(net, result)
        if not failing:
            return net, _proof(proven, [], result, fix_calls), fix_calls
        if fix_calls >= policy.safety_net_max_attempts:
            break
        fix_calls += 1
        report = failure_report_for_cases(net, result, failing)
        fixed = revise_safety_net(client, record, files, impact, policy, net, report, proven)
        if fixed.value is not None:
            net = fixed.value
        elif fixed.kind in ("unreachable", "too_big"):
            return fixed  # not the test's fault: keep nothing half-done
        # A "bad_reply" costs the attempt; the loop proves the same net again and tries once more.
    kept = drop_cases(net, failing)
    if not kept.cases:  # every case was dropped: cutting the methods would leave an empty class
        kept = kept.model_copy(update={"test_code": ""})
    return kept, _proof(proven, failing, result, fix_calls), fix_calls


def _proof(proven: list[str], dropped: list[str], result: LayerBResult, fix_calls: int) -> dict:
    """What is stored with the net row: compact, never the 200 KB run output."""
    return {
        "proven": proven,
        "dropped": dropped,
        "fix_calls": fix_calls,
        "timed_out": result.timed_out,
        "tests": [{"name": item.name, "result": item.result} for item in result.tests],
    }


def _written_text(net: SafetyNet, proof: dict) -> str:
    if net.cases:
        text = (
            f"Safety net: {len(net.cases)} test(s) capture today's behaviour. "
            f"All {len(net.cases)} pass on the unchanged code."
        )
    else:
        text = "Safety net: no test could be made to pass on today's code."
    if proof["dropped"]:
        text += (
            f" {len(proof['dropped'])} test(s) could not be made to pass on today's code and were "
            "dropped; they are listed as not covered."
        )
    if net.not_covered:
        text += f" {len(net.not_covered)} item(s) are not covered, so check them manually."
    return text


def _save_unable(
    settings: Settings,
    state,
    base_revision: int,
    failed: AIResult,
    now: datetime,
) -> EnhanceView:
    """The net could not be made: step `s_unable`, with Try again and Get help. No net is saved."""
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, state.request_id, now)
        tx.audit("system", "safety_net_unable", {"kind": failed.kind, "attempts": failed.attempts})
        tx.say("assistant", f"{UNABLE_TEXT} {_reason(failed)}".strip())
        save_enhance_state(conn, state.model_copy(update={"step": "s_unable"}), base_revision, now)
    return _view(settings, state.request_id)


def _reason(failed: AIResult) -> str:
    return failed.message or "; ".join(failed.problems) or failed.kind


def get_net_row(settings: Settings, request_id: str) -> SafetyNetRow | None:
    """The newest safety-net row for the screen (read only, no lock). None = none written yet."""
    with _read(settings.db_path) as conn:
        return read_latest_safety_net(conn, request_id)


# --- the review actions (spec section 8, step 6) ---


def accept_safety_net(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> EnhanceView:
    """"Continue to Approach": the net in review is accepted and frozen for this record version.
    Accepting appends a copy of the row with `accepted` True (rows are never edited)."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, ("s_review",))
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        latest = read_latest_safety_net(conn, request_id)
        if latest is None or latest.accepted:
            raise EnhanceError("There is no safety net waiting for your OK.")
        insert_safety_net(
            conn,
            latest.model_copy(
                update={"net_version": next_net_version(conn, request_id), "accepted": True}
            ),
            now,
        )
        tx.audit(
            "developer", "safety_net_accepted",
            {"net_version": latest.net_version, "cases": len(latest.net.cases),
             "not_covered": len(latest.net.not_covered)},
        )
        tx.say("developer", "Continue to Approach")
        tx.say(
            "assistant",
            "Safety net accepted. These tests are frozen: the build may not change them.",
        )
        accepted = state.model_copy(update={"step": "s_accepted"})
        save_enhance_state(conn, accepted, base_revision, now)
    return _view(settings, request_id)


def mark_expected_change(
    settings: Settings,
    request_id: str,
    case_id: str,
    mark: str,
    base_revision: int,
    now: datetime | None = None,
) -> EnhanceView:
    """He changes the "After the change" mark of one case: an AC ID ("Expected to change") or
    `MARK_NONE` ("Must still pass"). Plain code saves it as a new row; the test file is not
    touched."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, ("s_review",))
    record, _version, _impact = _read_inputs(settings, request_id)
    if mark != MARK_NONE and mark not in {item.id for item in record.acceptance_criteria}:
        raise EnhanceError(f"{mark} is not a criterion of this request.")
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        latest = read_latest_safety_net(conn, request_id)
        case = next((c for c in latest.net.cases if c.id == case_id), None) if latest else None
        if latest is None or latest.accepted or case is None:
            raise EnhanceError(f"{case_id} is not a test in the safety net in review.")
        before = case.expected_to_change or MARK_NONE
        if before == mark:
            raise EnhanceError(f"{case_id} is already marked that way.")
        changed = case.model_copy(update={"expected_to_change": mark or None})
        net = latest.net.model_copy(
            update={"cases": [changed if c.id == case_id else c for c in latest.net.cases]}
        )
        insert_safety_net(
            conn,
            latest.model_copy(
                update={"net_version": next_net_version(conn, request_id), "net": net}
            ),
            now,
        )
        detail = {"case": case_id, "from": before, "to": mark}
        tx.audit("developer", "expected_change_marked", detail)
        meaning = f"{mark} is expected to change" if mark else "must still pass"
        tx.say("assistant", f"{case_id} is now marked: {meaning}.")
        # A new revision, so old windows go stale.
        save_enhance_state(conn, state, base_revision, now)
    return _view(settings, request_id)


def correct_safety_net(
    settings: Settings,
    request_id: str,
    note: str,
    base_revision: int,
    runner: ProofRunner | None = None,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> EnhanceView:
    """"Correct something": one Tester call with his note, then the proof again (and fix calls, as
    for the first net). At most `safety_net_max_corrections` times. A correction that cannot be made
    leaves the net in review as it was and says why; it does not use up a correction."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, ("s_review",))
    policy = _policy(settings, request_id)
    if state.corrections_used >= policy.safety_net_max_corrections:
        raise EnhanceError(
            f"You have used all {policy.safety_net_max_corrections} corrections. "
            "Continue to Approach, or use Get help."
        )
    problem = developer_message_problem(note)
    if problem:
        raise EnhanceError(problem)
    note = note.strip()
    record, _version, impact = _read_inputs(settings, request_id)
    files = baseline_texts(settings, request_id)
    with _read(settings.db_path) as conn:
        latest = read_latest_safety_net(conn, request_id)
    if latest is None or latest.accepted:
        raise EnhanceError("There is no safety net in review to correct.")
    runner = runner or sandbox_runner(settings, request_id, policy)
    tester = _tester_client(settings, client)
    if isinstance(tester, AIResult):
        raise EnhanceError(_reason(tester))

    with _one_at_a_time(settings, request_id):
        revised = revise_safety_net(tester, record, files, impact, policy, latest.net, "", [], note)
        if revised.value is None:
            raise EnhanceError(f"{UNABLE_TEXT} {_reason(revised)}".strip())
        proved = _prove_and_repair(tester, runner, record, files, impact, policy, revised.value)
    if isinstance(proved, AIResult):
        raise EnhanceError(f"{UNABLE_TEXT} {_reason(proved)}".strip())
    net, proof, fix_calls = proved
    net = complete_not_covered(net, record)

    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        insert_safety_net(
            conn,
            SafetyNetRow(
                request_id=request_id, net_version=next_net_version(conn, request_id),
                record_version=latest.record_version, net=net,
                fingerprint=fingerprint(net.test_code), proof=proof,
            ),
            now,
        )
        tx.say("developer", note)
        tx.audit("developer", "safety_net_corrected", {"note": note[:300], "fix_calls": fix_calls})
        tx.audit(
            "system", "safety_net_proved",
            {"passed": len(proof["proven"]), "dropped": len(proof["dropped"])},
        )
        tx.say("assistant", _written_text(net, proof))
        new = state.model_copy(update={"corrections_used": state.corrections_used + 1})
        save_enhance_state(conn, new, base_revision, now)
    return _view(settings, request_id)


# --- after a restart (F3) ---


def recover_interrupted_safety_nets(settings: Settings, now: datetime | None = None) -> list[str]:
    """At server start-up no safety net can really be running, so a request still at `s_writing`
    was cut off. It becomes `s_unable` with the restart message; Try again runs it from the start
    (nothing is saved until a run is complete). Returns the requests that were fixed."""
    now = now or datetime.now(UTC)
    with _read(settings.db_path) as conn:
        stuck = list_requests_at_step(conn, "s_writing")
    fixed = []
    for request_id in stuck:
        if is_safety_net_running(request_id):
            continue
        if _interrupt_writing(settings, request_id, RESTART_TEXT, now):
            fixed.append(request_id)
    return fixed


def mark_safety_net_stopped(
    settings: Settings, request_id: str, now: datetime | None = None
) -> bool:
    """The background write died on an error (not a restart): `s_writing` becomes `s_unable` so
    the screen stops polling and shows Try again. True when the step was moved."""
    return _interrupt_writing(settings, request_id, STOPPED_TEXT, now or datetime.now(UTC))


def _interrupt_writing(settings: Settings, request_id: str, text: str, now: datetime) -> bool:
    with _write_transaction(settings.db_path) as conn:
        state = read_enhance_state(conn, request_id)
        if state is None or state.step != "s_writing":
            return False
        tx = _Tx(conn, request_id, now)
        tx.audit("system", "safety_net_interrupted", {"why": text})
        tx.say("assistant", text)
        unable = state.model_copy(update={"step": "s_unable"})
        save_enhance_state(conn, unable, state.revision, now)
    return True
