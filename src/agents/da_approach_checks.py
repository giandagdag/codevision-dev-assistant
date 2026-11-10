"""App checks for Approach (spec sections 4, 5 and 6). Plain Python, no AI.

The AI suggests, the app decides, the developer approves. Every check returns plain sentences, so
the Generator or the Tester sees the whole list at once as its retry note.

Like a program change form being checked by the librarian before it goes to sign-off: right
library, right object names, nothing on the protected list.
"""

import re
import sys
from fnmatch import fnmatchcase

from agents.da_understand_checks import (
    developer_message_problem,
    find_code,
    find_invented_names,
    is_vague_then,
)
from pydantic_classes.da_approach_models import (
    CASE_TEXT_LIMIT,
    CHANGE_LIMIT,
    CUSTOM_ANSWER_LIMIT,
    LIMIT_REASON_LIMIT,
    LIMIT_REASON_MIN,
    MAX_TESTER_CASES_PER_CRITERION,
    ApproachReply,
    ApproachState,
    ApproachVersion,
    GateCheck,
    TestCaseReply,
    TestPlanReply,
    TestPlanVersion,
)
from pydantic_classes.da_discovery_models import MATCH_KINDS, DiscoveryResult
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Policy

# Which Generator call the reply came from (spec section 8).
PROPOSE = "propose"
SETTLE = "settle"
CHANGE = "change"

TESTS_FOLDER_PREFIX = "tests/"
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")

NO_CRITERION_MESSAGE = (
    "This does not match any acceptance criterion. If it is a new requirement, the "
    "requirement has to change first (a later phase)."
)
CUSTOM_TOO_LONG = (
    f"Please keep your own answer under {CUSTOM_ANSWER_LIMIT} characters, or choose a button."
)


def normalise_path(path: str) -> str:
    """Backslashes become slashes (spec 4, check 1). Case is kept; matching lower-cases."""
    return path.strip().replace("\\", "/")


# --- the Generator's reply (spec section 4) ---


def find_approach_problems(
    reply: ApproachReply,
    policy: Policy,
    discovery: DiscoveryResult,
    answered_questions: set[str],
    call: str,
    targets: list[str] | None = None,
) -> list[str]:
    """Every reason the reply cannot be used. An empty list means it is fine."""
    problems = _file_problems(reply, policy)
    problems += _target_problems(reply, targets or [])
    problems += _needs_people_problems(reply)
    problems += _reuse_problems(reply, discovery)
    problems += _library_problems(reply, policy)
    problems += _design_choice_problems(reply, policy, answered_questions, call)
    problems += _code_problems(reply)
    return problems


def _file_problems(reply: ApproachReply, policy: Policy) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    folders = [normalise_path(folder).rstrip("/").lower() for folder in policy.allowed_folders]
    for item in reply.files:
        path = normalise_path(item.path)
        lower = path.lower()
        path_problem = _path_problem(path)
        if path_problem:
            problems.append(f"{item.path}: {path_problem}")
            continue
        if lower.startswith(TESTS_FOLDER_PREFIX):
            problems.append(
                f"{path}: Tests are written by the Tester, not planned here. Remove it."
            )
            continue
        if not any(lower.startswith(folder + "/") for folder in folders):
            problems.append(
                f"{path} is not in an allowed folder. Use one of: "
                f"{', '.join(policy.allowed_folders)}."
            )
        elif matches_any(lower, policy.protected_files):
            problems.append(
                f"{path} is protected. List it under needs_people with the reason instead."
            )
        elif item.action == "create" and not re.match(
            policy.new_file_name_pattern, path.rsplit("/", 1)[-1]
        ):
            problems.append(
                f"{path}: a new file name must match {policy.new_file_name_pattern} "
                "(lower case, digits and underscores, ending in .py)."
            )
        if lower in seen:
            problems.append(f"{path} is listed more than once.")
        seen.add(lower)
    return problems


def _target_problems(reply: ApproachReply, targets: list[str]) -> list[str]:
    """Phase 9 (spec section 9): each confirmed target appears in the file plan as `modify`.
    A target that a person must change (needs_people) is the one allowed exception."""
    modified = {normalise_path(i.path).lower() for i in reply.files if i.action == "modify"}
    people = {normalise_path(i.path).lower() for i in reply.needs_people}
    problems = []
    for target in targets:
        lower = normalise_path(target).lower()
        if lower not in modified and lower not in people:
            problems.append(
                f"{normalise_path(target)} is the program being enhanced. List it in files "
                "with action modify."
            )
    return problems


