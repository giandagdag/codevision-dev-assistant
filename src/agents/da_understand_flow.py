"""The Understand conversation (spec 3.2): the program that decides every step and status.

Like a 5250 interactive program whose state is kept in a work file between screens: each action
reads the session, checks it is still the revision the screen showed, calls the interpreter
with no database lock held (it can take seconds), and then saves everything in one
transaction: chat messages, the session, the request's status and the audit events (rule R6).
If anything fails, nothing is written.

The interpreter only suggests (rule R2). Questions, decisions, statuses and the confirmation
gate are all decided here.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from agents.da_enhance_checks import (
    available_symbols,
    number_keep_items,
    parse_keep_lines,
    scope_problems,
)
from agents.da_enhance_flow import baseline_texts, maybe_offer_switch
from agents.da_llm_client import LLMClient, LLMClientError
from agents.da_understand_agent import InterpretResult, get_understand_client, interpret
from agents.da_understand_checks import (
    confirmation_gate_problems,
    developer_message_problem,
    refresh_scope_conflicts,
)
from configs.da_config import ConfigError, Settings
from da_logging import get_logger
from db_table_functions import db_tbl_da_requests
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_requests import (
    get_rulebook_for_request,
    insert_request,
    read_request,
    update_request,
)
from db_table_functions.db_tbl_da_rulebook import RulebookError, ensure_rulebook_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    UnderstandError,
    add_message,
    ensure_understand_tables,
    get_session,
    insert_confirmed_record,
    insert_session,
    list_messages,
    read_confirmed_record,
    read_messages,
    read_session,
    save_session,
)
from pydantic_classes.da_models import (
    ALLOWED_MOVES,
    STATUS_CLARIFICATION,
    STATUS_CONFIRMED,
    STATUS_DECISION_REQUIRED,
    STATUS_READY,
    Actor,
    Request,
    display_status,
)
from pydantic_classes.da_request_record_models import (
    QUESTION_COUNT,
    TEXT_LIMIT,
    Decision,
    InputMode,
    MustNotChange,
    PendingDecision,
    RequestRecord,
    Speaker,
    UnderstandSession,
    UnderstandView,
)
from pydantic_classes.da_rulebook_models import DEFAULT_MAX_MATERIAL_DECISIONS

logger = get_logger(__name__)

NEW_REQUEST_TITLE = "New change request"

# The fixed question wording is app text; the interpreter only adds a hint (spec 3.2).
QUESTIONS: dict[int, str] = {
    1: "What needs to change, and why?",
    2: "What happens today? (you don't need to know the source files)",
    3: "What should happen after the change?",
    4: "What are the inputs, outputs, and important success or failure cases?",
}
OPENING_QUESTION = "The developer's first description of the change"
OPENING_LABEL = "The developer's opening statement:"
OPTIONAL_QUESTION = "Optional: constraints, exclusions, or references?"
CORRECTION_QUESTION = "What should change?"

HELP_OPTION = "I need help deciding"
PROCEED_OPTION = "Proceed with this understanding"
CORRECT_OPTION = "Correct something"
# Two buttons. Typing in the open text box and pressing "Correct something" is the correction
# (Phase 6 fixes, section 2), so there is no Correct button.
CHECKPOINT_OPTIONS: tuple[str, ...] = (PROCEED_OPTION, HELP_OPTION)
CHECKPOINT_SEND_LABEL = CORRECT_OPTION
CHECKPOINT_PROMPT = "Type what should change, then press Correct something."
SKIP_TEXT = "Skip"

# The form (Phase 6 fixes, U1): the 4 mandatory questions in their wording, plus the optional box.
FORM_BOXES: tuple[tuple[int, str], ...] = tuple(QUESTIONS.items())
FORM_OPTIONAL_BOX = QUESTION_COUNT + 1
# Phase 9: the form of an enhance or fix request (spec section 6, step 2). Still 5 boxes. Box 1 is
# pre-filled by the today-draft; box 3 holds the must-NOT-change items, one per line.
ENHANCE_FORM_BOXES: tuple[tuple[int, str], ...] = (
    (1, "What does it do today?"),
    (2, "What should change?"),
    (3, "What must NOT change? (one item per line, or write Nothing special)"),
    (4, QUESTIONS[4]),
)
SCOPE_REQUIRED = "Tick at least one function that the change touches, then press Proceed."
FORM_QUESTION = (
    "The developer's opening statement and the answers to the 4 mandatory questions "
    "(and the optional notes)"
)
FORM_MESSAGE = (
    "Thanks. Please answer the 4 questions in the form below, then press Submit. "
    "The last box is optional."
)
FORM_STEP = "form"
BOX_EMPTY_MESSAGE = "Please answer this question."
CUSTOM_ANSWER_LIMIT = 300
CUSTOM_TOO_LONG = "Please keep your own answer under 300 characters, or choose a button."
DECISION_STEP = "decision"  # the interpreter script step used after a decision
DECISION_NOT_APPLIED = (
    "Your decision is saved. I couldn't update the summary from it; it will be picked up "
    "with your next answer."
)
QUESTION_4_HINT = (
    "Each case you name becomes an acceptance criterion, and every criterion gets tested."
)
HELP_PREFIX = "Help requested: "
SENIOR_PREFIX = "Needs a senior decision: "
CHECKPOINT_HELP_ITEM = HELP_PREFIX + "confirmation"

SENIOR_MESSAGE = "This change has many open decisions. Please get help from a senior."
OPTIONAL_MESSAGE = (
    f"{OPTIONAL_QUESTION}\nIf there is an existing feature to use as a reference, or something "
    "that must not change, tell me. Not sure? Press Skip."
)
CHECKPOINT_MESSAGE = (
    "Here is my understanding. Please check the summary, then choose how to continue."
)

# Which Summary fields the screen shows (W5). The AI still fills any field from any message; only
# the screen waits. The title is not listed: the header keeps updating as it does today.
ALWAYS_VISIBLE: tuple[str, ...] = ("assumptions", "decisions", "open_items")
REVEALED_BY_QUESTION: dict[int, tuple[str, ...]] = {
    1: ("objective", "reason"),
    2: ("current_behaviour",),
    3: ("expected_behaviour", "functional_flow", "in_scope"),
    4: ("inputs", "outputs", "acceptance_criteria", "out_of_scope"),
}
REVEALED_BY_OPTIONAL: tuple[str, ...] = ("constraints", "references")
# From the correction step on, the gate messages name fields, so every field must be visible.
SHOW_ALL_STEPS = ("correction", "checkpoint", "done")

# Which input the screen offers at each step.
_INPUT_MODES: dict[str, InputMode] = {
    "form": "form",
    "question": "text",
    "optional": "text",
    "correction": "text",
    "decision": "choices",
    "checkpoint": "choices",
    "senior": "waiting",
    "done": "done",
}


@dataclass
class _Turn:
    """One action's work inside its write transaction: what it reads and what it changes."""

    conn: sqlite3.Connection
    request: Request
    session: UnderstandSession
    now: datetime
    # What the screen showed before this action, to highlight what the action reveals (W5).
    visible_before: list[str]
    # False for a save that only parks the session (the decision's save 1): the real step, and
    # so the real reveal, comes with save 2.
    reveal: bool = True
    # How many AI clarifying questions this request may ask: the rulebook policy it is pinned to.
    max_decisions: int = DEFAULT_MAX_MATERIAL_DECISIONS

    def say(self, speaker: Speaker, text: str) -> None:
        add_message(self.conn, self.request.request_id, speaker, text, self.now)

    def audit(self, actor: Actor, event_type: str, details: dict | None = None) -> None:
        insert_audit_event(
            self.conn, self.request.request_id, actor, event_type, details, self.now
        )

    def move_to(self, status: str) -> None:
        """Move to a status through the 3.1 table, auditing every single move (rule R6).

        From DECISION_REQUIRED the only way on is back to CLARIFICATION_IN_PROGRESS, so a move
        to anywhere else goes through it first, as two audited moves.
        """
        if self.request.status == status:
            return
        path = [status]
        if status not in ALLOWED_MOVES[self.request.status]:
            path = [STATUS_CLARIFICATION, status]
        for next_status in path:
            old_status = self.request.status
            self.request = update_request(
                self.conn, self.request.request_id, now=self.now, status=next_status
            )
            self.audit("system", "status_changed", {"from": old_status, "to": next_status})


