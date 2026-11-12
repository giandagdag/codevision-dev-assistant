"""The independent Tester (spec sections 5 and 8): writes the test plan and turns a typed case
into one draft case.

The Tester NEVER sees the file plan, the reuse decisions, any code or the chat (decision D-B), so
its test plan is not shaped by how the code will be built. It gets the confirmed record (with the
criteria and their IDs) and the developer's design decisions, nothing else. Like QA writing the
test script from the signed-off requirement, not from the programmer's source.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from agents.da_approach_agent import MAX_ATTEMPTS, NOT_JSON, fill_template, load_json, retry_note
from agents.da_approach_checks import find_test_case_problems, find_test_plan_problems
from agents.da_llm_client import LLMClient, LLMClientError, LLMReply, get_llm_client
from agents.da_rejected_reply_log import write_rejected_reply
from agents.da_understand_checks import describe_validation_error
from configs.da_config import Settings
from da_logging import get_logger
from pydantic_classes.da_approach_models import (
    ApproachDecision,
    TestCase,
    TestCaseDraftReply,
    TestCaseReply,
    TestPlanReply,
)
from pydantic_classes.da_request_record_models import RequestRecord

logger = get_logger(__name__)

DATA_FOLDER = Path(__file__).resolve().parents[1] / "data"
PLAN_PROMPT_FILE = DATA_FOLDER / "da_test_plan_prompt.md"
CASE_PROMPT_FILE = DATA_FOLDER / "da_test_case_prompt.md"
FAKE_SCRIPT_FILE = DATA_FOLDER / "da_tester_fake_script.json"

PLAN_MARKER = "Task: write a test plan"
CASE_MARKER = "Task: write one test case"
SCRIPT_MODEL = "fake-tester-script"

PLAN_STEP = "test_plan"
CASE_STEP = "test_case"


@dataclass(frozen=True)
class TestPlanResult:
    __test__ = False

    reply: TestPlanReply | None
    provider: str
    model: str
    attempts: int
    problems: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.reply is not None


@dataclass(frozen=True)
class TestCaseResult:
    __test__ = False

    # None with ok=True means: the Tester says it fits no criterion (see note).
    case: TestCaseReply | None
    note: str
    ok: bool
    provider: str
    model: str
    attempts: int
    problems: list[str] = field(default_factory=list)
    message: str = ""


class ScriptedTesterClient:
    """The fake provider for the Tester: the scripted reply for its step. Ignores what was typed."""

    def __init__(self, step: str, script_file: Path = FAKE_SCRIPT_FILE):
        self.model = SCRIPT_MODEL
        self._step = step
        self._entry = json.loads(Path(script_file).read_text(encoding="utf-8"))[step]

    def complete(self, prompt: str, system: str | None = None) -> LLMReply:
        entry = _fit_plan_to_prompt(self._entry, prompt) if self._step == PLAN_STEP else self._entry
        return LLMReply(text=json.dumps(entry), provider="fake", model=self.model)


def _fit_plan_to_prompt(entry: dict, prompt: str) -> dict:
    """A revision asks the Tester about the new and changed criteria only (Phase 8 spec section 5),
    so the scripted plan keeps the cases of the criteria in the prompt and gets one plain case for
    a criterion the script does not know (a criterion the revision added)."""
    wanted = list(dict.fromkeys(re.findall(r'"id":\s*"(AC-\d+)"', prompt)))
    if not wanted:
        return entry
    cases = [case for case in entry["cases"] if case["criterion_id"] in wanted]
    known = {case["criterion_id"] for case in entry["cases"]}
    cases += [
        {
            "criterion_id": criterion,
            "given": "A file that breaks the new rule of this request",
            "expect": "The file is rejected with a clear error message",
        }
        for criterion in wanted
        if criterion not in known
    ]
    return {**entry, "cases": cases}


def get_tester_client(settings: Settings, step: str, model: str = "") -> LLMClient:
    """The scripted client for the fake provider, otherwise the tester role.

    model is the Admin's Tester model from the pinned rulebook (empty = the .env model)."""
    if settings.llm_provider == "fake":
        return ScriptedTesterClient(step)
    return get_llm_client("tester", settings, model)


# --- prompts ---


def build_plan_prompt(record: RequestRecord, decisions: list[ApproachDecision]) -> str:
    return fill_template(PLAN_PROMPT_FILE, {"record": record.model_dump_json(indent=2),
                                    "decisions": _decisions(decisions)})


