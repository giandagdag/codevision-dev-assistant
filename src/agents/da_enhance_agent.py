"""The AI calls of Enhance (Phase 9 spec sections 6 and 8): "what does it do today" and the safety
net (write, fix, correct). The AI only proposes; plain code (da_enhance_checks.py and
da_safety_net_checks.py) decides what is used.

What each call sees:
- The today-draft: the charter purpose, what he asked, and the text of the functions found in his
  chosen files. Never the chat.
- The safety net: the record, the in-scope function text (line-numbered), the names and signatures
  of the other functions, and the impact rows. Never the chat, never Discover snippets. This call is
  built apart from every criterion Tester call, which still sees no code (watch item W6).

The scripted replies for the fake provider and the pretend work server are here too, so both prove
the same path. AS400 picture: a test pack written by someone who may read the program's source, and
checked by a machine before anybody trusts it.
"""

import json
import re
from collections.abc import Iterable

from pydantic import ValidationError

from agents import da_build_agent as build_agent
from agents.da_approach_agent import MAX_ATTEMPTS, fill_template, load_json
from agents.da_build_agent import AIResult
from agents.da_build_checks import TOO_BIG_MESSAGE, module_of_path, prompt_too_big
from agents.da_code_splitter import MODULE_SYMBOL, CodePiece, split_python_file
from agents.da_enhance_checks import keep_known_symbols
from agents.da_llm_client import ContextTooLargeError, LLMClient, LLMClientError
from agents.da_rejected_reply_log import write_rejected_reply
from agents.da_safety_net_checks import (
    code_modules_of,
    kept_case_problems,
    safety_net_problems,
)
from agents.da_understand_checks import contains_code, describe_validation_error
from da_logging import get_logger
from pydantic_classes.da_enhance_models import ImpactRow, SafetyNet, TodayDraft
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

DATA_FOLDER = build_agent.DATA_FOLDER
TODAY_PROMPT = DATA_FOLDER / "da_today_prompt.md"
NET_PROMPT = DATA_FOLDER / "da_safety_net_prompt.md"
NET_FIX_PROMPT = DATA_FOLDER / "da_safety_net_fix_prompt.md"

# Which role setting writes the today-draft (work fact WF-7): one line to change. The safety net
# uses the Tester role (WF-6).
TODAY_ROLE = "generator"
NET_ROLE = "tester"

# The line each prompt carries so the fake and pretend servers can tell the calls apart.
TODAY_MARKER = "Task: describe what the program does today"
NET_MARKER = "Task: write the safety net"
FIX_MARKER = "Task: fix the failing safety-net cases"
CORRECT_MARKER = "Task: correct the safety net"
SCRIPT_MODEL = "fake-enhance-script"

NAMES_ONLY_NOTE = "The draft is from the function names only: the files are too big to send."
NOT_JSON_NOTE = "The reply was not valid JSON. Reply with JSON only."

# Test-only switches for the fake provider (add to the Phase 6 to 8 ones in da_build_agent):
#   today_unusable        the today-draft reply is not JSON, every time
#   net_unusable          the safety-net reply is not JSON, every time
#   net_case_keeps_failing  one safety-net case stays wrong, even after the fix call
# (the Generator switches for A8 and A9 and the `main` unreachable switch come with their steps)

NET_RULES = """Reply with JSON only, in exactly this shape:

{"cases": [{"id": "S-1", "today_behaviour": "<one plain sentence>", "function": "<symbol>",
            "nc_ids": ["NC-1"], "expected_to_change": null}],
 "test_code": "<one Python test file>",
 "not_covered": [{"item": "<symbol or NC-id>", "reason": "<one line>"}]}

Rules:
- `cases`: IDs S-1, S-2 and so on. `function` is one of the functions in scope, spelled exactly as
  shown. `nc_ids` lists the must-not-change items the case covers (zero or more).
  `expected_to_change` is the AC id of the criterion that will make this behaviour change on
  purpose, or null when the behaviour must still be the same after the change.
- `test_code`: one file, `unittest` only, one class, one method per case named
  `test_s<number>_<short words>` in lower case (case S-3 gives `test_s3_...`), each with a
  one-sentence docstring. Import only unittest, the standard library and the programs being changed.
  Each method checks what the program does TODAY with an assertion. No network, no files outside a
  `tempfile` folder.
- `not_covered`: anything you could not test, such as a screen layout, with a one-line reason.
- At most {{max_tests}} cases."""


