"""The Approach actions the screen calls (spec section 1). Thin, like da_discover_flow.

Each action reads with no lock held, makes its one AI call, and only then opens ONE write
transaction that saves versions, state, status moves, audit events and chat lines together
(rule G2). So nothing is ever half-saved. Approach keeps its own revision number for the
stale-window check.

The one exception is Accept approach, which saves twice on purpose: the first save accepts the
approach and parks the request at the saved step `tests_pending`; the Tester is then called with
no lock held; the second save writes the test plan. If the Tester fails, the approach stays
accepted and the button "Write the test plan" retries it.

The Generator and the Tester only suggest. The steps, statuses and the gate are decided here.
Like a change form that goes through two sign-offs, in a fixed order, with every move journaled.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agents.da_approach_agent import (
    ApproachContext,
    ApproachResult,
    generate_approach,
    get_approach_client,
)
from agents.da_approach_checks import (
    CHANGE,
    NO_CRITERION_MESSAGE,
    PROPOSE,
    SETTLE,
    case_text_problem,
    change_text_problem,
    compute_gate,
    compute_warnings,
    custom_answer_problem,
    folder_for_tests,
    gate_problem_lines,
    limit_reason_problem,
)
from agents.da_llm_client import LLMClient, LLMClientError
from agents.da_tester_agent import (
    CASE_STEP,
    PLAN_STEP,
    draft_test_case,
    get_tester_client,
    write_test_plan,
)
from configs.da_config import ConfigError, Settings
from da_logging import get_logger
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_approach import (
    ApproachError,
    confirmed_discovery_round,
    confirmed_round_record_version,
    ensure_approach_tables,
    first_call_failed,
    highest_test_number,
    insert_approach_version,
    insert_test_plan,
    read_approach_revision,
    read_approach_state,
    read_latest_approach,
    read_latest_plan,
    save_approach_state,
)
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_discovery import count_rounds, read_latest_result
from db_table_functions.db_tbl_da_requests import (
    get_rulebook_for_request,
    read_request,
    update_request,
)
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    add_message,
    read_confirmed_record,
    read_messages,
)
from pydantic_classes.da_approach_models import (
    MAX_CHANGES,
    MAX_DEVELOPER_CASES,
    ApproachDecision,
    ApproachState,
    ApproachStep,
    ApproachVersion,
    ApproachView,
    TestCase,
    TestPlanVersion,
)
from pydantic_classes.da_discovery_models import DiscoveryResult
from pydantic_classes.da_models import (
    STATUS_APPROACH_PROPOSED,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_ESCALATION,
    STATUS_READY_TO_BUILD,
    Actor,
    Request,
    display_status,
)
from pydantic_classes.da_request_record_models import RequestRecord, Speaker
from pydantic_classes.da_rulebook_models import RulebookVersion

logger = get_logger(__name__)

APPROACH_DIVIDER = "🧭 Approach"

# Button labels (the screen shows these; the keys below say which action each stands for).
PROCEED_OPTION = "Proceed to Approach"
TRY_AGAIN_OPTION = "Try again"
ACCEPT_APPROACH_OPTION = "Accept approach"
CHANGE_OPTION = "Change something"
HELP_BUTTON = "Get help"
WRITE_PLAN_OPTION = "Write the test plan"
ACCEPT_PLAN_OPTION = "Accept test plan"
ADD_CASE_OPTION = "Add a test case"
CHANGE_APPROACH_OPTION = "Change the approach"
# At the test plan step it is a secondary button that goes back (Phase 6 fixes, F5).
GO_BACK_OPTION = "Go back and change the approach"
KEEP_CASE_OPTION = "Keep this case"
DISCARD_CASE_OPTION = "Discard it"
HELP_DECIDING_OPTION = "I need help deciding"

# Button keys.
START_KEY = "start"
CHOOSE_KEY = "choose"
DECIDE_HELP_KEY = "decide_help"
ACCEPT_KEY = "accept"
CHANGE_KEY = "change"
HELP_KEY = "help"
WRITE_PLAN_KEY = "write_plan"
ACCEPT_PLAN_KEY = "accept_plan"
CHANGE_APPROACH_KEY = "change_approach"
KEEP_KEY = "keep"
DISCARD_KEY = "discard"

HELP_PREFIX = "Help requested: "
ESCALATED_PREFIX = "Escalated in Approach: "
TEXT_PROMPTS: dict[str, str] = {
    "choices": "Other, type here",
    "change": "What should change? (up to 1,000 characters)",
    "limit_reason": "Why are this many files needed? (10 to 300 characters)",
    "case_text": "Type your test case in plain words (up to 500 characters)",
}
# The text box is open at these steps and the Send button carries the action's name (Phase 6
# fixes, section 2): typing and pressing Send means "Change something" or "Add a test case".
TYPING_PROMPTS: dict[str, str] = {
    "review": "Type what should change, then press Change something.",
    "tests": "Type a test case in plain words, then press Add a test case.",
}
SEND_LABELS: dict[str, str] = {"review": "Change something", "tests": "Add a test case"}
CASE_CAP_MESSAGE = (
    f"You already added {MAX_DEVELOPER_CASES} test cases of your own. That is the limit."
)
CAP_MESSAGE = (
    f"You have used all {MAX_CHANGES} changes, so you can only accept the approach or get help."
)
NOT_REACHABLE = "The AI could not be reached or gave an answer the app could not use."


@dataclass
class _Snap:
    """What one action read before its AI call. Nothing here is written back directly."""

    request: Request
    record: RequestRecord
    discovery: DiscoveryResult | None
    state: ApproachState | None
    approach: ApproachVersion | None
    plan: TestPlanVersion | None
    developer_text: str


@dataclass
class _Turn:
    """One action's work inside its write transaction."""

    conn: sqlite3.Connection
    request: Request
    state: ApproachState
    now: datetime

    def say(self, speaker: Speaker, text: str) -> None:
        add_message(self.conn, self.request.request_id, speaker, text, self.now)

    def audit(self, actor: Actor, event_type: str, details: dict | None = None) -> None:
        insert_audit_event(
            self.conn, self.request.request_id, actor, event_type, details, self.now
        )

    def move_to(self, status: str) -> None:
        """One status move through the spec table, audited in the same transaction."""
        if self.request.status == status:
            return
        old = self.request.status
        self.request = update_request(
            self.conn, self.request.request_id, now=self.now, status=status
        )
        self.audit("system", "status_changed", {"from": old, "to": status})


