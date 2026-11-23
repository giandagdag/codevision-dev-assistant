"""Plain words for why Approach refused the AI's plan (Fix G7, R2 to R4).

Every sentence here is the app's own: a check sentence, or a shape error turned into words. The
AI's reply text is never repeated (it stays in logs/da_rejected_replies.log).
"""

import re
from collections.abc import Sequence

from pydantic import ValidationError

REJECTED_HEADER = "The AI answered, but its plan broke these rules:"
REJECTED_FOOTER = "Press Try again, or change the request."
MAX_SHOWN = 3
MAX_KEPT = 12  # problems kept in the audit for the Approach tab
KEPT_LENGTH = 300
LIBRARY_HINT = (
    "Ask your admin to approve {name} in Admin, Coding standards, Libraries (it must also be "
    "installed), or change the request to use the standard library."
)
_LIBRARY_NAME = re.compile(r"^Library '([^']+)'")

_PARTS = {
    "design_choices": "design question",
    "options": "option",
    "files": "file",
    "needs_people": "person-needed item",
    "reuse_decisions": "reuse decision",
    "libraries": "library",
}
_FIELDS = {
    "summary": "the summary",
    "purpose": "the purpose",
    "reason": "the reason",
    "question": "the question",
    "impact": "the impact",
    "path": "the path",
    "action": "the action",
    "decision": "the decision",
    "label": "the label",
    "detail": "the detail",
}


def _plain_where(loc: Sequence) -> str:
    """("design_choices", 0, "options", 1) becomes "option 2 of design question 1"."""
    words: list[str] = []
    parts = list(loc)
    while parts:
        part = parts.pop(0)
        if part in _PARTS and parts and isinstance(parts[0], int):
            words.append(f"{_PARTS[part]} {parts.pop(0) + 1}")
        elif isinstance(part, str):
            words.append(_FIELDS.get(part, "a field"))
    # The innermost part reads first: "option 2 of design question 1".
    return " of ".join(reversed(words)) or "the reply"


def _plain_message(message: str) -> str:
    lower = message.lower()
    if "at most" in lower or "too long" in lower:
        return "is too long"
    if "required" in lower or "at least" in lower:
        return "is missing or empty"
    return "has a value the app cannot use"


def plain_shape_problems(error: ValidationError) -> list[str]:
    """One plain sentence per shape error, with no raw field path (R3)."""
    sentences = []
    for problem in error.errors():
        where = _plain_where(problem["loc"])
        sentences.append(
            f"The reply has the wrong shape: {where[0].upper() + where[1:]} "
            f"{_plain_message(problem['msg'])}."
        )
    return sentences


def kept_problems(problems: Sequence[str]) -> list[str]:
    """The problems saved in the audit for the Approach tab, capped."""
    return [problem[:KEPT_LENGTH] for problem in problems[:MAX_KEPT]]


def rejected_message(problems: Sequence[str]) -> str:
    """What the chat says when the AI answered but the checks refused the plan (R2, R4)."""
    lines = [f"- {problem}" for problem in problems[:MAX_SHOWN]]
    extra = len(problems) - MAX_SHOWN
    if extra > 0:
        lines.append(f"...and {extra} more (see the Approach tab)")
    parts = [REJECTED_HEADER, "\n".join(lines)]
    for problem in problems:
        found = _LIBRARY_NAME.match(problem)
        if found:
            parts.append(LIBRARY_HINT.format(name=found.group(1)))
            break
    parts.append(REJECTED_FOOTER)
    return "\n".join(parts)