# --- prompts ---


def numbered(text: str, first_line: int = 1) -> str:
    """The text with a line number in front of each line, for reading only."""
    return "\n".join(
        f"{number:>4} | {line}" for number, line in enumerate(text.splitlines(), first_line)
    )


def _piece_text(piece: CodePiece, source: str) -> str:
    lines = source.splitlines()[piece.line_start - 1 : piece.line_end]
    return numbered("\n".join(lines), piece.line_start)


def _symbol_pieces(files: dict[str, str]) -> list[CodePiece]:
    return [
        piece
        for path, text in files.items()
        for piece in split_python_file(path, text)
        if piece.symbol and piece.symbol != MODULE_SYMBOL
    ]


def format_functions(files: dict[str, str], symbols: Iterable[str] | None = None) -> str:
    """The text of the chosen functions, line-numbered. `symbols` None means all of them."""
    wanted = None if symbols is None else set(symbols)
    blocks = []
    for path, text in files.items():
        for piece in split_python_file(path, text):
            if piece.symbol == MODULE_SYMBOL or (wanted is not None and piece.symbol not in wanted):
                continue
            blocks.append(
                f"File: {path}\nSymbol: {piece.symbol} (lines {piece.line_start} to "
                f"{piece.line_end})\n{_piece_text(piece, text)}"
            )
    return "\n\n".join(blocks) or "(no functions found)"


def format_function_list(files: dict[str, str]) -> str:
    """Names only: path, symbol, lines, and the first line of the piece (its signature)."""
    lines = []
    for piece in _symbol_pieces(files):
        lines.append(
            f"File: {piece.path}\nSymbol: {piece.symbol} (lines {piece.line_start} to "
            f"{piece.line_end}): {_signature(piece)}"
        )
    return "\n".join(lines) or "(no functions found)"


def _signature(piece: CodePiece) -> str:
    for line in piece.snippet.splitlines():
        stripped = line.strip()
        if stripped.startswith(("def ", "async def ", "class ")):
            return stripped.rstrip(":")
    return piece.symbol


def format_signatures(files: dict[str, str], in_scope: Iterable[str]) -> str:
    """The other functions of the files: names and signatures, no bodies (spec section 8)."""
    skip = set(in_scope)
    lines = [
        f"- {piece.path}: {_signature(piece)}"
        for piece in _symbol_pieces(files)
        if piece.symbol not in skip
    ]
    return "\n".join(lines) or "- (none)"


def format_impact(rows: list[ImpactRow]) -> str:
    lines = [
        f"- {row.caller_path} line {row.line}: {row.caller_function} uses {row.function_in_scope} "
        f"({row.kind.replace('_', ' ')})"
        for row in rows
    ]
    return "\n".join(lines) or "- (none found)"


def build_today_prompt(
    purpose: str, request_text: str, files: dict[str, str], limit: int
) -> tuple[str, bool]:
    """(prompt, names_only). Too big for the limit: only the function list goes (spec section 6)."""
    values = {"purpose": purpose, "request": request_text, "code": format_functions(files)}
    prompt = fill_template(TODAY_PROMPT, values)
    if not prompt_too_big(prompt, limit):
        return prompt, False
    return fill_template(TODAY_PROMPT, values | {"code": format_function_list(files)}), True