# --- the actions the screen calls ---


def create_understand_request(
    settings: Settings,
    first_message: str,
    developer_id: str | None = None,
    now: datetime | None = None,
) -> UnderstandView:
    """Start a request from the developer's first message and show the 4-box form.

    One save: the request (pinned to the active rulebook), the first message, the move to
    CLARIFICATION_IN_PROGRESS and the form. There is NO interpreter call here (Phase 6 fixes, U3):
    the one call before the first AI question happens when the form is submitted, so it sees the
    opening statement and all the answers together.
    """
    text = _accept_developer_text(first_message)
    now = now or datetime.now(UTC)
    developer_id = developer_id or settings.developer_id
    with _write_transaction(settings.db_path) as conn:
        request = insert_request(conn, NEW_REQUEST_TITLE, developer_id, now)
        record = RequestRecord(
            request_id=request.request_id, rulebook_version=request.rulebook_version
        )
        session = UnderstandSession(request_id=request.request_id, record=record, step=FORM_STEP)
        insert_session(conn, session, now)
        add_message(conn, request.request_id, "developer", text, now)
        insert_audit_event(
            conn,
            request.request_id,
            "developer",
            "request_created",
            {"rulebook_version": request.rulebook_version},
            now,
        )
        update_request(conn, request.request_id, now=now, status=STATUS_CLARIFICATION)
        insert_audit_event(
            conn,
            request.request_id,
            "system",
            "status_changed",
            {"from": request.status, "to": STATUS_CLARIFICATION},
            now,
        )
        add_message(conn, request.request_id, "assistant", FORM_MESSAGE, now)
    logger.info("Created Understand request %s", request.request_id)
    return get_understand_view(settings, request.request_id)


class FormError(UnderstandError):
    """One or more boxes of the form failed their check. problems maps the box number (1 to 5) to
    the plain message shown under that box. Nothing was saved."""

    def __init__(self, problems: dict[int, str]):
        self.problems = problems
        super().__init__("\n".join(problems[number] for number in sorted(problems)))


