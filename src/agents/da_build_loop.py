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
    add_progress,
    ensure_build_tables,
    insert_build_file,
    insert_round,
    read_build_state,
    read_frozen_files,
    read_latest_code,
    read_progress,
    read_rounds,
    save_build_state,
)
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from db_table_functions.db_tbl_da_understand import read_confirmed_record
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables, read_file_versions
from pydantic_classes.da_approach_models import ApproachVersion, PlannedFile, TestCase
from pydantic_classes.da_build_models import (
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
from pydantic_classes.da_models import STATUS_READY_TO_BUILD, Request
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Charter, Policy

logger = get_logger(__name__)

# At home the fake provider builds against this made-up CodeVision-shaped folder when
# DA_SANDBOX_SOURCE_DIR is not set (spec section 11).
FIXTURE_REFERENCE = PROJECT_ROOT / "tests" / "fixtures" / "da_reference_codevision"
CONTRACT_FILE = "contract.json"


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
    planned: list[PlannedFile] = field(init=False)

    def __post_init__(self) -> None:
        self.planned = list(self.approach.plan.files)


def run_build(
    settings: Settings,
    request_id: str,
    client_factory: Callable[[Settings, str], object] | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> str:
    """Run (or resume) the running build of a request to its end. Returns what happened:
    `done`, `interrupted`, `unable` or `cancelled`. Never raises for anything the code or the AI
    did; an unexpected error pauses the build with a plain message instead of leaving it
    marked running for ever."""
    run = _Run(settings, request_id, client_factory or agent.get_build_client, now_fn)
    return run.go()


class _Run:
    def __init__(self, settings, request_id, client_factory, now_fn):
        self.settings = settings
        self.request_id = request_id
        self.client_factory = client_factory
        self.now_fn = now_fn or (lambda: datetime.now(UTC))
        self.inp: _Inputs
        self.reference: Path
        self.context: agent.BuildContext
        self._layer_b_line: int | None = None

    # --- the top ---

    def go(self) -> str:
        try:
            self._load()
            self._check_environment()
            contract, tests = self._frozen()
            return self._rounds(contract, tests)
        except _Cancelled:
            return "cancelled"
        except _Paused as paused:
            return self._pause(paused.kind, paused.message)
        except Exception as error:  # noqa: BLE001 - a thread must never die silently
            logger.exception("The build stopped on an unexpected error.")
            if not hasattr(self, "inp"):
                return "interrupted"  # nothing was read yet; start-up recovery will pick it up
            return self._pause(
                "interrupted", f"An unexpected error stopped the build ({type(error).__name__})."
            )

    def _pause(self, kind: str, message: str) -> str:
        try:
            with self._turn() as tx:
                rounds_used = len(self.inp.rounds)
                tx.audit("system", "build_interrupted", {"why": message, "kind": kind})
                if kind == "unable":
                    tx.close_run(STATUS_READY_TO_BUILD, LABEL_UNABLE, message, rounds_used)
                    tx.move_to(STATUS_READY_TO_BUILD)
                    tx.set(step="b_unable", message=message)
                    tx.say("assistant", f"{UNABLE_MESSAGE} Result: {LABEL_UNABLE}.")
                else:
                    tx.set(step="b_interrupted", message=message)
                    tx.say("assistant", f"The build paused: {message}")
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
            conn.execute("BEGIN")
            request = _require_request(conn, self.request_id)
            state = read_build_state(conn, self.request_id)
            if state is None or state.step not in RUNNING_STEPS:
                raise _Cancelled
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
            self.inp = _Inputs(
                request=request,
                state=state,
                charter=rulebook.charter,
                policy=rulebook.policy,
                record=record,
                approach=approach,
                cases=plans[approach_state.accepted_plan_version].cases,
                start_texts=starts,
                frozen=read_frozen_files(conn, self.request_id, state.approach_version),
                rounds=read_rounds(conn, self.request_id, number),
                code=read_latest_code(conn, self.request_id, number),
                next_line=(progress[-1].line_number + 1) if progress else 1,
            )
        self.context = agent.BuildContext(
            charter=self.inp.charter,
            record=self.inp.record,
            approach=self.inp.approach,
            cases=self.inp.cases,
            policy=self.inp.policy,
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
        return contract, self.inp.frozen["test"].text

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
        limit = self.inp.policy.build_max_rounds
        while True:
            done = self.inp.rounds
            if done and _round_passed(done[-1]):
                return self._finish(True, len(done))  # saved, but the finish was not
            if len(done) >= limit:
                return self._finish(False, len(done))
            number = len(done) + 1
            passed = self._one_round(number, contract, tests)
            if passed:
                return self._finish(True, number)
            if number >= limit:
                return self._finish(False, number)

    def _one_round(self, number: int, contract: Contract, tests: str) -> bool:
        limit = self.inp.policy.build_max_rounds
        if number == 1:
            to_write = [_clean(item.path) for item in self.inp.planned]
        else:
            to_write = self.inp.rounds[-1].files_to_fix
        with self._turn() as tx:
            tx.set(step="b_running", current_round=len(self.inp.rounds))
            self._note(tx, f"Round {number} of {limit}", "done")
        failures = ""
        if self.inp.rounds and self.inp.rounds[-1].failure_report:
            failures = report_for_generator(self.inp.rounds[-1].failure_report)
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
        prompt = agent.build_code_prompt(
            self.context, contract, path, action, number, tests, base, failures
        )
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
                    made_by="generator",
                ),
                tx.now,
            )
            self.inp.code[path] = saved
            tx.audit("system", "code_generated", {"path": path, "round": number})
            self._note(tx, f"AI wrote {name}", "failed" if problems else "done", line)
        return text, problems

    def _saved_this_round(self, path: str, number: int) -> BuildFile | None:
        saved = self.inp.code.get(path)
        return saved if saved is not None and saved.round == number else None

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
        return LayerAResult(
            problems=problems + found.problems,
            rulebook_checks_applied=found.rulebook_checks_applied,
        )

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
            if not passed:
                tx.audit("system", "round_failed", {"round": number, "files_to_fix": fix})
                if number < limit:
                    tx.set(step="b_round_failed", current_round=number)
                    tx.say(
                        "assistant",
                        _round_failed_text(number, layer_a, layer_b, len(self.inp.cases), fix),
                    )
        self.inp.rounds.append(record)
        return passed

    # --- the end (spec section 8) ---

    def _finish(self, passed: bool, rounds_used: int) -> str:
        status, label = result_for(passed)
        with self._turn() as tx:
            tx.close_run(status, label, "", rounds_used)
            tx.move_to(status)
            tx.set(step="b_done", current_round=rounds_used, write_state="not_written", message="")
            event = "build_passed" if passed else "build_not_passing"
            tx.audit(
                "system",
                event,
                {
                    "rounds": rounds_used,
                    "label": label,
                    "zones_touched": self.inp.approach.zones_touched,
                },
            )
            tx.say(
                "assistant",
                _finish_text(passed, rounds_used, label, self.inp.rounds, len(self.inp.cases)),
            )
            self._note(tx, "Layer C: independent Tester review (coming in Phase 7)", "pending")
        return "done"

    # --- helpers ---

    @property
    def test_id(self) -> str:
        return self.request_id.lower().replace("-", "_")

    def client(self, role: str):
        return self.client_factory(self.settings, role)

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
                or state.step not in RUNNING_STEPS
                or state.build_number != self.inp.state.build_number
            ):
                raise _Cancelled
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

    def _note(self, tx: BuildTx, text: str, state: ProgressState, line: int | None = None) -> None:
        """Add a progress line, or a new row for an existing line number (its newest row wins)."""
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


def _clean(path: str) -> str:
    return normalise_path(path)


def _parse(text: str) -> ast.Module:
    return ast.parse(text)


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


def _finish_text(
    passed: bool, rounds: int, label: str, records: list[RoundRecord], cases: int
) -> str:
    if passed:
        return (
            f"All {cases} tests passed in round {rounds}. Result: {label}. "
            "The independent Tester review (Layer C) is not built yet. Writing your code files now."
        )
    last = records[-1].layer_b if records else None
    left = last.failed if last else 0
    return (
        f"I used all {rounds} rounds and {left} test(s) still fail. Result: {label}. "
        "I will still write the code files so you can see them."
    )