def _net_values(
    record: RequestRecord, files: dict[str, str], impact: list[ImpactRow], policy: Policy
) -> dict[str, str]:
    return {
        "record": record.model_dump_json(indent=2),
        "scope": format_functions(files, record.functions_in_scope),
        "signatures": format_signatures(files, record.functions_in_scope),
        "impact": format_impact(impact),
        "rules": NET_RULES.replace("{{max_tests}}", str(policy.safety_net_max_tests)),
    }


def build_net_prompt(
    record: RequestRecord, files: dict[str, str], impact: list[ImpactRow], policy: Policy
) -> str:
    return fill_template(NET_PROMPT, _net_values(record, files, impact, policy))


def build_net_fix_prompt(
    record: RequestRecord,
    files: dict[str, str],
    impact: list[ImpactRow],
    policy: Policy,
    net: SafetyNet,
    report: str,
    keep_ids: list[str],
    note: str = "",
) -> str:
    """`note` is the developer's words (Correct something); empty for a plain fix call."""
    cases = "\n".join(
        f"- {case.id} ({case.function}): {case.today_behaviour}" for case in net.cases
    )
    values = _net_values(record, files, impact, policy) | {
        "task": CORRECT_MARKER if note else FIX_MARKER,
        "cases": cases or "- (none)",
        "code": net.test_code,
        "report": report or "(nothing failed; follow the developer's note)",
        "note": note or "(none)",
        "keep": ", ".join(keep_ids) or "(none)",
    }
    return fill_template(NET_FIX_PROMPT, values)


# --- the calls ---


def draft_today(
    client: LLMClient,
    purpose: str,
    request_id: str,
    request_text: str,
    files: dict[str, str],
    limit: int,
) -> AIResult:
    """One today-draft call (retry once with a note). `value` is a TodayDraft whose guess holds
    only symbols that exist in the files. `message` carries NAMES_ONLY_NOTE when the draft is
    from names only. Two unusable replies give kind `bad_reply`: the box is left empty."""
    prompt, names_only = build_today_prompt(purpose, request_text, files, limit)
    known = [piece.symbol for piece in _symbol_pieces(files)]

    def check(text: str):
        data = load_json(text)
        if not isinstance(data, dict):
            return None, [NOT_JSON_NOTE]
        try:
            draft = TodayDraft.model_validate(data)
        except ValidationError as error:
            return None, [f"The reply has the wrong shape: {m}" for m in _errors(error)]
        if contains_code(draft.today):
            return None, ["`today` must be plain sentences with no code."]
        kept, _dropped = keep_known_symbols(draft.functions_in_scope_guess, known)
        return draft.model_copy(update={"functions_in_scope_guess": kept}), []

    result = _ask(client, prompt, check, request_id, "enhance_today", MAX_ATTEMPTS, None)
    if result.value is not None and names_only:
        return AIResult(result.value, result.provider, result.model, result.attempts,
                        message=NAMES_ONLY_NOTE)
    return result


def write_safety_net(
    client: LLMClient,
    record: RequestRecord,
    files: dict[str, str],
    impact: list[ImpactRow],
    policy: Policy,
) -> AIResult:
    """One safety-net call (retry once with a note). `value` is a checked SafetyNet. Two unusable
    replies give kind `bad_reply`: the step becomes `s_unable`."""
    prompt = build_net_prompt(record, files, impact, policy)
    modules = code_modules_of(list(files))

    def check(text: str):
        return _check_net(text, record, policy, modules, None, [])

    return _ask(
        client, prompt, check, record.request_id, "safety_net", MAX_ATTEMPTS,
        policy.tester_max_prompt_chars,
    )


