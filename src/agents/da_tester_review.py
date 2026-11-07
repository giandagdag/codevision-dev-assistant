"""The plain-code half of Layer C (Phase 7): checks 1, 2, 3 and 7, the evidence rule, the label
rules, the fix lines for the Generator, and the Tester prompt.

No AI is called here. The AI only proposes findings (da_tester_review_agent.py); this file decides
which ones count. Like a review board's clerk: a comment without a member name and a line number
does not go on the sheet.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from agents.da_approach_agent import fill_template
from agents.da_build_agent import format_approach, format_cases
from agents.da_build_checks import case_ids_from_method, find_test_methods
from pydantic_classes.da_approach_models import ApproachVersion, TestCase
from pydantic_classes.da_build_models import (
    LABEL_NOT_PASSING,
    LABEL_READY,
    LABEL_UNABLE,
    LABEL_WITH_WARNINGS,
    LayerBResult,
)
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Charter, Policy, Rule
from pydantic_classes.da_tester_models import (
    CHECK_NAMES,
    MESSAGE_LIMIT,
    QUOTE_LIMIT,
    CheckResult,
    Finding,
    FindingAction,
    ReplyFinding,
)

DATA_FOLDER = Path(__file__).resolve().parents[1] / "data"
REVIEW_PROMPT = DATA_FOLDER / "da_tester_review_prompt.md"
REVIEW_MARKER = "Task: review the code"
_ROUND_LINE = re.compile(r"^Round: (\d+)$", re.MULTILINE)

TOO_BIG_FOR_TESTER = "This change is too big for the Tester to review in one go."
NOT_FIXABLE = "Not fixable by the Generator: change the approach or get help."


# --- the review's input, read once ---


@dataclass(frozen=True)
class ReviewInput:
    """Everything one review may see. Never the Generator's chat, earlier findings, or the frozen
    test file text (spec section 4)."""

    charter: Charter
    rules: list[Rule]
    record: RequestRecord
    approach: ApproachVersion
    cases: list[TestCase]
    policy: Policy
    layer_b: LayerBResult
    code: dict[str, str]
    start_texts: dict[str, str]
    planned_paths: list[str]
    round: int


def judgement_rules(rules: list[Rule]) -> list[Rule]:
    return [rule for rule in rules if rule.kind == "judgement"]


# --- plain checks (spec section 5) ---


def _plain(
    number: int, check: int, severity, file: str, line: int, cites: str, message: str, fixable=True
) -> Finding:
    return Finding(
        finding_id=f"P-{number}",  # renumbered F-n by number_findings
        check=check,
        severity=severity,
        file=file,
        line=line,
        quote="",
        cites=cites,
        message=message,
        made_by="plain",
        fixable=fixable,
    )


def check_criteria_have_tests(record: RequestRecord, test_text: str) -> list[Finding]:
    """Check 1: every criterion ID has at least one test method named with it."""
    try:
        methods = find_test_methods(ast.parse(test_text))
    except SyntaxError:
        methods = {}
    covered = {ids[1] for name in methods if (ids := case_ids_from_method(name))}
    found = []
    for criterion in record.acceptance_criteria:
        if criterion.id not in covered:
            message = f"Criterion {criterion.id} has no test. {NOT_FIXABLE}"
            found.append(_plain(len(found) + 1, 1, "must_fix", "", 1, criterion.id, message, False))
    return found


def check_tests_pass(record: RequestRecord, layer_b: LayerBResult) -> list[Finding]:
    """Check 2: every criterion's tests pass. Only a guard: Layer C runs after Layer B passed."""
    failed = set()
    for outcome in layer_b.tests:
        ids = case_ids_from_method(outcome.name)
        if ids and outcome.result != "pass":
            failed.add(ids[1])
    found = []
    for criterion in record.acceptance_criteria:
        if criterion.id in failed:
            message = f"A test for {criterion.id} does not pass."
            found.append(_plain(len(found) + 1, 2, "must_fix", "", 1, criterion.id, message))
    return found


def check_files_match_plan(
    planned: list[tuple[str, str]], code: dict[str, str], start_texts: dict[str, str]
) -> list[Finding]:
    """Check 3. `planned` is (path, action). Missing or extra file: Must fix. A `modify` file whose
    text did not change: Should fix."""
    found = []
    paths = [path for path, _ in planned]
    for path in paths:
        if path not in code:
            message = f"The plan says to write {path}, but it is missing."
            found.append(_plain(len(found) + 1, 3, "must_fix", path, 1, f"PLAN:{path}", message))
    for path in sorted(set(code) - set(paths)):
        message = f"{path} was written but is not in the file plan."
        found.append(_plain(len(found) + 1, 3, "must_fix", path, 1, f"PLAN:{path}", message))
    for path, action in planned:
        if action == "modify" and path in code and code[path] == start_texts.get(path):
            message = f"The plan said to change {path}, but it was not changed."
            found.append(_plain(len(found) + 1, 3, "should_fix", path, 1, f"PLAN:{path}", message))
    return found


