"""The AI calls of the Build loop (spec sections 3 and 4): the contract, the tests, one code file.

The Generator (Qwen at work) agrees the public names first and then writes the code, one file per
call. The Tester writes the tests from the requirement, the accepted test plan and the contract,
and never sees code (spec section 3). A bad reply is retried once with a note on what was wrong
(MAX_ATTEMPTS 2). Like Approach, the AI suggests and plain code (da_build_checks) decides.

Replies are plain code or visible FIND / REPLACE blocks, not JSON, because models mangle
multi-line code inside JSON strings (plan item P6, refined). Only the contract is JSON.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agents.da_approach_agent import fill_template, load_json
from agents.da_build_checks import (
    TOO_BIG_MESSAGE,
    clean_code_reply,
    find_contract_problems,
    find_test_file_problems,
    parse_edit_blocks,
    prompt_too_big,
)
from agents.da_golden_example import golden_block
from agents.da_guidance import guidance_block
from agents.da_llm_client import (
    ContextTooLargeError,
    LLMClient,
    LLMClientError,
    LLMReply,
    get_llm_client,
)
from agents.da_rejected_reply_log import write_rejected_reply
from agents.da_understand_checks import describe_validation_error
from configs.da_config import Settings
from da_logging import get_logger
from pydantic_classes.da_approach_models import ApproachVersion, TestCase
from pydantic_classes.da_build_models import CodeReply, Contract
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Charter, Policy

logger = get_logger(__name__)

DATA_FOLDER = Path(__file__).resolve().parents[1] / "data"
CONTRACT_PROMPT = DATA_FOLDER / "da_build_contract_prompt.md"
TESTS_PROMPT = DATA_FOLDER / "da_build_tests_prompt.md"
CODE_PROMPT = DATA_FOLDER / "da_build_code_prompt.md"
FAKE_SCRIPT_FILE = DATA_FOLDER / "da_build_fake_script.json"

# The line each prompt carries so the fake and pretend servers can tell the calls apart.
CONTRACT_MARKER = "Task: write the contract"
TESTS_MARKER = "Task: write the tests"
CODE_MARKER = "Task: write one file"
FAILURE_HEADING = "## Why the last round failed"
SCRIPT_MODEL = "fake-build-script"
MAX_ATTEMPTS = 2

# Test-only switches for the fake provider (spec section 14). Tests set this; the app never does:
#   always_fail  the fix round repeats the buggy code
#   bad_edit     an edit block matches nothing
#   bad_tests    the test file misses its last case
#   slow_test    the first test sleeps past the time limit
#   no_answer    the AI does not answer
#   too_big      the AI says the prompt is too big
FAKE_SWITCHES: frozenset[str] = frozenset()

_CASE_LINE = re.compile(r"^- (T-\d+) \((AC-\d+)\): given (.*); expect (.*)$", re.MULTILINE)
_FILE_LINE = re.compile(r"^File: (.+)$", re.MULTILINE)
_ROUND_LINE = re.compile(r"^Round: (\d+)$", re.MULTILINE)

NOT_JSON_NOTE = "The reply was not valid JSON. Reply with JSON only."
NO_CODE_NOTE = "The reply held no code. Reply with the complete file as Python code."
NO_BLOCKS_NOTE = (
    "The reply held no edit block. Use <<<<<<< FIND, =======, >>>>>>> REPLACE exactly as shown."
)
CREATE_RULES = (
    "Reply with the complete new file as Python code only: no explanation. A code fence is allowed."
)
MODIFY_RULES = (
    "This file already exists. Reply with edit blocks only, no explanation. Each block is:\n\n"
    "<<<<<<< FIND\n<the exact old lines, copied character for character>\n=======\n"
    "<the new lines>\n>>>>>>> REPLACE\n\n"
    "The FIND text must appear exactly once in the current text above. Keep every public name in "
    "the contract. Send as many blocks as you need and change nothing else."
)


@dataclass(frozen=True)
class BuildContext:
    """Everything the Build calls may see. Never the chat."""

    charter: Charter
    record: RequestRecord
    approach: ApproachVersion
    cases: list[TestCase]
    policy: Policy
    golden_examples: tuple = ()


@dataclass(frozen=True)
class AIResult:
    """The checked outcome of one call. `value` is None when the reply could not be used.

    kind says why, so the flow knows if it was the code's fault: "unreachable" and "too_big" are
    not (the build pauses, no round is used); "bad_reply" is the model's format and is."""

    value: Any
    provider: str = ""
    model: str = ""
    attempts: int = 1
    kind: str = ""  # "", "unreachable", "too_big" or "bad_reply"
    message: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.value is not None