def revise_safety_net(
    client: LLMClient,
    record: RequestRecord,
    files: dict[str, str],
    impact: list[ImpactRow],
    policy: Policy,
    net: SafetyNet,
    report: str,
    keep_ids: list[str],
    note: str = "",
) -> AIResult:
    """One fix call (a failing case, `report` says why) or one correct call (`note` is his words).
    The reply is the whole net again; proven cases in `keep_ids` must come back byte for byte."""
    prompt = build_net_fix_prompt(record, files, impact, policy, net, report, keep_ids, note)
    modules = code_modules_of(list(files))

    def check(text: str):
        return _check_net(text, record, policy, modules, net, keep_ids)

    return _ask(
        client, prompt, check, record.request_id, "safety_net_fix", MAX_ATTEMPTS,
        policy.tester_max_prompt_chars,
    )


def _check_net(
    text: str,
    record: RequestRecord,
    policy: Policy,
    modules: set[str],
    old: SafetyNet | None,
    keep_ids: list[str],
):
    data = load_json(text)
    if not isinstance(data, dict):
        return None, [NOT_JSON_NOTE]
    try:
        net = SafetyNet.model_validate(data)
    except ValidationError as error:
        return None, [f"The reply has the wrong shape: {m}" for m in _errors(error)]
    problems = safety_net_problems(net, record, policy, modules)
    if old is not None:
        problems += kept_case_problems(old, net, keep_ids)
    return (None, problems) if problems else (net, [])


def _errors(error: ValidationError) -> list[str]:
    return describe_validation_error(error)


def _ask(client, prompt, check, request_id: str, step: str, attempts: int, limit) -> AIResult:
    """Ask, check, retry with a note (`attempts` calls in all). Never raises for a bad reply or an
    AI that does not answer: the result says why."""
    if limit is not None and prompt_too_big(prompt, limit):
        return AIResult(None, kind="too_big", message=TOO_BIG_MESSAGE)
    sent, provider, model, problems = prompt, "", "", []
    for attempt in range(1, attempts + 1):
        try:
            reply = client.complete(sent)
        except ContextTooLargeError as error:
            logger.warning("Enhance call %s: the AI said the prompt is too big (%s).", step, error)
            return AIResult(None, provider, model, attempt, "too_big", TOO_BIG_MESSAGE)
        except LLMClientError as error:
            logger.warning("Enhance call %s could not reach the AI (%s).", step, error)
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

_SYMBOL_LINE = re.compile(r"^Symbol: (\S+)", re.MULTILINE)
_FILE_LINE = re.compile(r"^File: (\S+)$", re.MULTILINE)
_NC_ID = re.compile(r'"id": "(NC-\d+)"')
_AC_ID = re.compile(r'"id": "(AC-\d+)"')

# What the made-up limits program (src/data/da_fake_codevision) does today, per symbol:
# (short words, one-sentence docstring, the check). `{m}` is the imported module alias.
_KNOWN_CHECKS = {
    "days_left": (
        "days_left_counts_down",
        "Days left is the expiry day minus today.",
        "self.assertEqual({m}.days_left(20, 10), 10)",
    ),
    "format_expiry": (
        "expiry_has_two_digits",
        "The expiry date shows day, month and year with two digits.",
        'self.assertEqual({m}.format_expiry(3, 4, 2026), "03/04/2026")',
    ),
    "ExpiryReport.build_line": (
        "line_names_the_customer",
        "The report line names the customer and the days left.",
        'self.assertEqual({m}.ExpiryReport().build_line("ACME", 15), "ACME: 5 days left")',
    ),
}
# The case that is wrong at first and right after the fix call (the demo's "fails at first").
_WRONG_AT_FIRST = {
    "format_expiry": 'self.assertEqual({m}.format_expiry(3, 4, 2026), "3/4/2026")',
}


def is_enhance_prompt(prompt: str) -> bool:
    return any(
        re.search(rf"^{re.escape(marker)}$", prompt, re.MULTILINE)
        for marker in (TODAY_MARKER, NET_MARKER, FIX_MARKER, CORRECT_MARKER)
    )


