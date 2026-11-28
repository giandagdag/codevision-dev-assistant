"""G5 B3 (why it is not passing, one line) and B4 (model short name)."""

from agents.da_model_label import model_label
from agents.da_tester_review import reason_line
from layouts import da_tester_panel as panel
from pydantic_classes.da_build_models import LayerBResult, TestOutcome
from pydantic_classes.da_tester_models import (
    CheckResult,
    Finding,
    FindingRow,
    ReviewRecord,
    TesterView,
)
from tests.da_approach_samples import REQUEST_ID


def results(*kinds):
    return LayerBResult(tests=[TestOutcome(name=f"t{n}", result=k) for n, k in enumerate(kinds)])


def test_b4_model_label_keeps_the_last_part_only():
    assert model_label("/data/models/Qwen3.6-35B-A3B") == "Qwen3.6-35B-A3B"
    assert model_label("C:\\models\\Llama-3") == "Llama-3"
    assert model_label("fake-review-script") == "fake-review-script"
    assert model_label("") == ""


def test_b3_the_reason_line_for_failing_tests_tester_findings_and_not_proven():
    assert reason_line("Not passing", 0, [], results("pass", "fail", "fail")) == (
        "2 of 3 tests fail."
    )
    text = reason_line(
        "Not passing", 2, ["Tester check 6, Judgement rules kept"], results("pass", "pass")
    )
    assert text == (
        "All 2 tests passed, but 2 Must fix findings are still open: "
        "Tester check 6, Judgement rules kept."
    )
    assert "not proven" in reason_line("Not passing", 0, [], results("pass", "not_proven"))
    assert reason_line("Ready for your review", 0, [], results("pass")) == ""


def test_b3_the_banner_shows_the_reason_and_a_link_to_the_findings():
    review = ReviewRecord(
        request_id=REQUEST_ID,
        build_number=1,
        round=1,
        review_number=1,
        model="/m/Qwen3.6-35B-A3B",
        checks=[CheckResult(number=6, name="Judgement rules kept", state="failed", findings=1)],
    )
    finding = Finding(finding_id="F-1", check=6, severity="must_fix")
    view = TesterView(
        review=review,
        label="Not passing",
        rows=[FindingRow(finding=finding)],
        summary="s",
        reason="2 of 19 tests fail.",
        layer_c_ran=True,
    )

    text = str(panel.tester_report(view, can_act=True))

    assert "2 of 19 tests fail." in text
    assert "See the findings" in text and panel.SEE_FINDINGS_ID in text  # G9 S2: a button now
    assert "Reviewed by Qwen3.6-35B-A3B in" in text and "/m/" not in text