def _path_problem(path: str) -> str:
    if path.startswith("/") or _DRIVE_LETTER.match(path):
        return "the path must be relative (no leading / and no drive letter)."
    if ".." in path.split("/"):
        return "the path must not contain '..'."
    return ""


def _needs_people_problems(reply: ApproachReply) -> list[str]:
    problems = []
    for item in reply.needs_people:
        problem = _path_problem(normalise_path(item.path))
        if problem:
            problems.append(f"needs_people {item.path}: {problem}")
    return problems


def matches_any(lower_path: str, patterns: list[str]) -> bool:
    return any(fnmatchcase(lower_path, pattern.lower()) for pattern in patterns)


def _reuse_problems(reply: ApproachReply, discovery: DiscoveryResult) -> list[str]:
    known = {hit.hit_id for hit in discovery.hits}
    problems: list[str] = []
    for item in reply.files:
        for hit_id in item.reuses:
            if hit_id not in known:
                problems.append(
                    f"{item.path} reuses hit {hit_id}, which Discover did not find. "
                    "Use only the hit numbers you were given."
                )
    for decision in reply.reuse_decisions:
        if decision.hit_id not in known:
            problems.append(
                f"Reuse decision for hit {decision.hit_id}, which Discover did not find. "
                "Use only the hit numbers you were given."
            )
    needed = sorted(
        {
            hit_id
            for finding in discovery.findings
            if finding.kind in MATCH_KINDS
            for hit_id in finding.hit_ids
        }
    )
    for hit_id in needed:
        count = sum(1 for decision in reply.reuse_decisions if decision.hit_id == hit_id)
        if count == 0:
            problems.append(
                f"Discover hit {hit_id} needs a reuse decision (reuse, extend or ignore)."
            )
        elif count > 1:
            problems.append(
                f"Discover hit {hit_id} has {count} reuse decisions. Give exactly one."
            )
    return problems


def library_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def _library_problems(reply: ApproachReply, policy: Policy) -> list[str]:
    approved = {library_name(name) for name in policy.approved_libraries}
    allowed = approved | {name.lower() for name in sys.stdlib_module_names}
    return [
        f"Library '{name}' is not in the Python standard library or on the approved list "
        f"({', '.join(policy.approved_libraries)})."
        for name in reply.libraries
        if library_name(name) not in allowed
    ]


def _design_choice_problems(
    reply: ApproachReply, policy: Policy, answered: set[str], call: str
) -> list[str]:
    choices = reply.design_choices
    problems: list[str] = []
    if call == SETTLE and choices:
        return ["The settled plan must have no design choices. Decide them from the answers."]
    if len(choices) > policy.max_design_choices:
        problems.append(
            f"There are {len(choices)} design choices. The limit is {policy.max_design_choices}."
        )
    seen: set[str] = set()
    for choice in choices:
        key = question_key(choice.question)
        if key in seen:
            problems.append(f'The design question "{choice.question}" is asked twice.')
        elif key in answered:
            problems.append(
                f'The design question "{choice.question}" was already answered. Do not ask again.'
            )
        seen.add(key)
    return problems


def question_key(question: str) -> str:
    """A question compared without case or extra spaces."""
    return " ".join(question.lower().split())


def _code_problems(reply: ApproachReply) -> list[str]:
    problems = []
    for text in _reply_texts(reply):
        code = find_code(text)
        if code is not None:
            problems.append(
                f'The reply contains code: "{code[:60]}". Describe the change in plain words '
                "only, and do not start a line with def, class, import or from ... import."
            )
    return problems


def _reply_texts(reply: ApproachReply) -> list[str]:
    texts = [reply.summary, *reply.libraries]
    for item in reply.files:
        texts += [item.path, item.purpose]
    for item in reply.needs_people:
        texts += [item.path, item.reason]
    texts += [item.reason for item in reply.reuse_decisions]
    for choice in reply.design_choices:
        texts += [choice.question, choice.impact, *choice.options]
    return texts


def normalise_reply_paths(reply: ApproachReply) -> ApproachReply:
    """The reply with every path cleaned (spec 4, check 1), so the saved plan holds the path
    later phases will read, not the raw text the AI wrote."""
    return reply.model_copy(
        update={
            "files": [
                item.model_copy(update={"path": normalise_path(item.path)}) for item in reply.files
            ],
            "needs_people": [
                item.model_copy(update={"path": normalise_path(item.path)})
                for item in reply.needs_people
            ],
        }
    )


