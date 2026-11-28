"""Fix G9 U2: the rule check. One AI call that reads the whole record against the rulebook.

The app decides: the reply is only a list of suggestions, and plain code keeps the real ones
(da_rule_conflicts). A call that fails or cannot be read is "could not run", never "no conflicts".
"""

from dataclasses import dataclass, field
from pathlib import Path

from agents.da_llm_client import LLMClient, LLMClientError
from agents.da_rejected_reply_log import write_rejected_reply
from agents.da_reply_reader import read_json_object
from agents.da_rule_conflicts import (
    keep_real_conflicts,
    keep_real_gaps,
    plain_conflicts,
    rulebook_text,
    texts_of,
    titled,
)
from agents.da_understand_agent import get_understand_client
from configs.da_config import ConfigError, Settings
from da_logging import get_logger
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rule_conflict_models import Gap, RuleConflict
from pydantic_classes.da_rulebook_models import Rulebook

logger = get_logger(__name__)

PROMPT_FILE = Path(__file__).resolve().parents[1] / "data" / "da_rule_check_prompt.md"
STEP = "rule_check"  # the fake script step
MARKER = "You are the rule check of a developer assistant"  # the prompt's first words
COULD_NOT_RUN = "The rule and gap check could not run: Try again"
CONFLICT_KEYS = ("criterion", "rule", "why", "fix")
GAP_KEYS = ("case", "question", "suggested_criterion")


@dataclass(frozen=True)
class RuleCheckResult:
    ran: bool
    conflicts: list[RuleConflict] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)


def build_prompt(record: RequestRecord, rulebook: Rulebook) -> str:
    values = {
        "purpose": rulebook.charter.purpose,
        "out_of_scope": "\n".join(
            f"{n}. {item}" for n, item in enumerate(rulebook.charter.out_of_scope, 1)
        )
        or "(none)",
        "rules": rulebook_text(rulebook),
        "request": "\n\n".join(f"[{place}]\n{text}" for place, text in texts_of(record).items()),
    }
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    # One pass per marker; request text is filled last so a marker typed inside it stays text.
    for name in ("purpose", "out_of_scope", "rules"):
        prompt = prompt.replace("{{" + name + "}}", values[name], 1)
    return prompt.replace("{{request}}", values["request"], 1)


def run_rule_check(
    settings: Settings,
    record: RequestRecord,
    rulebook: Rulebook,
    client: LLMClient | None = None,
) -> RuleCheckResult:
    """Plain conflicts plus the AI's, real ones only. One AI call, no database lock held."""
    plain = plain_conflicts(record, rulebook)
    try:
        client = client or get_understand_client(settings, STEP)
        reply = client.complete(build_prompt(record, rulebook))
    except (ConfigError, LLMClientError):
        logger.warning("Rule check: the AI call failed")
        return RuleCheckResult(ran=False)
    data = read_json_object(reply.text)
    asked = data.get("conflicts") if data else None
    if not isinstance(asked, list):
        logger.warning("Rule check: the AI reply could not be read")
        write_rejected_reply(
            record.request_id, 1, reply.provider, reply.model, ["not a conflicts list"],
            reply.text, step=STEP,
        )  # fmt: skip
        return RuleCheckResult(ran=False)
    from_ai = [_conflict(item) for item in asked if isinstance(item, dict)]
    found = keep_real_conflicts([c for c in from_ai if c], record, rulebook)
    # No "uncovered" key (an older script or reply) means no gaps, never a failure.
    uncovered = data.get("uncovered")
    gaps = [_gap(item) for item in uncovered if isinstance(item, dict)] if isinstance(
        uncovered, list
    ) else []
    return RuleCheckResult(
        ran=True,
        conflicts=titled(_merge(plain, found), rulebook),
        gaps=keep_real_gaps([g for g in gaps if g], record, rulebook),
    )


def _gap(item: dict) -> Gap | None:
    values = [str(item.get(key, "")).strip() for key in GAP_KEYS]
    return Gap(*values) if all(values[:2]) else None


def _conflict(item: dict) -> RuleConflict | None:
    values = [str(item.get(key, "")).strip() for key in CONFLICT_KEYS]
    return RuleConflict(*values) if all(values[:2]) else None


def _merge(plain: list[RuleConflict], from_ai: list[RuleConflict]) -> list[RuleConflict]:
    """Plain conflicts first; an AI conflict for the same place and rule is not repeated."""
    seen = {(c.criterion, c.rule) for c in plain}
    return [*plain, *(c for c in from_ai if (c.criterion, c.rule) not in seen)]