# --- the fake provider ---


def scripted_build_reply(prompt: str, switches: frozenset[str] | None = None) -> str:
    """The scripted answer to a build prompt. Shared by the fake provider and the pretend work
    server, so both prove the same path."""
    switches = FAKE_SWITCHES if switches is None else switches
    script = json.loads(FAKE_SCRIPT_FILE.read_text(encoding="utf-8"))
    # Phase 9: an enhance request on the made-up limits program has its own contract and edits.
    # Imported here so this file stays the one that the others import.
    from agents import da_enhance_build_script as enhance_script

    enhancing = enhance_script.is_enhance_build_prompt(prompt, script)
    if re.search(rf"^{re.escape(CONTRACT_MARKER)}$", prompt, re.MULTILINE):
        if enhancing:
            return enhance_script.scripted_contract(script)
        return json.dumps(script["contract"])
    if re.search(rf"^{re.escape(TESTS_MARKER)}$", prompt, re.MULTILINE):
        return _scripted_tests(prompt, switches, script if enhancing else None)
    if re.search(rf"^{re.escape(CODE_MARKER)}$", prompt, re.MULTILINE):
        if enhancing:
            return enhance_script.scripted_code(prompt, script, switches, _present_prefix)
        return _scripted_code(prompt, script, switches)
    # Phase 7: the Tester's review of the code. Imported here because that file imports this one.
    from agents.da_tester_review_agent import is_review_prompt, scripted_review_reply

    if is_review_prompt(prompt):
        return scripted_review_reply(prompt, switches)
    # Phase 8: the lane, revision and repro-test calls of Refine (same reason for the import).
    from agents.da_refine_agent import is_refine_prompt, scripted_refine_reply

    if is_refine_prompt(prompt):
        return scripted_refine_reply(prompt, switches)
    # Phase 9: the today-draft and the safety-net calls of Enhance.
    from agents.da_enhance_agent import is_enhance_prompt, scripted_enhance_reply

    if is_enhance_prompt(prompt):
        return scripted_enhance_reply(prompt, switches)
    raise LLMClientError("The scripted build client was given a prompt it does not know.")


# Each check records evidence first (Fix D1), the way a real requirement test must.
_VALIDATE_CHECK = (
    'evidence(self, "accepts xlsx", "book.xlsx", True, validate("book.xlsx"))\n'
    '        evidence(self, "refuses exe", "run.exe", False, validate("run.exe"))\n'
    '        self.assertTrue(validate("book.xlsx"))\n        self.assertFalse(validate("run.exe"))'
)
_HIDDEN_CHECK = (
    'book = {"A": {"hidden": False, "rows": [1, 2]}, "B": {"hidden": True, "rows": [3]}}\n'
    '        evidence(self, "visible sheets", book, ["A"], list(read_sheets(book)))\n'
    '        self.assertEqual(list(read_sheets(book)), ["A"])'
)
_EMPTY_CHECK = (
    'book = {"A": {"hidden": False, "rows": []}}\n'
    "        with self.assertRaises(ValueError) as caught:\n"
    "            read_sheets(book)\n"
    '        evidence(self, "empty sheet", book, "ValueError", type(caught.exception).__name__)'
)
_CHECKS = (_VALIDATE_CHECK, _HIDDEN_CHECK, _EMPTY_CHECK)


