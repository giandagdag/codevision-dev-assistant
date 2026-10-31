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
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
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
    Decision,
    InputMode,
    PendingDecision,
    RequestRecord,
    Speaker,
    UnderstandSession,
    UnderstandView,
)

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
OPTIONAL_QUESTION = "Optional: constraints, exclusions, or references?"
CORRECTION_QUESTION = "What should change?"

HELP_OPTION = "I need help deciding"
PROCEED_OPTION = "Proceed with this understanding"
CORRECT_OPTION = "Correct something"
CHECKPOINT_OPTIONS: tuple[str, ...] = (PROCEED_OPTION, CORRECT_OPTION, HELP_OPTION)
SKIP_TEXT = "Skip"

MAX_MATERIAL_DECISIONS = 5
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
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> UnderstandView:
    """Start a request from the developer's first message, then ask question 1.

    Two saves (review S2). Save 1 creates the request, pinned to the active rulebook, at DRAFT
    with the first message. The interpreter then reads the message with no lock held. Save 2
    moves to CLARIFICATION_IN_PROGRESS and asks question 1, with the interpreter's hint. If the
    interpreter fails, the request still exists and question 1 is asked without a hint.
    """
    text = _accept_developer_text(first_message)
    now = now or datetime.now(UTC)
    developer_id = developer_id or settings.developer_id
    with _write_transaction(settings.db_path) as conn:
        request = insert_request(conn, NEW_REQUEST_TITLE, developer_id, now)
        record = RequestRecord(
            request_id=request.request_id, rulebook_version=request.rulebook_version
        )
        session = UnderstandSession(request_id=request.request_id, record=record)
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
    logger.info("Created Understand request %s", request.request_id)

    result = _interpret(settings, session, "opening", OPENING_QUESTION, text, client)
    with _turn(settings.db_path, request.request_id, session.revision, now) as turn:
        if result.ok:
            _apply_result(turn, result, answered=None)
        else:
            _audit_failure(turn, "opening", result)
        _advance(turn)
    return get_understand_view(settings, request.request_id)


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
    result = _interpret(settings, session, step_name, question, text, client)

    with _turn(settings.db_path, request_id, base_revision, now) as turn:
        turn.say("developer", text)
        turn.audit("developer", "question_answered", {"step": step_name})
        if result.ok:
            answered = session.current_question if session.step == "question" else None
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


def _apply_result(turn: _Turn, result: InterpretResult, answered: int | None) -> None:
    """Use a checked reply: new record, assumptions, decisions to ask, and changed fields."""
    session = turn.session
    old = session.record
    record = refresh_scope_conflicts(result.record)
    if answered is not None:
        answered_questions = sorted(set(old.answered_questions) | {answered})
        record = record.model_copy(update={"answered_questions": answered_questions})

    turn.audit(
        "llm",
        "interpreter_reply",
        {"provider": result.provider, "model": result.model, "attempts": result.attempts},
    )
    for assumption in record.assumptions:
        if assumption not in old.assumptions:
            turn.audit("system", "assumption_added", assumption.model_dump())

    record = _queue_material_decisions(session, record, result)
    session.record = record
    session.next_hint = result.reply.hint
    session.last_changed_fields = _changed_fields(old, record)
    if record.title and record.title != turn.request.title:
        turn.request = update_request(
            turn.conn, turn.request.request_id, now=turn.now, title=record.title
        )


def _queue_material_decisions(
    session: UnderstandSession, record: RequestRecord, result: InterpretResult
) -> RequestRecord:
    """Queue material ambiguities to ask one at a time (rule R3). After 5 on one request, the
    rest become open items and a senior is needed (spec 3.5)."""
    already = {decision.question for decision in record.decisions}
    already |= {pending.question for pending in session.pending_decisions}
    open_items = list(record.open_items)
    for ambiguity in result.reply.ambiguities:
        if not ambiguity.material or ambiguity.text in already:
            continue
        already.add(ambiguity.text)
        if session.material_decisions_asked < MAX_MATERIAL_DECISIONS:
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
            _apply_result(turn, result, answered=None)
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
    turn.say("assistant", "Noted as a confirmed decision.")
    if not session.pending_decisions:
        # A valid resting step in case the app stops before save 2; save 2 sets the real one.
        session.step = "correction"
        turn.reveal = False
    return True


def _choose_checkpoint(turn: _Turn, option: str) -> None:
    session = turn.session
    if option not in CHECKPOINT_OPTIONS:
        raise UnderstandError(_not_a_choice_message(option, list(CHECKPOINT_OPTIONS)))
    turn.say("developer", option)

    if option == HELP_OPTION:
        if session.checkpoint_help:
            raise UnderstandError(
                "Help has already been requested. Choose Proceed or Correct something "
                "when you are ready."
            )
        session.checkpoint_help = True
        _set_open_items(session, [*session.record.open_items, CHECKPOINT_HELP_ITEM])
        session.last_changed_fields = ["open_items"]
        turn.move_to(STATUS_DECISION_REQUIRED)
        turn.audit("developer", "help_requested", {"question": "confirmation"})
        turn.say(
            "assistant",
            "Help requested. This request will wait here. When you are ready, choose Proceed "
            "or Correct something.",
        )
        return

    if session.checkpoint_help:
        # Choosing later clears the help item, the same way a decision does (review M2).
        session.checkpoint_help = False
        _set_open_items(
            session, [i for i in session.record.open_items if i != CHECKPOINT_HELP_ITEM]
        )
        session.last_changed_fields = ["open_items"]
        turn.move_to(STATUS_CLARIFICATION)

    if option == CORRECT_OPTION:
        session.step = "correction"
        turn.move_to(STATUS_CLARIFICATION)
        turn.audit("developer", "correction_requested")
        turn.say("assistant", CORRECTION_QUESTION)
        return

    # Proceed: the gate runs again, then record v1 is saved. From DECISION_REQUIRED this is
    # one action with every move audited, no second click (review S1).
    if _run_gate(turn, announce=False):
        _confirm(turn)


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
    lines.append("Press Proceed to Discovery to search approved sources.")
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
        )
        yield turn
        _highlight_revealed(turn)
        save_session(conn, turn.session, base_revision, now)


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
    if _INPUT_MODES[session.step] != "text":
        raise UnderstandError(_wrong_step_message(session))


def _wrong_step_message(session: UnderstandSession) -> str:
    messages = {
        "question": "Please answer the question first.",
        "optional": "Please type your constraints, exclusions, or references, or press Skip.",
        "correction": "Please type what should change first.",
        "decision": "A decision is waiting. Please choose an option or type your own answer.",
        "checkpoint": (
            f"Please choose one of the options: {PROCEED_OPTION}, {CORRECT_OPTION}, "
            f"or {HELP_OPTION}."
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