def submit_form(
    settings: Settings,
    request_id: str,
    answers: list[str],
    base_revision: int,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> UnderstandView:
    """The 4-box form (Phase 6 fixes, U1 to U5, U8): boxes 1 to 4 are the mandatory questions,
    box 5 is the optional area and may stay empty.

    Every box is checked first; a failing box raises FormError and nothing is saved. Then ONE
    interpreter call (no lock held) sees the opening statement and all the answers together, and
    ONE write transaction saves the answers, the reply and the next step. If the interpreter
    fails, nothing is saved in the chat so the developer's text is not lost; the failure is
    still written to the audit trail.
    """
    now = now or datetime.now(UTC)
    session = _load_session(settings.db_path, request_id, base_revision)
    if session.step != FORM_STEP:
        raise UnderstandError(_wrong_step_message(session))
    answers = _check_form_boxes(answers)
    boxes = form_boxes(session.record.kind)
    # Phase 9: the must-NOT-change items are numbered by plain code before any AI call.
    keep_items = _numbered_keep_items(settings, session, answers) if boxes != FORM_BOXES else []
    text = _form_text(answers, boxes)
    # The interpreter sees the opening statement AND the answers together (U3).
    prompt_text = f"{OPENING_LABEL}\n{_opening_statement(settings, request_id)}\n\n{text}"
    result = _interpret(settings, session, FORM_STEP, FORM_QUESTION, prompt_text, client)
    if not result.ok:
        with _write_transaction(settings.db_path) as conn:
            insert_audit_event(
                conn,
                request_id,
                "system",
                "interpreter_failed",
                {"step": FORM_STEP, "provider": result.provider, "problems": result.problems},
                now,
            )
        raise UnderstandError(result.message)

    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        turn.say("developer", text)
        turn.audit("developer", "form_submitted", {"optional_used": bool(answers[-1])})
        _apply_result(turn, result, answered=tuple(number for number, _ in FORM_BOXES))
        if boxes != FORM_BOXES:
            _apply_enhance_boxes(turn, answers[0], keep_items)
        turn.session.optional_done = True
        _advance(turn)
    # Phase 9 (D-N): if the description names a program that already exists, offer to switch to
    # Enhance or fix. Plain code only; it never changes the form's result.
    maybe_offer_switch(settings, request_id, now=now)
    return get_understand_view(settings, request_id)


def _opening_statement(settings: Settings, request_id: str) -> str:
    """The developer's first message on this request."""
    for message in list_messages(settings.db_path, request_id):
        if message.speaker == "developer":
            return message.text
    return ""


def _check_form_boxes(answers: list[str]) -> list[str]:
    """Trim the 5 boxes and check each one with the same checks as any message (R8, R9)."""
    if len(answers) != FORM_OPTIONAL_BOX:
        raise UnderstandError("The form has 5 boxes. Please reload the page.")
    cleaned = [(answer or "").strip() for answer in answers]
    problems: dict[int, str] = {}
    for number, text in enumerate(cleaned, start=1):
        if not text:
            if number != FORM_OPTIONAL_BOX:
                problems[number] = BOX_EMPTY_MESSAGE
            continue
        problem = developer_message_problem(text)
        if problem:
            problems[number] = problem
    if problems:
        raise FormError(problems)
    return cleaned


def form_boxes(kind: str) -> tuple[tuple[int, str], ...]:
    """The four titled boxes of the form for a request kind (the optional box is always last)."""
    return FORM_BOXES if kind == "new" else ENHANCE_FORM_BOXES


def _numbered_keep_items(
    settings: Settings, session: UnderstandSession, answers: list[str]
) -> list[MustNotChange]:
    """Check box 1 and box 3 of an enhance form and number its NC items (never reusing an ID).
    Raises FormError with the plain message under the box; nothing is saved."""
    record = session.record
    policy = get_rulebook_for_request(settings.db_path, record.request_id).rulebook.policy
    lines, problems = parse_keep_lines(answers[2], policy)
    if len(answers[0]) > TEXT_LIMIT:
        raise FormError({1: f"Please keep this under {TEXT_LIMIT} characters."})
    if problems:
        raise FormError({3: problems[0]})
    try:
        return number_keep_items(lines, record.must_not_change, [record])
    except ValidationError as error:
        raise FormError({3: "Please keep each item to one short line."}) from error


def _apply_enhance_boxes(turn: _Turn, today: str, keep_items: list[MustNotChange]) -> None:
    """Plain code sets what the AI may not: the today text and the NC items."""
    record = turn.session.record.model_copy(
        update={"today": today, "must_not_change": keep_items}
    )
    turn.session.record = record
    turn.session.last_changed_fields = [
        *turn.session.last_changed_fields, "today", "must_not_change"
    ]


def set_functions_in_scope(
    settings: Settings,
    request_id: str,
    chosen: list[str],
    base_revision: int,
    now: datetime | None = None,
) -> UnderstandView:
    """The checkpoint tick list (D-D). Plain code refuses symbols that are not in the chosen
    programs, and an empty list. Saved in the record; confirm uses it."""
    now = now or datetime.now(UTC)
    texts = baseline_texts(settings, request_id)
    available = [name for path, text in texts.items() for name in available_symbols(path, text)]
    problems = scope_problems(chosen, available)
    if problems:
        raise UnderstandError("\n".join(problems))
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        if turn.session.record.kind == "new" or turn.session.step == "done":
            raise UnderstandError("The functions in scope cannot be set on this request.")
        turn.session.record = turn.session.record.model_copy(
            update={"functions_in_scope": list(dict.fromkeys(chosen))}
        )
        turn.session.last_changed_fields = ["functions_in_scope"]
        turn.audit("developer", "functions_in_scope_set", {"functions": chosen})
    return get_understand_view(settings, request_id)


def _form_text(answers: list[str], boxes: tuple[tuple[int, str], ...] = FORM_BOXES) -> str:
    """The answers as one readable message: each question's wording, then the developer's text."""
    sections = [f"{number}. {title}\n{answers[number - 1]}" for number, title in boxes]
    if answers[-1]:
        sections.append(f"{OPTIONAL_QUESTION}\n{answers[-1]}")
    return "\n\n".join(sections)


def submit_answer(
    settings: Settings,
    request_id: str,
    text: str,
    base_revision: int,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> UnderstandView:
    """The developer's answer to a question, the optional area, or a correction."""
    text = _accept_developer_text(text)
    now = now or datetime.now(UTC)
    # Refuse early, before the slow interpreter call. Checked again when saving.
    session = _load_session(settings.db_path, request_id, base_revision)
    if session.step == "decision":
        # "Other, type here" (W3): a typed answer is a decision like a button.
        return _submit_custom_decision(settings, session, text, base_revision, client, now)
    _require_text_step(session)
    step_name, question = _interpreter_step(session)
    result = _interpret(
        settings, _without_checkpoint_help(session), step_name, question, text, client
    )

    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        turn.say("developer", text)
        turn.audit("developer", "question_answered", {"step": step_name})
        if result.ok:
            if session.step == "checkpoint":
                # Typing at the checkpoint is "Correct something": the same as the old two
                # clicks. A failed AI call leaves the request at the checkpoint untouched.
                _start_correction(turn)
            answered = (session.current_question,) if session.step == "question" else ()
            _apply_result(turn, result, answered)
            if session.step == "optional":
                turn.session.optional_done = True
            _advance(turn)
        else:
            # The record does not change; both messages stay in the chat (Gian, 25 Oct 2026).
            turn.say("assistant", result.message)
            _audit_failure(turn, step_name, result)
            turn.session.last_changed_fields = []
    return get_understand_view(settings, request_id)


def choose_option(
    settings: Settings,
    request_id: str,
    option: str,
    base_revision: int,
    now: datetime | None = None,
    client: LLMClient | None = None,
) -> UnderstandView:
    """The developer picks a choice: a material decision, or one of the 3 checkpoint choices."""
    now = now or datetime.now(UTC)
    session = _load_session(settings.db_path, request_id, base_revision)
    if session.step == "decision":
        return _decide(settings, request_id, option, False, base_revision, now, client)
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        if turn.session.step == "checkpoint":
            _choose_checkpoint(turn, option)
        else:
            raise UnderstandError(_wrong_step_message(turn.session))
    return get_understand_view(settings, request_id)


def skip_optional(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> UnderstandView:
    """Skip the optional area (constraints, exclusions, references) and go to the checkpoint."""
    now = now or datetime.now(UTC)
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        if turn.session.step != "optional":
            raise UnderstandError(_wrong_step_message(turn.session))
        turn.say("developer", SKIP_TEXT)
        turn.audit("developer", "optional_skipped")
        turn.session.optional_done = True
        turn.session.last_changed_fields = []
        _advance(turn)
    return get_understand_view(settings, request_id)


def confirm_request(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> UnderstandView:
    """Confirm the record as version 1: the same as choosing "Proceed with this understanding"."""
    return choose_option(settings, request_id, PROCEED_OPTION, base_revision, now)


def get_understand_view(settings: Settings, request_id: str) -> UnderstandView:
    """Everything the screen needs to show one request.

    Read on one connection, in one read transaction, so the status, session and chat always
    match each other even if another window saves at the same moment.
    """
    with open_db(settings.db_path) as conn:
        ensure_understand_tables(conn)
        conn.execute("BEGIN")
        request = read_request(conn, request_id)
        session = read_session(conn, request_id)
        if request is None or session is None:
            raise UnderstandError(f"Request {request_id} does not exist.")
        messages = read_messages(conn, request_id)
        record = session.record
        if session.step == "done":
            record = read_confirmed_record(conn, request_id, request.version) or record
    return UnderstandView(
        request=request,
        record=record,
        messages=messages,
        status_label=display_status(request.status),
        progress_text=_progress_text(request, session),
        answered_count=len(record.answered_questions),
        input_mode=_INPUT_MODES[session.step],
        prompt=_prompt_for(session),
        choices=_choices_for(session),
        can_skip=session.step == "optional",
        changed_fields=session.last_changed_fields,
        visible_fields=visible_fields(session),
        custom_choice_allowed=session.step == "decision",
        send_label=CHECKPOINT_SEND_LABEL if session.step == "checkpoint" else "Send",
        text_prompt=CHECKPOINT_PROMPT if session.step == "checkpoint" else "",
        revision=session.revision,
        demo_mode=settings.llm_provider == "fake",
    )


def list_my_requests(settings: Settings, developer_id: str | None = None) -> list[Request]:
    """The developer's requests, newest first, for "My recent requests"."""
    developer_id = developer_id or settings.developer_id
    return db_tbl_da_requests.list_my_requests(settings.db_path, developer_id)


# --- the interpreter call (no database lock held) ---


def _interpret(
    settings: Settings,
    session: UnderstandSession,
    step_name: str,
    question: str,
    answer: str,
    client: LLMClient | None,
) -> InterpretResult:
    request_id = session.request_id
    developer_text = "\n".join(
        message.text
        for message in list_messages(settings.db_path, request_id)
        if message.speaker == "developer"
    )
    # The pinned version, never the active one, so the request keeps its house rules (R10).
    pinned = get_rulebook_for_request(settings.db_path, request_id)
    try:
        client = client or get_understand_client(settings, step_name)
        return interpret(
            client,
            question,
            answer,
            session.record,
            pinned.rulebook.charter,
            pinned.version_number,
            f"{developer_text}\n{answer}",
            # Told what is already decided or waiting, so only NEW questions come back (U5).
            decided=[decision.question for decision in session.record.decisions],
            queued=[pending.question for pending in session.pending_decisions],
        )
    except (ConfigError, LLMClientError) as error:
        # Shown in the chat as a plain message: e.g. onprem "not configured yet".
        return InterpretResult(
            record=None,
            reply=None,
            provider=settings.llm_provider,
            model="",
            attempts=0,
            problems=[str(error)],
            message=str(error),
        )


def _interpreter_step(session: UnderstandSession) -> tuple[str, str]:
    """The script step name and the question text for the step the developer is answering."""
    if session.step == "question":
        number = session.current_question
        return f"question_{number}", QUESTIONS[number]
    if session.step == "optional":
        return "optional", OPTIONAL_QUESTION
    return "correction", CORRECTION_QUESTION


# --- applying a reply ---


def _apply_result(turn: _Turn, result: InterpretResult, answered: tuple[int, ...] = ()) -> None:
    """Use a checked reply: new record, assumptions, decisions to ask, and changed fields."""
    session = turn.session
    old = session.record
    record = refresh_scope_conflicts(result.record)
    if answered:
        answered_questions = sorted(set(old.answered_questions) | set(answered))
        record = record.model_copy(update={"answered_questions": answered_questions})

    turn.audit(
        "llm",
        "interpreter_reply",
        {"provider": result.provider, "model": result.model, "attempts": result.attempts},
    )
    for assumption in record.assumptions:
        if assumption not in old.assumptions:
            turn.audit("system", "assumption_added", assumption.model_dump())

    record = _queue_material_decisions(session, record, result, turn.max_decisions)
    session.record = record
    session.next_hint = result.reply.hint
    session.last_changed_fields = _changed_fields(old, record)
    if record.title and record.title != turn.request.title:
        turn.request = update_request(
            turn.conn, turn.request.request_id, now=turn.now, title=record.title
        )


def _queue_material_decisions(
    session: UnderstandSession, record: RequestRecord, result: InterpretResult, limit: int
) -> RequestRecord:
    """Queue material ambiguities to ask one at a time (rule R3). After `limit` on one request
    (the rulebook policy, default 5), the rest become open items and a senior is needed (3.5)."""
    already = {decision.question for decision in record.decisions}
    already |= {pending.question for pending in session.pending_decisions}
    open_items = list(record.open_items)
    for ambiguity in result.reply.ambiguities:
        if not ambiguity.material or ambiguity.text in already:
            continue
        already.add(ambiguity.text)
        if session.material_decisions_asked < limit:
            session.pending_decisions.append(
                PendingDecision(question=ambiguity.text, options=ambiguity.options)
            )
            session.material_decisions_asked += 1
        else:
            open_items.append(SENIOR_PREFIX + ambiguity.text)
            session.needs_senior = True
    return record.model_copy(update={"open_items": open_items})


def _changed_fields(old: RequestRecord, new: RequestRecord) -> list[str]:
    return [name for name in RequestRecord.model_fields if getattr(old, name) != getattr(new, name)]


def _audit_failure(turn: _Turn, step_name: str, result: InterpretResult) -> None:
    turn.audit(
        "system",
        "interpreter_failed",
        {"step": step_name, "provider": result.provider, "problems": result.problems},
    )


# --- what comes next ---


def _advance(turn: _Turn) -> None:
    """Decide the next step after an action and say it in the chat.

    Order: waiting decisions, then the senior stop, then the next unanswered question, then
    the optional area, then the confirmation gate.
    """
    session = turn.session
    record = session.record
    unanswered = [n for n in range(1, QUESTION_COUNT + 1) if n not in record.answered_questions]
    if session.pending_decisions:
        _ask_decision(turn)
    elif session.needs_senior:
        # The only place that says it, and only when the step changes (W4).
        if session.step != "senior":
            turn.say("assistant", SENIOR_MESSAGE)
        session.step = "senior"
        turn.move_to(STATUS_DECISION_REQUIRED)
    elif unanswered:
        session.step = "question"
        session.current_question = unanswered[0]
        turn.move_to(STATUS_CLARIFICATION)
        turn.say("assistant", _question_message(session))
    elif not session.optional_done:
        session.step = "optional"
        session.next_hint = ""
        turn.move_to(STATUS_CLARIFICATION)
        turn.say("assistant", OPTIONAL_MESSAGE)
    else:
        _run_gate(turn)


def _ask_decision(turn: _Turn) -> None:
    session = turn.session
    pending = session.pending_decisions[0]
    session.step = "decision"
    turn.move_to(STATUS_DECISION_REQUIRED)
    turn.audit("system", "decision_asked", {"question": pending.question})
    turn.say(
        "assistant",
        f"One decision needed: {pending.question}\n"
        "This changes what gets built, so I won't assume it. Please choose below.",
    )


def _run_gate(turn: _Turn, announce: bool = True) -> bool:
    """Run the confirmation gate. Pass: the checkpoint. Fail: list every problem and ask what
    should change. Returns True if it passed.

    announce=False is for Proceed, which goes straight on to confirming, so the checkpoint
    message is not shown again.
    """
    session = turn.session
    problems = confirmation_gate_problems(session.record, len(session.pending_decisions))
    if problems:
        session.step = "correction"
        turn.move_to(STATUS_CLARIFICATION)
        listed = "\n".join(f"- {problem}" for problem in problems)
        turn.say(
            "assistant",
            f"Before you can confirm, these items need attention:\n{listed}\n"
            f"{CORRECTION_QUESTION}",
        )
        return False
    session.step = "checkpoint"
    if turn.request.status != STATUS_READY:
        turn.move_to(STATUS_READY)
        turn.audit("system", "ready_for_confirmation")
    if announce:
        turn.say("assistant", CHECKPOINT_MESSAGE)
    return True


def _question_message(session: UnderstandSession) -> str:
    number = session.current_question
    text = f"Question {number} of {QUESTION_COUNT}: {QUESTIONS[number]}"
    if number == QUESTION_COUNT:
        text += f"\n{QUESTION_4_HINT}"
    if session.next_hint:
        text += f"\n{session.next_hint}"
    # A hint is only for the question that comes straight after it.
    session.next_hint = ""
    return text


# --- choices ---


def _submit_custom_decision(
    settings: Settings,
    session: UnderstandSession,
    text: str,
    base_revision: int,
    client: LLMClient | None,
    now: datetime | None,
) -> UnderstandView:
    """A typed answer at a decision step: the checks of any message, then at most 300 characters."""
    text = _accept_developer_text(text)
    if len(text) > CUSTOM_ANSWER_LIMIT:
        raise UnderstandError(CUSTOM_TOO_LONG)
    now = now or datetime.now(UTC)
    # Typing the exact words of a button is the same as pressing it.
    custom = text not in _decision_choices(session.pending_decisions[0])
    return _decide(settings, session.request_id, text, custom, base_revision, now, client)


def _decide(
    settings: Settings,
    request_id: str,
    choice: str,
    custom: bool,
    base_revision: int,
    now: datetime,
    client: LLMClient | None,
) -> UnderstandView:
    """Record a decision, then let the interpreter update the Summary from it (D-C).

    Same pattern as creating a request: save 1 records the decision, the interpreter is called
    with no lock held, save 2 applies the reply and moves on. If the interpreter fails the
    decision stays saved.
    """
    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        if turn.session.step != "decision":
            raise UnderstandError(_wrong_step_message(turn.session))
        question = turn.session.pending_decisions[0].question
        decided = _record_decision(turn, choice, custom)
        shown_before = turn.visible_before
    if not decided:
        # "I need help deciding": nothing was decided, so the interpreter is not asked.
        return get_understand_view(settings, request_id)

    session = _load_session(settings.db_path, request_id, base_revision + 1)
    result = _interpret(settings, session, DECISION_STEP, question, choice, client)
    with _turn(settings.db_path, request_id, session.revision, now) as turn:
        turn.visible_before = shown_before
        carried = list(turn.session.last_changed_fields)
        if result.ok:
            _apply_result(turn, result)
            merged = carried + [f for f in turn.session.last_changed_fields if f not in carried]
            turn.session.last_changed_fields = merged
        else:
            turn.say("assistant", DECISION_NOT_APPLIED)
            _audit_failure(turn, DECISION_STEP, result)
        _advance(turn)
    return get_understand_view(settings, request_id)


def _record_decision(turn: _Turn, choice: str, custom: bool) -> bool:
    """Save the choice. False means help was requested instead (nothing decided)."""
    session = turn.session
    pending = session.pending_decisions[0]
    if choice not in _decision_choices(pending) and not custom:
        raise UnderstandError(_not_a_choice_message(choice, _decision_choices(pending)))
    turn.say("developer", choice)
    help_item = HELP_PREFIX + pending.question

    if choice == HELP_OPTION:
        # The request waits at DECISION_REQUIRED; the developer can come back and choose.
        if help_item not in session.record.open_items:
            _set_open_items(session, [*session.record.open_items, help_item])
            turn.audit("developer", "help_requested", {"question": pending.question})
        session.last_changed_fields = ["open_items"]
        turn.say(
            "assistant",
            "Help requested. This request will wait here. You can come back and choose at any "
            "time. (A senior escalation inbox comes in a later phase.)",
        )
        return False

    decision = Decision(question=pending.question, choice=choice, decided_at=turn.now)
    old = session.record
    open_items = [item for item in old.open_items if item != help_item]
    session.record = RequestRecord.model_validate(
        old.model_dump() | {"decisions": [*old.decisions, decision], "open_items": open_items}
    )
    session.pending_decisions.pop(0)
    session.last_changed_fields = _changed_fields(old, session.record)
    turn.audit(
        "developer",
        "decision_recorded",
        {"question": pending.question, "choice": choice, "custom": custom},
    )
    turn.move_to(STATUS_CLARIFICATION)
    if not session.pending_decisions:
        # A valid resting step in case the app stops before save 2; save 2 sets the real one.
        session.step = "correction"
        turn.reveal = False
    return True


def _choose_checkpoint(turn: _Turn, option: str) -> None:
    session = turn.session
    if option not in CHECKPOINT_OPTIONS:
        raise UnderstandError(_not_a_choice_message(option, list(CHECKPOINT_OPTIONS)))
    # Phase 9: an enhance or fix request needs at least one function in scope before it is saved.
    if (
        option == PROCEED_OPTION
        and session.record.kind != "new"
        and not session.record.functions_in_scope
    ):
        raise UnderstandError(SCOPE_REQUIRED)
    turn.say("developer", option)

    if option == HELP_OPTION:
        if session.checkpoint_help:
            raise UnderstandError(
                f"Help has already been requested. Choose Proceed or type what should change "
                f"and press {CORRECT_OPTION} when you are ready."
            )
        session.checkpoint_help = True
        _set_open_items(session, [*session.record.open_items, CHECKPOINT_HELP_ITEM])
        session.last_changed_fields = ["open_items"]
        turn.move_to(STATUS_DECISION_REQUIRED)
        turn.audit("developer", "help_requested", {"question": "confirmation"})
        turn.say(
            "assistant",
            f"Help requested. This request will wait here. When you are ready, choose Proceed "
            f"or type what should change and press {CORRECT_OPTION}.",
        )
        return

    _clear_checkpoint_help(turn)
    # Proceed: the gate runs again, then record v1 is saved. From DECISION_REQUIRED this is
    # one action with every move audited, no second click (review S1).
    if _run_gate(turn, announce=False):
        _confirm(turn)


def _clear_checkpoint_help(turn: _Turn) -> None:
    """Choosing later clears the help item, the same way a decision does (review M2)."""
    session = turn.session
    if session.checkpoint_help:
        session.checkpoint_help = False
        _set_open_items(
            session, [i for i in session.record.open_items if i != CHECKPOINT_HELP_ITEM]
        )
        session.last_changed_fields = ["open_items"]
        turn.move_to(STATUS_CLARIFICATION)


def _without_checkpoint_help(session: UnderstandSession) -> UnderstandSession:
    """Typing a correction clears a waiting "help requested" item (as choosing Proceed does), so
    the interpreter's record must not hold it, or applying the reply would bring it back."""
    if session.step != "checkpoint" or not session.checkpoint_help:
        return session
    items = [i for i in session.record.open_items if i != CHECKPOINT_HELP_ITEM]
    record = session.record.model_copy(update={"open_items": items})
    return session.model_copy(update={"record": record})


def _start_correction(turn: _Turn) -> None:
    """The developer typed a correction at the checkpoint (Send = Correct something)."""
    _clear_checkpoint_help(turn)
    turn.move_to(STATUS_CLARIFICATION)
    turn.audit("developer", "correction_requested")


def _confirm(turn: _Turn) -> None:
    """Save record v1 and move to CONFIRMED_FOR_DISCOVERY, in the action's one transaction."""
    session = turn.session
    record = session.record
    insert_confirmed_record(turn.conn, record, turn.request.developer_id, turn.now)
    turn.move_to(STATUS_CONFIRMED)
    turn.request = update_request(
        turn.conn, turn.request.request_id, now=turn.now, version=record.version
    )
    turn.audit("developer", "confirmed", {"version": record.version})
    session.step = "done"
    session.last_changed_fields = []
    turn.say("assistant", _confirmed_message(turn.request, record))


def _confirmed_message(request: Request, record: RequestRecord) -> str:
    lines = [
        f"Request {request.request_id} is saved as version {record.version}. "
        f"Status: {display_status(request.status)}.",
        f"Title: {record.title}",
    ]
    lines.append(f"Acceptance criteria: {len(record.acceptance_criteria)}")
    if record.decisions:
        lines.append("Decisions:")
        lines += [f"- {d.question} {d.choice}" for d in record.decisions]
    if record.references:
        lines.append("References:")
        lines += [f"- {reference}" for reference in record.references]
    return "\n".join(lines)


def _decision_choices(pending: PendingDecision) -> list[str]:
    # "I need help deciding" is always added by the app (rule R3), and only once.
    return [option for option in pending.options if option != HELP_OPTION] + [HELP_OPTION]


def _set_open_items(session: UnderstandSession, open_items: list[str]) -> None:
    session.record = session.record.model_copy(update={"open_items": open_items})


# --- shared helpers ---


@contextmanager
def _write_transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Set up tables before taking the lock: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_audit_table(conn)
        ensure_understand_tables(conn)
        begin_write(conn)
        yield conn


@contextmanager
def _turn(db_path: Path, request_id: str, base_revision: int, now: datetime) -> Iterator[_Turn]:
    """Open one action's transaction, check the revision, and save the session at the end."""
    # Read before the write lock opens (P18): the limit of AI questions in the pinned rulebook.
    max_decisions = _decision_limit(db_path, request_id)
    with _write_transaction(db_path) as conn:
        request = read_request(conn, request_id)
        session = read_session(conn, request_id)
        if request is None or session is None:
            raise UnderstandError(f"Request {request_id} does not exist.")
        if session.revision != base_revision:
            raise StaleRevisionError(STALE_MESSAGE)
        turn = _Turn(
            conn=conn,
            request=request,
            session=session,
            now=now,
            visible_before=visible_fields(session),
            max_decisions=max_decisions,
        )
        yield turn
        _highlight_revealed(turn)
        save_session(conn, turn.session, base_revision, now)


def _decision_limit(db_path: Path, request_id: str) -> int:
    """How many AI clarifying questions the request's pinned rulebook allows (default 5)."""
    try:
        policy = get_rulebook_for_request(db_path, request_id).rulebook.policy
    except RulebookError:
        return DEFAULT_MAX_MATERIAL_DECISIONS
    return policy.max_material_decisions


def visible_fields(session: UnderstandSession) -> list[str]:
    """Which Summary fields the screen shows now (W5). Plain code, testable without Dash."""
    shown = set(ALWAYS_VISIBLE)
    if session.step in SHOW_ALL_STEPS:
        shown |= {name for names in REVEALED_BY_QUESTION.values() for name in names}
        shown |= set(REVEALED_BY_OPTIONAL)
    else:
        for number in session.record.answered_questions:
            shown |= set(REVEALED_BY_QUESTION.get(number, ()))
        if session.optional_done:
            shown |= set(REVEALED_BY_OPTIONAL)
    order = [
        *ALWAYS_VISIBLE,
        *(name for names in REVEALED_BY_QUESTION.values() for name in names),
        *REVEALED_BY_OPTIONAL,
    ]
    return [name for name in order if name in shown]


def _highlight_revealed(turn: _Turn) -> None:
    """A field that became visible in this action is highlighted like a changed one, even if its
    value was filled earlier (W5). A field with nothing in it is not."""
    session = turn.session
    if not turn.reveal:
        return
    for name in visible_fields(session):
        if name in turn.visible_before or name in session.last_changed_fields:
            continue
        if getattr(session.record, name):
            session.last_changed_fields = [*session.last_changed_fields, name]


def _load_session(db_path: Path, request_id: str, base_revision: int) -> UnderstandSession:
    session = get_session(db_path, request_id)
    if session is None:
        raise UnderstandError(f"Request {request_id} does not exist.")
    if session.revision != base_revision:
        raise StaleRevisionError(STALE_MESSAGE)
    return session


def _accept_developer_text(text: str) -> str:
    """Refuse an empty, too long, or secret-looking message before it is saved or sent (R8, R9)."""
    problem = developer_message_problem(text)
    if problem:
        raise UnderstandError(problem)
    return text.strip()


def _require_text_step(session: UnderstandSession) -> None:
    if _INPUT_MODES[session.step] != "text" and session.step != "checkpoint":
        raise UnderstandError(_wrong_step_message(session))


def _wrong_step_message(session: UnderstandSession) -> str:
    messages = {
        "form": "Please fill in the form and press Submit first.",
        "question": "Please answer the question first.",
        "optional": "Please type your constraints, exclusions, or references, or press Skip.",
        "correction": "Please type what should change first.",
        "decision": "A decision is waiting. Please choose an option or type your own answer.",
        "checkpoint": (
            f"Please choose {PROCEED_OPTION} or {HELP_OPTION}, or type what should change "
            f"and press {CORRECT_OPTION}."
        ),
        "senior": SENIOR_MESSAGE,
        "done": "This request is already confirmed. It cannot be changed in this phase.",
    }
    return messages[session.step]


def _not_a_choice_message(option: str, choices: list[str]) -> str:
    return f"'{option}' is not one of the choices. Choose one of: {', '.join(choices)}."


def _prompt_for(session: UnderstandSession) -> str:
    if session.step == "question":
        number = session.current_question
        return f"Question {number} of {QUESTION_COUNT}: {QUESTIONS[number]}"
    if session.step == "optional":
        return OPTIONAL_QUESTION
    if session.step == "correction":
        return CORRECTION_QUESTION
    if session.step == "decision":
        return session.pending_decisions[0].question
    if session.step == "checkpoint":
        return CHECKPOINT_MESSAGE
    if session.step == "senior":
        return SENIOR_MESSAGE
    return ""


def _choices_for(session: UnderstandSession) -> list[str]:
    if session.step == "decision":
        return _decision_choices(session.pending_decisions[0])
    if session.step == "checkpoint":
        return list(CHECKPOINT_OPTIONS)
    return []


def _progress_text(request: Request, session: UnderstandSession) -> str:
    if session.step == "done":
        return f"Confirmed and saved as version {request.version}"
    if request.status == STATUS_READY:
        return "Ready for confirmation"
    open_count = len(session.record.open_items) + len(session.pending_decisions)
    if open_count:
        noun = "open item" if open_count == 1 else "open items"
        return f"Clarification required: {open_count} {noun}"
    answered = len(session.record.answered_questions)
    return f"{answered} of {QUESTION_COUNT} mandatory questions answered"