# --- the actions the screen calls ---


def start_approach(
    settings: Settings,
    request_id: str,
    base_revision: int,
    generator: LLMClient | None = None,
    now: datetime | None = None,
) -> ApproachView:
    """Proceed to Approach (or Try again): the first Generator call, from DISCOVERY_CONFIRMED."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    if snap.request.status != STATUS_DISCOVERY_CONFIRMED or snap.state is not None:
        raise ApproachError(_wrong_step_message(snap))
    if snap.discovery is None:
        raise ApproachError("Discover has no saved round, so the approach cannot start.")
    pinned = get_rulebook_for_request(settings.db_path, request_id)
    context = _context(pinned, snap)
    result = _generate(settings, PROPOSE, context, generator)
    if not result.ok:
        with _write_transaction(settings.db_path) as conn:
            if read_approach_revision(conn, request_id) != base_revision:
                # Another window already acted (for example a double click on Try again).
                raise StaleRevisionError(STALE_MESSAGE)
            _say(conn, request_id, "system", APPROACH_DIVIDER, now)
            _say(conn, request_id, "assistant", _failure_text(result, "make a plan"), now)
            insert_audit_event(
                conn, request_id, "system", "approach_failed",
                {"provider": result.provider, "problems": result.problems[:5]}, now,
            )
        return get_approach_view(settings, request_id)

    version = _new_version(snap, pinned, result, PROPOSE, 1, [])
    state = ApproachState(
        request_id=request_id,
        step="choices" if result.reply.design_choices else "review",
        pending_choices=result.reply.design_choices,
    )
    with _write_transaction(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        turn = _Turn(conn, request, state, now)
        turn.state = save_approach_state(conn, state, base_revision, now)
        insert_approach_version(conn, version, now)
        turn.move_to(STATUS_APPROACH_PROPOSED)
        turn.audit("llm", "approach_proposed", _version_details(version))
        turn.say("system", APPROACH_DIVIDER)
        turn.say("assistant", _proposal_text(version))
        if state.pending_choices:
            turn.say("assistant", _ask_text(state.pending_choices[0]))
    logger.info("Approach proposed for %s", request_id)
    return get_approach_view(settings, request_id)


def choose_design_option(
    settings: Settings,
    request_id: str,
    option: str,
    base_revision: int,
    generator: LLMClient | None = None,
    now: datetime | None = None,
) -> ApproachView:
    """The developer presses a design-choice button (or "I need help deciding")."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "choices")
    pending = snap.state.pending_choices[0]
    if option == HELP_DECIDING_OPTION:
        _ask_for_help(settings, snap, pending.question, base_revision, now)
    elif option in pending.options:
        _answer_choice(settings, snap, option, False, base_revision, generator, now)
    else:
        raise ApproachError(
            f"'{option}' is not one of the choices. Choose one of: "
            f"{', '.join([*pending.options, HELP_DECIDING_OPTION])}."
        )
    return get_approach_view(settings, request_id)