def zone_warnings(zones: list[str]) -> list[str]:
    """Check 7: one line per flag-for-review zone touched. A warning, never a finding."""
    return [
        f"Touches the {name} zone: the named senior will be a required reviewer." for name in zones
    ]


def number_findings(findings: list[Finding]) -> list[Finding]:
    """The app numbers findings F-1, F-2... per review, plain ones first, kept and dropped alike."""
    return [item.model_copy(update={"finding_id": f"F-{n}"}) for n, item in enumerate(findings, 1)]


# --- the evidence rule (spec section 6) ---


def allowed_cites(
    check: int, approach: ApproachVersion, record: RequestRecord, rules: list[Rule], planned: list
) -> set[str]:
    """Every cite the Tester may use for one check."""
    if check == 4:
        count = len(approach.decisions)
        found = {f"DD-{n}" for n in range(1, count + 1)}
        return found | {f"RU-{n}" for n in range(1, len(approach.plan.reuse_decisions) + 1)}
    if check == 5:
        return {f"PLAN:{path}" for path in planned} | {c.id for c in record.acceptance_criteria}
    if check == 6:
        return {rule.rule_id for rule in judgement_rules(rules)}
    return set()


def check_evidence(
    item: ReplyFinding, files: dict[str, str], cites: set[str], window: int
) -> tuple[ReplyFinding | None, str]:
    """Rules E1 to E5. Returns (the finding, "") when it counts, with the line corrected if the
    quote was found on a nearby line; (None, the reason) when it is dropped."""
    text = files.get(item.file)
    if text is None:  # E1
        return None, f"The file {item.file or '(none)'} is not one of this round's code files."
    lines = text.splitlines()
    if not 1 <= item.line <= len(lines):  # E2
        return None, f"Line {item.line} is not inside {item.file} ({len(lines)} lines)."
    quote = item.quote.strip()
    if not quote or "\n" in quote or len(quote) > QUOTE_LIMIT:  # E3
        return None, "The quote is empty, longer than one line, or too long."
    line = _line_with_quote(lines, item.line, quote, window)
    if line is None:
        return None, f"The quote was not found within {window} lines of line {item.line}."
    if item.cites not in cites:  # E4
        return None, f"The cite {item.cites or '(none)'} is not allowed for check {item.check}."
    message = item.message.strip()
    if not message or len(message) > MESSAGE_LIMIT:  # E5
        return None, f"The message is empty or longer than {MESSAGE_LIMIT} characters."
    return item.model_copy(update={"line": line, "message": message}), ""


def _line_with_quote(lines: list[str], line: int, quote: str, window: int) -> int | None:
    """The stated line if it holds the quote, else the nearest line within the window that does."""
    for distance in range(window + 1):
        for candidate in (line - distance, line + distance):
            if 1 <= candidate <= len(lines) and quote in lines[candidate - 1]:
                return candidate
    return None


def split_findings(
    items: list[ReplyFinding],
    files: dict[str, str],
    approach: ApproachVersion,
    record: RequestRecord,
    rules: list[Rule],
    planned: list[str],
    window: int,
) -> list[Finding]:
    """Every AI finding as a saved Finding, kept or rejected with its reason."""
    result = []
    for item in items:
        cites = allowed_cites(item.check, approach, record, rules, planned)
        checked, reason = check_evidence(item, files, cites, window)
        base = checked or item
        result.append(
            Finding(
                finding_id="T",
                check=base.check,
                severity=base.severity,
                file=base.file,
                line=base.line,
                quote=base.quote.strip(),
                cites=base.cites,
                message=base.message.strip()[:MESSAGE_LIMIT],
                made_by="tester",
                kept=checked is not None,
                reject_reason=reason,
            )
        )
    return result


# --- the label (spec section 8) ---


def finding_state(finding_id: str, review_number: int, actions: list[FindingAction]) -> tuple:
    """(state, reason) of a finding from the newest action on it: open, accepted or disputed."""
    state, reason = "open", ""
    for action in actions:
        if action.finding_id == finding_id and action.review_number == review_number:
            state = {"accepted": "accepted", "reopened": "open", "disputed": "disputed"}[
                action.action
            ]
            reason = action.reason
    return state, reason


