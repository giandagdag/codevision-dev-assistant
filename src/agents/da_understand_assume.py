"""B2 S7d: "Proceed with these assumptions". One AI call writes one assumption per open decision,
each with a Given, When, Then. The AI only suggests: the app checks the reply and saves it."""

import json
import re

from pydantic import ValidationError

from agents.da_llm_client import LLMClient, LLMClientError
from agents.da_understand_agent import strip_think_block
from pydantic_classes.da_request_record_models import (
    AcceptanceCriterion,
    AssumedCase,
    RequestRecord,
)

# Marks an assumption as written by Proceed, so Confirm knows which ones become criteria.
ASSUME_BASIS = "Assumed at Proceed (no person decided this)"
ASSUME_FAILED = "I couldn't write the assumptions. Nothing was changed. Please try again."
_PROMPT = """You help a developer who has too many open decisions on one change request.
For EACH decision below, write the safest reasonable assumption as one plain sentence, and one
test case for it: given (the situation), when (the action), then (what can be seen).
Reply with JSON only, one item per decision, in the same order, each item up to 300 characters:
{{"assumptions": [{{"text": "...", "given": "...", "when": "...", "then": "..."}}]}}

Request so far:
{record}

Open decisions:
{questions}
"""


class AssumeError(Exception):
    """The call or the reply was not usable. The message is safe to show."""


def ask_assumptions(
    client: LLMClient, questions: list[str], record: RequestRecord
) -> list[AssumedCase]:
    """The checked assumptions, exactly one per question. Raises AssumeError otherwise."""
    listed = "\n".join(f"{n}. {q}" for n, q in enumerate(questions, 1))
    prompt = _PROMPT.format(record=record.model_dump_json(indent=2), questions=listed)
    try:
        text = client.complete(prompt).text
    except LLMClientError as error:
        raise AssumeError(f"{ASSUME_FAILED} ({error})") from error
    data = _load(text) or _load(strip_think_block(text))
    try:
        cases = [AssumedCase.model_validate(item) for item in (data or {}).get("assumptions", [])]
    except (ValidationError, AttributeError, TypeError) as error:
        raise AssumeError(ASSUME_FAILED) from error
    if len(cases) != len(questions):
        raise AssumeError(ASSUME_FAILED)
    return cases


def _load(text: str) -> dict | None:
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text.strip(), re.DOTALL)
    try:
        data = json.loads(fenced.group(1) if fenced else text.strip())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def criteria_for(record: RequestRecord, cases: list[AssumedCase]) -> list[AcceptanceCriterion]:
    """New success criteria for the cases whose assumption is still on the record (marked with
    the Proceed basis and not edited away), numbered after the highest existing AC number."""
    kept = {a.text for a in record.assumptions if a.basis == ASSUME_BASIS}
    numbers = [int(c.id[3:]) for c in record.acceptance_criteria]
    start = max(numbers, default=0) + 1
    chosen = [case for case in cases if case.text in kept]
    return [
        AcceptanceCriterion(
            id=f"AC-{start + offset}",
            kind="success",
            given=case.given,
            when=case.when,
            then=case.then,
        )
        for offset, case in enumerate(chosen)
    ]
