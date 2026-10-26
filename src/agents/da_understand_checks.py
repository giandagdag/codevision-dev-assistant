"""App checks for Understand (spec 3.5). Plain Python, no AI.

The app decides; the interpreter only suggests (rule R2). Every check returns plain sentences,
so the developer, or the interpreter on its retry, sees the whole list at once.
"""

import re

from pydantic import ValidationError

from pydantic_classes.da_request_record_models import (
    FIELD_LABELS,
    INTERPRETER_FIELDS,
    LIST_FIELDS,
    QUESTION_COUNT,
    TEXT_FIELDS,
    InterpreterReply,
    RequestRecord,
)

MAX_MESSAGE_LENGTH = 4000
SCOPE_CONFLICT_PREFIX = "Scope conflict: "

# Fields where an invented file or function name would mislead later phases (spec 3.5).
NAME_CHECKED_FIELDS: tuple[str, ...] = ("functional_flow", "expected_behaviour")

GATE_TEXT_FIELDS: tuple[str, ...] = (
    "title",
    "objective",
    "reason",
    "current_behaviour",
    "expected_behaviour",
    "inputs",
    "outputs",
)
MIN_FLOW_STEPS = 2

_CODE_FENCE = "```"
# A line that starts like Python code. Lower case only, so "Class sizes..." in a sentence passes.
_CODE_LINE = re.compile(r"^\s*(?:def|class|import)\s|^\s*from\s+\S+\s+import\s", re.MULTILINE)

_PYTHON_FILE = re.compile(r"\b[\w-]+\.py\b")
# A name straight after "(" with no space, like check_type() or check_type(file).
_FUNCTION_CALL = re.compile(r"\b[A-Za-z_]\w*\(([^()]*)\)")
# "worksheet(s)" is an English plural, not a function call.
_PLURAL_ENDINGS = frozenset({"s", "es", "ies"})
# Each part starts with a letter or "_" and is at least 2 characters, so "e.g.", "i.e." and
# "v1.2" never match, but "upload.check_type" does.
_DOTTED_NAME = re.compile(r"\b[A-Za-z_]\w+(?:\.[A-Za-z_]\w+)+\b")

# A short fixed list (rule R8). Each pattern comes with the words used in the refusal.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "an API key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "a cloud access key"),
    (
        re.compile(r"\b(?:password|passwd|pwd|secret|api[_ -]?key|token)\s*[:=]\s*\S+", re.I),
        "a password or key",
    ),
)


def developer_message_problem(text: str) -> str | None:
    """Why a developer's message cannot be accepted, or None if it is fine (rules R8, R9)."""
    if not text.strip():
        return "Please type a message first."
    if len(text) > MAX_MESSAGE_LENGTH:
        return (
            f"Your message is {len(text):,} characters long. The limit is "
            f"{MAX_MESSAGE_LENGTH:,}. Please shorten it and send it again."
        )
    secret = find_secret(text)
    if secret:
        return (
            f"This message looks like it contains {secret}, so it was not saved or sent. "
            "Remove it and send the message again. Secrets never belong in a change request."
        )
    return None


def find_secret(text: str) -> str | None:
    """What kind of secret the text seems to hold, such as "an API key", or None."""
    for pattern, what in _SECRET_PATTERNS:
        if pattern.search(text):
            return what
    return None


def find_reply_problems(
    reply: InterpreterReply, record: RequestRecord, developer_text: str
) -> list[str]:
    """Every reason the interpreter's reply cannot be used. An empty list means it is fine."""
    problems = _update_field_problems(reply) + _ambiguity_problems(reply)
    if not problems:
        # Only build the record once the field names and types are right.
        try:
            build_candidate(record, reply)
        except ValidationError as error:
            problems += [f"A value breaks a limit: {p}" for p in describe_validation_error(error)]
    problems += _code_problems(reply)
    problems += _invented_name_problems(reply, developer_text)
    return problems


def build_candidate(record: RequestRecord, reply: InterpreterReply) -> RequestRecord:
    """The record with the reply's updates and new assumptions applied, checked by Pydantic.

    Raises ValidationError if a limit is broken. The record passed in is never changed.
    """
    data = record.model_dump()
    for name, value in reply.updates.items():
        data[name] = value.strip() if isinstance(value, str) else [v.strip() for v in value]
    known = record.assumptions
    for ambiguity in reply.ambiguities:
        if not ambiguity.material and ambiguity.assumption and ambiguity.assumption not in known:
            known = [*known, ambiguity.assumption]
    data["assumptions"] = [assumption.model_dump() for assumption in known]
    # model_validate, not model_copy: model_copy would skip the limit checks.
    return RequestRecord.model_validate(data)


def refresh_scope_conflicts(record: RequestRecord) -> RequestRecord:
    """Turn every item that is both in scope and out of scope into an open item.

    Recomputed after every reply, so a later correction that removes the clash also clears it.
    Never fixed silently: the developer has to say which side is right.
    """
    out_of_scope = {item.strip().lower() for item in record.out_of_scope}
    conflicts = [
        f'{SCOPE_CONFLICT_PREFIX}"{item}" is both in scope and out of scope.'
        for item in record.in_scope
        if item.strip().lower() in out_of_scope
    ]
    kept = [item for item in record.open_items if not item.startswith(SCOPE_CONFLICT_PREFIX)]
    return record.model_copy(update={"open_items": kept + conflicts})