def build_case_prompt(
    record: RequestRecord,
    decisions: list[ApproachDecision],
    cases: list[TestCase],
    typed_case: str,
) -> str:
    plan_lines = [
        f"- {case.test_id} ({case.criterion_id}): given {case.given}; expect {case.expect}"
        for case in cases
    ]
    return fill_template(
        CASE_PROMPT_FILE,
        {
            "record": record.model_dump_json(indent=2),
            "decisions": _decisions(decisions),
            "plan": "\n".join(plan_lines) or "- (none yet)",
            "typed": typed_case.strip(),
        },
    )


def _decisions(decisions: list[ApproachDecision]) -> str:
    lines = [f"- {item.question} -> {item.choice}" for item in decisions]
    return "\n".join(lines) or "- (none)"


# --- the calls ---


def write_test_plan(
    client: LLMClient,
    record: RequestRecord,
    decisions: list[ApproachDecision],
    developer_text: str,
) -> TestPlanResult:
    """Ask the Tester for the test plan; retry once with a note. Never raises for a bad reply."""
    prompt = build_plan_prompt(record, decisions)
    sent = prompt
    provider, model, problems = "", "", []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            llm_reply = client.complete(sent)
        except LLMClientError as error:
            logger.warning("The Tester could not be reached (%s).", error)
            return TestPlanResult(None, provider, model, attempt, [str(error)], str(error))
        provider, model = llm_reply.provider, llm_reply.model
        reply, problems = _parse_plan(llm_reply.text, record, developer_text)
        if reply is not None and not problems:
            return TestPlanResult(reply, provider, model, attempt)
        _log_rejected(record.request_id, attempt, llm_reply, problems)
        sent = prompt + retry_note(problems)
    return TestPlanResult(None, provider, model, MAX_ATTEMPTS, problems)


def draft_test_case(
    client: LLMClient,
    record: RequestRecord,
    decisions: list[ApproachDecision],
    cases: list[TestCase],
    typed_case: str,
    developer_text: str,
) -> TestCaseResult:
    """Ask the Tester to turn the developer's words into ONE case. Never raises for a bad reply."""
    prompt = build_case_prompt(record, decisions, cases, typed_case)
    sent = prompt
    provider, model, problems = "", "", []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            llm_reply = client.complete(sent)
        except LLMClientError as error:
            logger.warning("The Tester could not be reached (%s).", error)
            return TestCaseResult(None, "", False, provider, model, attempt, [str(error)],
                                  str(error))
        provider, model = llm_reply.provider, llm_reply.model
        draft, problems = _parse_case(llm_reply.text, record, developer_text)
        if draft is not None and not problems:
            return TestCaseResult(draft.case, draft.note, True, provider, model, attempt)
        _log_rejected(record.request_id, attempt, llm_reply, problems)
        sent = prompt + retry_note(problems)
    return TestCaseResult(None, "", False, provider, model, MAX_ATTEMPTS, problems)


def _parse_plan(
    text: str, record: RequestRecord, developer_text: str
) -> tuple[TestPlanReply | None, list[str]]:
    data = load_json(text)
    if data is NOT_JSON:
        return None, ["The reply was not valid JSON. Reply with JSON only."]
    try:
        reply = TestPlanReply.model_validate(data)
    except ValidationError as error:
        return None, _shape_problems(error)
    return reply, find_test_plan_problems(reply, record, developer_text)


def _parse_case(
    text: str, record: RequestRecord, developer_text: str
) -> tuple[TestCaseDraftReply | None, list[str]]:
    data = load_json(text)
    if data is NOT_JSON:
        return None, ["The reply was not valid JSON. Reply with JSON only."]
    try:
        draft = TestCaseDraftReply.model_validate(data)
    except ValidationError as error:
        return None, _shape_problems(error)
    if draft.case is None:
        return draft, []
    return draft, find_test_case_problems(draft.case, record, developer_text)


def _shape_problems(error: ValidationError) -> list[str]:
    return [f"The reply has the wrong shape: {line}" for line in describe_validation_error(error)]


def _log_rejected(request_id: str, attempt: int, llm_reply: LLMReply, problems: list[str]) -> None:
    logger.warning("Tester reply %s was not usable: %d problems", attempt, len(problems))
    write_rejected_reply(
        request_id,
        attempt,
        llm_reply.provider,
        llm_reply.model,
        problems,
        llm_reply.text,
        step="tester",
    )