def compute_label(
    findings: list[Finding],
    zones: list[str],
    result: str,
    review_number: int,
    actions: list[FindingAction],
) -> str:
    """The label from the last review and the developer's actions. Plain code only."""
    kept = [item for item in findings if item.kept]
    # A plain-code Must fix (checks 1 to 3) beats "unable": the build ends Not passing then.
    if any(item.severity == "must_fix" for item in kept):
        return LABEL_NOT_PASSING
    if result == "unable":
        return LABEL_UNABLE
    open_should = [
        item
        for item in kept
        if item.severity == "should_fix"
        and finding_state(item.finding_id, review_number, actions)[0] != "accepted"
    ]
    if open_should or zones:
        return LABEL_WITH_WARNINGS
    return LABEL_READY


def check_results(findings: list[Finding], zones: list[str], ran_ai: bool) -> list[CheckResult]:
    """The seven rows of the report. Checks 4 to 6 are Not run when the AI gave no usable reply."""
    rows = []
    for number, name in CHECK_NAMES.items():
        count = sum(1 for item in findings if item.kept and item.check == number)
        if number == 7:
            state = "warning" if zones else "passed"
            rows.append(CheckResult(number=7, name=name, state=state, findings=len(zones)))
        elif number in (4, 5, 6) and not ran_ai:
            rows.append(CheckResult(number=number, name=name, state="not_run"))
        else:
            state = "failed" if count else "passed"
            rows.append(CheckResult(number=number, name=name, state=state, findings=count))
    return rows


# --- what the Generator gets for a Must fix round (spec section 7) ---


def must_fix_items(findings: list[Finding]) -> list[Finding]:
    return [item for item in findings if item.kept and item.severity == "must_fix"]


def files_to_fix(findings: list[Finding], planned: list[str]) -> list[str]:
    """The planned files named by the Must fix findings, in file-plan order. Never the tests.
    A Must fix that names no planned file (a guard failure) sends every planned file."""
    named = {item.file for item in must_fix_items(findings)}
    chosen = [path for path in planned if path in named]
    return chosen or list(planned)


def report_for_generator(findings: list[Finding]) -> str:
    """One line per Must fix. Should fix and FYI never go to the Generator."""
    lines = []
    for item in must_fix_items(findings):
        lines.append(
            f"- {item.finding_id} {item.file}:{item.line} `{item.quote}` "
            f"(cites {item.cites}): {item.message}"
        )
    return "The independent Tester found these problems (Must fix):\n" + "\n".join(lines)


# --- the prompt (spec section 4) ---


def number_lines(text: str) -> str:
    """The code with its line number in front of every line, so the Tester can cite lines."""
    return "\n".join(f"{n:>4}| {line}" for n, line in enumerate(text.splitlines(), 1))


def _bullets(items) -> str:
    return "\n".join(f"- {item}" for item in items) or "- (none)"


def format_results(layer_b: LayerBResult) -> str:
    lines = []
    for outcome in layer_b.tests:
        ids = case_ids_from_method(outcome.name)
        label = f"{ids[0]} ({ids[1]})" if ids else outcome.name
        lines.append(f"- {label}: {outcome.result}")
    return _bullets(lines)


def build_review_prompt(data: ReviewInput, only_file: str | None = None) -> str:
    """The Tester prompt. With `only_file`, only that file's code goes in (the per-file split)."""
    approach = data.approach
    rules = [f"{rule.rule_id}: {rule.title}. {rule.why}" for rule in judgement_rules(data.rules)]
    decisions = [
        f"DD-{n}: {item.question} -> {item.choice}" for n, item in enumerate(approach.decisions, 1)
    ]
    reuse = [
        f"RU-{n}: hit {item.hit_id}, {item.decision}: {item.reason}"
        for n, item in enumerate(approach.plan.reuse_decisions, 1)
    ]
    blocks = []
    for path in data.planned_paths:
        if only_file is not None and path != only_file:
            continue
        action = next((i.action for i in approach.plan.files if _same(i.path, path)), "create")
        blocks.append(f"### {path} ({action})\n{number_lines(data.code.get(path, ''))}")
    values = {
        "round": str(data.round),
        "purpose": data.charter.purpose,
        "principles": _bullets(data.charter.architecture_principles),
        "constraints": _bullets(data.charter.constraints),
        "rules": _bullets(rules),
        "record": data.record.model_dump_json(indent=2),
        "approach": format_approach(approach),
        "decisions": _bullets(decisions),
        "reuse": _bullets(reuse),
        "cases": format_cases(data.cases),
        "results": format_results(data.layer_b),
        "code": "\n\n".join(blocks) or "(no code)",
    }
    return fill_template(REVIEW_PROMPT, values)


def _same(a: str, b: str) -> bool:
    return a.replace("\\", "/").strip("/") == b.replace("\\", "/").strip("/")


def round_of_prompt(prompt: str) -> int:
    """The round number a review prompt carries (the fake provider answers by it)."""
    match = _ROUND_LINE.search(prompt)
    return int(match.group(1)) if match else 0
