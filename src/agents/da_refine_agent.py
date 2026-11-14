"""The AI calls of Refine (Phase 8 spec sections 4, 5 and 7): suggest a lane, revise the record
(changes only), and write one repro test. Like the other agents, the AI only proposes: plain code
(da_refine_checks.py) decides what is used.

What the AI sees: the record, the accepted approach, the test plan cases, the latest label and
finding lines, and the developer's words between marker lines as information. Never the chat.
Never code: the lane call and the Tester call get none (decision D-G, watch item W6).

The scripted replies for the fake provider and the pretend work server are here too, so both
prove the same path.
"""

import ast
import json
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from agents import da_build_agent as build_agent
from agents.da_approach_agent import fill_template, load_json
from agents.da_build_agent import AIResult, format_approach, format_cases, format_contract_lines
from agents.da_build_checks import (
    TOO_BIG_MESSAGE,
    _file_access_problems,
    _risky_call_problems,
    case_ids_from_method,
    prompt_too_big,
)
from agents.da_guidance import guidance_block
from agents.da_llm_client import ContextTooLargeError, LLMClient, LLMClientError
from agents.da_refine_checks import check_lane_suggestion
from agents.da_rejected_reply_log import write_rejected_reply
from agents.da_understand_checks import describe_validation_error
from da_logging import get_logger
from pydantic_classes.da_approach_models import ApproachVersion, TestCase
from pydantic_classes.da_build_models import Contract
from pydantic_classes.da_refine_models import LaneSuggestion, RevisionReply
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Charter, Policy
from pydantic_classes.da_tester_models import Finding

logger = get_logger(__name__)

DATA_FOLDER = build_agent.DATA_FOLDER
LANE_PROMPT = DATA_FOLDER / "da_refine_lane_prompt.md"
REVISION_PROMPT = DATA_FOLDER / "da_refine_revision_prompt.md"
REPRO_PROMPT = DATA_FOLDER / "da_refine_repro_prompt.md"

# Which role setting suggests the lane (work fact WF-3: not decided yet). One line to change.
LANE_ROLE = "tester"
REVISION_ROLE = "generator"
REPRO_ROLE = "tester"

# The line each prompt carries so the fake and pretend servers can tell the calls apart.
LANE_MARKER = "Task: suggest a lane"
REVISION_MARKER = "Task: revise the record"
REPRO_MARKER = "Task: write a repro test"
OWN_TEST_MARKER = "Task: write a test for the developer"
SCRIPT_MODEL = "fake-refine-script"

NOT_JSON_NOTE = "The reply was not valid JSON. Reply with JSON only."
NO_CASE_NOTE = "The reply must have a CASE part and a METHOD part, exactly as shown."

# Test-only switches for the fake provider (add to the Phase 6 and 7 ones in da_build_agent):
#   lane_unusable            the lane reply is not JSON, every time
#   lane_bug_no_criterion    the lane reply says bug with no criterion
#   vague                    the own-test reply is VAGUE plus a question (Add a test case)
#   repro_passes_today      the repro test passes on today's code (does not show the bug)
#   approach_changes_criterion  the approach-lane reply would change a criterion (step 8)
#   conflict                 the rebuild's edit block overlaps his lines (step 10)


@dataclass(frozen=True)
class RefineContext:
    """Everything the lane and revision calls may see. Never the chat, never code."""

    charter: Charter
    record: RequestRecord
    approach: ApproachVersion
    cases: list[TestCase]
    policy: Policy
    label: str = ""
    findings: list[Finding] = field(default_factory=list)
    # Phase 10: guidance a senior sent, handed over once (da_guidance.py). Plain text only.
    senior_guidance: str = ""


@dataclass(frozen=True)
class ReproReply:
    """A parsed repro reply: the new case in plain words and one test method."""

    criterion_id: str
    given: str
    expect: str
    method: str
    # Own test only (F1b): the Tester found the case too vague and asks one question instead.
    question: str = ""


# --- prompts ---


def format_result(label: str, findings: list[Finding]) -> str:
    """The latest label and one line per finding: ID, severity, message. No quote, no code."""
    lines = [f"Label: {label or '(none yet)'}"]
    for item in findings:
        if item.kept:
            lines.append(f"- {item.finding_id} ({item.severity}): {item.message}")
    return "\n".join(lines)