def submit_text(
    settings: Settings,
    request_id: str,
    text: str,
    base_revision: int,
    generator: LLMClient | None = None,
    tester: LLMClient | None = None,
    now: datetime | None = None,
) -> ApproachView:
    """Typed text. What it means depends on the step (rule G1): a custom design answer, a
    change, the reason for more files than the limit, or a test case. At the review and tests
    steps the text box is always open and Send is the action (Phase 6 fixes, section 2)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    step = snap.state.step if snap.state else "start"
    if step == "choices":
        pending = snap.state.pending_choices[0]
        problem = custom_answer_problem(text)
        if problem:
            raise ApproachError(problem)
        typed = text.strip()
        if typed == HELP_DECIDING_OPTION:
            _ask_for_help(settings, snap, pending.question, base_revision, now)
        else:
            custom = typed not in pending.options
            _answer_choice(settings, snap, typed, custom, base_revision, generator, now)
    elif step == "review":
        # Typing + Send is "Change something" (Phase 6 fixes). At most 3 changes (rule G9).
        if snap.state.change_count >= MAX_CHANGES:
            raise ApproachError(CAP_MESSAGE)
        _change(settings, snap, text, base_revision, generator, now)
    elif step == "tests":
        # Typing + Send is "Add a test case". At most 5 developer cases.
        _draft_case(settings, snap, text, base_revision, tester, now)
    elif step == "change":
        _change(settings, snap, text, base_revision, generator, now)
    elif step == "limit_reason":
        problem = limit_reason_problem(text)
        if problem:
            raise ApproachError(problem)
        _accept(settings, snap, text.strip(), base_revision, tester, now)
    elif step == "case_text":
        _draft_case(settings, snap, text, base_revision, tester, now)
    else:
        raise ApproachError(_wrong_step_message(snap))
    return get_approach_view(settings, request_id)


def accept_approach(
    settings: Settings,
    request_id: str,
    base_revision: int,
    tester: LLMClient | None = None,
    now: datetime | None = None,
) -> ApproachView:
    """Accept approach. More code files than the limit asks for a reason first (decision D-C)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "review")
    limit = _policy(settings, request_id).max_files
    files = len(snap.approach.plan.files)
    if files > limit:
        with _turn(settings.db_path, request_id, base_revision, now) as turn:
            turn.say("developer", ACCEPT_APPROACH_OPTION)
            turn.state.step = "limit_reason"
            turn.say(
                "assistant",
                f"This plan has {files} code files; the limit is {limit}. Splitting the request "
                "is safer. To accept it anyway, type the reason (10 to 300 characters). Or "
                "choose Change something or Get help.",
            )
        return get_approach_view(settings, request_id)
    _accept(settings, snap, "", base_revision, tester, now, label=ACCEPT_APPROACH_OPTION)
    return get_approach_view(settings, request_id)


