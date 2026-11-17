"""Judging failing code tests (Fix D1, E5): the Tester says, for each failing C-n test, whether the
code is wrong (a code bug: the Generator must fix it) or the test is wrong (it is dropped, with its
reason, and the label stops at Ready with warnings).

Like a second pair of eyes on a failed RPG test case: is the program wrong, or is the test?
"""

import json
import re

from agents.da_approach_agent import fill_template
from agents.da_build_agent import DATA_FOLDER, AIResult, BuildContext, _ask
from agents.da_build_checks import clean_code_reply
from agents.da_code_tests import code_test_id
from agents.da_llm_client import LLMClient
from pydantic_classes.da_build_models import TestOutcome

JUDGE_PROMPT = DATA_FOLDER / "da_build_judge_prompt.md"
JUDGE_MARKER = "Task: judge the failing code tests"
CODE_BUG = "code_bug"
WRONG_TEST = "wrong_test"
REASON_LIMIT = 200
UNJUDGED = "The Tester could not judge this test, so it counts as a code problem."
_FAILURE_LINE = re.compile(r"^- (C-\d+) \((\w+)\): ", re.MULTILINE)


def failing_code_tests(tests: list[TestOutcome]) -> list[tuple[str, TestOutcome]]:
    """(C-n, outcome) of every code test that did not pass."""
    return [(code_test_id(o.name), o) for o in tests if o.result != "pass" and code_test_id(o.name)]


def judge_code_tests(
    client: LLMClient,
    context: BuildContext,
    code_files: dict[str, str],
    test_text: str,
    failing: list[tuple[str, TestOutcome]],
) -> AIResult:
    """One call. The value is {C-n: (verdict, reason)} with one entry per failing test."""
    code = "\n\n".join(f"### {path}\n{text}" for path, text in code_files.items())
    lines = [f"- {cid} ({o.name}): {o.message or o.result}" for cid, o in failing]
    prompt = fill_template(
        JUDGE_PROMPT,
        {"code": code or "(no code)", "tests": test_text, "failures": "\n".join(lines)},
    )
    wanted = {cid for cid, _ in failing}

    def check(text: str):
        try:
            data = json.loads(clean_code_reply(text) if text.lstrip().startswith("```") else text)
            verdicts = {
                item["test"]: (item["verdict"], str(item.get("reason", ""))[:REASON_LIMIT])
                for item in data["verdicts"]
            }
        except (ValueError, KeyError, TypeError, AttributeError):
            return None, ["The reply was not the JSON shape asked for. Reply with JSON only."]
        problems = []
        if set(verdicts) != wanted:
            problems.append(f"Give exactly one verdict for each of: {', '.join(sorted(wanted))}.")
        if any(v[0] not in (CODE_BUG, WRONG_TEST) for v in verdicts.values()):
            problems.append(f'Each verdict is "{CODE_BUG}" or "{WRONG_TEST}".')
        return verdicts, problems

    return _ask(client, prompt, check, context, "build_judge_code_tests")


# --- the fake provider ---


def is_judge_prompt(prompt: str) -> bool:
    return bool(re.search(rf"^{re.escape(JUDGE_MARKER)}$", prompt, re.MULTILINE))


def scripted_judge_reply(prompt: str) -> str:
    """The fake Tester reads the end of the failing test's name: `_wrong_test` means the test is
    wrong, anything else means the code is."""
    verdicts = [
        {
            "test": cid,
            "verdict": WRONG_TEST if name.endswith("wrong_test") else CODE_BUG,
            "reason": "The test expects something the code is not meant to do."
            if name.endswith("wrong_test")
            else "The code does not handle this case.",
        }
        for cid, name in _FAILURE_LINE.findall(prompt)
    ]
    return json.dumps({"verdicts": verdicts})