def confirmation_gate_problems(record: RequestRecord, waiting_decisions: int) -> list[str]:
    """Every reason the record cannot be confirmed yet, in plain words (spec 3.5)."""
    problems = [
        f"Question {number} has not been answered yet."
        for number in range(1, QUESTION_COUNT + 1)
        if number not in record.answered_questions
    ]
    problems += [
        f"{FIELD_LABELS[name]} is empty."
        for name in GATE_TEXT_FIELDS
        if not getattr(record, name).strip()
    ]
    steps = len(record.functional_flow)
    if steps < MIN_FLOW_STEPS:
        problems.append(
            f"The functional flow needs at least {MIN_FLOW_STEPS} steps (it has {steps})."
        )
    if not record.success_scenarios:
        problems.append("At least 1 success scenario is needed.")
    if not record.failure_scenarios:
        problems.append("At least 1 failure scenario is needed.")
    problems += [f"Open item: {item}" for item in record.open_items]
    if waiting_decisions:
        problems.append(f"Decisions still waiting for your choice: {waiting_decisions}.")
    return problems


def describe_validation_error(error: ValidationError) -> list[str]:
    lines = []
    for problem in error.errors():
        where = ".".join(str(part) for part in problem["loc"]) or "(top level)"
        lines.append(f"{where}: {problem['msg']}")
    return lines


def contains_code(text: str) -> bool:
    return find_code(text) is not None


def find_code(text: str) -> str | None:
    """The first piece of text that looks like code, or None."""
    if _CODE_FENCE in text:
        return _CODE_FENCE
    match = _CODE_LINE.search(text)
    if match is None:
        return None
    # The whole line, so the retry note can say exactly which line to rephrase.
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.start())
    return text[line_start : line_end if line_end != -1 else len(text)].strip()


def find_invented_names(text: str, developer_text: str) -> list[str]:
    """File names, function calls and dotted names in text that the developer never typed."""
    found: list[str] = []
    found += _PYTHON_FILE.findall(text)
    found += [
        match.group(0)
        for match in _FUNCTION_CALL.finditer(text)
        if match.group(1).strip().lower() not in _PLURAL_ENDINGS
    ]
    found += _DOTTED_NAME.findall(text)
    typed = developer_text.lower()
    invented = []
    for name in found:
        if name.lower() not in typed and name not in invented:
            invented.append(name)
    return invented


def _update_field_problems(reply: InterpreterReply) -> list[str]:
    problems = []
    for name, value in reply.updates.items():
        if name not in INTERPRETER_FIELDS:
            problems.append(
                f"'{name}' is not a field you may fill. Use only: {', '.join(INTERPRETER_FIELDS)}."
            )
        elif name in TEXT_FIELDS and not isinstance(value, str):
            problems.append(f"'{name}' must be text, not a list.")
        elif name in LIST_FIELDS and not isinstance(value, list):
            problems.append(f"'{name}' must be a list of short items, not text.")
    return problems


def _ambiguity_problems(reply: InterpreterReply) -> list[str]:
    problems = []
    for ambiguity in reply.ambiguities:
        label = f"Ambiguity \"{ambiguity.text}\""
        if ambiguity.material:
            if not 2 <= len(ambiguity.options) <= 3:
                problems.append(
                    f"{label} is material, so it needs 2 or 3 options "
                    f"(it has {len(ambiguity.options)})."
                )
            if ambiguity.assumption is not None:
                problems.append(
                    f"{label} is material, so it must not have an assumption: "
                    "the developer decides."
                )
        else:
            if ambiguity.assumption is None:
                problems.append(f"{label} is minor, so it needs an assumption with its basis.")
            if ambiguity.options:
                problems.append(f"{label} is minor, so it must not have options.")
    return problems


def _code_problems(reply: InterpreterReply) -> list[str]:
    problems = []
    for text in _all_reply_text(reply):
        code = find_code(text)
        if code is not None:
            # Spec 3.5 refuses any line starting with def, class or import, even an English
            # one, so the note names the line and says how to rephrase it.
            problems.append(
                f'The reply contains code: "{code}". Describe the change in plain words only, '
                "and do not start a line with def, class, import or from ... import."
            )
    return problems


def _invented_name_problems(reply: InterpreterReply, developer_text: str) -> list[str]:
    problems = []
    for name in NAME_CHECKED_FIELDS:
        value = reply.updates.get(name)
        if value is None:
            continue
        text = value if isinstance(value, str) else "\n".join(value)
        for invented in find_invented_names(text, developer_text):
            problems.append(
                f"{FIELD_LABELS[name]} names '{invented}', which the developer did not type. "
                "Describe the step in plain words instead of naming files or functions."
            )
    return problems


def _all_reply_text(reply: InterpreterReply) -> list[str]:
    texts = [reply.hint]
    for value in reply.updates.values():
        texts += [value] if isinstance(value, str) else value
    for ambiguity in reply.ambiguities:
        texts += [ambiguity.text, *ambiguity.options]
        if ambiguity.assumption:
            texts += [ambiguity.assumption.text, ambiguity.assumption.basis]
    return texts
