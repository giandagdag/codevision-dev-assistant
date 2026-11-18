"""Fix D1 step 5: the report body is laid out from made-up saved results."""

from agents.da_test_report import NO_EVIDENCE, build_report, case_id_of, evidence_note
from pydantic_classes.da_build_models import EvidenceLine, TestOutcome

LINE = EvidenceLine(label="empty", given="()", expected="0", actual="0", match=True)
CASES = {"T-1": {"criterion_id": "AC-1", "given": "a", "expect": "b", "negative": True}}


def outcome(name, result="pass", evidence=None, message=""):
    return TestOutcome(name=name, result=result, message=message, evidence=evidence or [])


def report(is_enhance, text="evidence(x)"):
    layer_b = [
        outcome("Tests.test_t1_ac1_empty", evidence=[LINE]),
        outcome("Tests.test_t2_ac2_x", "fail", message="boom"),
        outcome("Tests.test_s1_keeps_old"),
    ]
    code = [outcome("Tests.test_c1_adds", evidence=[LINE])]
    return build_report(
        {"title": "made up"}, layer_b, code, ["C-2: wrong"], CASES, text, is_enhance, [], []
    )


def test_ids_come_from_the_test_names():
    assert case_id_of("Tests.test_t12_ac3_x") == "T-12"
    assert case_id_of("test_c1_adds") == "C-1"
    assert case_id_of("setUp") == ""


def test_d1_14_section_three_is_for_enhance_only():
    assert [s["key"] for s in report(True)["sections"]] == ["requirement", "code", "safety"]
    assert [s["key"] for s in report(False)["sections"]] == ["requirement", "code"]


def test_the_summary_counts_each_layer_and_the_dropped_tests():
    summary = report(True)["summary"]

    assert summary["requirement"] == {"passed": 1, "failed": 1, "other": 0}
    assert summary["code"] == {"passed": 1, "failed": 0, "other": 0, "dropped": 1}


def test_a_row_carries_its_case_evidence_and_the_failure_message():
    first, second = report(False)["sections"][0]["rows"]

    assert (first["id"], first["criterion"], first["negative"]) == ("T-1", "AC-1", True)
    assert first["evidence"][0]["actual"] == "0" and first["message"] == ""
    assert second["message"] == "boom" and second["evidence_note"] == NO_EVIDENCE


def test_d1_13_a_test_frozen_before_d1_gets_the_longer_note_and_still_counts():
    old = outcome("Tests.test_t1_ac1_x")

    assert evidence_note(old, "self.assertEqual(1, 1)").endswith("(test written before 17 Nov)")
    assert evidence_note(old, "evidence('a')") == NO_EVIDENCE
    assert evidence_note(outcome("t", evidence=[LINE]), "") == ""
    assert report(False, text="plain")["summary"]["requirement"]["passed"] == 1
