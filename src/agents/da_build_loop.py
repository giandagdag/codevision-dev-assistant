"""The build loop (spec sections 3, 4, 7 and 8): the work a background thread does after Build.

contract -> tests (frozen) -> rounds of [write or fix code, Layer A, Layer B] -> result.

The database is the truth, not this code's memory: every step is saved before the next begins,
so a build that pauses (the AI did not answer, a restart) resumes exactly where it stopped, and a
finished file is never written twice. Like a batch job that writes its job log as it goes, so
WRKJOB shows how far it got.

Two ways to leave early, both silent about the code: `_Paused` (the AI or the sandbox could not
run, so NO round is used, decision D-H) and `_Cancelled` (the developer pressed Stop).
"""

import ast
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agents import da_build_agent as agent
from agents import da_tester_review as tester
from agents import da_tester_review_agent as tester_agent
from agents.da_approach_checks import normalise_path
from agents.da_build_checks import (
    LayerAContext,
    apply_edits,
    build_failure_report,
    check_layer_a,
    choose_files_to_fix,
    find_test_methods,
    list_codevision_modules,
    report_for_generator,
    result_for,
)
from agents.da_build_flow import (
    RUNNING_STEPS,
    UNABLE_MESSAGE,
    BuildTx,
    _require_request,
    _write,
)
from agents.da_check_words import NOT_PROVEN_TEXT, testing_files_line
from agents.da_enhance_build_checks import (
    STILL_OLD,
    ExpectedOutcome,
    expected_outcomes,
    expected_test_text,
    frozen_set_with_net,
    net_nc_status,
    scope_problems,
    scoped_view,
    signature_problems,
)
from agents.da_escalation_flow import escalate as open_escalation
from agents.da_escalation_triggers import (
    CAP_HIT_TWICE,
    TESTER_UNABLE_TWICE,
    cap_hit_twice,
    tester_unable_twice,
)
from agents.da_guidance import USED_FIX_ROUND, USED_TESTER_REVIEW, take_guidance
from agents.da_refine_merge import his_lines, marker_text, plan_merge
from agents.da_sandbox import run_tests
from agents.da_workspace_checks import fingerprint
from configs.da_config import PROJECT_ROOT, Settings
from da_logging import get_logger
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import (
    read_approach_state,
    read_approach_versions,
    read_test_plans,
)
from db_table_functions.db_tbl_da_audit import ensure_audit_table
from db_table_functions.db_tbl_da_build import (
    BuildError,
    add_progress,
    ensure_build_tables,
    insert_build_file,
    insert_round,
    read_build_run,
    read_build_state,
    read_frozen_files,
    read_latest_code,
    read_progress,
    read_rounds,
    save_build_state,
)
from db_table_functions.db_tbl_da_discovery import read_latest_result
from db_table_functions.db_tbl_da_enhance import ensure_enhance_tables, read_accepted_net
from db_table_functions.db_tbl_da_escalation import last_fired_count
from db_table_functions.db_tbl_da_refine import (
    add_build_result,
    close_refine,
    insert_conflict_row,
    insert_test_set,
    next_test_set_version,
    read_latest_test_set,
    read_refine_state,
    save_refine_state,
    set_last_tested,
)
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from db_table_functions.db_tbl_da_tester import (
    insert_review,
    next_review_number,
    read_reviews,
    unable_review_numbers,
)
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    read_confirmed_record,
)
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables, read_file_versions
from pydantic_classes.da_approach_models import ApproachVersion, PlannedFile, TestCase
from pydantic_classes.da_build_models import (
    LABEL_NOT_PASSING,
    LABEL_UNABLE,
    BuildFile,
    BuildState,
    Contract,
    LayerAProblem,
    LayerAResult,
    LayerBResult,
    ProgressLine,
    ProgressState,
    RoundRecord,
)
from pydantic_classes.da_enhance_models import ImpactRow, SafetyNetRow
from pydantic_classes.da_models import (
    ALLOWED_MOVES,
    STATUS_BUILDING,
    STATUS_ESCALATION,
    STATUS_NOT_PASSING,
    STATUS_READY_FOR_REVIEW,
    STATUS_READY_TO_BUILD,
    STATUS_TESTER_REVIEW,
    Request,
)
from pydantic_classes.da_refine_models import STEP_BUG_FIXING, STEP_FINDING_FIXING, TestSet
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Charter, Policy, Rule
from pydantic_classes.da_tester_models import Finding, ReviewRecord

logger = get_logger(__name__)

# At home the fake provider builds against this made-up CodeVision-shaped folder when
# DA_SANDBOX_SOURCE_DIR is not set (spec section 11).
FIXTURE_REFERENCE = PROJECT_ROOT / "tests" / "fixtures" / "da_reference_codevision"
CONTRACT_FILE = "contract.json"
TESTER_PAUSE = "The Tester review paused"
RERUN_STEPS = ("b_done", "b_written", "b_write_stopped")


