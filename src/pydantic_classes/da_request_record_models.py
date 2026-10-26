"""Data shapes for Understand: the request record, the interpreter's reply, chat and session.

The limits here (spec 3.3) work like DDS field lengths: a value that is too long is refused,
never cut short.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN, Request

TITLE_LIMIT = 80
TEXT_LIMIT = 1000
LIST_ITEM_LIMIT = 300
LIST_LENGTH_LIMIT = 12
HINT_LIMIT = 200
QUESTION_COUNT = 4

ShortText = Annotated[str, Field(min_length=1, max_length=LIST_ITEM_LIMIT)]
LongText = Annotated[str, Field(max_length=TEXT_LIMIT)]
ShortList = Annotated[list[ShortText], Field(max_length=LIST_LENGTH_LIMIT)]

# The fields the interpreter may fill. Everything else in the record is filled by the app.
TEXT_FIELDS: tuple[str, ...] = (
    "title",
    "objective",
    "reason",
    "current_behaviour",
    "expected_behaviour",
    "inputs",
    "outputs",
)
LIST_FIELDS: tuple[str, ...] = (
    "functional_flow",
    "in_scope",
    "out_of_scope",
    "success_scenarios",
    "failure_scenarios",
    "constraints",
    "references",
)
INTERPRETER_FIELDS: tuple[str, ...] = TEXT_FIELDS + LIST_FIELDS

# How a field is named in plain-language messages.
FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "objective": "Objective",
    "reason": "Reason",
    "current_behaviour": "Current behaviour",
    "expected_behaviour": "Expected behaviour",
    "inputs": "Inputs",
    "outputs": "Outputs",
    "functional_flow": "Functional flow",
    "in_scope": "In scope",
    "out_of_scope": "Out of scope",
    "success_scenarios": "Success scenarios",
    "failure_scenarios": "Failure scenarios",
    "constraints": "Constraints",
    "references": "References",
}

Speaker = Literal["developer", "assistant", "system"]

# Where the conversation is. Each step allows one kind of input (see the flow module).
Step = Literal["question", "decision", "optional", "correction", "checkpoint", "senior", "done"]
InputMode = Literal["text", "choices", "waiting", "done"]


class _Shape(BaseModel):
    # extra="forbid": an unknown field name is an error, not silently dropped.
    model_config = ConfigDict(extra="forbid")


class Decision(_Shape):
    question: ShortText
    choice: ShortText
    decided_at: AwareDatetime


class Assumption(_Shape):
    text: ShortText
    # Why the assumption is safe, for example "Rulebook v1 glossary" (rule R4).
    basis: ShortText


class RequestRecord(_Shape):
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    version: int = Field(default=1, ge=1)
    rulebook_version: int = Field(ge=1)
    title: str = Field(default="", max_length=TITLE_LIMIT)
    objective: LongText = ""
    reason: LongText = ""
    current_behaviour: LongText = ""
    expected_behaviour: LongText = ""
    functional_flow: ShortList = Field(default_factory=list)
    in_scope: ShortList = Field(default_factory=list)
    out_of_scope: ShortList = Field(default_factory=list)
    inputs: LongText = ""
    outputs: LongText = ""
    success_scenarios: ShortList = Field(default_factory=list)
    failure_scenarios: ShortList = Field(default_factory=list)
    constraints: ShortList = Field(default_factory=list)
    references: ShortList = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    assumptions: Annotated[list[Assumption], Field(max_length=LIST_LENGTH_LIMIT)] = Field(
        default_factory=list
    )
    # Filled by the app only, so no length limits that could block the app's own work.
    open_items: list[str] = Field(default_factory=list)
    answered_questions: list[Annotated[int, Field(ge=1, le=QUESTION_COUNT)]] = Field(
        default_factory=list
    )


class Ambiguity(_Shape):
    text: ShortText
    # Material: it changes what gets built, so the developer must decide (rule R3).
    material: bool
    # Material only: 2 or 3 choices. Checked by da_understand_checks, so the count problem is
    # reported in plain words and sent back to the interpreter.
    options: list[ShortText] = Field(default_factory=list)
    # Minor only: what was assumed and why.
    assumption: Assumption | None = None


class InterpreterReply(_Shape):
    # Field name -> new value. Which names and value types are allowed is checked by
    # da_understand_checks, so a wrong one becomes a plain retry note.
    updates: dict[str, str | list[str]] = Field(default_factory=dict)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    hint: str = Field(default="", max_length=HINT_LIMIT)


class ChatMessage(BaseModel):
    # frozen=True: chat messages are append-only, in memory too (rule R5).
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    sent_at: AwareDatetime
    speaker: Speaker
    text: str


class PendingDecision(_Shape):
    question: ShortText
    options: list[ShortText]


class UnderstandSession(_Shape):
    """The working state of one unfinished conversation, like a work file between screens."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    step: Step = "question"
    current_question: int = Field(default=1, ge=1, le=QUESTION_COUNT)
    record: RequestRecord
    # Asked one at a time, first in the list first.
    pending_decisions: list[PendingDecision] = Field(default_factory=list)
    material_decisions_asked: int = 0
    needs_senior: bool = False
    optional_done: bool = False
    checkpoint_help: bool = False
    # The interpreter's hint, shown with the next question.
    next_hint: str = ""
    last_changed_fields: list[str] = Field(default_factory=list)
    # Stored in its own column; goes up by 1 with every save (stale-save protection, rule R7).
    revision: int = Field(default=1, ge=1)


class UnderstandView(BaseModel):
    """Everything the screen needs to show one request (used by the 2B screen)."""

    request: Request
    record: RequestRecord
    messages: list[ChatMessage]
    status_label: str
    progress_text: str
    answered_count: int
    input_mode: InputMode
    prompt: str
    choices: list[str]
    can_skip: bool
    changed_fields: list[str]
    revision: int
    demo_mode: bool
