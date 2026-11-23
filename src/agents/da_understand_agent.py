"""The interpreter (spec 3.4): turns a developer's answer into suggested record updates.

It only suggests (rule R2). Every reply is checked by da_understand_checks before the app uses
it; a bad reply is retried once with a note on what was wrong, then given up.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from agents.da_llm_client import LLMClient, LLMReply, get_llm_client
from agents.da_problem_kinds import problem_kinds
from agents.da_rejected_reply_log import write_rejected_reply
from agents.da_understand_checks import (
    build_candidate,
    describe_validation_error,
    find_reply_problems,
)
from configs.da_config import Settings
from da_logging import get_logger
from pydantic_classes.da_request_record_models import (
    INTERPRETER_FIELDS,
    LIST_FIELDS,
    TEXT_FIELDS,
    InterpreterReply,
    RequestRecord,
)
from pydantic_classes.da_rulebook_models import Charter

logger = get_logger(__name__)

DATA_FOLDER = Path(__file__).resolve().parents[1] / "data"
PROMPT_FILE = DATA_FOLDER / "da_understand_prompt.md"
FAKE_SCRIPT_FILE = DATA_FOLDER / "da_understand_fake_script.json"

FAILED_MESSAGE = "I couldn't process that answer. Please try again or rephrase it."
SCRIPT_MODEL = "fake-understand-script"
MAX_ATTEMPTS = 2

_EMPTY_REPLY = {"updates": {}, "ambiguities": [], "hint": ""}
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
# Some models wrap JSON in a ```json fence even when told not to; that wrapper is allowed.
_FENCED_REPLY = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
# Reasoning models (CodeVision's default is "reasoning-vlm") put their thinking in <think> tags.
# Only a block at the very start is removed, up to the FIRST closing tag (P13).
_THINK_BLOCK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
# Some servers drop the opening tag: remove everything up to and including the first closing one.
_THINK_TAIL = re.compile(r"^.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_NOT_JSON = object()


@dataclass(frozen=True)
class InterpretResult:
    """The checked outcome. record is the updated record, or None if the reply was not usable."""

    record: RequestRecord | None
    reply: InterpreterReply | None
    provider: str
    model: str
    attempts: int
    problems: list[str] = field(default_factory=list)
    # What the developer sees in the chat when the reply was not usable.
    message: str = FAILED_MESSAGE

    @property
    def ok(self) -> bool:
        return self.record is not None


class ScriptedUnderstandClient:
    """The fake provider for Understand: scripted replies for the demo (decision D-C).

    It ignores what was typed and replies with the script entry for its step. A step that comes
    up again reuses its entry; a step not in the script gets an empty reply.
    """

    def __init__(self, step: str, script_file: Path = FAKE_SCRIPT_FILE):
        self.model = SCRIPT_MODEL
        self._step = step
        self._script = json.loads(Path(script_file).read_text(encoding="utf-8"))

    def complete(self, prompt: str, system: str | None = None) -> LLMReply:
        entry = self._script.get(self._step, _EMPTY_REPLY)
        return LLMReply(text=json.dumps(entry), provider="fake", model=self.model)


def get_understand_client(settings: Settings, step: str) -> LLMClient:
    """The scripted client for the fake provider, otherwise the generator role (decision D-D)."""
    if settings.llm_provider == "fake":
        return ScriptedUnderstandClient(step)
    return get_llm_client("generator", settings)


def build_prompt(
    question: str,
    answer: str,
    record: RequestRecord,
    charter: Charter,
    rulebook_version: int,
    decided: Sequence[str] = (),
    queued: Sequence[str] = (),
) -> str:
    """The prompt text. Only the charter's purpose, scope lists and glossary go in (rule R10).

    decided and queued are the questions already decided and already waiting to be asked, so the
    interpreter returns only NEW ones (Phase 6 fixes, U5)."""
    values = {
        "rulebook_version": str(rulebook_version),
        "purpose": charter.purpose,
        "in_scope": _bullets(charter.in_scope),
        "out_of_scope": _bullets(charter.out_of_scope),
        "glossary": _bullets(f"{entry.term}: {entry.meaning}" for entry in charter.glossary),
        "record": record.model_dump_json(indent=2),
        "decided": _bullets(decided),
        "queued": _bullets(queued),
        "question": question,
        "answer": answer,
        "allowed_fields": ", ".join(INTERPRETER_FIELDS),
        "text_fields": ", ".join(TEXT_FIELDS),
        "list_fields": ", ".join(LIST_FIELDS),
    }
    template = PROMPT_FILE.read_text(encoding="utf-8")
    # One pass over the template only, so text inside the answer that looks like a
    # {{placeholder}} is never filled in.
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def interpret(
    client: LLMClient,
    question: str,
    answer: str,
    record: RequestRecord,
    charter: Charter,
    rulebook_version: int,
    developer_text: str,
    decided: Sequence[str] = (),
    queued: Sequence[str] = (),
) -> InterpretResult:
    """Ask the interpreter, check the reply, retry once with a note. The record is never changed.

    developer_text is everything the developer has typed on this request, used to tell names
    the developer gave from names the interpreter invented.
    """
    prompt = build_prompt(question, answer, record, charter, rulebook_version, decided, queued)
    sent = prompt
    for attempt in range(1, MAX_ATTEMPTS + 1):
        llm_reply = client.complete(sent)
        reply, problems = parse_reply(llm_reply.text, record, developer_text)
        if reply is not None and not problems:
            return InterpretResult(
                record=build_candidate(record, reply),
                reply=reply,
                provider=llm_reply.provider,
                model=llm_reply.model,
                attempts=attempt,
            )
        logger.warning("Interpreter reply %s was not usable: %s", attempt, problem_kinds(problems))
        write_rejected_reply(
            record.request_id,
            attempt,
            llm_reply.provider,
            llm_reply.model,
            problems,
            llm_reply.text,
        )
        sent = prompt + _retry_note(problems)
    return InterpretResult(
        record=None,
        reply=None,
        provider=llm_reply.provider,
        model=llm_reply.model,
        attempts=MAX_ATTEMPTS,
        problems=problems,
    )


def parse_reply(
    text: str, record: RequestRecord, developer_text: str
) -> tuple[InterpreterReply | None, list[str]]:
    """Read the reply text as JSON in the agreed shape, then run the app checks."""
    # The reply as it is first. Think text is cleaned only if that fails, so a hint that happens
    # to contain "</think>" is never cut (P13).
    data = _load_json(text)
    if data is _NOT_JSON:
        data = _load_json(strip_think_block(text))
    if data is _NOT_JSON:
        return None, ["The reply was not valid JSON. Reply with JSON only."]
    try:
        reply = InterpreterReply.model_validate(data)
    except ValidationError as error:
        shape_problems = describe_validation_error(error)
        return None, [f"The reply has the wrong shape: {p}" for p in shape_problems]
    return reply, find_reply_problems(reply, record, developer_text)


def _load_json(text: str):
    """Trim, remove a whole-reply ```json fence, and parse. _NOT_JSON if it does not parse."""
    text = text.strip()
    fenced = _FENCED_REPLY.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _NOT_JSON


def strip_think_block(text: str) -> str:
    """Remove a leading reasoning block, or with no opening tag everything up to the first
    closing tag. Think text inside or after the JSON is never touched."""
    if _THINK_BLOCK.match(text):
        return _THINK_BLOCK.sub("", text, count=1)
    if "<think>" not in text.lower():
        return _THINK_TAIL.sub("", text, count=1)
    return text


def _retry_note(problems: list[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        f"\n\nYour previous reply was not accepted, for these reasons:\n{listed}\n"
        "Reply again with JSON only, fixing these problems."
    )


def _bullets(items) -> str:
    lines = [f"- {item}" for item in items]
    return "\n".join(lines) or "- (none)"
