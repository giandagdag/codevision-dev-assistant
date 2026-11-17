"""Data shapes for the Build + test loop (Phase 6): the contract, the Generator's replies, the
results of Layer A and Layer B, the failure report, and what is saved.

Plain code builds and checks all of these (da_build_checks.py), so the rules can be tested with
made-up values and no AI. Think of the contract as the agreed parameter list of a called program
(PR/PI in RPG): names and arguments, no bodies.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN
from pydantic_classes.da_tester_models import TesterView

# Where the build is. "start" is not a saved row state of a running build: it means no build is
# running (no row yet, or the last build was stopped). b_prescan is shown by the browser only,
# like ws_picking in Phase 5, so it is never saved.
BuildStep = Literal[
    "start",
    "b_running",
    "b_round_failed",
    "b_tester_review",
    "b_interrupted",
    "b_done",
    "b_written",
    "b_write_stopped",
    "b_conflicts",  # Phase 8: the build is done, the write waits for his picks per conflict
    "b_unable",
    "escalated",
]
# Whether the code files are in the developer's folder yet.
WriteState = Literal["not_written", "written", "stopped"]
FileKind = Literal["contract", "test", "code"]
MadeBy = Literal["generator", "tester", "system", "merge"]  # merge: his picks (Phase 8)
TestResultKind = Literal[
    "pass", "fail", "error", "skipped", "expected_failure", "unexpected_success", "not_proven"
]
ProgressState = Literal["pending", "running", "done", "failed"]
ContractKind = Literal["function", "class"]

# The label shown to the developer (Phase 7 spec section 8). Never "Approved".
LABEL_READY = "Ready for your review"
LABEL_WITH_WARNINGS = "Ready with warnings"
LABEL_NOT_PASSING = "Not passing"
LABEL_UNABLE = "Unable to assess"

NAME_LIMIT = 100
TEXT_LIMIT = 300
MAX_CONTRACT_ITEMS = 30
MAX_EDITS = 20


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- the contract (spec section 3, step 1) ---


class ContractItem(_Shape):
    """One public name a planned file will have (or already has)."""

    name: str = Field(min_length=1, max_length=NAME_LIMIT)
    kind: ContractKind
    # Argument names in order. For a class: the arguments of __init__ (without self).
    args: list[str] = Field(default_factory=list, max_length=15)
    summary: str = Field(min_length=1, max_length=TEXT_LIMIT)


class ContractFile(_Shape):
    path: str = Field(min_length=1, max_length=200)
    items: list[ContractItem] = Field(max_length=MAX_CONTRACT_ITEMS)


class Contract(_Shape):
    files: list[ContractFile] = Field(min_length=1, max_length=12)


# --- the Generator's reply for one file (decision D-C, plan P6) ---


class FileEdit(_Shape):
    """An edit block: find this exact text (must appear once), replace it with this."""

    find: str = Field(min_length=1)
    replace: str


class CodeReply(_Shape):
    """A new file sends `text`; an existing file sends `edits`. Exactly one of the two."""

    text: str | None = None
    edits: list[FileEdit] | None = Field(default=None, max_length=MAX_EDITS)


# --- Layer A (plain code checks) ---


class LayerAProblem(_Shape):
    code: str  # A1 to A7, or E1 for an edit block that did not match
    path: str
    text: str


class LayerAResult(_Shape):
    problems: list[LayerAProblem] = Field(default_factory=list)
    # How many plain-code rulebook rules ran (plan P2: none exist today).
    rulebook_checks_applied: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems


# --- Layer B (the sandbox) ---


class EvidenceLine(_Shape):
    """One recorded check inside a test (Fix D1): what went in, what was expected, what came out.
    Each value is the repr() text, cut at 500 characters (`cut` says so)."""

    label: str
    given: str
    expected: str
    actual: str
    match: bool
    cut: bool = False


class TestOutcome(_Shape):
    """What one test did. The runner writes these into results.json."""

    __test__ = False  # not a pytest class

    name: str
    result: TestResultKind
    message: str = ""
    # The last 20 lines of the traceback, cut by the runner.
    traceback_tail: list[str] = Field(default_factory=list, max_length=20)
    # Fix D1: empty for a row saved before D1 (so it still loads) or a test that recorded none.
    evidence: list[EvidenceLine] = Field(default_factory=list)


# Every result that blocks a pass but was reported (Not proven is the app's problem, not these).
NOT_PASSING = ("fail", "error", "skipped", "expected_failure", "unexpected_success")


class LayerBResult(_Shape):
    # False when the sandbox could not run at all (not the code's fault: b_interrupted).
    ran: bool = True
    timed_out: bool = False
    # The test that was running when the time limit ended the run.
    running_test: str = ""
    output_cut: bool = False
    # What the run printed, cut at 200 KB by the sandbox (spec section 6).
    output: str = ""
    tests: list[TestOutcome] = Field(default_factory=list)
    error: str = ""
    # B1 P26: True for runs made since F1/F2 (a skip blocks a pass). A record saved earlier lacks
    # the field, so it reads False and keeps the old rule: a skip did not block a pass.
    strict: bool = False

    @property
    def passed(self) -> int:
        return sum(1 for item in self.tests if item.result == "pass")

    @property
    def _blocking(self) -> tuple[str, ...]:
        return NOT_PASSING if self.strict else ("fail", "error")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.tests if item.result in self._blocking)

    @property
    def not_proven(self) -> list[str]:
        """Frozen tests that never reported (F2): the Developer Assistant's problem."""
        return [item.name for item in self.tests if item.result == "not_proven"]

    @property
    def ok(self) -> bool:
        # Pass means proven: every test reported, and every one of them passed.
        return (
            self.ran
            and not self.timed_out
            and bool(self.tests)
            and not any(item.result in self._blocking + ("not_proven",) for item in self.tests)
        )