class _Paused(Exception):
    """The build cannot go on for a reason that is not the code's fault (no round is used)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # "interrupted" or "unable"
        self.message = message


class _Cancelled(Exception):
    """The developer stopped the build (or it is no longer the running build)."""


def resolve_reference_dir(settings: Settings) -> Path | None:
    """The CodeVision folder (the one holding src/) the sandbox copies from."""
    if settings.sandbox_source_dir is not None:
        return settings.sandbox_source_dir
    if settings.llm_provider == "fake" and FIXTURE_REFERENCE.is_dir():
        return FIXTURE_REFERENCE
    return None


@dataclass
class _Inputs:
    """Everything one run needs, read once with no lock held."""

    request: Request
    state: BuildState
    charter: Charter
    policy: Policy
    record: RequestRecord
    approach: ApproachVersion
    cases: list[TestCase]
    start_texts: dict[str, str]
    frozen: dict[str, BuildFile]
    rounds: list[RoundRecord]
    code: dict[str, BuildFile]
    next_line: int
    rules: list[Rule]
    reviews: list[ReviewRecord]
    # Phase 8: the newest frozen test set version (the bug lane appends to it); "" when none.
    test_set_text: str = ""
    # Fix 11-1: the rulebook's golden examples (Generator prompt only).
    golden: list = field(default_factory=list)
    brand: list = field(default_factory=list)
    # Phase 9: the accepted safety net and the callers found by impact (enhance and fix only).
    net: SafetyNetRow | None = None
    impact_rows: list[ImpactRow] = field(default_factory=list)
    planned: list[PlannedFile] = field(init=False)

    def __post_init__(self) -> None:
        self.planned = list(self.approach.plan.files)


def run_build(
    settings: Settings,
    request_id: str,
    client_factory: Callable[[Settings, str], object] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    build_number: int | None = None,
) -> str:
    """Run (or resume) the running build of a request to its end. With `build_number`, only that
    build is run: if the request has moved on to a newer one (Stop, then Build), this returns
    `cancelled` and leaves the newer build to its own thread. Returns what happened:
    `done`, `interrupted`, `unable` or `cancelled`. Never raises for anything the code or the AI
    did; an unexpected error pauses the build with a plain message instead of leaving it
    marked running for ever."""
    run = _Run(settings, request_id, client_factory or agent.get_build_client, now_fn)
    run.expected_build = build_number
    return run.go()


def rerun_review(
    settings: Settings,
    request_id: str,
    base_revision: int,
    client_factory: Callable[[Settings, str], object] | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> str:
    """Run the Tester review again (spec 7-12), only when the label is Unable to assess. Same
    machinery as a round's review, but no round is used and the build stays finished: read with
    no lock, ask the AI outside any transaction, then ONE write holding both status moves.
    Returns `done`. Raises BuildError (nothing changed) when the AI cannot be reached."""
    run = _Run(settings, request_id, client_factory or agent.get_build_client, now_fn)
    run.rerun = True
    run.base_revision = base_revision
    return run.go_rerun()


class _Run:
    def __init__(self, settings, request_id, client_factory, now_fn):
        self.settings = settings
        self.request_id = request_id
        self.client_factory = client_factory
        self.now_fn = now_fn or (lambda: datetime.now(UTC))
        self.expected_build: int | None = None
        self.rerun = False
        # Phase 8: the kind of this build (build, rebuild or check). A check run (Check my edits)
        # is one pass of Layers A, B and C on his files: no Generator, no fix rounds, no budget.
        self.kind = "build"
        self.check = False
        self.merge = False
        self.bug_fix = False
        self.finding_fix = None
        self.base_revision = 0
        self.inp: _Inputs
        self.reference: Path
        self.context: agent.BuildContext
        self._layer_b_line: int | None = None
        self.expected_outcomes: list[ExpectedOutcome] = []

    # --- the top ---

    def go(self) -> str:
        try:
            self._load()
            self._check_environment()
            if self.check:
                return self._check_run()
            contract, tests = self._frozen()
            return self._rounds(contract, tests)
        except _Cancelled:
            return "cancelled"
        except _Paused as paused:
            return self._pause(paused.kind, paused.message)
        except Exception as error:  # noqa: BLE001 - a thread must never die silently
            logger.exception("The build stopped on an unexpected error.")
            if not hasattr(self, "inp"):
                return self._pause_early(f"The build could not start ({type(error).__name__}).")
            return self._pause(
                "interrupted", f"An unexpected error stopped the build ({type(error).__name__})."
            )

    def go_rerun(self) -> str:
        try:
            self._load()
            self._check_rerun_allowed()
            self._layer_c(self.inp.rounds[-1])
        except _Cancelled:
            raise BuildError("This build changed. Reload the page and try again.") from None
        except _Paused as paused:
            raise BuildError(f"{paused.message} Nothing was changed.") from None
        except BuildError, StaleRevisionError:
            raise
        except Exception:  # noqa: BLE001 - the page must show a plain message, not a trace
            logger.exception("The Tester re-run stopped on an unexpected error.")
            raise BuildError("The Tester review could not run. Nothing was changed.") from None
        return "done"

    def _check_rerun_allowed(self) -> None:
        reviews = self.inp.reviews
        if (
            self.inp.request.status != STATUS_READY_FOR_REVIEW
            or not reviews
            or reviews[-1].result != "unable"
        ):
            raise BuildError(
                "Run the Tester review again only works when the label is Unable to assess."
            )

    def _pause_early(self, message: str) -> str:
        """The build failed before its inputs were read. Best effort: mark it paused, so the page
        shows Try again instead of 'running' for ever. If even that fails, start-up recovery
        picks it up."""
        try:
            with _write(self.settings.db_path) as conn:
                state = read_build_state(conn, self.request_id)
                if state is None or state.step not in RUNNING_STEPS:
                    return "cancelled"
                tx = BuildTx(conn, _require_request(conn, self.request_id), state, self.now_fn())
                tx.audit("system", "build_interrupted", {"why": message, "kind": "interrupted"})
                tx.say("assistant", f"The build paused: {message}")
                tx.set(step="b_interrupted", message=message)
                save_build_state(conn, tx.state, state.revision, tx.now)
        except Exception:  # noqa: BLE001
            logger.exception("The build could not even be marked as paused.")
        return "interrupted"

    def _pause(self, kind: str, message: str) -> str:
        try:
            with self._turn() as tx:
                rounds_used = _rounds_used(self.inp.rounds)
                tx.audit("system", "build_interrupted", {"why": message, "kind": kind})
                if kind == "unable":
                    tx.close_run(STATUS_READY_TO_BUILD, LABEL_UNABLE, message, rounds_used)
                    tx.move_to(STATUS_READY_TO_BUILD)
                    tx.set(step="b_unable", message=message)
                    tx.say("assistant", f"{UNABLE_MESSAGE} Result: {LABEL_UNABLE}.")
                else:
                    tx.set(step="b_interrupted", message=message)
                    # A Tester pause already says what it is (spec section 2).
                    own = message.startswith(TESTER_PAUSE) or message == NOT_PROVEN_TEXT
                    tx.say("assistant", message if own else f"The build paused: {message}")
        except _Cancelled:
            return "cancelled"
        return kind

    # --- reading ---

    def _load(self) -> None:
        # The rulebook is read BEFORE the read transaction below. Opening a second connection
        # while one is open can deadlock when another build is saving at the same moment.
        rulebook = get_rulebook_for_request(self.settings.db_path, self.request_id).rulebook
        with open_db(self.settings.db_path) as conn:
            ensure_build_tables(conn)
            ensure_workspace_tables(conn)
            ensure_audit_table(conn)
            ensure_enhance_tables(conn)
            conn.execute("BEGIN")
            request = _require_request(conn, self.request_id)
            state = read_build_state(conn, self.request_id)
            if state is None or state.step not in self._live_steps:
                raise _Cancelled
            if self.expected_build is not None and state.build_number != self.expected_build:
                raise _Cancelled
            if self.rerun and state.revision != self.base_revision:
                raise StaleRevisionError(STALE_MESSAGE)
            run_row = read_build_run(conn, self.request_id, state.build_number)
            self.kind = run_row.kind if run_row else "build"
            self.check = self.kind == "check"
            approach_state = read_approach_state(conn, self.request_id)
            versions = {
                v.approach_version: v for v in read_approach_versions(conn, self.request_id)
            }
            plans = {p.plan_version: p for p in read_test_plans(conn, self.request_id)}
            approach = versions[state.approach_version]
            record = read_confirmed_record(conn, self.request_id, request.version)
            number = state.build_number
            starts = {}
            for item in approach.plan.files:
                versions_of = read_file_versions(conn, self.request_id, _clean(item.path))
                if versions_of:
                    # The newest known text of a file that exists in his folder: his own edit
                    # (a re-scan), or what an earlier build wrote. A new file with such a text
                    # is treated like an old one, so his edits are patched, never overwritten.
                    starts[_clean(item.path)] = versions_of[-1].text
            progress = read_progress(conn, self.request_id, number)
            latest_set = read_latest_test_set(conn, self.request_id, state.approach_version)
            refine = read_refine_state(conn, self.request_id)
            # The bug lane's fix build: a rebuild started from "Yes, this is the bug".
            self.bug_fix = (
                self.kind == "rebuild" and refine is not None and refine.step == STEP_BUG_FIXING
            )
            # Fix it on a Should fix: the finding is the only input of round 1.
            self.finding_fix = (
                refine.fix_finding
                if self.kind == "rebuild" and refine is not None
                and refine.step == STEP_FINDING_FIXING
                else None
            )
            enhancing = record.kind != "new"
            net = read_accepted_net(conn, self.request_id, request.version) if enhancing else None
            found = read_latest_result(conn, self.request_id) if enhancing else None
            impact = found.impact if found is not None else None
            self.inp = _Inputs(
                net=net,
                impact_rows=impact.rows if impact is not None and impact.available else [],
                test_set_text=latest_set.text if latest_set else "",
                request=request,
                state=state,
                charter=rulebook.charter,
                policy=rulebook.policy,
                golden=list(rulebook.golden_examples),
                brand=list(rulebook.brand_constants),
                record=record,
                approach=approach,
                cases=plans[approach_state.accepted_plan_version].cases,
                start_texts=starts,
                frozen=read_frozen_files(conn, self.request_id, state.approach_version),
                rounds=read_rounds(conn, self.request_id, number),
                code=read_latest_code(conn, self.request_id, number),
                next_line=(progress[-1].line_number + 1) if progress else 1,
                rules=list(rulebook.rules),
                reviews=read_reviews(conn, self.request_id, number),
            )
        # A check run whose files were saved by his picks (Apply my choices): test exactly them.
        self.merge = self.check and any(f.made_by == "merge" for f in self.inp.code.values())
        self.context = agent.BuildContext(
            charter=self.inp.charter,
            record=self.inp.record,
            approach=self.inp.approach,
            cases=self.inp.cases,
            policy=self.inp.policy,
            golden_examples=tuple(self.inp.golden),
            brand_constants=tuple(self.inp.brand),
            ui_rules=tuple(self.inp.rules),
        )

    def _check_environment(self) -> None:
        reference = resolve_reference_dir(self.settings)
        if reference is None or not (reference / "src").is_dir():
            raise _Paused(
                "interrupted",
                "The sandbox could not start: the CodeVision source folder was not found. "
                "Check DA_SANDBOX_SOURCE_DIR.",
            )
        self.reference = reference

    # --- contract and tests (spec section 3) ---

    def _frozen(self) -> tuple[Contract, str]:
        frozen = self.inp.frozen
        if "contract" not in frozen:
            self._write_contract()
        contract = Contract.model_validate_json(self.inp.frozen["contract"].text)
        if "test" not in self.inp.frozen:
            self._write_tests(contract)
        self._freeze_safety_net()
        # The frozen file is never changed; test set versions only add methods to it.
        return contract, self.inp.test_set_text or self.inp.frozen["test"].text

    def _freeze_safety_net(self) -> None:
        """Phase 9 (spec section 10): the frozen set of an enhance request is the criterion tests
        plus the safety-net tests that must still pass, as the first test set version. Tests
        expected to change are only recorded by name: they do not run in Layer B."""
        if self.inp.net is None or self.inp.test_set_text:
            return
        text, net_methods, expected = frozen_set_with_net(
            self.inp.frozen["test"].text, self.inp.net.net
        )
        with self._turn() as tx:
            version = next_test_set_version(tx.conn, self.request_id)
            insert_test_set(
                tx.conn,
                TestSet(
                    request_id=self.request_id,
                    test_set_version=version,
                    approach_version=tx.state.approach_version,
                    added_case_ids=[case.id for case in self.inp.net.net.cases],
                    text=text,
                    fingerprint=fingerprint(text),
                    net_methods=net_methods,
                    expected_to_change_methods=expected,
                ),
                tx.now,
            )
            tx.audit(
                "system", "safety_net_frozen",
                {"tests": len(net_methods), "expected_to_change": len(expected)},
            )
        self.inp.test_set_text = text

    def _write_contract(self) -> None:
        self._alive()
        line = self._line("Agreeing the function names with the Tester", "running")
        result = agent.write_contract(self.client("generator"), self.context, self.inp.start_texts)
        self._raise_for(result, "I could not agree the function names for the code.")
        contract = result.value
        self._save_frozen(
            "contract", CONTRACT_FILE, contract.model_dump_json(indent=2), "generator", line
        )

    def _write_tests(self, contract: Contract) -> None:
        self._alive()
        line = self._line("Tester writes the tests from your test plan", "running")
        result = agent.write_tests(self.client("tester"), self.context, contract)
        self._raise_for(result, UNABLE_MESSAGE)
        path = f"tests/{self.test_id}/test_{self.test_id}.py"
        self._save_frozen("test", path, result.value, "tester", line)

    def _raise_for(self, result: agent.AIResult, unable_text: str) -> None:
        if result.ok:
            return
        if result.kind == "bad_reply":
            raise _Paused("unable", unable_text)
        raise _Paused("interrupted", result.message)

    def _save_frozen(self, kind: str, path: str, text: str, made_by: str, line: int) -> None:
        with self._turn() as tx:
            saved = insert_build_file(
                tx.conn,
                BuildFile(
                    request_id=self.request_id,
                    build_number=tx.state.build_number,
                    round=0,
                    path=path,
                    kind=kind,
                    text=text,
                    fingerprint=fingerprint(text),
                    made_by=made_by,
                ),
                tx.now,
            )
            self.inp.frozen[kind] = saved
            if kind == "contract":
                tx.audit(
                    "system",
                    "contract_written",
                    {"files": len(Contract.model_validate_json(text).files)},
                )
                self._note(tx, "Function names agreed", "done", line)
            else:
                count = len(find_test_methods(_parse(text)))
                tx.audit("system", "tests_written", {"tests": count})
                tx.audit("system", "tests_frozen", {"fingerprint": saved.fingerprint})
                self._note(tx, f"Tester wrote {count} tests (frozen)", "done", line)

    # --- the rounds (spec section 7) ---

    def _rounds(self, contract: Contract, tests: str) -> str:
        """Round after round until the build ends. A round that passes Layers A and B is reviewed
        by the independent Tester (Layer C, Phase 7). A Must fix there uses a round like a failing
        test does: one shared budget (spec section 7)."""
        limit = self.inp.policy.build_max_rounds
        while True:
            done = self.inp.rounds
            last = done[-1] if done else None
            if last is not None and _round_passed(last) and self._review_of(last.round) is None:
                if self._layer_c(last):
                    return "done"
                continue
            if last is not None and last.layer_b is not None and last.layer_b.not_proven:
                self._retry_unproven(last, contract, tests)  # Run again: no round is used
                continue
            used = _rounds_used(done)
            if used >= limit:
                return self._finish_failed(used)
            self._one_round(len(done) + 1, contract, tests)

    def _retry_unproven(self, last: RoundRecord, contract: Contract, tests: str) -> None:
        """Run only Layer B again on the saved code, as a new row (rounds are append-only, so the
        unproven row stays as the record). That row does not count against the budget (F3)."""
        self._record_round(
            last.round + 1, last.layer_a, self._layer_b(tests), contract, tests
        )

    def _review_of(self, round_number: int) -> ReviewRecord | None:
        """The saved review of a round. A saved review of a passed round that is not the end of the
        build is a Must fix review: the next round is waiting for its fix."""
        found = [item for item in self.inp.reviews if item.round == round_number]
        return found[-1] if found else None

    def _fix_input(self, number: int) -> tuple[list[str], str]:
        """(files to write, the failure text for the Generator) for a round (spec section 7)."""
        planned = [_clean(item.path) for item in self.inp.planned]
        if number == 1:
            return planned, ""
        last = self.inp.rounds[-1]
        if _round_passed(last):  # Layer C found a Must fix: only its lines go to the Generator
            review = self._review_of(last.round)
            findings = review.findings if review else []
            return tester.files_to_fix(findings, planned), tester.report_for_generator(findings)
        failures = report_for_generator(last.failure_report) if last.failure_report else ""
        return last.files_to_fix, failures

    def _one_round(self, number: int, contract: Contract, tests: str) -> bool:
        limit = self.inp.policy.build_max_rounds
        if number == 1 and self.bug_fix:
            to_write, failures = self._trace_bug(contract, tests)
        elif number == 1 and self.finding_fix is not None:
            to_write, failures = self._finding_input()
        else:
            to_write, failures = self._fix_input(number)
        with self._turn() as tx:
            tx.set(step="b_running", current_round=len(self.inp.rounds))
            # Not proven rows hold a row number but no budget, so show the budget count.
            used_now = _rounds_used(self.inp.rounds) + 1
            self._note(tx, f"Round {used_now} of {limit}", "done")
        generated: dict[str, str] = {}
        problems: list[LayerAProblem] = []
        for path in to_write:
            text, found = self._write_file(path, number, contract, tests, failures)
            generated[path] = text
            problems += found
        layer_a = self._layer_a(generated, contract, problems)
        if not layer_a.ok:
            return self._record_round(number, layer_a, None, contract, tests)
        layer_b = self._layer_b(tests)
        return self._record_round(number, layer_a, layer_b, contract, tests)

    def _trace_bug(self, contract: Contract, tests: str) -> tuple[list[str], str]:
        """Round 1 of a bug fix (spec section 7): run the new test set on his files as they are,
        and send ONLY the traced files to the Generator, with the failure. Every other planned
        file is kept as his text, so the sandbox still sees it. No round is used by this run."""
        planned = [_clean(item.path) for item in self.inp.planned]
        starts = {p: self.inp.start_texts[p] for p in planned if p in self.inp.start_texts}
        result = run_tests(
            self.reference,
            starts,
            self.test_id,
            tests,
            exclude=self.inp.policy.build_sandbox_exclude,
            timeout_seconds=self.inp.policy.build_test_timeout_seconds,
        )
        if not result.ran:
            raise _Paused("interrupted", result.error)
        empty = LayerAResult()
        traced = choose_files_to_fix(empty, result, planned, contract, tests)
        report = build_failure_report(empty, result, self.inp.cases, tests, traced)
        self._keep_untraced(starts, traced)
        return traced, report_for_generator(report)

    def _finding_input(self) -> tuple[list[str], str]:
        """Round 1 of Fix it (spec section 7): only the cited file goes to the Generator, with the
        finding as a Must fix line. Every other planned file stays as his text."""
        planned = [_clean(item.path) for item in self.inp.planned]
        starts = {p: self.inp.start_texts[p] for p in planned if p in self.inp.start_texts}
        finding = self.finding_fix
        cited = _clean(finding.file)
        traced = [cited] if cited in planned else planned
        self._keep_untraced(starts, traced)
        as_must = finding.model_copy(update={"severity": "must_fix"})
        return traced, tester.report_for_generator([as_must])

    def _keep_untraced(self, starts: dict[str, str], traced: list[str]) -> None:
        """His text of each file the Generator will not touch becomes part of this build's code."""
        with self._turn() as tx:
            for path, text in starts.items():
                if path in traced or path in self.inp.code:
                    continue
                self.inp.code[path] = insert_build_file(
                    tx.conn,
                    BuildFile(
                        request_id=self.request_id,
                        build_number=tx.state.build_number,
                        round=1,
                        path=path,
                        kind="code",
                        text=text,
                        fingerprint=fingerprint(text),
                        made_by="system",
                    ),
                    tx.now,
                )

    def _his_lines_note(self, path: str) -> str:
        """R5.3 step 1: on a rebuild, tell the Generator which lines he wrote (last app-written
        version against his scanned version). Empty when he changed nothing in this file."""
        if self.kind != "rebuild":
            return ""
        with open_db(self.settings.db_path) as conn:
            conn.execute("BEGIN")
            versions = read_file_versions(conn, self.request_id, path)
        written = [v for v in versions if v.kind == "written"]
        if not versions or not written:
            return ""
        return marker_text(his_lines(written[-1].text, versions[-1].text))

    def _write_file(
        self, path: str, number: int, contract: Contract, tests: str, failures: str
    ) -> tuple[str, list[LayerAProblem]]:
        """One file per AI call. A new file is the whole reply; an old file gets edit blocks."""
        planned_action = next(i.action for i in self.inp.planned if _clean(i.path) == path)
        action = "modify" if path in self.inp.start_texts else planned_action
        base = (
            self.inp.code[path].text
            if path in self.inp.code
            else self.inp.start_texts.get(path, "")
        )
        saved = self._saved_this_round(path, number)
        if saved is not None:
            return saved.text, []  # a resume: this file is already written, do not ask again
        self._alive()
        name = path.rsplit("/", 1)[-1]
        line = self._line(f"AI writes {name}", "running")
        scoped = self._is_scoped(path, action)
        # Phase 9: an enhance target shows only the functions in scope, never the whole file.
        shown = (
            scoped_view(path, base, self.inp.record.functions_in_scope) if scoped else base
        )
        # Phase 10: a senior's guidance goes into the first FIX round call only, once.
        note = ""
        if failures:
            note = take_guidance(self.settings.db_path, self.request_id, USED_FIX_ROUND)
        prompt = agent.build_code_prompt(
            self.context, contract, path, action, number, tests, shown, failures,
            self._his_lines_note(path), note,
        )  # fmt: skip
        result = agent.write_code(self.client("generator"), self.context, prompt, action)
        if result.kind in ("unreachable", "too_big"):
            raise _Paused(
                "interrupted",
                f"{result.message} ({path})" if result.kind == "too_big" else result.message,
            )
        problems: list[LayerAProblem] = []
        if not result.ok:
            text = base
            detail = result.problems[0] if result.problems else "no usable code"
            problems.append(
                LayerAProblem(
                    code="E2", path=path, text=f"The AI reply could not be used: {detail}"
                )
            )
        elif action == "modify":
            text, problems = apply_edits(base, result.value.edits, path)
            if scoped:
                # A8: an edit outside the functions in scope is a Layer A problem.
                problems += scope_problems(
                    path, base, result.value.edits, self.inp.record.functions_in_scope
                )
        else:
            text = result.value.text
        with self._turn() as tx:
            saved = insert_build_file(
                tx.conn,
                BuildFile(
                    request_id=self.request_id,
                    build_number=tx.state.build_number,
                    round=number,
                    path=path,
                    kind="code",
                    text=text,
                    fingerprint=fingerprint(text),
                    made_by="system" if problems else "generator",
                ),
                tx.now,
            )
            self.inp.code[path] = saved
            tx.audit("system", "code_generated", {"path": path, "round": number})
            self._note(tx, f"AI wrote {name}", "failed" if problems else "done", line)
        return text, problems

    def _is_scoped(self, path: str, action: str) -> bool:
        """True for an existing target of an enhance or fix request that names functions."""
        record = self.inp.record
        targets = {_clean(target).lower() for target in record.targets}
        return (
            record.kind != "new"
            and action == "modify"
            and bool(record.functions_in_scope)
            and path.lower() in targets
        )

    def _saved_this_round(self, path: str, number: int) -> BuildFile | None:
        """The file already written in this round, if it was written cleanly. A file saved with
        problems (made_by "system": its edit blocks did not match) is NOT skipped on a resume, so
        a pause can never turn its failure into a pass."""
        saved = self.inp.code.get(path)
        if saved is None or saved.round != number or saved.made_by == "system":
            return None
        return saved

    def _layer_a(
        self, generated: dict[str, str], contract: Contract, problems: list[LayerAProblem]
    ) -> LayerAResult:
        context = LayerAContext(
            planned_paths=[_clean(i.path) for i in self.inp.planned],
            policy=self.inp.policy,
            contract=contract,
            codevision_modules=list_codevision_modules(self.reference / "src"),
        )
        found = check_layer_a(generated, context)
        problems = problems + self._locked_signature_problems(generated)
        return LayerAResult(
            problems=problems + found.problems,
            rulebook_checks_applied=found.rulebook_checks_applied,
        )

    def _locked_signature_problems(self, generated: dict[str, str]) -> list[LayerAProblem]:
        """A9: a function in scope that a file outside the plan calls keeps its arguments."""
        if not self.inp.impact_rows:
            return []
        planned = [_clean(i.path) for i in self.inp.planned]
        found: list[LayerAProblem] = []
        for path, text in generated.items():
            if path in self.inp.start_texts:
                found += signature_problems(
                    path, self.inp.start_texts[path], text, self.inp.impact_rows, planned
                )
        return found

    def _layer_b(self, tests: str) -> LayerBResult:
        self._alive()
        policy = self.inp.policy
        count = len(find_test_methods(_parse(tests)))
        line = self._line(
            f"Layer B: running {count} tests in a sandbox "
            f"(time limit {policy.build_test_timeout_seconds} seconds per run)",
            "running",
        )
        everything = {path: item.text for path, item in self.inp.code.items()}
        result = run_tests(
            self.reference,
            everything,
            self.test_id,
            tests,
            exclude=policy.build_sandbox_exclude,
            timeout_seconds=policy.build_test_timeout_seconds,
        )
        if not result.ran:
            raise _Paused("interrupted", result.error)
        self._layer_b_line = line
        return result

    def _record_round(
        self,
        number: int,
        layer_a: LayerAResult,
        layer_b: LayerBResult | None,
        contract: Contract,
        tests: str,
    ) -> bool:
        passed = layer_a.ok and layer_b is not None and layer_b.ok
        # F3: tests that never reported are the Developer Assistant's problem. Show the rows,
        # then pause like an interrupted run. No repair round, no Generator call.
        unproven = bool(layer_b and layer_b.not_proven)
        planned = [_clean(i.path) for i in self.inp.planned]
        fix: list[str] = []
        report = None
        if not passed:
            fix = choose_files_to_fix(layer_a, layer_b, planned, contract, tests)
            report = build_failure_report(layer_a, layer_b, self.inp.cases, tests, fix)
        record = RoundRecord(
            request_id=self.request_id,
            build_number=self.inp.state.build_number,
            round=number,
            layer_a=layer_a,
            layer_b=layer_b,
            failure_report=report,
            timed_out=bool(layer_b and layer_b.timed_out),
            files_to_fix=fix,
        )
        limit = self.inp.policy.build_max_rounds
        with self._turn() as tx:
            insert_round(tx.conn, record, tx.now)
            tx.audit(
                "system", "layer_a_result", {"round": number, "problems": len(layer_a.problems)}
            )
            self._note(tx, "Layer A: syntax, imports, rules", "done" if layer_a.ok else "failed")
            if layer_b is not None:
                tx.audit(
                    "system",
                    "layer_b_result",
                    {
                        "round": number,
                        "passed": layer_b.passed,
                        "failed": layer_b.failed,
                        "timed_out": layer_b.timed_out,
                    },
                )
                self._note(
                    tx,
                    f"Layer B: {layer_b.passed} of {len(layer_b.tests)} tests passed "
                    f"(time limit {self.inp.policy.build_test_timeout_seconds} seconds per run)",
                    "done" if layer_b.ok else "failed",
                    self._layer_b_line,
                )
            if not passed and not unproven:
                tx.audit("system", "round_failed", {"round": number, "files_to_fix": fix})
                counted = _rounds_used(self.inp.rounds) + 1  # this round is not appended yet
                if counted < limit and not self.check:
                    tx.set(step="b_round_failed", current_round=number)
                    tx.say(
                        "assistant",
                        _round_failed_text(counted, layer_a, layer_b, len(self.inp.cases), fix),
                    )
        self.inp.rounds.append(record)
        if unproven:
            raise _Paused("interrupted", NOT_PROVEN_TEXT)
        return passed

    # --- a check run: Check my edits (Phase 8 spec section 3) ---

    def _check_run(self) -> str:
        """One pass of Layers A, B and C on the files as they are in his folder. No Generator call,
        no fix round, nothing counted against the budget, nothing written (they are already his).
        A pause in Layer C resumes here: the saved round is not run again."""
        contract, tests = self._frozen()
        if not self.inp.rounds:
            self._check_round(contract, tests)
        last = self.inp.rounds[-1]
        if last.layer_b is not None and last.layer_b.not_proven:
            self._retry_unproven(last, contract, tests)
            last = self.inp.rounds[-1]
        if not _round_passed(last):
            return self._finish_check_failed(last)
        if self._review_of(last.round) is None:
            self._layer_c(last)
        return "done"

    def _check_round(self, contract: Contract, tests: str) -> None:
        """Take his current text of every planned file as this run's code, then Layers A and B."""
        self._alive()
        planned = [_clean(item.path) for item in self.inp.planned]
        if self.merge:  # saved already by Apply my choices
            texts = {path: self.inp.code[path].text for path in planned if path in self.inp.code}
            self._alive()
            layer_a = self._layer_a(texts, contract, [])
            layer_b = self._layer_b(tests) if layer_a.ok else None
            self._record_round(1, layer_a, layer_b, contract, tests)
            return
        texts = {
            path: self.inp.start_texts[path] for path in planned if path in self.inp.start_texts
        }
        with self._turn() as tx:
            tx.set(step="b_running", current_round=0)
            edited = sum(1 for path in texts if self._edited_by_him(tx.conn, path))
            self._note(tx, testing_files_line(len(texts), edited), "done")
            for path, text in texts.items():
                saved = insert_build_file(
                    tx.conn,
                    BuildFile(
                        request_id=self.request_id,
                        build_number=tx.state.build_number,
                        round=1,
                        path=path,
                        kind="code",
                        text=text,
                        fingerprint=fingerprint(text),
                        made_by="system",
                    ),
                    tx.now,
                )
                self.inp.code[path] = saved
        layer_a = self._layer_a(texts, contract, [])
        layer_b = self._layer_b(tests) if layer_a.ok else None
        self._record_round(1, layer_a, layer_b, contract, tests)

    def _edited_by_him(self, conn, path: str) -> bool:
        """F9: the newest known text of the file differs from the last one the app wrote."""
        versions = read_file_versions(conn, self.request_id, path)
        written = [v for v in versions if v.kind == "written"]
        if not versions:
            return False
        return not written or versions[-1].fingerprint != written[-1].fingerprint

    def _finish_check_failed(self, last: RoundRecord) -> str:
        """Layer A or B failed: Not passing, with the failure report. No Generator, no fix round."""
        if last.layer_b is not None:
            what = f"{last.layer_b.failed} test(s)"
            text = f"Your edit breaks {what}. Result: {LABEL_NOT_PASSING}."
        else:
            problems = len(last.layer_a.problems)
            text = (
                f"Your edit did not pass the code checks ({problems} problem(s)), "
                f"so the tests did not run. Result: {LABEL_NOT_PASSING}."
            )
        with self._turn() as tx:
            self._close(tx, False, 0, LABEL_NOT_PASSING, text)
        return "done"

    # --- the end (spec section 8) ---

    def _finish_failed(self, rounds_used: int) -> str:
        """The budget is used up with tests still failing (Layer C did not run in that round)."""
        with self._turn() as tx:
            text = _finish_text(False, rounds_used, LABEL_NOT_PASSING, self.inp.rounds, self._cases)
            self._close(tx, False, rounds_used, LABEL_NOT_PASSING, text)
        return "done"

    def _close(self, tx: BuildTx, passed: bool, rounds_used: int, label: str, text: str) -> None:
        """Close the build inside the caller's transaction: run row, status, step, audit, chat.
        Used by the failed finish and by the review that ends the build (rule T2: one write)."""
        status, label = result_for(passed, label)
        tx.close_run(status, label, "", rounds_used)
        tx.move_to(status)
        if self.merge:
            # His merged files are not in his folder yet: the write follows, whatever the label.
            tx.set(
                step="b_done",
                current_round=rounds_used,
                write_state="not_written",
                message="",
                return_status="",
            )
        elif self.check:
            # Nothing is written after a check run: the files in his folder are the tested ones.
            tx.set(
                step="b_written",
                current_round=rounds_used,
                write_state="written",
                message="",
                return_status="",
            )
        else:
            found = self._find_conflicts(tx) if self.kind == "rebuild" else 0
            # Conflicts: the build is finished but nothing is written until he has picked (R5.3).
            step = "b_conflicts" if found else "b_done"
            tx.set(step=step, current_round=rounds_used, write_state="not_written", message="")
        event = "build_passed" if passed else "build_not_passing"
        details = {
            "rounds": rounds_used,
            "label": label,
            "zones_touched": self.inp.approach.zones_touched,
        }
        if self.kind != "build":
            details["kind"] = self.kind
        tx.audit("system", event, details)
        tx.say("assistant", text)
        # "Last tested" for Phase 10, and the NOT_PASSING-in-a-row count of rebuilds (F4).
        set_last_tested(tx.conn, self.request_id, tx.state.build_number, self.kind, tx.now)
        if self.kind in ("build", "rebuild"):
            count = add_build_result(tx.conn, self.request_id, not passed, tx.now)
            self._cap_hit_twice(tx, count)
        if self.bug_fix or self.finding_fix is not None:
            self._close_bug_refine(tx, passed)

    def _cap_hit_twice(self, tx: BuildTx, count: int) -> None:
        """Escalation trigger 1 (spec section 7): two builds in a row ended NOT_PASSING. Same
        transaction as the build_not_passing audit. A returned row reset the count, so only open
        rows are looked at (rule X2)."""
        if count < 2:
            return
        last = last_fired_count(tx.conn, self.request_id, CAP_HIT_TWICE, ("open",))
        number = tx.state.build_number
        decision = cap_hit_twice(self.inp.policy.escalation_triggers, count, number, last)
        if open_escalation(tx.conn, self.request_id, decision, tx.now).opened:
            tx.move_to(STATUS_ESCALATION)

    def _find_conflicts(self, tx: BuildTx) -> int:
        """R5.3 steps 2 to 4: compare the Generator's result with his version of each file, save
        every conflict (nothing is written), audit the count. Returns how many were found."""
        distance = self.inp.policy.refine_conflict_context_lines
        found = []
        for item in self.inp.planned:
            path = _clean(item.path)
            built = self.inp.code.get(path)
            versions = read_file_versions(tx.conn, self.request_id, path)
            written = [v for v in versions if v.kind == "written"]
            if built is None or not versions or not written:
                continue  # no app-written version: he has no lines of his own to protect
            plan = plan_merge(
                path, written[-1].text, versions[-1].text, built.text, distance, distance
            )
            for conflict in plan.conflicts:
                number = tx.state.build_number
                insert_conflict_row(tx.conn, self.request_id, number, conflict, tx.now)
                found.append(conflict)
        if found:
            tx.audit("system", "conflicts_found", {"count": len(found)})
            tx.say(
                "assistant",
                f"The rebuild touches {len(found)} place(s) you edited. Nothing is written yet: "
                "pick Keep mine or Take the AI's for each one.",
            )
        return len(found)

    def _finding_gone(self, tx: BuildTx, finding) -> bool:
        """The finding is gone when the newest review of this build no longer has it (same file,
        same check, same quoted line)."""
        reviews = read_reviews(tx.conn, self.request_id, tx.state.build_number)
        if not reviews:
            return False
        same = [
            f for f in reviews[-1].findings
            if f.kept and f.file == finding.file and f.check == finding.check
            and f.quote == finding.quote
        ]
        return not same

    def _close_bug_refine(self, tx: BuildTx, passed: bool) -> None:
        """The bug lane and Fix it end with their fix build: the Refine row is closed and the Refine
        screen is free again (same write transaction as the build's own end, rule F1)."""
        state = read_refine_state(tx.conn, self.request_id)
        if state is None or state.step not in (STEP_BUG_FIXING, STEP_FINDING_FIXING):
            return
        result = "fixed" if passed else "not_passing"
        if state.fix_finding is not None:
            gone = self._finding_gone(tx, state.fix_finding)
            result = "fixed" if gone else "not_fixed"
            tx.audit(
                "system",
                "finding_fixed" if gone else "finding_not_fixed",
                {"finding": state.fix_finding.finding_id, "build": tx.state.build_number},
            )
        close_refine(
            tx.conn,
            self.request_id,
            state.refine_number,
            result=result,
            record_version_after=tx.request.version,
            approach_version_after=tx.state.approach_version,
            build_number=tx.state.build_number,
            repro_passed_today=state.repro_passed_today,
            now=tx.now,
        )
        idle = state.model_copy(
            update={
                "step": "start",
                "pending_feedback": "",
                "suggested_lane": "",
                "suggested_reason": "",
                "suggested_criterion": "",
                "chosen_lane": "",
                "repro": None,
                "fix_finding": None,
                "repro_tries": 0,
                "repro_passed_today": 0,
            }
        )
        save_refine_state(tx.conn, idle, state.revision, tx.now)

    @property
    def _cases(self) -> int:
        return len(self.inp.cases)

    # --- Layer C: the independent Tester (Phase 7) ---

    def _layer_c(self, last: RoundRecord) -> bool:
        """Review a round that passed Layers A and B. True when the build ended in this review,
        False when a Must fix sends the next round (spec sections 2, 5, 7). Read with no lock, plain
        checks, the AI call outside any transaction, then ONE write (rule T2)."""
        number = last.round
        line = None if self.rerun else self._enter_layer_c(number)
        data = self._review_input(last)
        self._run_expected_tests()
        plain = self._plain_findings(last)
        # Only a Must fix of check 1 ends the build; the Phase 9 FYI lines (an NC item listed as
        # not covered, a test that still shows the old result) never change the label.
        check_one_failed = any(f.check == 1 and f.severity == "must_fix" for f in plain)
        started = self.now_fn()
        client = self.client("tester")
        outcome = tester_agent.ReviewOutcome(model=getattr(client, "model", ""))
        if not check_one_failed:  # no need to ask the AI when the build ends anyway
            outcome = tester_agent.review_code(client, data, self.request_id)
            if outcome.kind in ("unreachable", "too_big"):
                reason = (
                    "the change is too big for the Tester to review in one go."
                    if outcome.kind == "too_big"
                    else "the AI did not answer."
                )
                raise _Paused("interrupted", f"{TESTER_PAUSE}: {reason}")
        ai_findings = (
            []
            if outcome.kind
            else tester.split_findings(
                outcome.findings,
                data.code,
                self.inp.approach,
                self.inp.record,
                self.inp.rules,
                data.planned_paths,
                self.inp.policy.tester_quote_window,
            )
        )
        findings = tester.number_findings(plain + ai_findings)
        seconds = int((self.now_fn() - started).total_seconds())
        return self._save_review(last, findings, outcome, check_one_failed, line, seconds)

    def _enter_layer_c(self, number: int) -> int:
        """Status TESTER_REVIEW, step b_tester_review, the audit event and the progress line."""
        with self._turn() as tx:
            if tx.request.status == STATUS_BUILDING:
                tx.move_to(STATUS_TESTER_REVIEW)
            tx.set(step="b_tester_review", current_round=number)
            tx.audit("system", "tester_review_started", {"round": number})
            tx.say("assistant", "Tests pass. The independent Tester is now reviewing the code.")
            return self._note(
                tx, "Layer C: the independent Tester is reviewing the code.", "running"
            )

    def _review_input(self, last: RoundRecord) -> tester.ReviewInput:
        return tester.ReviewInput(
            charter=self.inp.charter,
            rules=self.inp.rules,
            record=self.inp.record,
            approach=self.inp.approach,
            cases=self.inp.cases,
            policy=self.inp.policy,
            layer_b=last.layer_b,
            code={path: item.text for path, item in self.inp.code.items()},
            start_texts=self._review_start_texts,
            planned_paths=[_clean(item.path) for item in self.inp.planned],
            round=last.round,
            # Phase 10: a senior's guidance goes into this one review, then it is marked used.
            senior_guidance=take_guidance(
                self.settings.db_path, self.request_id, USED_TESTER_REVIEW
            ),
        )

    def _plain_findings(self, last: RoundRecord) -> list[Finding]:
        """Checks 1, 2 and 3 (check 7 is a warning, not a finding)."""
        test_text = self.inp.frozen["test"].text
        planned = [(_clean(item.path), item.action) for item in self.inp.planned]
        code = {path: item.text for path, item in self.inp.code.items()}
        return (
            tester.check_criteria_have_tests(self.inp.record, test_text)
            + self._enhance_findings()
            + tester.check_tests_pass(self.inp.record, last.layer_b)
            + tester.check_files_match_plan(planned, code, self._review_start_texts)
        )

    def _enhance_findings(self) -> list[Finding]:
        """Phase 9, check 1: the NC line, and the FYI for an expected-to-change test that still
        shows the old result (it never changes the label)."""
        if self.inp.net is None:
            return []
        net = self.inp.net.net
        run_ids, listed = net_nc_status(net)
        found = tester.check_nc_items(self.inp.record, run_ids, listed)
        still_old = [(o.case_id, o.ac_id) for o in self.expected_outcomes if o.label == STILL_OLD]
        return found + tester.check_still_old(still_old)

    def _run_expected_tests(self) -> None:
        """Run the expected-to-change tests once, for information, on the code that passed Layer B
        (D-G). A sandbox that cannot run them is not a pause: nothing is claimed and the audit says
        so."""
        self.expected_outcomes = []
        if self.inp.net is None:
            return
        net = self.inp.net.net
        text = expected_test_text(net)
        if not text:
            return
        policy = self.inp.policy
        result = run_tests(
            self.reference,
            {path: item.text for path, item in self.inp.code.items()},
            self.test_id,
            text,
            exclude=policy.build_sandbox_exclude,
            timeout_seconds=policy.build_test_timeout_seconds,
        )
        if result.ran:
            self.expected_outcomes = expected_outcomes(net, result)
        with self._turn() as tx:
            tx.audit(
                "system",
                "expected_to_change_run",
                {
                    "ran": result.ran,
                    "results": [
                        {"case": o.case_id, "ac": o.ac_id, "label": o.label}
                        for o in self.expected_outcomes
                    ],
                },
            )

    @property
    def _review_start_texts(self) -> dict[str, str]:
        """What the files were before this run. A check run reviews his files as a whole: there is
        no "before", so nothing is compared (a file is never "not changed")."""
        return {} if self.check else self.inp.start_texts

    def _save_review(
        self,
        last: RoundRecord,
        findings: list[Finding],
        outcome: tester_agent.ReviewOutcome,
        check_one_failed: bool,
        line: int | None,
        seconds: int,
    ) -> bool:
        """The one write of a review: the review and its findings, audit events, chat lines, and
        either the next round or the end of the build. True when the build ended."""
        zones = self.inp.approach.zones_touched
        one_failed = check_one_failed
        unable = outcome.kind == "unable"
        limit = self.inp.policy.build_max_rounds
        used = _rounds_used(self.inp.rounds)
        must =tester.must_fix_items(findings)
        label = tester.compute_label(findings, zones, "unable" if unable else "done", 1, [])
        with self._turn() as tx:
            record = ReviewRecord(
                request_id=self.request_id,
                build_number=tx.state.build_number,
                round=last.round,
                review_number=next_review_number(tx.conn, self.request_id, tx.state.build_number),
                model=outcome.model,
                calls=outcome.calls,
                prompt_chars=outcome.prompt_chars,
                attempts=outcome.attempts,
                result="unable" if unable else "done",
                checks=tester.check_results(findings, zones, ran_ai=not (unable or one_failed)),
                zone_warnings=tester.zone_warnings(zones),
                label=label,
                findings=findings,
            )
            saved = insert_review(tx.conn, record, tx.now)
            self.inp.reviews.append(saved)
            self._audit_review(tx, saved, outcome)
            self._note_review(tx, saved, line, seconds)
            if self.rerun:
                self._finish_rerun(tx, saved, label, bool(must) or check_one_failed)
            elif check_one_failed:
                criterion = next(
                    f for f in findings if f.check == 1 and f.severity == "must_fix"
                )
                text = f"Criterion {criterion.cites} has no test. Change the approach or get help."
                self._close(tx, False, used, LABEL_NOT_PASSING, text)
            elif self.check and must:
                text = (
                    f"The Tester found {len(must)} Must fix in your files. "
                    f"Result: {LABEL_NOT_PASSING}."
                )
                self._close(tx, False, 0, LABEL_NOT_PASSING, text)
            elif must and used >= limit:
                text = (
                    f"I used all {used} rounds and the Tester's Must fix is still open. "
                    f"Result: {LABEL_NOT_PASSING}. I will still write the code files."
                )
                self._close(tx, False, used, LABEL_NOT_PASSING, text)
            elif must:
                self._start_fix_round(tx, last.round, findings)
                return False
            elif self.check:
                text = _passed_text(last.round, label, _counts(saved), zones, self._cases)
                text = text.replace(" Writing your code files now.", " Nothing was written.")
                self._close(tx, True, 0, label, text)
            else:
                text = _passed_text(last.round, label, _counts(saved), zones, self._cases)
                self._close(tx, True, used, label, text)
            self._unable_twice(tx, saved)
        return True

    def _unable_twice(self, tx: BuildTx, saved: ReviewRecord) -> None:
        """Escalation trigger 4 (spec section 7): two reviews of this request ended Unable to
        assess. Same transaction as the review. Skipped when the request cannot move to a senior
        from its status now (the next review will count again)."""
        if saved.result != "unable":
            return
        if STATUS_ESCALATION not in ALLOWED_MOVES.get(tx.request.status, ()):
            return
        numbers = unable_review_numbers(tx.conn, self.request_id)
        last = last_fired_count(tx.conn, self.request_id, TESTER_UNABLE_TWICE)
        decision = tester_unable_twice(self.inp.policy.escalation_triggers, numbers, last)
        if open_escalation(tx.conn, self.request_id, decision, tx.now).opened:
            tx.move_to(STATUS_ESCALATION)

    def _finish_rerun(self, tx: BuildTx, saved: ReviewRecord, label: str, must: bool) -> None:
        """The end of a re-run: both moves in one transaction. A Must fix ends NOT_PASSING (Gian,
        7 Nov): the build is closed, and fixing it is Phase 8. The run row stays as it was."""
        tx.move_to(STATUS_TESTER_REVIEW)
        tx.move_to(STATUS_NOT_PASSING if must else STATUS_READY_FOR_REVIEW)
        counts = _counts(saved)
        tx.audit(
            "developer",
            "tester_review_rerun",
            {"round": saved.round, "review": saved.review_number, "label": label} | counts,
        )
        shown = LABEL_NOT_PASSING if must else label
        tx.say(
            "assistant",
            f"The Tester reviewed round {saved.round} again: {counts['must_fix']} Must fix, "
            f"{counts['should_fix']} Should fix, {counts['fyi']} FYI. Result: {shown}.",
        )
        tx.set()  # the revision goes up, so an old window is refused

    def _start_fix_round(self, tx: BuildTx, number: int, findings: list[Finding]) -> None:
        """A Must fix with budget left: back to BUILDING, the next round fixes only the cited
        files. Should fix and FYI never reach the Generator."""
        planned = [_clean(item.path) for item in self.inp.planned]
        fix = tester.files_to_fix(findings, planned)
        tx.move_to(STATUS_BUILDING)
        tx.set(step="b_round_failed", current_round=number)
        names = ", ".join(path.rsplit("/", 1)[-1] for path in fix)
        count = len(tester.must_fix_items(findings))
        tx.audit("system", "round_failed", {"round": number, "files_to_fix": fix, "by": "tester"})
        tx.say(
            "assistant",
            f"Round {number}: the Tester found {count} Must fix. "
            + (f"Fixing only {names}." if len(fix) == 1 else f"Fixing only these files: {names}."),
        )

    def _audit_review(self, tx: BuildTx, saved: ReviewRecord, outcome) -> None:
        if saved.calls > 1:
            tx.audit("system", "tester_review_split", {"calls": saved.calls})
        for attempt in range(1, outcome.attempts - outcome.calls + 1):
            tx.audit("system", "tester_reply_unusable", {"attempt": attempt})
        for item in saved.findings:
            if not item.kept:
                tx.audit(
                    "system",
                    "tester_finding_rejected",
                    {"finding": item.finding_id, "reason": item.reject_reason},
                )
        if saved.result == "unable":
            tx.audit("system", "tester_unable_to_assess", {"round": saved.round})
        counts = _counts(saved)
        tx.audit(
            "system",
            "tester_review_done",
            {"round": saved.round, "review": saved.review_number, "model": saved.model}
            | counts
            | {"zones": self.inp.approach.zones_touched},
        )

    def _note_review(self, tx, saved: ReviewRecord, line: int, seconds: int) -> None:
        counts = _counts(saved)
        if saved.result == "unable":
            text = "Layer C: the Tester's reply could not be used (Unable to assess)"
            state = "failed"
        else:
            text = (
                f"Layer C: {counts['must_fix']} Must fix, {counts['should_fix']} Should fix, "
                f"{counts['fyi']} FYI ({seconds} seconds)"
            )
            if saved.calls > 1:
                text += f". Reviewed file by file ({saved.calls} calls)"
            state = "failed" if counts["must_fix"] else "done"
        self._note(tx, text, state, line)

    # --- helpers ---

    @property
    def _live_steps(self) -> tuple[str, ...]:
        """The steps this run may write in: the running steps, or (a re-run) a finished build."""
        return RERUN_STEPS if self.rerun else RUNNING_STEPS

    @property
    def test_id(self) -> str:
        return self.request_id.lower().replace("-", "_")

    def client(self, role: str):
        # The model per role comes from the request's pinned rulebook version (Phase 11, D-G), so a
        # request keeps its models like it keeps its rules. Empty = the .env model, and then the
        # factory is called exactly as before.
        model = self._pinned_model(role)
        if model:
            return self.client_factory(self.settings, role, model=model)
        return self.client_factory(self.settings, role)

    def _pinned_model(self, role: str) -> str:
        policy = get_rulebook_for_request(self.settings.db_path, self.request_id).rulebook.policy
        return policy.tester_model if role == "tester" else policy.generator_model

    def _alive(self) -> None:
        """Stop quietly if the developer pressed Stop since the last step."""
        with open_db(self.settings.db_path) as conn:
            ensure_build_tables(conn)
            state = read_build_state(conn, self.request_id)
        if state is None or state.build_number != self.inp.state.build_number:
            raise _Cancelled
        if state.step not in RUNNING_STEPS:
            raise _Cancelled

    @contextmanager
    def _turn(self) -> Iterator[BuildTx]:
        """One write transaction. It re-reads the state inside the lock; if the build is no
        longer the running build, nothing is written."""
        with _write(self.settings.db_path) as conn:
            request = _require_request(conn, self.request_id)
            state = read_build_state(conn, self.request_id)
            if (
                state is None
                or state.step not in self._live_steps
                or state.build_number != self.inp.state.build_number
            ):
                raise _Cancelled
            if self.rerun and (
                state.revision != self.inp.state.revision
                or request.status != STATUS_READY_FOR_REVIEW
            ):
                raise StaleRevisionError(STALE_MESSAGE)
            tx = BuildTx(conn, request, state, self.now_fn())
            yield tx
            if tx.dirty:
                save_build_state(conn, tx.state, state.revision, tx.now)

    def _line(self, text: str, state: ProgressState) -> int:
        """Save a new progress line at once, so the page shows what is happening now."""
        number = self.inp.next_line
        self.inp.next_line += 1
        with self._turn() as tx:
            add_progress(
                tx.conn,
                ProgressLine(
                    request_id=self.request_id,
                    build_number=tx.state.build_number,
                    line_number=number,
                    text=text,
                    state=state,
                    started_at=tx.now,
                ),
            )
        return number

    def _note(self, tx: BuildTx, text: str, state: ProgressState, line: int | None = None) -> int:
        """Add a progress line, or a new row for an existing line number (its newest row wins).
        Returns the line number."""
        if line is None:
            line = self.inp.next_line
            self.inp.next_line += 1
        add_progress(
            tx.conn,
            ProgressLine(
                request_id=self.request_id,
                build_number=tx.state.build_number,
                line_number=line,
                text=text,
                state=state,
                started_at=tx.now if state == "running" else None,
                ended_at=tx.now if state in ("done", "failed") else None,
            ),
        )
        return line