# --- warnings and zones (computed by the app, never by the AI) ---


def compute_warnings(
    reply: ApproachReply, policy: Policy, discovery: DiscoveryResult
) -> tuple[list[str], list[str]]:
    """The warnings and the flag-for-review zones touched. Warnings never refuse a plan."""
    warnings: list[str] = []
    zones: list[str] = []
    hit_paths = {normalise_path(hit.source_path).lower() for hit in discovery.hits}
    for item in reply.files:
        if item.action == "modify" and normalise_path(item.path).lower() not in hit_paths:
            warnings.append(
                f"{normalise_path(item.path)}: Not found in Discover. It will be checked "
                "against your workspace in Phase 5."
            )
    if len(reply.files) > policy.max_files:
        warnings.append(
            f"{len(reply.files)} code files; the limit is {policy.max_files}. "
            "Splitting the request is safer."
        )
    for person in reply.needs_people:
        warnings.append(f"A person must change {normalise_path(person.path)}: {person.reason}.")
    for zone in policy.flag_review_zones:
        paths = [normalise_path(item.path).lower() for item in reply.files]
        if any(matches_any(path, zone.path_patterns) for path in paths):
            zones.append(zone.name)
            warnings.append(
                f"Touches {zone.name}. A named senior becomes a required reviewer at the "
                "pull request."
            )
    # Phase 9 (spec section 7): a caller found by impact inside a zone adds that zone, warning only.
    impact_rows = discovery.impact.rows if discovery.impact else []
    for name in dict.fromkeys(row.zone for row in impact_rows if row.zone):
        if name not in zones:
            zones.append(name)
            warnings.append(
                f"Touches {name}: a caller is in this zone. A named senior becomes a required "
                "reviewer at the pull request."
            )
    return warnings, zones


def folder_for_tests(request_id: str) -> str:
    """The fixed test line on screen: tests/<request id in lower case with _>/."""
    return f"tests/{request_id.lower().replace('-', '_')}/"


# --- the Tester's replies (spec section 5) ---


def find_test_plan_problems(
    reply: TestPlanReply, record: RequestRecord, developer_text: str
) -> list[str]:
    criteria = [criterion.id for criterion in record.acceptance_criteria]
    problems = _case_problems(reply.cases, criteria, developer_text)
    counts = {criterion: 0 for criterion in criteria}
    for case in reply.cases:
        if case.criterion_id in counts:
            counts[case.criterion_id] += 1
    for criterion, count in counts.items():
        if count == 0:
            problems.append(f"{criterion} has no test case.")
        elif count > MAX_TESTER_CASES_PER_CRITERION:
            problems.append(
                f"{criterion} has {count} test cases. The limit is "
                f"{MAX_TESTER_CASES_PER_CRITERION}."
            )
    return problems


def find_test_case_problems(
    case: TestCaseReply, record: RequestRecord, developer_text: str
) -> list[str]:
    criteria = [criterion.id for criterion in record.acceptance_criteria]
    return _case_problems([case], criteria, developer_text)


def _case_problems(
    cases: list[TestCaseReply], criteria: list[str], developer_text: str
) -> list[str]:
    problems: list[str] = []
    for number, case in enumerate(cases, start=1):
        label = f"Case {number} ({case.criterion_id})"
        if case.criterion_id not in criteria:
            problems.append(f"{label}: {case.criterion_id} is not a criterion of this request.")
        if is_vague_then(case.expect):
            problems.append(
                f"{label}: 'expect' must say something a person or a test can see, "
                "for example a message, a saved value, or a rejected file."
            )
        for part, text in (("given", case.given), ("expect", case.expect)):
            code = find_code(text)
            if code is not None:
                problems.append(f'{label}: {part} contains code ("{code[:60]}"). Use plain words.')
            for invented in find_invented_names(text, developer_text):
                problems.append(
                    f"{label}: {part} names '{invented}', which the developer did not type. "
                    "Describe the case in plain words instead of naming files or functions."
                )
    return problems


# --- typed text (spec section 1, rule G7) ---


def custom_answer_problem(text: str) -> str | None:
    return developer_message_problem(text) or (
        CUSTOM_TOO_LONG if len(text.strip()) > CUSTOM_ANSWER_LIMIT else None
    )