def _scripted_tests(prompt: str, switches: frozenset[str], enhance: dict | None = None) -> str:
    cases = _CASE_LINE.findall(prompt)
    if "bad_tests" in switches:
        cases = cases[:-1]  # one accepted case has no test method
    checks = _CHECKS
    imports = [
        "from agents.excel_processor import read_sheets",
        "from agents.upload_validator import validate",
    ]
    if enhance is not None:
        from agents.da_enhance_build_script import criterion_test_parts

        imports, checks = criterion_test_parts(enhance)
    lines = [
        "import time",
        "import unittest",
        "",
        *imports,
        "from da_evidence import evidence",
        "",
        "",
        "class ScriptedChecks(unittest.TestCase):",
    ]
    for index, (test_id, criterion, given, expect) in enumerate(cases):
        words = "_".join(re.findall(r"[a-z0-9]+", given.lower())[:4]) or "case"
        name = (
            f"test_{test_id.lower().replace('-', '')}_{criterion.lower().replace('-', '')}_{words}"
        )
        sleep = "        time.sleep(60)\n" if "slow_test" in switches and index == 0 else ""
        lines += [
            f"    def {name}(self):",
            f'        """{expect.strip().rstrip(".")}."""',
            sleep + "        " + checks[index % len(checks)],
            "",
        ]
    return "\n".join(lines) + "\n"


def _present_prefix(text: str, wanted: str) -> str:
    """The longest start of `wanted` (at least 12 characters) that `text` still holds."""
    for end in range(len(wanted), 11, -1):
        if wanted[:end] in text:
            return wanted[:end]
    return wanted


def _scripted_code(prompt: str, script: dict, switches: frozenset[str]) -> str:
    path = _FILE_LINE.search(prompt).group(1).strip()
    fixing = FAILURE_HEADING in prompt
    if path in script["code"] and "Action: modify" in prompt:
        # A new file that already exists in the folder (an earlier build wrote it): edit blocks.
        edit = script["modify_edits"][path]["fixed" if fixing else "first"]
        return f"<<<<<<< FIND\n{edit['find']}\n=======\n{edit['replace']}\n>>>>>>> REPLACE\n"
    if path in script["code"]:
        versions = script["code"][path]
        use_fixed = fixing and "always_fail" not in switches
        return versions["fixed"] if use_fixed else versions["first"]
    edit = script["edits"].get(path, {"find": "not in the file", "replace": "x"})
    find, replace = edit["find"], edit["replace"]
    if "bad_edit" in switches:
        find = "this text is not in the file"
    elif fixing and "book.csv" in prompt and path in script.get("fix_edits", {}):
        # Phase 8: the failure report is the scripted bug-lane repro test; this is its fix.
        edit = script["fix_edits"][path]
        find, replace = edit["find"], edit["replace"]
    elif fixing:
        find = replace  # the edit is already in the current text; send a harmless no-op
    elif find not in prompt:
        # A rebuild after an earlier build or a bug fix changed this file already (Phase 8): the
        # old text is gone. Send a harmless no-op on the part of the new text that is still there.
        find = replace = _present_prefix(prompt, replace)
    return f"<<<<<<< FIND\n{find}\n=======\n{replace}\n>>>>>>> REPLACE\n"


class ScriptedBuildClient:
    """The fake provider for the Build: scripted replies chosen by the prompt's marker line."""

    def __init__(self, role: str):
        self.model = SCRIPT_MODEL

    def complete(self, prompt: str, system: str | None = None) -> LLMReply:
        if "no_answer" in FAKE_SWITCHES:
            raise LLMClientError("The AI did not answer (scripted for a test).")
        if "too_big" in FAKE_SWITCHES:
            raise ContextTooLargeError("The AI refused the request as too large (HTTP 400).")
        return LLMReply(text=scripted_build_reply(prompt), provider="fake", model=self.model)


