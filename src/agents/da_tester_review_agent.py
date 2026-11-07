"""The AI call of Layer C (Phase 7 spec section 4): one review prompt to the Tester, checked.

One call for checks 4, 5 and 6 together (D-B). A prompt that is too big, or an HTTP 400, splits the
review into one call per planned file (D-C). An unusable reply is asked for once more with the
problems listed (`tester_max_attempts`); still unusable means Unable to assess (D-D). Like the
other agents, the AI only proposes: da_tester_review.py decides which findings count.

The scripted reply for the fake provider and the pretend work server is here too, so both prove
the same path.
"""

import json
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from agents import da_build_agent as build_agent
from agents.da_approach_agent import load_json
from agents.da_llm_client import ContextTooLargeError, LLMClient, LLMClientError
from agents.da_rejected_reply_log import write_rejected_reply
from agents.da_tester_review import (
    REVIEW_MARKER,
    TOO_BIG_FOR_TESTER,
    ReviewInput,
    build_review_prompt,
    round_of_prompt,
)
from agents.da_understand_checks import describe_validation_error
from da_logging import get_logger
from pydantic_classes.da_tester_models import ReplyFinding, TesterReviewReply

logger = get_logger(__name__)

NOT_JSON_NOTE = "The reply was not valid JSON. Reply with JSON only."
STEP = "tester_review"

# Test-only switches for the fake provider (add to the Phase 6 ones in da_build_agent):
#   review_unusable          the Tester's reply is not JSON, every time
#   review_must_fix_always   every review finds a Must fix
#   review_empty             every review finds nothing
# no_answer and too_big (Phase 6) also work, because they act on every call.


@dataclass
class ReviewOutcome:
    """The checked result of the whole AI side of one review."""

    # "" when the findings can be used; else "unable" (unusable twice), "unreachable" (no answer)
    # or "too_big" (not even one file fits).
    kind: str = ""
    message: str = ""
    findings: list[ReplyFinding] = field(default_factory=list)
    calls: int = 0
    attempts: int = 0
    prompt_chars: int = 0
    model: str = ""

    @property
    def ok(self) -> bool:
        return self.kind == ""


def review_code(client: LLMClient, data: ReviewInput, request_id: str) -> ReviewOutcome:
    """Ask the Tester about the round's code. Never raises for a bad reply or no answer."""
    limit = data.policy.tester_max_prompt_chars
    whole = build_review_prompt(data)
    outcome = ReviewOutcome(model=getattr(client, "model", ""))
    if len(whole) <= limit:
        _ask(client, whole, data, request_id, outcome)
        if outcome.kind != "too_big":
            return outcome  # a good reply, or a problem that splitting cannot cure
        outcome.kind, outcome.message = "", ""  # an HTTP 400 on the whole prompt: try per file
    return _review_per_file(client, data, request_id, outcome, limit)


def _review_per_file(client, data: ReviewInput, request_id, outcome, limit) -> ReviewOutcome:
    outcome.findings, outcome.calls, outcome.prompt_chars = [], 0, 0
    for path in data.planned_paths:
        prompt = build_review_prompt(data, only_file=path)
        if len(prompt) > limit:
            return _too_big(outcome)
        if _ask(client, prompt, data, request_id, outcome) is None:
            return _too_big(outcome) if outcome.kind == "too_big" else outcome
    return outcome


def _too_big(outcome: ReviewOutcome) -> ReviewOutcome:
    outcome.kind, outcome.message = "too_big", TOO_BIG_FOR_TESTER
    return outcome


def _ask(client, prompt: str, data: ReviewInput, request_id: str, outcome: ReviewOutcome):
    """One call with retries. On success, adds its findings to the outcome and returns the reply.
    Otherwise sets outcome.kind and returns None."""
    sent, problems = prompt, []
    for attempt in range(1, data.policy.tester_max_attempts + 1):
        outcome.attempts += 1
        try:
            reply = client.complete(sent)
        except ContextTooLargeError as error:
            logger.warning("Tester review: the AI said the prompt is too big (%s).", error)
            outcome.kind, outcome.message = "too_big", TOO_BIG_FOR_TESTER
            return None
        except LLMClientError as error:
            logger.warning("Tester review could not reach the AI (%s).", error)
            outcome.kind, outcome.message = "unreachable", str(error)
            return None
        outcome.model = reply.model or outcome.model
        parsed, problems = _check_reply(reply.text)
        if parsed is not None:
            outcome.calls += 1
            outcome.prompt_chars += len(prompt)
            outcome.findings += parsed.findings
            return parsed
        write_rejected_reply(
            request_id, attempt, reply.provider, reply.model, problems, reply.text, step=STEP
        )
        sent = prompt + _retry_note(problems)
    outcome.kind = "unable"
    outcome.message = "The Tester's reply could not be used."
    return None


