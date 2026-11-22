"""Fix NP step 5: the test report names a load error and never counts it as Not proven (NP-7)."""

from agents.da_test_report import build_report
from agents.da_test_report_pdf import report_pdf
from pydantic_classes.da_build_models import LoadError, TestOutcome

HEADER = {
    "request_id": "CVDA-1", "title": "t", "requirement_version": 1, "approach_version": 1,
    "test_set_version": 1, "build_number": 1, "round": 1, "fingerprints": {}, "time": "now",
    "models": {}, "ran_where": "x", "label": "Not passing",
}  # fmt: skip


def make(load_error):
    tests = [TestOutcome(name=f"T.test_t{i}_ac1", result="not_run") for i in range(1, 4)]
    return build_report(HEADER, tests, [], [], {}, "", False, [], [], load_error=load_error)


def test_np7_a_load_error_gets_its_own_line_and_is_not_counted_as_not_proven():
    error = LoadError(
        kind="import",
        error_type="ModuleNotFoundError",
        message="No module named 'openpyxl'",
        traceback_tail=['  File "/srv/da_sandbox_ab/src/agents/x.py", line 3', "api_key = abc123"],
    )
    report = make(error)

    assert report["summary"]["requirement"] == {"passed": 0, "failed": 0, "other": 0}
    page = report_pdf(report)
    assert b"Load error: The test file could not load" in page
    assert b"No module named 'openpyxl'" in page
    assert b"<sandbox>/src/agents/x.py" in page
    assert b"da_sandbox_" not in page and b"abc123" not in page


def test_an_older_report_without_the_key_still_renders():
    report = make(None)
    del report["load_error"]
    assert b"Load error" not in report_pdf(report)