def change_text_problem(text: str) -> str | None:
    return developer_message_problem(text) or (
        f"Please keep your change under {CHANGE_LIMIT:,} characters."
        if len(text.strip()) > CHANGE_LIMIT
        else None
    )


def limit_reason_problem(text: str) -> str | None:
    problem = developer_message_problem(text)
    if problem:
        return problem
    if not LIMIT_REASON_MIN <= len(text.strip()) <= LIMIT_REASON_LIMIT:
        return (
            f"Please give a reason of {LIMIT_REASON_MIN} to {LIMIT_REASON_LIMIT} characters "
            f"(yours is {len(text.strip())})."
        )
    return None


def case_text_problem(text: str) -> str | None:
    return developer_message_problem(text) or (
        f"Please keep your test case under {CASE_TEXT_LIMIT} characters."
        if len(text.strip()) > CASE_TEXT_LIMIT
        else None
    )


# --- the gate (spec section 6): recomputed from saved data every time ---

GATE_NAMES = ("Request confirmed", "Discover done", "Approach confirmed", "Test plan accepted")


def compute_gate(
    record: RequestRecord | None,
    request_version: int,
    approach: ApproachVersion | None,
    saved_rounds: int,
    confirmed_round: int,
    state: ApproachState | None,
    plan: TestPlanVersion | None,
    confirmed_round_record_version: int | None = None,
    net_accepted: bool = False,
) -> list[GateCheck]:
    """The 4 checks. A false check carries a plain sentence saying why.

    Phase 9 (spec section 9): for an enhance or fix request, check 4 also needs the safety net
    accepted for this record version (`net_accepted`). A new-program request ignores it.

    `confirmed_round_record_version` is the request version the confirmed Discover round was
    built from (N2). None means the caller has no such round to compare, so only the round
    numbers are checked."""
    checks = []
    ok = approach is not None and approach.record_version == request_version
    checks.append(
        GateCheck(
            name=GATE_NAMES[0],
            passed=ok,
            detail=(
                f"v{request_version}, {len(record.acceptance_criteria) if record else 0} criteria"
                if ok
                else "The approach was not built from the latest confirmed request."
            ),
        )
    )
    ok = approach is not None and approach.discovery_round == saved_rounds == confirmed_round
    stale_record = (
        confirmed_round_record_version is not None
        and confirmed_round_record_version != request_version
    )
    checks.append(
        GateCheck(
            name=GATE_NAMES[1],
            passed=ok and not stale_record,
            detail=(
                "The confirmed Discover round was built from an older version of the request."
                if ok and stale_record
                else f"Round {saved_rounds} confirmed"
                if ok
                else "The approach was not built from the latest confirmed Discover round."
            ),
        )
    )
    ok = (
        approach is not None
        and state is not None
        and state.accepted_approach_version == approach.approach_version
    )
    checks.append(
        GateCheck(
            name=GATE_NAMES[2],
            passed=ok,
            detail=(
                f"v{approach.approach_version}, by you"
                if ok
                else "The latest approach has not been accepted."
            ),
        )
    )
    reason = _plan_problem(record, state, plan)
    if not reason and record is not None and record.kind != "new" and not net_accepted:
        reason = "The safety net has not been accepted for this version of the request."
    checks.append(
        GateCheck(
            name=GATE_NAMES[3],
            passed=not reason,
            detail=reason
            or (
                f"{len(plan.cases)} tests, "
                f"{sum(1 for c in plan.cases if c.source == 'developer')} yours"
            ),
        )
    )
    return checks


def _plan_problem(
    record: RequestRecord | None, state: ApproachState | None, plan: TestPlanVersion | None
) -> str:
    if plan is None or state is None:
        return "There is no test plan yet."
    if state.accepted_plan_version != plan.plan_version:
        return "The latest test plan has not been accepted."
    if plan.approach_version != state.accepted_approach_version:
        return "The accepted test plan was written for an older approach."
    covered = {case.criterion_id for case in plan.cases}
    missing = [c.id for c in (record.acceptance_criteria if record else []) if c.id not in covered]
    if missing:
        return f"{', '.join(missing)} has no test case."
    return ""


def gate_problem_lines(checks: list[GateCheck]) -> list[str]:
    return [f"{check.name}: {check.detail}" for check in checks if not check.passed]