def build_lane_prompt(context: RefineContext, feedback: str) -> str:
    values = {
        "purpose": context.charter.purpose,
        "record": context.record.model_dump_json(indent=2),
        "approach": format_approach(context.approach),
        "cases": format_cases(context.cases) or "- (none)",
        "result": format_result(context.label, context.findings),
        "feedback": feedback,
    }
    return fill_template(LANE_PROMPT, values) + guidance_block(context.senior_guidance)


def build_revision_prompt(context: RefineContext, feedback: str) -> str:
    values = {
        "purpose": context.charter.purpose,
        "version": str(context.record.version),
        "record": context.record.model_dump_json(indent=2),
        "feedback": feedback,
    }
    return fill_template(REVISION_PROMPT, values)


def build_repro_prompt(
    record: RequestRecord,
    contract: Contract,
    cases: list[TestCase],
    criterion_id: str,
    case_id: str,
    feedback: str,
    own_test: bool = False,
) -> str:
    """The bug-lane and Add-a-test-case Tester prompt. No code text of any kind goes in (D-G):
    the record, the contract (names only), this criterion's cases, and the developer's words."""
    own = [case for case in cases if case.criterion_id == criterion_id]
    prefix = f"{case_id.lower().replace('-', '')}_{criterion_id.lower().replace('-', '')}_"
    values = {
        "task": OWN_TEST_MARKER if own_test else REPRO_MARKER,
        "record": record.model_dump_json(indent=2),
        "contract": format_contract_lines(contract),
        "criterion": criterion_id,
        "cases": format_cases(own) or "- (none yet)",
        "feedback": feedback,
        "case_id": case_id,
        "method_prefix": prefix,
    }
    return fill_template(REPRO_PROMPT, values)


# --- the calls ---


def suggest_lane(client: LLMClient, context: RefineContext, feedback: str) -> AIResult:
    """One lane call, checked. `value` is the (possibly turned) LaneSuggestion; kind `bad_reply`
    after `refine_lane_max_attempts` unusable replies, and the flow then shows no suggestion."""
    prompt = build_lane_prompt(context, feedback)

    def check(text: str):
        data = load_json(text)
        if not isinstance(data, dict):
            return None, [NOT_JSON_NOTE]
        try:
            raw = LaneSuggestion.model_validate(data)
        except ValidationError as error:
            return None, [f"The reply has the wrong shape: {m}" for m in _errors(error)]
        checked, why = check_lane_suggestion(raw, context.record)
        return (checked, []) if checked else (None, [why])

    return _ask(
        client,
        prompt,
        check,
        context.record.request_id,
        "refine_lane",
        context.policy.refine_lane_max_attempts,
        context.policy.build_max_prompt_chars,
    )


def revise_record(client: LLMClient, context: RefineContext, feedback: str) -> AIResult:
    """One revision call. `value` is a RevisionReply (changes only)."""
    prompt = build_revision_prompt(context, feedback)

    def check(text: str):
        data = load_json(text)
        if not isinstance(data, dict):
            return None, [NOT_JSON_NOTE]
        try:
            return RevisionReply.model_validate(data), []
        except ValidationError as error:
            return None, [f"The reply has the wrong shape: {m}" for m in _errors(error)]

    return _ask(
        client,
        prompt,
        check,
        context.record.request_id,
        "refine_revision",
        context.policy.refine_lane_max_attempts,
        context.policy.build_max_prompt_chars,
    )


def write_repro_test(
    client: LLMClient,
    record: RequestRecord,
    contract: Contract,
    cases: list[TestCase],
    policy: Policy,
    criterion_id: str,
    case_id: str,
    feedback: str,
    own_test: bool = False,
) -> AIResult:
    """One Tester call. `value` is a ReproReply. Whether the test fails today is the sandbox's
    job (step 9), not this call's."""
    prompt = build_repro_prompt(record, contract, cases, criterion_id, case_id, feedback, own_test)
    prefix = f"test_{case_id.lower().replace('-', '')}_{criterion_id.lower().replace('-', '')}_"

    def check(text: str):
        if own_test:
            question = parse_vague_reply(text)
            if question:
                return ReproReply(criterion_id, "", "", "", question), []
        reply, problems = parse_repro_reply(text, criterion_id, prefix)
        return (reply, []) if reply else (None, problems)

    return _ask(
        client,
        prompt,
        check,
        record.request_id,
        "refine_repro",
        policy.refine_repro_max_attempts,
        policy.tester_max_prompt_chars,
    )