# --- the failure report ---


class FailureItem(_Shape):
    test_id: str  # T-3
    criterion_id: str  # AC-4
    yours: bool = False
    expected: str  # one plain sentence from the test's docstring
    message: str
    traceback_tail: list[str] = Field(default_factory=list)
    # Phase 9: a safety-net test is told in its own words ("Safety-net test S-4 ... now fails").
    note: str = ""


class FailureReport(_Shape):
    items: list[FailureItem] = Field(default_factory=list)
    layer_a: list[LayerAProblem] = Field(default_factory=list)
    timed_out: bool = False
    running_test: str = ""
    # Planned files to send to the Generator again (decision D-J).
    files_to_fix: list[str] = Field(default_factory=list)


# --- saved rows ---


class BuildState(_Shape):
    """The working state of one request's build (a row in da_build_state)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    build_number: int = Field(default=0, ge=0)
    step: BuildStep = "start"
    approach_version: int = Field(default=0, ge=0)
    # The round in progress, or the last one that finished.
    current_round: int = Field(default=0, ge=0)
    write_state: WriteState = "not_written"
    # Why the build paused, or the plain message for b_unable.
    message: str = ""
    # Phase 8: the status a check run came from (READY_FOR_REVIEW or NOT_PASSING). Stop build on
    # a check run goes back to it. Empty for a normal build.
    return_status: str = ""
    revision: int = Field(default=1, ge=1)


class BuildRun(_Shape):
    """One build (a row in da_build_runs). Updated only to close it."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    build_number: int = Field(ge=1)
    approach_version: int = Field(ge=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    rounds_used: int = Field(default=0, ge=0)
    result_status: str = ""
    label: str = ""
    stop_reason: str = ""
    # Phase 8: a build after a Refine is a rebuild; Check my edits is a check run (no Generator).
    kind: Literal["build", "rebuild", "check"] = "build"


class BuildFile(_Shape):
    """One saved file of a build (da_build_files, append-only)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    build_number: int = Field(ge=1)
    round: int = Field(ge=0)
    path: str
    kind: FileKind
    text: str
    fingerprint: str
    made_by: MadeBy
    created_at: AwareDatetime | None = None


class RoundRecord(_Shape):
    """One finished round (da_build_rounds, append-only)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    build_number: int = Field(ge=1)
    round: int = Field(ge=1)
    layer_a: LayerAResult
    layer_b: LayerBResult | None = None
    # None when the round passed. Plain code builds it (build_failure_report), not the AI.
    failure_report: FailureReport | None = None
    timed_out: bool = False
    # The planned files the next round will send to the Generator again (decision D-J). Saved so
    # a build that pauses between rounds can pick up exactly where it stopped.
    files_to_fix: list[str] = Field(default_factory=list)
    # Fix D1: the code tests (C-n) run after the requirement tests passed. None = not run.
    code_tests: LayerBResult | None = None
    # Fix D1: code tests dropped as a wrong test, each "C-3: reason". Filled in step 3c.
    dropped_code_tests: list[str] = Field(default_factory=list)
    created_at: AwareDatetime | None = None


class ProgressLine(_Shape):
    """One line of the live progress list (da_build_progress, append-only)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    build_number: int = Field(ge=1)
    line_number: int = Field(ge=1)
    text: str
    state: ProgressState
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None


# --- what the screen shows (Build tab, Tests tab, chat buttons) ---


class TestRow(BaseModel):
    """One line of the frozen test list on the Tests tab."""

    __test__ = False

    test_id: str
    criterion_id: str
    yours: bool = False
    # Phase 8: "New" (requirement lane), "Bug" (repro test) or "Yours"; "" for a plain test.
    tag: str = ""
    description: str
    # The newest result of this test: pass, fail, error, skipped, or "" when it has not run.
    result: str = ""
    # Phase 8 fix 1 (F1): a new case waiting for his choice; shown in orange, not a result.
    pending: str = ""
    # Fix D1: what the test recorded (empty for an old test).
    evidence: list[EvidenceLine] = Field(default_factory=list)


class BuildFileRow(BaseModel):
    """One line of the Build tab file table."""

    path: str
    action: str
    status: str


class BuildView(BaseModel):
    """Everything the screen needs to draw the build of one request."""

    state: BuildState
    # The revision a window sends back with its next action. 0 means no build row yet.
    revision: int
    request_status: str
    banner_kind: str = ""  # "", "blue", "red", "green" or "orange"
    banner_text: str = ""
    run: BuildRun | None = None
    progress: list[ProgressLine] = Field(default_factory=list)
    rounds: list[RoundRecord] = Field(default_factory=list)
    max_rounds: int = 3
    time_limit: int = 60
    tests: list[TestRow] = Field(default_factory=list)
    # Fix D1: the C-n code tests of the newest tested round (not frozen; written per build).
    code_tests: list[TestRow] = Field(default_factory=list)
    # Phase 8: "Test set version 3, approach version 2" (empty before any Refine added a test).
    tests_note: str = ""
    # True when a round ran but the tests never did, because the code checks (Layer A) failed.
    tests_not_run: bool = False
    test_code: str = ""
    rows: list[BuildFileRow] = Field(default_factory=list)
    label: str = ""
    # Server buttons (Cancel build, Resume build, Get help...) and browser buttons (Build...).
    buttons: list[tuple[str, str]] = Field(default_factory=list)
    browser_buttons: list[tuple[str, str]] = Field(default_factory=list)
    note: str = ""
    # The page asks again every 3 seconds while this is true, and writes by itself when it is.
    polling: bool = False
    auto_write: bool = False
    folder_name: str = ""
    mode: str = "picker"
    seconds_taken: int = 0
    tests_passing: str = ""
    # Fix D1: the summary line of the newest round and whether a saved report exists.
    report_summary: str = ""
    has_report: bool = False
    # Phase 7: the Tester's report, added by da_tester_flow.get_build_view (not by the build flow).
    tester: TesterView | None = None