def request_change(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> ApproachView:
    """Change something at the too-many-files step, where typed text means "the reason", so the
    button opens the change box. Everywhere else typing + Send is the change. At most 3 changes
    per request (rule G9)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "limit_reason")
    if snap.state.change_count >= MAX_CHANGES:
        raise ApproachError(CAP_MESSAGE)
    _open_change_box(settings, request_id, base_revision, now, CHANGE_OPTION, False)
    return get_approach_view(settings, request_id)


def request_plan_change(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> ApproachView:
    """Go back and change the approach (from the tests step, rule G4). It does not count toward
    the 3."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "tests")
    _open_change_box(settings, request_id, base_revision, now, GO_BACK_OPTION, True)
    return get_approach_view(settings, request_id)


def request_help(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> ApproachView:
    """Get help: ESCALATION_REQUIRED with an open item (rule G6). The inbox comes in Phase 10."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    # tests_pending is included so a Tester that stays down is not a dead end (P24).
    _require_step(snap, "review", "limit_reason", "tests_pending", "tests")
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        step = turn.state.step
        open_item = f"{ESCALATED_PREFIX}{step}"
        turn.say("developer", HELP_BUTTON)
        turn.state.open_item = open_item
        turn.state.step = "escalated"
        turn.audit("developer", "escalated", {"step": step, "open_item": open_item})
        turn.move_to(STATUS_ESCALATION)
        turn.say(
            "assistant",
            "A senior developer will pick this up. (The escalations inbox comes in Phase 10.)",
        )
    return get_approach_view(settings, request_id)


def write_test_plan_again(
    settings: Settings,
    request_id: str,
    base_revision: int,
    tester: LLMClient | None = None,
    now: datetime | None = None,
) -> ApproachView:
    """Write the test plan: the retry button after the Tester failed (step tests_pending)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "tests_pending")
    _run_tester(settings, request_id, base_revision, tester, now, say_button=WRITE_PLAN_OPTION)
    return get_approach_view(settings, request_id)


def keep_case(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> ApproachView:
    """Keep this case: the draft becomes the next T-number, "Yours", in a new plan version."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "case_check")
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        draft = turn.state.draft_case
        plan = read_latest_plan(turn.conn, request_id)
        number = highest_test_number(turn.conn, request_id) + 1
        case = TestCase(
            test_id=f"T-{number}", criterion_id=draft.criterion_id, given=draft.given,
            expect=draft.expect, source="developer",
        )
        saved = TestPlanVersion(
            request_id=request_id,
            plan_version=plan.plan_version + 1,
            approach_version=plan.approach_version,
            cases=[*plan.cases, case],
            source_of_change="developer_case",
            model=plan.model,
        )
        insert_test_plan(turn.conn, saved, now)
        turn.state.draft_case = None
        turn.state.step = "tests"
        turn.say("developer", KEEP_CASE_OPTION)
        turn.audit(
            "developer", "test_case_kept",
            {"test_id": case.test_id, "criterion_id": case.criterion_id,
             "plan_version": saved.plan_version},
        )
        turn.say(
            "assistant",
            f"Added as test {case.test_id}, marked as yours. {len(saved.cases)} test cases in "
            "total. Do you accept the test plan?",
        )
    return get_approach_view(settings, request_id)


def discard_case(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> ApproachView:
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "case_check")
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        turn.state.draft_case = None
        turn.state.step = "tests"
        turn.say("developer", DISCARD_CASE_OPTION)
        turn.audit("developer", "test_case_discarded")
        turn.say("assistant", "Discarded. Nothing was added to the test plan.")
    return get_approach_view(settings, request_id)


def accept_test_plan(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> ApproachView:
    """Accept test plan: runs the gate. All 4 checks true gives READY_TO_BUILD (section 6)."""
    now = now or datetime.now(UTC)
    snap = _snapshot(settings, request_id, base_revision)
    _require_step(snap, "tests")
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        plan = read_latest_plan(turn.conn, request_id)
        turn.say("developer", ACCEPT_PLAN_OPTION)
        turn.state.accepted_plan_version = plan.plan_version
        turn.audit("developer", "test_plan_accepted", {"plan_version": plan.plan_version})
        checks = _gate(turn.conn, turn.request, turn.state)
        failed = gate_problem_lines(checks)
        if failed:
            listed = "\n".join(f"- {line}" for line in failed)
            turn.say(
                "assistant",
                f"Not ready to build yet. These checks are not true:\n{listed}",
            )
        else:
            turn.state.step = "done"
            turn.move_to(STATUS_READY_TO_BUILD)
            turn.audit("system", "gate_passed", {"checks": [c.name for c in checks]})
            turn.say(
                "assistant",
                "All 4 gates passed. READY TO BUILD. The next step is choosing your workspace "
                "folder with the button below.",
            )
    return get_approach_view(settings, request_id)


def has_approach(settings: Settings, request_id: str) -> bool:
    """True once the first approach has been saved (so ESCALATION_REQUIRED can be told apart:
    escalated in Approach, or earlier in Discover)."""
    with open_db(settings.db_path) as conn:
        ensure_approach_tables(conn)
        return read_approach_revision(conn, request_id) > 0


def get_approach_view(settings: Settings, request_id: str) -> ApproachView:
    """Everything the screen needs to show Approach, read on one connection so the status, the
    state and the chat always match each other."""
    with open_db(settings.db_path) as conn:
        ensure_approach_tables(conn)
        ensure_audit_table(conn)
        conn.execute("BEGIN")
        request = _require_request(conn, request_id)
        record = read_confirmed_record(conn, request_id, request.version)
        if record is None:
            raise ApproachError("This request is not confirmed yet, so Approach cannot show it.")
        state = read_approach_state(conn, request_id)
        approach = read_latest_approach(conn, request_id)
        plan = read_latest_plan(conn, request_id)
        messages = read_messages(conn, request_id)
        discovery = read_latest_result(conn, request_id)
        failed = first_call_failed(conn, request_id)
        checks = (
            _gate(conn, request, state)
            if state
            else compute_gate(record, request.version, None, 0, 0, None, None)
        )
        revision = read_approach_revision(conn, request_id)
    file_limit = _policy(settings, request_id).max_files
    step: ApproachStep = state.step if state else "start"
    buttons, prompt, note = _screen_for(step, state, failed, approach, _developer_cases(plan))
    return ApproachView(
        request=request,
        record=record,
        messages=messages,
        status_label=display_status(request.status),
        step=step,
        discovery=discovery,
        approach=approach,
        plan=plan,
        gate=checks,
        buttons=buttons,
        text_prompt=prompt,
        send_label=SEND_LABELS.get(step, "Send"),
        note=note,
        open_item=state.open_item if state else "",
        draft_case=state.draft_case if state else None,
        change_count=state.change_count if state else 0,
        developer_case_count=_developer_cases(plan),
        tests_folder=folder_for_tests(request_id),
        file_limit=file_limit,
        failed_first_call=failed,
        revision=revision,
        demo_mode=settings.llm_provider == "fake",
    )


# --- the steps behind the actions ---


def _answer_choice(
    settings: Settings,
    snap: _Snap,
    choice: str,
    custom: bool,
    base_revision: int,
    generator: LLMClient | None,
    now: datetime,
) -> None:
    """Record one design answer. After the LAST one, ONE settle call makes the next version."""
    request_id = snap.request.request_id
    pending = snap.state.pending_choices[0]
    decision = ApproachDecision(
        question=pending.question, choice=choice, custom=custom, decided_at=now
    )
    decisions = [*snap.state.decisions, decision]
    remaining = snap.state.pending_choices[1:]
    settled: tuple[ApproachResult, RulebookVersion] | None = None
    if not remaining:
        pinned = get_rulebook_for_request(settings.db_path, request_id)
        context = _context(pinned, snap, decisions=decisions)
        result = _generate(settings, SETTLE, context, generator)
        if not result.ok:
            raise ApproachError(
                _failure_text(result, "settle the plan from your answers")
                + " Nothing was saved, so choose again to retry."
            )
        settled = (result, pinned)

    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        state = turn.state
        turn.say("developer", choice)
        state.decisions = decisions
        state.pending_choices = remaining
        state.open_item = ""
        turn.audit(
            "developer", "design_choice_recorded",
            {"question": pending.question, "choice": choice, "custom": custom},
        )
        if settled is None:
            turn.say("assistant", _ask_text(remaining[0]))
            return
        result, pinned = settled
        version = _new_version(
            snap, pinned, result, SETTLE, snap.approach.approach_version + 1, decisions
        )
        insert_approach_version(turn.conn, version, now)
        state.step = "review"
        turn.audit("llm", "approach_settled", _version_details(version))
        turn.say("assistant", "Noted. I settled the plan from your choices:")
        turn.say("assistant", _proposal_text(version))


def _ask_for_help(
    settings: Settings, snap: _Snap, question: str, base_revision: int, now: datetime
) -> None:
    """"I need help deciding": the request waits with an open item (rule G5)."""
    with _turn(settings.db_path, snap.request.request_id, base_revision, now) as turn:
        turn.say("developer", HELP_DECIDING_OPTION)
        item = HELP_PREFIX + question
        if turn.state.open_item != item:
            turn.state.open_item = item
            turn.audit("developer", "help_requested", {"question": question})
        turn.say(
            "assistant",
            "Help requested. This request will wait here. You can come back and choose at any "
            "time. (A senior escalation inbox comes in a later phase.)",
        )


def _open_change_box(
    settings: Settings,
    request_id: str,
    base_revision: int,
    now: datetime,
    label: str,
    from_tests: bool,
) -> None:
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        turn.say("developer", label)
        turn.state.step = "change"
        turn.state.change_from_tests = from_tests
        turn.say("assistant", TEXT_PROMPTS["change"] + ".")


def _change(
    settings: Settings,
    snap: _Snap,
    text: str,
    base_revision: int,
    generator: LLMClient | None,
    now: datetime,
) -> None:
    """The typed change: one Generator call, then a new approach version (the old one is kept)."""
    problem = change_text_problem(text)
    if problem:
        raise ApproachError(problem)
    typed = text.strip()
    request_id = snap.request.request_id
    pinned = get_rulebook_for_request(settings.db_path, request_id)
    context = _context(pinned, snap, decisions=snap.state.decisions, change_text=typed)
    result = _generate(settings, CHANGE, context, generator)
    if not result.ok:
        raise ApproachError(
            _failure_text(result, "apply your change") + " Nothing was saved. Please try again."
        )
    from_tests = snap.state.change_from_tests
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        state = turn.state
        turn.say("developer", typed)
        turn.audit(
            "developer", "approach_change_requested",
            {"text": typed, "from_tests": from_tests},
        )
        version = _new_version(
            snap, pinned, result, CHANGE, snap.approach.approach_version + 1, state.decisions
        )
        insert_approach_version(turn.conn, version, now)
        if not from_tests:
            state.change_count += 1
        state.change_from_tests = False
        state.pending_choices = result.reply.design_choices
        state.step = "choices" if state.pending_choices else "review"
        state.limit_reason = ""
        state.open_item = ""
        turn.audit("llm", "approach_changed", _version_details(version))
        turn.say("assistant", "Changed. Here is the new version:")
        turn.say("assistant", _proposal_text(version))
        if state.pending_choices:
            turn.say("assistant", _ask_text(state.pending_choices[0]))
        elif state.change_count >= MAX_CHANGES and not from_tests:
            turn.say("assistant", CAP_MESSAGE)


def _accept(
    settings: Settings,
    snap: _Snap,
    reason: str,
    base_revision: int,
    tester: LLMClient | None,
    now: datetime,
    label: str = "",
) -> None:
    """Save 1: the approach is accepted (with the reason if over the file limit). Then the
    Tester writes the test plan (save 2, in _run_tester)."""
    request_id = snap.request.request_id
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        state = turn.state
        version = snap.approach.approach_version
        turn.say("developer", reason or label or ACCEPT_APPROACH_OPTION)
        if reason:
            turn.audit(
                "developer", "file_limit_overridden",
                {"reason": reason, "files": len(snap.approach.plan.files),
                 "limit": _policy(settings, request_id).max_files},
            )
        state.accepted_approach_version = version
        state.limit_reason = reason
        state.step = "tests_pending"
        turn.audit("developer", "approach_accepted", {"approach_version": version})
        turn.say(
            "assistant",
            "Approach accepted. The independent Tester is now writing the test plan from your "
            "acceptance criteria. It does not see the file plan or any code.",
        )
    _run_tester(settings, request_id, base_revision + 1, tester, now)


def _run_tester(
    settings: Settings,
    request_id: str,
    base_revision: int,
    tester: LLMClient | None,
    now: datetime,
    say_button: str = "",
) -> None:
    """Save 2 of Accept approach, or the Write the test plan retry: the Tester's plan."""
    snap = _snapshot(settings, request_id, base_revision)
    decisions = snap.state.decisions
    client, error = _tester_client(settings, PLAN_STEP, tester)
    result = None
    if client is not None:
        result = write_test_plan(client, snap.record, decisions, snap.developer_text)
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        if say_button:
            turn.say("developer", say_button)
        if result is None or not result.ok:
            detail = error or (result.message if result else "") or NOT_REACHABLE
            turn.say(
                "assistant",
                f"The Tester could not write the test plan yet: {detail} "
                "Press Write the test plan to try again.",
            )
            return
        previous = read_latest_plan(turn.conn, request_id)
        kept = [c for c in (previous.cases if previous else []) if c.source == "developer"]
        first = highest_test_number(turn.conn, request_id) + 1
        fresh = [
            TestCase(
                test_id=f"T-{number}", criterion_id=case.criterion_id, given=case.given,
                expect=case.expect, source="tester",
            )
            for number, case in enumerate(result.reply.cases, start=first)
        ]
        cases = sorted([*kept, *fresh], key=lambda c: int(c.test_id.split("-")[1]))
        plan = TestPlanVersion(
            request_id=request_id,
            plan_version=(previous.plan_version + 1) if previous else 1,
            approach_version=turn.state.accepted_approach_version,
            cases=cases,
            source_of_change="tester_plan",
            model=result.model,
        )
        insert_test_plan(turn.conn, plan, now)
        turn.state.step = "tests"
        turn.audit(
            "llm", "test_plan_written",
            {"plan_version": plan.plan_version, "cases": len(cases), "model": result.model},
        )
        criteria = len({case.criterion_id for case in cases})
        turn.say(
            "assistant",
            f"The Tester wrote {len(cases)} test cases covering {criteria} of "
            f"{len(snap.record.acceptance_criteria)} criteria, in plain language. Is anything "
            "missing? You can add your own cases.",
        )


def _draft_case(
    settings: Settings,
    snap: _Snap,
    text: str,
    base_revision: int,
    tester: LLMClient | None,
    now: datetime,
) -> None:
    problem = case_text_problem(text)
    if problem:
        raise ApproachError(problem)
    _require_case_room(snap)
    typed = text.strip()
    client, error = _tester_client(settings, CASE_STEP, tester)
    if client is None:
        raise ApproachError(f"The Tester could not be set up: {error} Nothing was saved.")
    result = draft_test_case(
        client, snap.record, snap.state.decisions, snap.plan.cases, typed, snap.developer_text
    )
    if not result.ok:
        raise ApproachError(
            _failure_text_plain(result.message, "turn that into a test case")
            + " Nothing was saved. Try again or rephrase it."
        )
    with _turn(settings.db_path, snap.request.request_id, base_revision, now) as turn:
        turn.say("developer", typed)
        if result.case is None:
            # No dead end: back to the tests step, nothing saved (planning decision P4).
            turn.state.step = "tests"
            turn.say("assistant", NO_CRITERION_MESSAGE)
            return
        turn.state.draft_case = result.case
        turn.state.step = "case_check"
        turn.audit(
            "llm", "test_case_drafted",
            {"criterion_id": result.case.criterion_id, "model": result.model},
        )
        turn.say(
            "assistant",
            f"Here is the case I drafted for {result.case.criterion_id}:\n"
            f"Given {result.case.given}. Expect {result.case.expect}.\n"
            "Keep this case or discard it.",
        )


# --- helpers ---


def _snapshot(settings: Settings, request_id: str, base_revision: int) -> _Snap:
    """Read before any AI call. Refused early if the window is out of date. Nothing is written."""
    with open_db(settings.db_path) as conn:
        ensure_approach_tables(conn)
        ensure_audit_table(conn)
        conn.execute("BEGIN")
        request = _require_request(conn, request_id)
        if read_approach_revision(conn, request_id) != base_revision:
            raise StaleRevisionError(STALE_MESSAGE)
        record = read_confirmed_record(conn, request_id, request.version)
        if record is None:
            raise ApproachError("This request is not confirmed yet, so Approach cannot start.")
        snap = _Snap(
            request=request,
            record=record,
            discovery=read_latest_result(conn, request_id),
            state=read_approach_state(conn, request_id),
            approach=read_latest_approach(conn, request_id),
            plan=read_latest_plan(conn, request_id),
            developer_text="\n".join(
                m.text for m in read_messages(conn, request_id) if m.speaker == "developer"
            ),
        )
    return snap


@contextmanager
def _write_transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Set up tables before taking the lock: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_audit_table(conn)
        ensure_approach_tables(conn)
        begin_write(conn)
        yield conn


@contextmanager
def _turn(db_path: Path, request_id: str, base_revision: int, now: datetime) -> Iterator[_Turn]:
    """Open one action's transaction, check the revision, and save the state at the end."""
    with _write_transaction(db_path) as conn:
        request = _require_request(conn, request_id)
        state = read_approach_state(conn, request_id)
        if state is None or state.revision != base_revision:
            raise StaleRevisionError(STALE_MESSAGE)
        turn = _Turn(conn, request, state, now)
        yield turn
        save_approach_state(conn, turn.state, base_revision, now)


def _require_request(conn: sqlite3.Connection, request_id: str) -> Request:
    request = read_request(conn, request_id)
    if request is None:
        raise ApproachError(f"Request {request_id} does not exist.")
    return request


def _require_step(snap: _Snap, *steps: str) -> None:
    step = snap.state.step if snap.state else "start"
    if step not in steps:
        raise ApproachError(_wrong_step_message(snap))


def _wrong_step_message(snap: _Snap) -> str:
    step = snap.state.step if snap.state else "start"
    messages = {
        "start": f"Please press {PROCEED_OPTION} first.",
        "choices": "A design choice is waiting. Please choose an option or type your own answer.",
        "review": (
            f"Please choose {ACCEPT_APPROACH_OPTION} or {HELP_BUTTON}, or type what should "
            f"change and press {CHANGE_OPTION}."
        ),
        "change": "Please type what should change first.",
        "limit_reason": "Please type the reason for the number of files first.",
        "tests_pending": f"Please press {WRITE_PLAN_OPTION}.",
        "tests": (
            f"Please choose {ACCEPT_PLAN_OPTION}, {GO_BACK_OPTION} or {HELP_BUTTON}, or type a "
            f"test case and press {ADD_CASE_OPTION}."
        ),
        "case_text": "Please type your test case first.",
        "case_check": f"Please choose {KEEP_CASE_OPTION} or {DISCARD_CASE_OPTION}.",
        "done": "This request is READY TO BUILD. It cannot be changed in this phase.",
        "escalated": "This request was handed to a senior developer.",
    }
    if snap.state is None and snap.request.status != STATUS_DISCOVERY_CONFIRMED:
        return f"Approach cannot start now: the status is {display_status(snap.request.status)}."
    return messages[step]


def _require_case_room(snap: _Snap) -> None:
    if _developer_cases(snap.plan) >= MAX_DEVELOPER_CASES:
        raise ApproachError(CASE_CAP_MESSAGE)


def _developer_cases(plan: TestPlanVersion | None) -> int:
    return sum(1 for case in plan.cases if case.source == "developer") if plan else 0


def _policy(settings: Settings, request_id: str):
    return get_rulebook_for_request(settings.db_path, request_id).rulebook.policy


def _context(
    pinned: RulebookVersion,
    snap: _Snap,
    decisions: list[ApproachDecision] | None = None,
    change_text: str = "",
) -> ApproachContext:
    return ApproachContext(
        charter=pinned.rulebook.charter,
        record=snap.record,
        discovery=snap.discovery,
        policy=pinned.rulebook.policy,
        previous=snap.approach,
        decisions=decisions or [],
        change_text=change_text,
    )


def _generate(
    settings: Settings, call: str, context: ApproachContext, client: LLMClient | None
) -> ApproachResult:
    """One Generator call. A setup problem becomes a failed result, so it is shown in words."""
    try:
        client = client or get_approach_client(settings, call)
    except (ConfigError, LLMClientError) as error:
        return ApproachResult(None, settings.llm_provider, "", 0, [str(error)], str(error))
    return generate_approach(client, call, context)


def _tester_client(
    settings: Settings, step: str, client: LLMClient | None
) -> tuple[LLMClient | None, str]:
    try:
        return (client or get_tester_client(settings, step)), ""
    except (ConfigError, LLMClientError) as error:
        return None, str(error)


def _new_version(
    snap: _Snap,
    pinned: RulebookVersion,
    result: ApproachResult,
    call: str,
    number: int,
    decisions: list[ApproachDecision],
) -> ApproachVersion:
    source = {PROPOSE: "proposal", SETTLE: "settled", CHANGE: "change"}[call]
    warnings, zones = compute_warnings(result.reply, pinned.rulebook.policy, snap.discovery)
    return ApproachVersion(
        request_id=snap.request.request_id,
        approach_version=number,
        source=source,
        record_version=snap.record.version,
        rulebook_version=pinned.version_number,
        discovery_round=snap.discovery.round,
        plan=result.reply,
        decisions=decisions,
        warnings=warnings,
        zones_touched=zones,
        model=result.model,
    )


def _version_details(version: ApproachVersion) -> dict:
    return {
        "approach_version": version.approach_version,
        "files": len(version.plan.files),
        "warnings": len(version.warnings),
        "model": version.model,
    }


def _gate(conn: sqlite3.Connection, request: Request, state: ApproachState | None):
    request_id = request.request_id
    confirmed_round = confirmed_discovery_round(conn, request_id)
    return compute_gate(
        read_confirmed_record(conn, request_id, request.version),
        request.version,
        read_latest_approach(conn, request_id),
        count_rounds(conn, request_id),
        confirmed_round,
        state,
        read_latest_plan(conn, request_id),
        confirmed_round_record_version(conn, request_id, confirmed_round),
    )


def _say(
    conn: sqlite3.Connection, request_id: str, speaker: Speaker, text: str, now: datetime
) -> None:
    add_message(conn, request_id, speaker, text, now)


def _failure_text(result: ApproachResult, what: str) -> str:
    return _failure_text_plain(result.message, what)


def _failure_text_plain(message: str, what: str) -> str:
    return f"I couldn't {what}. {message or NOT_REACHABLE}"


def _proposal_text(version: ApproachVersion) -> str:
    files = len(version.plan.files)
    noun = "code file" if files == 1 else "code files"
    text = (
        f"Approach v{version.approach_version}: {files} {noun} plus the tests, which the Tester "
        f"writes. {version.plan.summary}"
    )
    if version.plan.design_choices:
        text += " One design choice needs you. See the Approach tab."
    else:
        text += " Please check the Approach tab."
    return text


def _ask_text(choice) -> str:
    return (
        f"Design choice: {choice.question}\n{choice.impact}\n"
        "Choose below, or type your own answer."
    )


def _screen_for(
    step: str,
    state: ApproachState | None,
    failed: bool,
    approach: ApproachVersion | None,
    developer_cases: int = 0,
) -> tuple[list[tuple[str, str]], str, str]:
    """The buttons, the text box prompt and a note for one step (spec section 1 table, and the
    Phase 6 fixes section 2 table). A capped box has no prompt: it is shown disabled with the
    cap message (the note)."""
    capped = state is not None and state.change_count >= MAX_CHANGES
    change = [] if capped else [(CHANGE_KEY, CHANGE_OPTION)]
    note = CAP_MESSAGE if capped and step in ("review", "limit_reason") else ""
    prompt = TEXT_PROMPTS.get(step, "")
    if step == "start":
        return [(START_KEY, TRY_AGAIN_OPTION if failed else PROCEED_OPTION)], "", ""
    if step == "choices":
        pending = state.pending_choices[0] if state and state.pending_choices else None
        if pending is None:
            return [], "", ""
        buttons = [(CHOOSE_KEY, option) for option in pending.options]
        return [*buttons, (DECIDE_HELP_KEY, HELP_DECIDING_OPTION)], prompt, ""
    if step == "review":
        return (
            [(ACCEPT_KEY, ACCEPT_APPROACH_OPTION), (HELP_KEY, HELP_BUTTON)],
            "" if capped else TYPING_PROMPTS["review"],
            note,
        )
    if step == "limit_reason":
        return [*change, (HELP_KEY, HELP_BUTTON)], prompt, note
    if step == "tests_pending":
        return [(WRITE_PLAN_KEY, WRITE_PLAN_OPTION), (HELP_KEY, HELP_BUTTON)], "", ""
    if step == "tests":
        case_capped = developer_cases >= MAX_DEVELOPER_CASES
        return (
            [
                (ACCEPT_PLAN_KEY, ACCEPT_PLAN_OPTION),
                (CHANGE_APPROACH_KEY, GO_BACK_OPTION),
                (HELP_KEY, HELP_BUTTON),
            ],
            "" if case_capped else TYPING_PROMPTS["tests"],
            CASE_CAP_MESSAGE if case_capped else "",
        )
    if step == "case_check":
        return [(KEEP_KEY, KEEP_CASE_OPTION), (DISCARD_KEY, DISCARD_CASE_OPTION)], "", ""
    return [], prompt, ""
