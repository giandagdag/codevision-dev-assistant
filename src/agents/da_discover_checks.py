"""App checks for Discover's one AI reply and for the developer's hint (spec 3.4, 3.5).

The AI suggests, the app decides (rule R1). Shape, allowed values and length limits are enforced
by the DiscoveryReply model; this file adds the checks the model cannot do: every cited hit must
be one we sent, and no code in any text. Each problem is a plain sentence that goes back to the
AI as a retry note.
"""

from pydantic import ValidationError

from agents.da_understand_checks import (
    describe_validation_error,
    developer_message_problem,
    find_code,
)
from pydantic_classes.da_discovery_models import CITING_KINDS, DiscoveryReply

HINT_LIMIT = 300


def find_discovery_problems(reply: DiscoveryReply, sent_hit_ids: set[int]) -> list[str]:
    """Every reason the reply cannot be used. An empty list means it is fine."""
    problems: list[str] = []
    for number, finding in enumerate(reply.findings, start=1):
        invented = sorted(set(finding.hit_ids) - sent_hit_ids)
        if invented:
            listed = ", ".join(str(hit_id) for hit_id in invented)
            problems.append(
                f"Finding {number} cites hit_ids that were not sent: {listed}. "
                "Use only the hit numbers you were given."
            )
        if finding.kind in CITING_KINDS and not finding.hit_ids:
            problems.append(
                f"Finding {number} (kind {finding.kind}) must cite at least one hit_ids number."
            )
    for where, text in _all_text(reply):
        line = find_code(text)
        if line is not None:
            problems.append(
                f"{where} contains code ('{line[:60]}'). Describe it in plain words, no code."
            )
    return problems


def describe_shape_problems(error: ValidationError) -> list[str]:
    return [f"The reply has the wrong shape: {line}" for line in describe_validation_error(error)]


def hint_problem(text: str) -> str | None:
    """Why the developer's hint cannot be used, or None if it is fine (spec 3.5)."""
    problem = developer_message_problem(text)
    if problem:
        return problem
    if len(text.strip()) > HINT_LIMIT:
        return (
            f"Your hint is {len(text.strip())} characters long. The limit is {HINT_LIMIT}. "
            "Please shorten it: name a feature, file or term."
        )
    if find_code(text) is not None:
        return "Please describe what is missing in words. Code cannot be used as a hint."
    return None


def _all_text(reply: DiscoveryReply) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for number, finding in enumerate(reply.findings, start=1):
        texts.append((f"Finding {number} title", finding.title))
        texts.append((f"Finding {number} explanation", finding.explanation))
    for number, limitation in enumerate(reply.limitations, start=1):
        texts.append((f"Limitation {number}", limitation))
    return texts
