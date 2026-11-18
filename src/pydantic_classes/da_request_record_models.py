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
    "acceptance_criteria": "Acceptance criteria",
    "constraints": "Constraints",
    "references": "References",
}

CRITERION_ID_PATTERN = r"^AC-[1-9]\d*$"
CriterionKind = Literal["success", "failure"]
CRITERION_PARTS: tuple[str, ...] = ("given", "when", "then")

Speaker = Literal["developer", "assistant", "system"]

# Where the conversation is. Each step allows one kind of input (see the flow module).
# "form" is the 4-box form of the Phase 6 fixes batch; "question" and "optional" are only used by
# requests saved before that change, which finish the old one-at-a-time way.
Step = Literal[
    "form", "question", "decision", "optional", "correction", "checkpoint", "senior", "done"
]
InputMode = Literal["form", "text", "choices", "waiting", "done"]


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


class AcceptanceCriterion(_Shape):
    """One testable case: Given a situation, when an action, then something that can be seen."""

    # Given by the app, never by the AI. Renumbered AC-1..n while the request is a draft.
    id: str = Field(pattern=CRITERION_ID_PATTERN)
    kind: CriterionKind
    given: ShortText
    when: ShortText
    then: ShortText


CriteriaList = Annotated[list[AcceptanceCriterion], Field(max_length=LIST_LENGTH_LIMIT)]

# Phase 9 (Enhance). The ID of a must-not-change item; never reused, like a criterion ID.
NC_ID_PATTERN = r"^NC-[1-9]\d*$"
RequestKind = Literal["new", "enhance", "fix"]
# "" = not checked yet. "intentional" = he confirmed his local changes. "unchecked" = main could
# not be reached and he went on without the check (spec section 5).
FreshnessOverride = Literal["", "intentional", "unchecked"]


class MustNotChange(_Shape):
    """One line of the answer to "What must NOT change?"."""

    id: str = Field(pattern=NC_ID_PATTERN)
    text: ShortText


class RecordFreshness(_Shape):
    result: str = ""
    override: FreshnessOverride = ""


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
    acceptance_criteria: CriteriaList = Field(default_factory=list)
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
    # Phase 9 (Enhance). All optional with empty defaults, so records saved before it still load.
    kind: RequestKind = "new"
    targets: list[str] = Field(default_factory=list)
    today: LongText = ""
    must_not_change: list[MustNotChange] = Field(default_factory=list)
    functions_in_scope: list[str] = Field(default_factory=list)
    capability: str = ""
    capability_confirmed: bool = True
    named_senior: str = ""
    freshness: RecordFreshness = Field(default_factory=RecordFreshness)


class Ambiguity(_Shape):
    text: ShortText
    # Material: it changes what gets built, so the developer must decide (rule R3).
    material: bool
    # Material only: 2 or 3 choices. Checked by da_understand_checks, so the count problem is
    # reported in plain words and sent back to the interpreter.
    options: list[ShortText] = Field(default_factory=list)
    # Minor only: what was assumed and why.
    assumption: Assumption | None = None


class ReplyCriterion(_Shape):
    """A criterion as the AI writes it: no id. Kind and lengths are checked by da_understand_checks,
    so a problem becomes a plain retry note naming the criterion."""

    kind: str
    given: str
    when: str
    then: str


class InterpreterReply(_Shape):
    # Field name -> new value. Which names and value types are allowed is checked by
    # da_understand_checks, so a wrong one becomes a plain retry note.
    updates: dict[str, str | list[str]] = Field(default_factory=dict)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    hint: str = Field(default="", max_length=HINT_LIMIT)
    # Left out or null: the criteria stay as they are. A list: the full new list.
    acceptance_criteria: list[ReplyCriterion] | None = None


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
    # B2 S7: how many of the first pending decisions the chat already listed (batch of up to 3).
    decisions_announced: int = 0
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
    # Which Summary fields the screen shows yet (W5). The record still holds all of them.
    visible_fields: list[str]
    # At a decision the text box opens for "Other, type here" (W3).
    custom_choice_allowed: bool
    # The label of the Send button: at the checkpoint it says what typing does there.
    send_label: str = "Send"
    # What the open text box says about typing, next to the choice buttons ("" = nothing special).
    text_prompt: str = ""
    revision: int
    demo_mode: bool