VAGUE_MAX_CHARS = 200
_VAGUE = re.compile(r"^\s*VAGUE\s*\n(?P<question>.+?)\s*$", re.DOTALL)


def parse_vague_reply(text: str) -> str:
    """F1b: `VAGUE` on the first line and one question after it (up to 200 characters; a longer one
    is cut). Returns the question, or "" when the reply is not a VAGUE reply."""
    found = _VAGUE.match(text)
    if not found:
        return ""
    return " ".join(found.group("question").split())[:VAGUE_MAX_CHARS]


_CASE_PART = re.compile(
    r"CASE\s*\n\s*criterion:\s*(?P<criterion>\S+)\s*\n\s*given:\s*(?P<given>.+?)\s*\n"
    r"\s*expect:\s*(?P<expect>.+?)\s*\nMETHOD\s*\n(?P<method>.+)",
    re.DOTALL,
)


def parse_repro_reply(
    text: str, criterion_id: str, prefix: str
) -> tuple[ReproReply | None, list[str]]:
    """The CASE / METHOD format, checked by plain code: one method with the agreed name and a
    docstring, no risky calls, no file access."""
    body = text.strip()
    fenced = re.match(r"^```[A-Za-z]*\s*\n(.*?)\n?```$", body, re.DOTALL)
    if fenced:
        body = fenced.group(1)
    found = _CASE_PART.search(body)
    if not found:
        return None, [NO_CASE_NOTE]
    method = found.group("method").strip("\n").rstrip() + "\n"
    problems = []
    if found.group("criterion") != criterion_id:
        problems.append(f"The criterion must be {criterion_id}.")
    problems += _method_problems(method, prefix)
    if problems:
        return None, problems
    return (
        ReproReply(
            criterion_id=criterion_id,
            given=found.group("given").strip(),
            expect=found.group("expect").strip(),
            method=method,
        ),
        [],
    )


def _method_problems(method: str, prefix: str) -> list[str]:
    try:
        tree = ast.parse(method)
    except SyntaxError as error:
        return [f"The test method has a syntax error on line {error.lineno}."]
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(tree.body) != 1 or len(functions) != 1:
        return ["Send exactly one test method and nothing else."]
    function = functions[0]
    problems = []
    if not function.name.startswith(prefix) or case_ids_from_method(function.name) is None:
        problems.append(f"Name the method test_{prefix[5:]}<short words> in lower case.")
    if not ast.get_docstring(function):
        problems.append("The method needs a one-sentence docstring.")
    problems += _risky_call_problems(tree, "the new test")
    problems += _file_access_problems(tree)
    return problems


def _errors(error: ValidationError) -> list[str]:
    return describe_validation_error(error)


def _ask(client, prompt, check, request_id: str, step: str, attempts: int, limit: int) -> AIResult:
    """Ask, check, retry with a note (`attempts` calls in all). Never raises for a bad reply or an
    AI that does not answer: the result says why."""
    if prompt_too_big(prompt, limit):
        return AIResult(None, kind="too_big", message=TOO_BIG_MESSAGE)
    sent, provider, model, problems = prompt, "", "", []
    for attempt in range(1, attempts + 1):
        try:
            reply = client.complete(sent)
        except ContextTooLargeError as error:
            logger.warning("Refine call %s: the AI said the prompt is too big (%s).", step, error)
            return AIResult(None, provider, model, attempt, "too_big", TOO_BIG_MESSAGE)
        except LLMClientError as error:
            logger.warning("Refine call %s could not reach the AI (%s).", step, error)
            return AIResult(None, provider, model, attempt, "unreachable", str(error))
        provider, model = reply.provider, reply.model
        value, problems = check(reply.text)
        if value is not None and not problems:
            return AIResult(value, provider, model, attempt)
        write_rejected_reply(request_id, attempt, provider, model, problems, reply.text, step=step)
        sent = prompt + _retry_note(problems)
    return AIResult(None, provider, model, attempts, "bad_reply", problems=problems)