def scripted_enhance_reply(prompt: str, switches: frozenset[str] | None = None) -> str:
    switches = build_agent.FAKE_SWITCHES if switches is None else switches
    if re.search(rf"^{re.escape(TODAY_MARKER)}$", prompt, re.MULTILINE):
        return _scripted_today(prompt, switches)
    return _scripted_net(prompt, switches)


def _scripted_today(prompt: str, switches: frozenset[str]) -> str:
    if "today_unusable" in switches:
        return "I think the program prints a report, but here is my answer in words, not JSON."
    symbols = list(dict.fromkeys(_SYMBOL_LINE.findall(prompt)))
    return json.dumps(
        {
            "today": "The program builds the limits expiry report: it works out how many days "
            "are left before each limit expires and shows the date as day, month and year.",
            "functions_in_scope_guess": symbols[:2],
        }
    )


def _scripted_net(prompt: str, switches: frozenset[str]) -> str:
    if "net_unusable" in switches:
        return "Here are my tests in words and not in JSON."
    fixing = bool(
        re.search(rf"^({re.escape(FIX_MARKER)}|{re.escape(CORRECT_MARKER)})$", prompt, re.M)
    )
    keep_wrong = "net_case_keeps_failing" in switches
    wrong_now = (not fixing) or keep_wrong
    scope = _scope_symbols(prompt)
    ncs, acs = _NC_ID.findall(prompt), _AC_ID.findall(prompt)
    module_alias = "target"
    cases, methods, imports = [], [], []
    for number, (path, symbol) in enumerate(scope, 1):
        words, doc, check = _KNOWN_CHECKS.get(symbol, _generic_check(symbol))
        if wrong_now and symbol in _WRONG_AT_FIRST:
            check = _WRONG_AT_FIRST[symbol]
        imports.append(f"import {module_of_path(path)} as {module_alias}")
        cases.append(
            {
                "id": f"S-{number}",
                "today_behaviour": doc,
                "function": symbol,
                "nc_ids": [ncs[number - 1]] if number <= len(ncs) else [],
                "expected_to_change": acs[0] if acs and number > len(scope) - 2 else None,
            }
        )
        methods.append(
            f"    def test_s{number}_{words}(self):\n"
            f'        """{doc}"""\n'
            f"        {check.format(m=module_alias)}\n"
        )
    code = ""
    if cases:
        header = "import unittest\n\n" + "\n".join(dict.fromkeys(imports))
        code = f"{header}\n\n\nclass SafetyNetChecks(unittest.TestCase):\n" + "\n".join(methods)
    return json.dumps(
        {
            "cases": cases,
            "test_code": code,
            "not_covered": [],  # plain code adds what has no proven case
        }
    )


def _generic_check(symbol: str) -> tuple[str, str, str]:
    """A symbol the script does not know: a check that the name is still there and callable."""
    words = "_".join(re.findall(r"[a-z0-9]+", symbol.lower())[:3]) or "symbol"
    return (
        f"{words}_is_there",
        "The function exists and can be called.",
        f"self.assertTrue(callable({{m}}.{symbol}))",
    )


def _scope_symbols(prompt: str) -> list[tuple[str, str]]:
    """(path, symbol) of each function in the 'in scope' part of the prompt, in order. A class that
    only holds the methods is left out when one of its methods is in the list."""
    start = prompt.find("## The functions in scope")
    end = prompt.find("## Other functions", start)
    block = prompt[start:end] if start >= 0 else ""
    found: list[tuple[str, str]] = []
    path = ""
    for line in block.splitlines():
        file_match = _FILE_LINE.match(line)
        if file_match:
            path = file_match.group(1)
        symbol_match = _SYMBOL_LINE.match(line)
        if symbol_match and (path, symbol_match.group(1)) not in found:
            found.append((path, symbol_match.group(1)))
    names = [symbol for _path, symbol in found]
    return [(p, s) for p, s in found if not any(n.startswith(f"{s}.") for n in names)]