def _clean(path: str) -> str:
    return normalise_path(path)


def _parse(text: str) -> ast.Module:
    return ast.parse(text)


def _rounds_used(rounds: list[RoundRecord]) -> int:
    """Rounds against the budget. A Not proven row is the app's problem, so it is not counted."""
    return sum(1 for item in rounds if not (item.layer_b and item.layer_b.not_proven))


def _round_passed(record: RoundRecord) -> bool:
    return record.layer_a.ok and record.layer_b is not None and record.layer_b.ok


def _round_failed_text(
    number: int, layer_a: LayerAResult, layer_b: LayerBResult | None, cases: int, fix: list[str]
) -> str:
    names = ", ".join(path.rsplit("/", 1)[-1] for path in fix)
    only = f"Fixing only {names}." if len(fix) == 1 else f"Fixing only these files: {names}."
    if not layer_a.ok:
        return f"Round {number}: {len(layer_a.problems)} problem(s) in the code checks. {only}"
    if layer_b is not None and layer_b.timed_out:
        return f"Round {number}: the tests ran out of time. {only}"
    failed = layer_b.failed if layer_b else 0
    return f"Round {number}: {failed} of {cases} tests failed. {only}"


def _counts(review: ReviewRecord) -> dict[str, int]:
    """Kept findings by severity, and how many were dropped by the evidence rule."""
    kept = [item for item in review.findings if item.kept]
    return {
        "must_fix": sum(1 for item in kept if item.severity == "must_fix"),
        "should_fix": sum(1 for item in kept if item.severity == "should_fix"),
        "fyi": sum(1 for item in kept if item.severity == "fyi"),
        "dropped": len(review.findings) - len(kept),
    }


