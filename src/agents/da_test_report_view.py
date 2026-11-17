"""Gather what the report page shows (Fix D1 spec E8/E9): read only, from saved results.

Takes the newest saved report row of a build (da_test_reports) and the saved facts around it
(test cases, frozen test file, Tester review, file fingerprints), then lets `build_report` lay
them out. Nothing runs again and no server path is read or returned.
"""

import sys

from agents.da_test_report import build_report, case_id_of
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import (
    ensure_approach_tables,
    read_approach_versions,
    read_test_plans,
)
from db_table_functions.db_tbl_da_build import (
    ensure_build_tables,
    read_build_run,
    read_frozen_files,
    read_latest_code,
)
from db_table_functions.db_tbl_da_test_report import read_test_reports
from db_table_functions.db_tbl_da_tester import read_reviews
from db_table_functions.db_tbl_da_understand import ensure_understand_tables, read_session
from pydantic_classes.da_build_models import LayerBResult, TestOutcome
from web.da_web_components import format_singapore_time


def report_file_name(request_id: str, build_number: int) -> str:
    return f"CVDA-{request_id}-build-{build_number}-test-report.html"


def get_report(settings, request_id: str, build_number: int) -> dict | None:
    """The report body of one build, or None when no report was saved (an old build)."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        ensure_approach_tables(conn)
        ensure_understand_tables(conn)
        conn.execute("BEGIN")
        saved = read_test_reports(conn, request_id, build_number)
        run = read_build_run(conn, request_id, build_number)
        if not saved or run is None:
            return None
        newest = saved[-1]
        approach = next(
            (a for a in read_approach_versions(conn, request_id)
             if a.approach_version == run.approach_version),
            None,
        )  # fmt: skip
        plans = [p for p in read_test_plans(conn, request_id)
                 if p.approach_version == run.approach_version]  # fmt: skip
        plan = plans[-1] if plans else None
        frozen = read_frozen_files(conn, request_id, run.approach_version)
        code = read_latest_code(conn, request_id, build_number)
        reviews = read_reviews(conn, request_id, build_number)
        session = read_session(conn, request_id)
    record = session.record if session else None
    criteria = record.acceptance_criteria if record else []
    negatives = {c.id for c in criteria if c.kind == "failure"}
    cases = {
        c.test_id: {"criterion_id": c.criterion_id, "given": c.given, "expect": c.expect,
                    "negative": c.criterion_id in negatives}
        for c in (plan.cases if plan else [])
    }  # fmt: skip
    body = newest["body"]
    layer_b = LayerBResult.model_validate(body["layer_b"]) if body.get("layer_b") else None
    code_tests = LayerBResult.model_validate(body["code_tests"]) if body.get("code_tests") else None
    review = reviews[-1] if reviews else None
    models = {"Approach": approach.model if approach else "",
              "Tests": plan.model if plan else "",
              "Tester": review.model if review else ""}  # fmt: skip
    header = {
        "request_id": request_id,
        "title": record.title if record else "",
        "requirement_version": record.version if record else 0,
        "approach_version": run.approach_version,
        "test_set_version": plan.plan_version if plan else 0,
        "build_number": build_number,
        "round": newest["round"],
        "fingerprints": {path: item.fingerprint for path, item in sorted(code.items())},
        "time": format_singapore_time(newest["created_at"]) + " SGT",
        "models": {role: name for role, name in models.items() if name},
        "ran_where": f"CodeVision server sandbox, Python {sys.version.split()[0]}",
        "label": (review.label if review and review.label else run.label),
    }
    checks = [c.model_dump() for c in review.checks] if review else []
    findings = [f.model_dump() for f in review.findings if f.kept] if review else []
    outcomes: list[TestOutcome] = layer_b.tests if layer_b else []
    return build_report(
        header, outcomes, code_tests.tests if code_tests else [],
        body.get("dropped_code_tests", []), cases,
        frozen["test"].text if "test" in frozen else "",
        is_enhance=any(case_id_of(o.name).startswith("S") for o in outcomes),  # S-n = Enhance
        checks=checks, findings=findings,
    )  # fmt: skip