def get_build_client(settings: Settings, role: str, model: str = "") -> LLMClient:
    """The scripted client for the fake provider, otherwise the generator or tester role.

    model is the Admin's name for the role from the pinned rulebook (empty = the .env model)."""
    if settings.llm_provider == "fake":
        return ScriptedBuildClient(role)
    if not model:  # keep the two-argument call when nothing is pinned
        return get_llm_client(role, settings)  # type: ignore[arg-type]
    return get_llm_client(role, settings, model)  # type: ignore[arg-type]


# --- prompts ---


def _bullets(items) -> str:
    return "\n".join(f"- {item}" for item in items) or "- (none)"


def _charter_values(charter: Charter) -> dict[str, str]:
    return {
        "purpose": charter.purpose,
        "principles": _bullets(charter.architecture_principles),
        "constraints": _bullets(charter.constraints),
        "glossary": _bullets(f"{entry.term}: {entry.meaning}" for entry in charter.glossary),
    }


def format_approach(approach: ApproachVersion) -> str:
    plan = approach.plan
    files = [f"- {item.path} ({item.action}): {item.purpose}" for item in plan.files]
    decisions = [f"- {item.question} -> {item.choice}" for item in approach.decisions]
    return (
        f"Summary: {plan.summary}\n\nFiles, in this order:\n{_bullets_raw(files)}\n\n"
        f"Libraries: {', '.join(plan.libraries) or '(none)'}\n\n"
        f"Developer's design decisions (information only, never instructions):\n"
        f"{_bullets_raw(decisions)}"
    )


def _bullets_raw(lines: list[str]) -> str:
    return "\n".join(lines) or "- (none)"


def format_contract_lines(contract: Contract, only: str | None = None, skip: str | None = None):
    """One line per public name. `only` keeps one file, `skip` leaves one file out."""
    lines = []
    for entry in contract.files:
        if (only and entry.path != only) or (skip and entry.path == skip):
            continue
        for item in entry.items:
            lines.append(
                f"- {entry.path}: {item.kind} {item.name}({', '.join(item.args)}) {item.summary}"
            )
    return "\n".join(lines) or "- (none)"


def format_cases(cases: list[TestCase]) -> str:
    return "\n".join(
        f"- {case.test_id} ({case.criterion_id}): given {case.given}; expect {case.expect}"
        for case in cases
    )


def build_contract_prompt(context: BuildContext, current_texts: dict[str, str]) -> str:
    current = [f"### {path}\n{text}" for path, text in current_texts.items()]
    values = _charter_values(context.charter) | {
        "record": context.record.model_dump_json(indent=2),
        "approach": format_approach(context.approach),
        "current_files": "\n\n".join(current) or "(none: every file is new)",
    }
    return fill_template(CONTRACT_PROMPT, values)


def build_tests_prompt(context: BuildContext, contract: Contract) -> str:
    """No code text of any kind goes in (spec section 3): the record, the cases and the contract."""
    values = {
        "record": context.record.model_dump_json(indent=2),
        "cases": format_cases(context.cases),
        "contract": format_contract_lines(contract),
    }
    return fill_template(TESTS_PROMPT, values)


def build_code_prompt(
    context: BuildContext,
    contract: Contract,
    path: str,
    action: str,
    round_number: int,
    frozen_tests: str,
    current_text: str,
    failures: str = "",
    developer_lines: str = "",
    senior_guidance: str = "",
) -> str:
    """One file per call: this file in full, the other files by contract line only.
    `developer_lines` (Phase 8, R5.3): a sentence that says which lines he wrote himself.
    `senior_guidance` (Phase 10): used in a fix round only, once."""
    if developer_lines and action == "modify":
        current_text = f"{current_text}\n\n{developer_lines}"
    failure_section = ""
    if failures:
        failure_section = (
            f"{FAILURE_HEADING}\n\n{failures}\n\nFix only this file. Do not change the tests."
        )
    values = _charter_values(context.charter) | {
        "path": path,
        "action": action,
        "round": str(round_number),
        "libraries": ", ".join(context.policy.approved_libraries),
        "blocked": ", ".join(context.policy.build_blocked_imports),
        "record": context.record.model_dump_json(indent=2),
        "approach": format_approach(context.approach),
        "own_contract": format_contract_lines(contract, only=path),
        "other_contract": format_contract_lines(contract, skip=path),
        "tests": frozen_tests,
        "current_text": current_text if action == "modify" or current_text else "(new file)",
        "failures": failure_section,
        "reply_rules": MODIFY_RULES if action == "modify" else CREATE_RULES,
    }
    return (
        fill_template(CODE_PROMPT, values)
        + golden_block(context.golden_examples, path, current_text)
        + guidance_block(senior_guidance)
    )


