"""Fix G5 P2 and P3: the AI safety check, and the plain-code decision that uses both checks.

The word check (da_safety_gate) always runs. The AI check adds judgement. Harmful intent found by
the words stops the request whatever the AI says: the AI can only make the check stricter.
"""

from dataclasses import dataclass
from pathlib import Path

from agents.da_llm_client import LLMClient, LLMClientError, LLMReply, get_llm_client
from agents.da_reply_reader import read_json_object
from agents.da_safety_gate import KIND_BOTH, KIND_DESTRUCTIVE, KIND_INTENT, GateScan
from configs.da_config import Settings
from da_logging import get_logger

logger = get_logger(__name__)

PROMPT_FILE = Path(__file__).resolve().parents[1] / "data" / "da_safety_prompt.md"
VERDICTS = ("ok", "stop", "review")
REASON_LIMIT = 300

# What decide() returns.
DECISION_STOP = "stop"
DECISION_P5 = "needs_p5"  # destructive work: continues only with the four P5 items
DECISION_GO = "go"


# The chat line (P4) and the audit events. {what} is one of the two phrases below.
STOP_LINE = (
    "I can't help build this. {what} is destructive and cannot be undone, and the reason given "
    "is not a business need. This request has been sent to Admin."
)
WHAT_DESTRUCTIVE = "Removing data this way"
WHAT_OTHER = "This request"
EVENT_STOP = "safety_stop"
EVENT_RELEASED = "safety_released"


def stop_line(scan: GateScan) -> str:
    destructive = scan.kind in (KIND_DESTRUCTIVE, KIND_BOTH)
    return STOP_LINE.format(what=WHAT_DESTRUCTIVE if destructive else WHAT_OTHER)


@dataclass(frozen=True)
class SafetyVerdict:
    verdict: str  # ok, stop or review
    reason: str = ""
    ai_failed: bool = False


class FakeSafetyClient:
    """The fake provider at home: always says ok, so tests see the word check do the work."""

    model = "fake-safety"

    def complete(self, prompt: str, system: str | None = None) -> LLMReply:
        return LLMReply(
            text='{"verdict": "ok", "reason": "fake check"}', provider="fake", model=self.model
        )


def get_safety_client(settings: Settings) -> LLMClient:
    """The Understand role model (the generator role), or the fake one."""
    if settings.llm_provider == "fake":
        return FakeSafetyClient()
    return get_llm_client("generator", settings)


def build_prompt(request_text: str) -> str:
    # One replace on a known marker, so a marker typed inside the request is never filled in twice.
    return PROMPT_FILE.read_text(encoding="utf-8").replace("{{request_text}}", request_text, 1)


def check_request(
    settings: Settings, request_text: str, client: LLMClient | None = None
) -> SafetyVerdict:
    """Ask the AI. A failed call or an unreadable reply is ai_failed (the words decide alone)."""
    try:
        reply = (client or get_safety_client(settings)).complete(build_prompt(request_text))
    except LLMClientError:
        logger.warning("Safety check: the AI call failed")
        return SafetyVerdict("ok", ai_failed=True)
    data = read_json_object(reply.text)
    verdict = str(data.get("verdict", "")).strip().lower() if data else ""
    if verdict not in VERDICTS:
        logger.warning("Safety check: the AI reply could not be read")
        return SafetyVerdict("ok", ai_failed=True)
    return SafetyVerdict(verdict, str(data.get("reason", "")).strip()[:REASON_LIMIT])


def decide(scan: GateScan, verdict: SafetyVerdict) -> str:
    """stop, needs_p5 or go. Intent always stops; an AI stop always stops."""
    if scan.kind in (KIND_INTENT, KIND_BOTH) or verdict.verdict == "stop":
        return DECISION_STOP
    if scan.kind == KIND_DESTRUCTIVE or verdict.verdict == "review":
        return DECISION_P5
    return DECISION_GO