def _check_reply(text: str) -> tuple[TesterReviewReply | None, list[str]]:
    data = load_json(text)
    if not isinstance(data, dict):
        return None, [NOT_JSON_NOTE]
    try:
        return TesterReviewReply.model_validate(data), []
    except ValidationError as error:
        return None, [
            f"The reply has the wrong shape: {line}" for line in describe_validation_error(error)
        ]


def _retry_note(problems: list[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        f"\n\nYour previous reply was not accepted, for these reasons:\n{listed}\n"
        "Reply again in the same format as before, fixing these problems."
    )


# --- the scripted reply (fake provider and pretend work server) ---

_CODE_BLOCK = re.compile(r"^### (\S+) \((?:create|modify)\)\n((?:[ \d]{4}\| .*\n?)*)", re.MULTILINE)
_CODE_LINE = re.compile(r"^\s*(\d+)\| (.*)$")
_RULE_ID = re.compile(r"\bCV-[A-Z]+-\d{3}\b")
_RU = re.compile(r"\bRU-\d+\b")
MUST_FIX_FILE = "excel_processor.py"
SCRIPT_REVIEW_MODEL = "fake-review-script"


def scripted_review_reply(prompt: str, switches: frozenset[str] | None = None) -> str:
    """The scripted answer to a review prompt, chosen by the `Round: N` line. Round 2 gives one
    Must fix. Later rounds give a Should fix and an FYI with good evidence, plus one finding whose
    quote is not in the file (it is dropped). Round 1 finds nothing."""
    switches = build_agent.FAKE_SWITCHES if switches is None else switches
    if "review_unusable" in switches:
        return "Sorry, here is my review in words and not in JSON."
    if "review_empty" in switches:
        return json.dumps({"findings": []})
    blocks = _code_blocks(prompt)
    if not blocks:
        return json.dumps({"findings": []})
    number = round_of_prompt(prompt)
    must_fix = "review_must_fix_always" in switches or number == 2
    if must_fix:
        path = _pick(blocks, MUST_FIX_FILE)
        message = "This file does more than the plan says."
        item = _finding(blocks, path, 5, "must_fix", f"PLAN:{path}", message)
        return json.dumps({"findings": [item]})
    if number < 2:
        return json.dumps({"findings": []})
    path, other = _pick(blocks, MUST_FIX_FILE), _pick(blocks, "upload_validator.py")
    rule = (_RULE_ID.findall(prompt) or ["CV-PY-001"])[0]
    reuse = (_RU.findall(prompt) or [f"PLAN:{path}"])[0]
    findings = [
        _finding(blocks, path, 6, "should_fix", rule, "A judgement rule is not fully kept here."),
        _finding(blocks, other, 4, "fyi", reuse, "This follows the reuse decision."),
        {
            "check": 5,
            "severity": "must_fix",
            "file": path,
            "line": 1,
            "quote": "this text is not in any file",
            "cites": f"PLAN:{path}",
            "message": "A made-up finding that the evidence rule drops.",
        },
    ]
    return json.dumps({"findings": findings})


def _code_blocks(prompt: str) -> dict[str, list[tuple[int, str]]]:
    """path -> [(line number, text)] for the first non-empty lines of each block in the prompt."""
    found = {}
    for path, body in _CODE_BLOCK.findall(prompt):
        lines = [_CODE_LINE.match(line) for line in body.splitlines()]
        found[path] = [(int(m.group(1)), m.group(2)) for m in lines if m and m.group(2).strip()]
    return found


def _pick(blocks: dict, name: str) -> str:
    return next((path for path in blocks if path.endswith(name)), next(iter(blocks)))


def _finding(blocks: dict, path: str, check: int, severity: str, cites: str, message: str) -> dict:
    lines = blocks[path]
    number, text = lines[0] if lines else (1, "")
    return {
        "check": check,
        "severity": severity,
        "file": path,
        "line": number,
        "quote": text.strip(),
        "cites": cites,
        "message": message,
    }


def is_review_prompt(prompt: str) -> bool:
    return bool(re.search(rf"^{re.escape(REVIEW_MARKER)}$", prompt, re.MULTILINE))