def _retry_note(problems: list[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        f"\n\nYour previous reply was not accepted, for these reasons:\n{listed}\n"
        "Reply again in the same format as before, fixing these problems."
    )


# --- the scripted replies (fake provider and pretend work server) ---

_CRITERION = re.compile(r"\"id\": \"(AC-\d+)\"")
_FEEDBACK = re.compile(
    r"--- developer (?:feedback|text) starts ---\n(.*?)\n--- developer (?:feedback|text) ends ---",
    re.DOTALL,
)
_CASE_ID = re.compile(r"^Next case id: (T-\d+)$", re.MULTILINE)
_CRITERION_LINE = re.compile(r"^Criterion: (AC-\d+)$", re.MULTILINE)
_BUG_WORDS = ("bug", "crash", "wrong", "broken", "fails", "error", "does not work")
_APPROACH_WORDS = ("approach", "design", "instead", "split", "move ")


def is_refine_prompt(prompt: str) -> bool:
    return any(
        re.search(rf"^{re.escape(marker)}$", prompt, re.MULTILINE)
        for marker in (LANE_MARKER, REVISION_MARKER, REPRO_MARKER, OWN_TEST_MARKER)
    )


def scripted_refine_reply(prompt: str, switches: frozenset[str] | None = None) -> str:
    switches = build_agent.FAKE_SWITCHES if switches is None else switches
    if re.search(rf"^{re.escape(LANE_MARKER)}$", prompt, re.MULTILINE):
        return _scripted_lane(prompt, switches)
    if re.search(rf"^{re.escape(REVISION_MARKER)}$", prompt, re.MULTILINE):
        return _scripted_revision()
    own = re.search(rf"^{re.escape(OWN_TEST_MARKER)}$", prompt, re.MULTILINE)
    if own and "vague" in switches:
        return "VAGUE\nWhat exactly should happen to the file after it is uploaded?"
    return _scripted_repro(prompt, switches)


def _feedback_of(prompt: str) -> str:
    found = _FEEDBACK.search(prompt)
    return found.group(1).lower() if found else ""


def _scripted_lane(prompt: str, switches: frozenset[str]) -> str:
    if "lane_unusable" in switches:
        return "I think this is a bug, but here is my answer in words and not in JSON."
    feedback = _feedback_of(prompt)
    criteria = _CRITERION.findall(prompt)
    if "lane_bug_no_criterion" in switches:
        lane, criterion = "bug", None
    elif any(word in feedback for word in _BUG_WORDS) and criteria:
        lane, criterion = "bug", criteria[0]
    elif any(word in feedback for word in _APPROACH_WORDS):
        lane, criterion = "approach", None
    else:
        lane, criterion = "requirement", None
    reasons = {
        "bug": f"The request is right, but {criterion} does not hold.",
        "approach": "The request stays the same, but the design must change.",
        "requirement": "The request itself must change.",
    }
    return json.dumps({"lane": lane, "reason": reasons[lane], "criterion_id": criterion})


def _scripted_revision() -> str:
    return json.dumps(
        {
            "criteria_ops": [
                {
                    "op": "add",
                    "kind": "failure",
                    "given": "a file larger than 5 MB",
                    "when": "the user uploads it",
                    "then": "a message says the file is too big and nothing is saved",
                }
            ],
            "field_updates": {},
        }
    )


def _scripted_repro(prompt: str, switches: frozenset[str]) -> str:
    case_id = (_CASE_ID.findall(prompt) or ["T-90"])[0]
    criterion = (_CRITERION_LINE.findall(prompt) or ["AC-1"])[0]
    name = f"test_{case_id.lower().replace('-', '')}_{criterion.lower().replace('-', '')}_shows_bug"
    # The fake validate() does not accept .csv files yet, so a test that expects it fails today (the
    # bug is shown) and the scripted fix round (see da_build_fake_script.json, "fix_edits") makes
    # it pass. With the switch the test passes today (it does not show the bug).
    check = (
        'self.assertTrue(validate("book.xlsx"))'
        if "repro_passes_today" in switches
        else 'self.assertTrue(validate("book.csv"))'
    )
    return (
        f"CASE\ncriterion: {criterion}\n"
        "given: a valid workbook is uploaded\n"
        "expect: the upload is judged as the developer describes\n"
        f"METHOD\ndef {name}(self):\n"
        '    """The upload is judged as the developer describes."""\n'
        "    from agents.upload_validator import validate\n"
        f"    {check}\n"
    )