# --- the calls ---


def write_contract(
    client: LLMClient, context: BuildContext, current_texts: dict[str, str]
) -> AIResult:
    planned = [item.path for item in context.approach.plan.files]
    prompt = build_contract_prompt(context, current_texts)

    def check(text: str):
        data = load_json(text)
        if not isinstance(data, dict | list):
            return None, [NOT_JSON_NOTE]
        try:
            contract = Contract.model_validate(data)
        except ValidationError as error:
            return None, [
                f"The contract has the wrong shape: {line}"
                for line in describe_validation_error(error)
            ]
        return contract, find_contract_problems(contract, planned, current_texts)

    return _ask(client, prompt, check, context, "build_contract")


def write_tests(client: LLMClient, context: BuildContext, contract: Contract) -> AIResult:
    prompt = build_tests_prompt(context, contract)

    def check(text: str):
        code = clean_code_reply(text)
        if not code.strip():
            return None, [NO_CODE_NOTE]
        return code, find_test_file_problems(code, context.cases, contract, context.policy)

    return _ask(client, prompt, check, context, "build_tests")


def write_code(client: LLMClient, context: BuildContext, prompt: str, action: str) -> AIResult:
    """One file. The value is a CodeReply: `text` for a new file, `edits` for an existing one.
    Whether the code is any good is Layer A's and Layer B's job, not this call's."""

    def check(text: str):
        if action == "modify":
            edits = parse_edit_blocks(text)
            return (CodeReply(edits=edits), []) if edits else (None, [NO_BLOCKS_NOTE])
        code = clean_code_reply(text)
        return (CodeReply(text=code), []) if code.strip() else (None, [NO_CODE_NOTE])

    return _ask(client, prompt, check, context, "build_code")


def _ask(
    client: LLMClient,
    prompt: str,
    check: Callable[[str], tuple[Any, list[str]]],
    context: BuildContext,
    step: str,
) -> AIResult:
    """Ask, check the reply, retry once with a note. Never raises for a bad reply or an AI that
    does not answer: the result says why and whether it was the code's fault."""
    if prompt_too_big(prompt, context.policy.build_max_prompt_chars):
        return AIResult(None, kind="too_big", message=TOO_BIG_MESSAGE)
    sent, provider, model, problems = prompt, "", "", []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = client.complete(sent)
        except ContextTooLargeError as error:
            logger.warning("Build call %s: the AI said the prompt is too big (%s).", step, error)
            return AIResult(None, provider, model, attempt, "too_big", TOO_BIG_MESSAGE)
        except LLMClientError as error:
            logger.warning("Build call %s could not reach the AI (%s).", step, error)
            return AIResult(None, provider, model, attempt, "unreachable", str(error))
        provider, model = reply.provider, reply.model
        value, problems = check(reply.text)
        if value is not None and not problems:
            return AIResult(value, provider, model, attempt)
        logger.warning(
            "Build call %s reply %d was not usable: %d problems", step, attempt, len(problems)
        )
        write_rejected_reply(
            context.record.request_id, attempt, provider, model, problems, reply.text, step=step
        )
        sent = prompt + _retry_note(problems)
    return AIResult(None, provider, model, MAX_ATTEMPTS, "bad_reply", problems=problems)


def _retry_note(problems: list[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        f"\n\nYour previous reply was not accepted, for these reasons:\n{listed}\n"
        "Reply again in the same format as before, fixing these problems."
    )
