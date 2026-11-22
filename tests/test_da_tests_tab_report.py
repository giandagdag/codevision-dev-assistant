"""Fix D1 step 7 (D1-12): the Tests tab shows the summary, the link, two groups and evidence."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_test_report import report_summary_line
from layouts.da_build_panel import NO_REPORT_LINE
from layouts.da_build_panel import tests_tab as draw_tests_tab
from pydantic_classes.da_build_models import LayerAResult, LayerBResult, RoundRecord, TestOutcome
from tests.da_build_play import ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def view_and_settings(make_settings):
    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    loop.run_build(settings, request_id)
    return flow.get_build_view(settings, request_id), settings, request_id


def test_d1_12_the_tab_has_a_summary_a_link_two_groups_and_an_evidence_column(view_and_settings):
    view = view_and_settings[0]
    text = str(draw_tests_tab(view))

    assert view.has_report and view.report_summary.startswith("Against the requirement:")
    assert "Download report (PDF)" in text and "Open report" not in text
    assert "Requirement tests" in text and "Evidence" in text
    assert ("Code tests" in text) == bool(view.code_tests)


def test_d1_12_a_build_with_tests_run_but_no_saved_report_says_so(view_and_settings):
    view = view_and_settings[0].model_copy(update={"has_report": False, "report_summary": ""})

    assert NO_REPORT_LINE in str(draw_tests_tab(view))


def test_the_summary_line_counts_requirement_code_and_dropped_tests():
    def outcome(name, result="pass"):
        return TestOutcome(name=name, result=result)

    last = RoundRecord(
        request_id="CVDA-2026-0001", build_number=1, round=1, layer_a=LayerAResult(),
        layer_b=LayerBResult(tests=[outcome("T.test_t1_a"), outcome("T.test_t2_b", "fail")]),
        code_tests=LayerBResult(tests=[outcome("T.test_c1_a"), outcome("T.test_c2_b")]),
        dropped_code_tests=["C-3: wrong"],
    )  # fmt: skip

    assert report_summary_line([last]) == (
        "Against the requirement: 1 of 2 passed. Against the code: 2 of 2 passed, 1 dropped."
    )
    assert report_summary_line([]) == ""
