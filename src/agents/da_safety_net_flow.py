"""The safety-net conversation, part A: write, check, fix calls and drop (Phase 9 spec section 8,
steps 1 to 5). The review actions and the sandbox runner come in part B.

Same pattern as the other flows (rules F1 to F3): read with no lock, do the slow work (the Tester
calls and the proof runs) outside any transaction, then save the net row, the state, the chat lines
and the audit events in ONE transaction, with the Enhance state's own revision as the stale check.

The proof run is handed in as `runner`, a function that runs the test file on today's code and gives
back a LayerBResult. So the loop here is tested without a sandbox, and part B only has to supply
the real one. AS400 picture: a test pack that is run against the production library as it is today;
a test that fails there is a wrong test, not a wrong program.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from agents.da_build_agent import AIResult, get_build_client
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
from agents.da_workspace_checks import fingerprint
from configs.da_config import ConfigError, Settings
from da_logging import get_logger
from db_table_functions.db_tbl_da_discovery import read_latest_result
from db_table_functions.db_tbl_da_enhance import (
    EnhanceError,
    insert_safety_net,
    next_net_version,
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
NO_RUNNER_TEXT = "The safety net cannot be proved here: the sandbox is not connected."
NO_RECORD_TEXT = "There is no confirmed request record to write a safety net for."


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
    if runner is None:
        raise EnhanceError(NO_RUNNER_TEXT)
    state = _load_state(settings, request_id, base_revision, WRITING_STEPS)
    record, record_version, impact = _read_inputs(settings, request_id)
    policy = _policy(settings, request_id)
    files = baseline_texts(settings, request_id)
    client_or_error = _tester_client(settings, client)
    if isinstance(client_or_error, AIResult):
        return _save_unable(settings, state, base_revision, client_or_error, now)

    first = write_safety_net(client_or_error, record, files, impact, policy)  # slow
    if first.value is None:
        return _save_unable(settings, state, base_revision, first, now)
    proved = _prove_and_repair(client_or_error, runner, record, files, impact, policy, first.value)
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
            return AIResult(None, kind="no_sandbox", message=result.error or NO_RUNNER_TEXT)
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
    reason = failed.message or "; ".join(failed.problems) or failed.kind
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, state.request_id, now)
        tx.audit("system", "safety_net_unable", {"kind": failed.kind, "attempts": failed.attempts})
        tx.say("assistant", f"{UNABLE_TEXT} {reason}".strip())
        save_enhance_state(conn, state.model_copy(update={"step": "s_unable"}), base_revision, now)
    return _view(settings, state.request_id)
