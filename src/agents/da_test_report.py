"""Build the test report body (Fix D1 spec E8) from results that were already saved.

Pure code, no database and no AI: the caller gathers the saved round body (da_test_reports), the
test cases (Given / Expect / criterion), the review and the header facts, and this module lays
them out. Nothing here runs a test again, so every number in the report is a saved one.
"""

import re
from typing import Any

from agents.da_evidence_helper import hide_secret
from agents.da_load_errors import hide_sandbox, load_failed_text
from pydantic_classes.da_build_models import LoadError, TestOutcome

NO_EVIDENCE = "Evidence not recorded"
ASTERISK_LEGEND = "* a negative scenario: the test passes when the code refuses or fails safely."

# (section key, title, test id letter). Section 3 is for Enhance only (D1-14).
_SECTIONS = (
    ("requirement", "1. Against the requirement", "T"),
    ("code", "2. Against the code", "C"),
    ("safety", "3. Safety net", "S"),
)
_ID_IN_NAME = re.compile(r"test_([tcs])(\d+)")


def case_id_of(name: str) -> str:
    """'ExcelTests.test_t2_ac1_empty' gives 'T-2'; '' when the name carries no id."""
    found = _ID_IN_NAME.search(name)
    return f"{found.group(1).upper()}-{found.group(2)}" if found else ""


def count_results(tests: list[TestOutcome]) -> dict[str, int]:
    """Passed, failed (failed + error), not proven (skipped or never reported) of one layer.
    A test that did not run because the file could not load is none of these (Fix NP)."""
    failed = sum(1 for item in tests if item.result in ("fail", "error"))
    passed = sum(1 for item in tests if item.result == "pass")
    not_run = sum(1 for item in tests if item.result == "not_run")
    return {"passed": passed, "failed": failed, "other": len(tests) - passed - failed - not_run}


def newest_tested_round(rounds):
    """The newest saved round that reached Layer B (it has a report), or None."""
    return next((r for r in reversed(list(rounds)) if r.layer_b is not None), None)


def report_summary_line(rounds) -> str:
    """'Against the requirement: 8 of 8 passed. Against the code: 11 of 12 passed, 1 dropped.'
    for the Tests tab and the handoff text. Empty when no round reached Layer B."""
    last = newest_tested_round(rounds)
    if last is None:
        return ""
    if last.layer_b.load_error is not None:
        return f"Load error: {load_failed_text(last.layer_b)}."
    tests = [t for t in last.layer_b.tests if case_id_of(t.name).startswith("T")]
    line = f"Against the requirement: {count_results(tests)['passed']} of {len(tests)} passed."
    if last.code_tests is not None:
        done = count_results(last.code_tests.tests)["passed"]
        dropped = len(last.dropped_code_tests)
        line += f" Against the code: {done} of {len(last.code_tests.tests)} passed"
        line += f", {dropped} dropped." if dropped else "."
    return line


def evidence_note(outcome: TestOutcome, test_text: str) -> str:
    """What the Evidence column says when a test recorded nothing. A test frozen before D1 never
    had the call at all, so it gets the longer, kinder wording; its pass still counts."""
    if outcome.evidence:
        return ""
    if "evidence(" not in test_text:
        return f"{NO_EVIDENCE} (test written before 17 Nov)"
    return NO_EVIDENCE


def _row(outcome: TestOutcome, case: dict[str, Any] | None, test_text: str) -> dict[str, Any]:
    case = case or {}
    return {
        "id": case_id_of(outcome.name),
        "name": outcome.name,
        "criterion": case.get("criterion_id", ""),
        "given": case.get("given", ""),
        "expect": case.get("expect", ""),
        "negative": bool(case.get("negative")),
        "result": outcome.result,
        "message": "" if outcome.result == "pass" else hide_secret(outcome.message),
        "evidence": [line.model_dump() for line in outcome.evidence],
        "evidence_note": evidence_note(outcome, test_text),
    }


def build_report(
    header: dict[str, Any],
    layer_b: list[TestOutcome],
    code_tests: list[TestOutcome],
    dropped_code_tests: list[str],
    cases: dict[str, dict[str, Any]],
    test_text: str,
    is_enhance: bool,
    checks: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    targets: dict[str, str] | None = None,
    load_error: LoadError | None = None,
) -> dict[str, Any]:
    """The report as plain data. `layer_b` holds the T-n and (Enhance) S-n outcomes, `cases` maps
    'T-1' to its criterion_id, given, expect and negative flag. `header` passes through."""
    groups = {
        "requirement": [t for t in layer_b if case_id_of(t.name).startswith("T")],
        "code": code_tests,
        "safety": [t for t in layer_b if case_id_of(t.name).startswith("S")],
    }
    sections = []
    for key, title, _letter in _SECTIONS:
        if key == "safety" and not is_enhance:
            continue
        rows = [_row(t, cases.get(case_id_of(t.name)), test_text) for t in groups[key]]
        if key == "code":  # a code test has no criterion: its Targets line says what it checks
            for row in rows:
                row["criterion"] = (targets or {}).get(row["id"], "")
        sections.append({"key": key, "title": title, "rows": rows})
    summary = {key: count_results(items) for key, items in groups.items()}
    summary["code"]["dropped"] = len(dropped_code_tests)
    shown = None
    if load_error is not None:  # hidden again here, so a report of an older build is safe too
        shown = {
            "text": f"The test file could not load. {load_error.error_type}: "
            f"{hide_sandbox(load_error.message)}".strip(),
            "tail": [hide_sandbox(line) for line in load_error.traceback_tail],
        }
    return {
        "load_error": shown,
        "header": header,
        "summary": summary,
        "sections": sections,
        "dropped_code_tests": dropped_code_tests,
        "checks": checks,
        "findings": findings,
        "legend": ASTERISK_LEGEND,
    }
