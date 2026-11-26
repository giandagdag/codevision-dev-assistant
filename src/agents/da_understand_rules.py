"""Fix G9 U5: what the rule check means for the Understand screen. Plain code, no AI, no database.

The flow (da_understand_flow) runs the check and saves its result on the session. This module only
reads that result: the lines that block Confirm, the buttons, and what a button changes.
"""

import re

from agents.da_rule_check_agent import COULD_NOT_RUN
from agents.da_rule_conflicts import SUMMARY, record_fingerprint
from pydantic_classes.da_request_record_models import (
    LIST_ITEM_LIMIT,
    RequestRecord,
    UnderstandSession,
)
from pydantic_classes.da_rule_conflict_models import RuleConflict

USE_WORDING_PREFIX = "Use the suggested wording "  # then the conflict's number
CHANGE_MYSELF_PREFIX = "Change it myself "  # then the conflict's number
ASK_EXCEPTION_PREFIX = "Ask for an exception "  # then the number; the box holds the reason
EXCEPTION_MIN_CHARS = 10
EXCEPTION_NEEDS_REASON = (
    f"Type the reason in the box first (at least {EXCEPTION_MIN_CHARS} characters), "
    "then press Ask for an exception."
)
TRY_AGAIN_OPTION = "Try again"
_RX_LINE = re.compile(r"^(RX-\d+): (.+?) allowed for (.+?), approved by ")
EXCEPTION_PROMPT_HEAD = (
    "A senior allowed these exceptions to the rulebook. They beat the rule they name, "
    "for that criterion only:\n"
)
CHANGE_MYSELF_MESSAGE = (
    "Type the new wording in the box and press Send. The rule check runs again when you confirm."
)
NO_WORDING_MESSAGE = "This conflict has no suggested wording. Please change it yourself."


def open_conflicts(session: UnderstandSession) -> list[RuleConflict]:
    """The conflicts that still count: only when the check read the text as it is now."""
    if session.rule_check_state == "ok" and _current(session):
        allowed = excepted_pairs(session.record)
        return [c for c in session.rule_conflicts if (c.criterion, c.rule) not in allowed]
    return []


def exception_ids(record: RequestRecord) -> dict[tuple[str, str], str]:
    """(criterion, rule) -> "RX-n" for every exception a senior allowed (RX-n lines)."""
    found = (_RX_LINE.match(line) for line in record.exceptions)
    return {(m.group(3), m.group(2)): m.group(1) for m in found if m}


def excepted_pairs(record: RequestRecord) -> set[tuple[str, str]]:
    return set(exception_ids(record))


def exception_prompt_lines(record: RequestRecord) -> str:
    """The RX-n lines for the Approach, Build and Tester prompts ("" when there are none)."""
    if not record.exceptions:
        return ""
    return EXCEPTION_PROMPT_HEAD + "\n".join(f"- {line}" for line in record.exceptions) + "\n"


def exception_line(record: RequestRecord, rule: str, criterion: str, who: str, why: str) -> str:
    """The next RX-n line (spec U6 wording)."""
    number = len(record.exceptions) + 1
    return f"RX-{number}: {rule} allowed for {criterion}, approved by {who}, {why}"


def check_failed(session: UnderstandSession) -> bool:
    return session.rule_check_state == "failed" and _current(session)


def gate_lines(session: UnderstandSession) -> list[str]:
    """The lines that stop Confirm, in plain words, one per open conflict (U5)."""
    lines = [_conflict_line(number, c) for number, c in enumerate(open_conflicts(session), 1)]
    if check_failed(session):
        lines.append(COULD_NOT_RUN)
    return lines


def buttons(session: UnderstandSession) -> list[str]:
    """Per conflict: use the suggested wording, or change it yourself. Try again after a failure."""
    out: list[str] = []
    for number in range(1, len(open_conflicts(session)) + 1):
        out += [
            f"{USE_WORDING_PREFIX}{number}",
            f"{CHANGE_MYSELF_PREFIX}{number}",
            f"{ASK_EXCEPTION_PREFIX}{number}",
        ]
    if check_failed(session):
        out.append(TRY_AGAIN_OPTION)
    return out


def conflict_for(session: UnderstandSession, option: str, prefix: str) -> RuleConflict | None:
    """The conflict a numbered button stands for, or None when the number is not an open one."""
    number = option.removeprefix(prefix)
    found = open_conflicts(session)
    return found[int(number) - 1] if number.isdigit() and 1 <= int(number) <= len(found) else None


def with_wording(record: RequestRecord, conflict: RuleConflict) -> tuple[RequestRecord, str]:
    """The record with the suggested wording in the place the conflict names, and the field name.
    Raises ValueError when there is no wording or the place is gone."""
    wording = conflict.fix.strip()[:LIST_ITEM_LIMIT]
    if not wording:
        raise ValueError(NO_WORDING_MESSAGE)
    place = conflict.criterion
    if place == SUMMARY:
        return record.model_copy(update={"expected_behaviour": wording}), "expected_behaviour"
    if place.startswith("DD-") and place[3:].isdigit() and 0 < int(place[3:]) <= len(
        record.decisions
    ):
        decisions = list(record.decisions)
        index = int(place[3:]) - 1
        decisions[index] = decisions[index].model_copy(update={"choice": wording})
        return record.model_copy(update={"decisions": decisions}), "decisions"
    criteria = [
        c.model_copy(update={"then": wording}) if c.id == place else c
        for c in record.acceptance_criteria
    ]
    if criteria == record.acceptance_criteria:
        raise ValueError(NO_WORDING_MESSAGE)
    return record.model_copy(update={"acceptance_criteria": criteria}), "acceptance_criteria"


def _current(session: UnderstandSession) -> bool:
    return session.rule_check_for == record_fingerprint(session.record)


def _conflict_line(number: int, conflict: RuleConflict) -> str:
    title = f" ({conflict.title})" if conflict.title else ""
    return (
        f"{number}. {conflict.criterion} conflicts with rule {conflict.rule}{title}: "
        f"{conflict.why.rstrip('. ')}. Suggested wording: {conflict.fix}"
    )
