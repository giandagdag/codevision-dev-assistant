"""Fix D1 step 8 (D1-16, D1-17): the PR summary names the report; the Admin tab says it exists."""

from agents.da_handoff_summary import build_summary
from layouts.da_admin_build_tab import TEST_FACTS
from pydantic_classes.da_handoff_models import SummaryFacts

FACTS = SummaryFacts(request_id="CVDA-2026-0001", summary="Add a limit", tester_label="Ready")


def test_d1_16_the_summary_has_the_report_lines_and_the_file_name_only_when_a_report_exists():
    with_report = FACTS.model_copy(
        update={
            "report_summary": "Against the requirement: 3 of 3 passed.",
            "report_file": "CVDA-2026-0001-build-1-test-report.html",
        }
    )
    lines = build_summary(with_report, 6000).split("\n")

    assert "Against the requirement: 3 of 3 passed." in lines
    assert "Test report: CVDA-2026-0001-build-1-test-report.html" in lines
    assert "Test report" not in build_summary(FACTS, 6000)


def test_d1_17_the_admin_tests_card_lists_the_report_line_and_keeps_the_code_tests_line():
    assert "Every build saves a test report: input, expected, actual, pass or fail" in TEST_FACTS
    assert any(line.startswith("Code tests after the build") for line in TEST_FACTS)