def _passed_text(round_number: int, label: str, counts: dict, zones: list, cases: int) -> str:
    """The chat line when the Tester review ends the build well (green, yellow or grey)."""
    if label == LABEL_UNABLE:
        review = "The Tester's reply could not be used, so I could not assess the code."
    else:
        review = (
            f"Tester review of round {round_number}: {counts['must_fix']} Must fix, "
            f"{counts['should_fix']} Should fix, {counts['fyi']} FYI."
        )
        if zones:
            review += f" Touches the {', '.join(zones)} zone."
    return (
        f"All {cases} tests passed in round {round_number}. {review} Result: {label}. "
        "Writing your code files now."
    )


def _finish_text(
    passed: bool, rounds: int, label: str, records: list[RoundRecord], cases: int
) -> str:
    if passed:
        return f"All {cases} tests passed in round {rounds}. Result: {label}."
    last = records[-1].layer_b if records else None
    still_writing = "I will still write the code files so you can see them."
    if last is None:
        # Layer A stopped the last round, so no test ran in it. "0 tests still fail" would be
        # untrue (Phase 6 fixes, F9a).
        ran_before = any(record.layer_b is not None for record in records)
        what = (
            "The code checks failed in the last round, so the tests did not run in it."
            if ran_before
            else "The code checks failed in every round, so the tests never ran."
        )
        return f"{what} Result: {label}. {still_writing}"
    return (
        f"I used all {rounds} rounds and {last.failed} test(s) still fail. "
        f"Result: {label}. {still_writing}"
    )
