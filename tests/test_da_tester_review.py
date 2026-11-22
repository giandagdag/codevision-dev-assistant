"""The plain-code half of Layer C: checks 1, 2, 3, 7, the evidence rule, labels, the Generator's
fix lines and the Tester prompt (Phase 7 tests 7-3 to 7-9, 7-24 prompt side)."""

from datetime import UTC, datetime

import pytest

from agents import da_tester_review as review
from pydantic_classes.da_approach_models import ApproachDecision
from pydantic_classes.da_build_models import LayerBResult, TestOutcome
from pydantic_classes.da_tester_models import Finding, FindingAction, ReplyFinding
from tests.da_approach_samples import REQUEST_ID, sample_record
from tests.da_build_play import CREATE, MODIFY, make_approach, make_cases

CODE = "def read_sheets(book):\n    rows = []\n    return rows\n\n\nx = 1\ny = 2\nz = 3\nw = 4\n"
NOW = datetime(2026, 11, 7, tzinfo=UTC)


def make_test_file(*ids):
    lines = ["import unittest", "", "", "class T(unittest.TestCase):"]
    for n, criterion in ids:
        lines += [f"    def test_t{n}_ac{criterion}_x(self):", "        pass", ""]
    return "\n".join(lines)


def reply(**changes) -> ReplyFinding:
    base = {
        "check": 6,
        "severity": "must_fix",
        "file": CREATE,
        "line": 6,
        "quote": "x = 1",
        "cites": "CV-PY-001",
        "message": "A plain sentence.",
    }
    return ReplyFinding(**{**base, **changes})


@pytest.fixture
def approach():
    made = make_approach()
    decision = ApproachDecision(question="Which?", choice="This", custom=False, decided_at=NOW)
    return made.model_copy(update={"decisions": [decision]})


def evidence(item, approach, window=2, rules=None):
    cites = review.allowed_cites(
        item.check, approach, sample_record(), rules or [], [CREATE, MODIFY]
    )
    return review.check_evidence(item, {CREATE: CODE}, cites, window)


# --- checks 1, 2, 3, 7 ---


def test_7_4_a_criterion_without_a_test_is_a_must_fix_the_generator_cannot_fix():
    found = review.check_criteria_have_tests(sample_record(), make_test_file((1, 1), (2, 2)))

    assert [(f.check, f.severity, f.cites, f.fixable) for f in found] == [
        (1, "must_fix", "AC-3", False)
    ]
    assert "Criterion AC-3 has no test" in found[0].message


def test_check_1_passes_when_every_criterion_has_a_test():
    text = make_test_file((1, 1), (2, 2), (3, 3))

    assert review.check_criteria_have_tests(sample_record(), text) == []


def test_check_1_treats_an_unreadable_test_file_as_no_tests():
    found = review.check_criteria_have_tests(sample_record(), "def (:")

    assert len(found) == 3


def test_check_2_names_a_criterion_whose_test_does_not_pass():
    layer_b = LayerBResult(
        tests=[
            TestOutcome(name="test_t1_ac1_x", result="pass"),
            TestOutcome(name="test_t2_ac2_x", result="fail"),
        ]
    )

    found = review.check_tests_pass(sample_record(), layer_b)

    assert [(f.check, f.cites) for f in found] == [(2, "AC-2")]


def test_7_5_a_missing_or_an_extra_file_is_a_must_fix():
    planned = [(CREATE, "create"), (MODIFY, "modify")]

    found = review.check_files_match_plan(planned, {MODIFY: "a", "src/other.py": "b"}, {})

    assert [(f.severity, f.file) for f in found] == [
        ("must_fix", CREATE),
        ("must_fix", "src/other.py"),
    ]


def test_7_6_a_modify_file_with_unchanged_text_is_a_should_fix():
    planned = [(CREATE, "create"), (MODIFY, "modify")]
    code = {CREATE: "new", MODIFY: "same"}

    found = review.check_files_match_plan(planned, code, {MODIFY: "same"})

    assert [(f.severity, f.file) for f in found] == [("should_fix", MODIFY)]
    assert f"The plan said to change {MODIFY}, but it was not changed." == found[0].message


def test_check_3_is_quiet_when_files_match():
    planned = [(CREATE, "create"), (MODIFY, "modify")]

    assert review.check_files_match_plan(planned, {CREATE: "a", MODIFY: "b"}, {MODIFY: "old"}) == []


def test_7_7_a_zone_is_a_warning_line_not_a_finding():
    lines = review.zone_warnings(["Login"])

    assert lines == ["Touches the Login zone: the named senior will be a required reviewer."]
    assert review.zone_warnings([]) == []


def test_findings_are_numbered_f_1_f_2():
    plain = review.check_files_match_plan([(CREATE, "create")], {}, {})

    numbered = review.number_findings(plain + plain)

    assert [f.finding_id for f in numbered] == ["F-1", "F-2"]


# --- the evidence rule ---


def test_a_finding_with_good_evidence_is_kept(approach, seed_rulebook):
    item = reply()

    kept, why = evidence(item, approach, rules=seed_rulebook.rules)

    assert why == "" and kept.line == 6


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({"file": "src/agents/not_built.py"}, "not one of this round's code files"),
        ({"line": 0}, "not inside"),
        ({"line": 99}, "not inside"),
        ({"quote": "no such text"}, "not found within 2 lines"),
        ({"line": 1}, "not found within 2 lines"),  # the quote is five lines away
        ({"quote": ""}, "quote is empty"),
        ({"cites": "DD-1"}, "not allowed for check 6"),  # wrong kind of cite
        ({"cites": "CV-PY-999"}, "not allowed for check 6"),  # unknown rule ID
        ({"message": ""}, "message is empty"),
        ({"message": "x" * 301}, "longer than 300"),
    ],
)
def test_7_8_each_bad_piece_of_evidence_drops_the_finding(approach, seed_rulebook, changes, words):
    item = reply(**changes)

    kept, why = evidence(item, approach, rules=seed_rulebook.rules)

    assert kept is None and words in why


def test_7_9_a_quote_two_lines_away_is_kept_and_the_line_is_corrected(approach, seed_rulebook):
    kept, why = evidence(reply(line=4), approach, rules=seed_rulebook.rules)  # x = 1 is on line 6

    assert why == "" and kept.line == 6


def test_a_quote_three_lines_away_is_dropped_with_window_two(approach, seed_rulebook):
    kept, _ = evidence(reply(line=3), approach, rules=seed_rulebook.rules)

    assert kept is None


def test_a_wider_window_keeps_it(approach, seed_rulebook):
    kept, _ = evidence(reply(line=3), approach, window=3, rules=seed_rulebook.rules)

    assert kept.line == 6


def test_cites_for_checks_4_and_5(approach):
    ok4 = evidence(reply(check=4, cites="DD-1"), approach)[0]
    ok4b = evidence(reply(check=4, cites="RU-2"), approach)[0]
    bad4 = evidence(reply(check=4, cites="DD-2"), approach)[0]
    ok5 = evidence(reply(check=5, cites=f"PLAN:{CREATE}"), approach)[0]
    ok5b = evidence(reply(check=5, cites="AC-2"), approach)[0]
    bad5 = evidence(reply(check=5, cites="AC-9"), approach)[0]

    assert ok4 and ok4b and ok5 and ok5b
    assert bad4 is None and bad5 is None


def test_split_findings_keeps_every_finding_with_its_reason(approach, seed_rulebook):
    items = [reply(), reply(quote="not there")]

    result = review.split_findings(
        items,
        {CREATE: CODE},
        approach,
        sample_record(),
        seed_rulebook.rules,
        [CREATE, MODIFY],
        2,
    )

    assert [(f.kept, bool(f.reject_reason)) for f in result] == [(True, False), (False, True)]
    assert all(f.made_by == "tester" for f in result)


def test_b1_short_words_and_parts_of_words_are_not_required_text():
    from agents.da_tester_review import required_by

    record = sample_record()
    criterion = record.acceptance_criteria[0].model_copy(
        update={"then": "The id sees the invalid file message"}
    )
    record = record.model_copy(update={"acceptance_criteria": [criterion]})

    assert required_by('password = "id"', record) == ""  # too short
    assert required_by('x = "valid"', record) == ""  # only part of "invalid"
    assert required_by('x = "invalid"', record) == criterion.id


def test_b1_required_text_becomes_fyi_required_by_ac(approach, seed_rulebook):
    record = sample_record()
    criterion = record.acceptance_criteria[0].model_copy(update={"then": 'It shows "Done now"'})
    record = record.model_copy(update={"acceptance_criteria": [criterion]})
    code = 'def f():\n    print("Done now")\n    print("Other text")\n'
    items = [
        reply(line=2, quote='print("Done now")'),
        reply(line=3, quote='print("Other text")'),
    ]

    result = review.split_findings(
        items, {CREATE: code}, approach, record, seed_rulebook.rules, [CREATE], 2
    )

    assert [f.severity for f in result] == ["fyi", "must_fix"]
    assert result[0].message.startswith(f"Required by {criterion.id}.")


def test_b1_the_tester_prompt_lists_the_criteria_and_the_error_path_line(approach, seed_rulebook):
    prompt = review.build_review_prompt(make_input(seed_rulebook))

    assert "AC-1: Given" in prompt and "Expect:" in prompt
    assert "applies only to error\npaths: raise, except, logged errors" in prompt


def test_b2_the_same_must_fix_again_is_found_and_the_stop_text_names_it():
    was = Finding(finding_id="F-1", check=6, severity="must_fix", file=CREATE, line=6, cites="X")
    same = was.model_copy(update={"finding_id": "F-2"})
    other = was.model_copy(update={"finding_id": "F-3", "line": 99})
    ac_one = was.model_copy(update={"finding_id": "F-4", "cites": "AC-1"})

    assert review.repeated_must_fix([other], [was]) is None
    assert review.repeated_must_fix([same], [was]) == same
    text = review.stop_text(ac_one, sample_record())
    assert text.startswith("The Tester's finding F-4 conflicts with what was built for AC-1,")
    assert "Dispute F-4" in text


# --- labels ---



def finding(severity, check=5, kept=True, fid="F-1"):
    return Finding(finding_id=fid, check=check, severity=severity, kept=kept)


def action(kind, fid="F-1", review_number=1):
    return FindingAction(
        request_id=REQUEST_ID,
        build_number=1,
        review_number=review_number,
        finding_id=fid,
        action=kind,
        reason="a good reason",
    )


@pytest.mark.parametrize(
    ("findings", "zones", "result", "acts", "label"),
    [
        ([], [], "done", [], "Ready for your review"),
        ([finding("fyi")], [], "done", [], "Ready for your review"),
        ([finding("should_fix")], [], "done", [], "Ready with warnings"),
        ([], ["z"], "done", [], "Ready with warnings"),
        ([finding("should_fix")], [], "done", [action("accepted")], "Ready for your review"),
        (
            [finding("should_fix")],
            [],
            "done",
            [action("accepted"), action("reopened")],
            "Ready with warnings",
        ),
        ([finding("should_fix")], ["z"], "done", [action("accepted")], "Ready with warnings"),
        ([finding("must_fix")], [], "done", [], "Not passing"),
        ([finding("must_fix", kept=False)], [], "done", [], "Ready for your review"),
        ([], [], "unable", [], "Unable to assess"),
        ([finding("must_fix")], [], "unable", [], "Not passing"),  # a plain Must fix wins
    ],
)
def test_label_rules(findings, zones, result, acts, label):
    assert review.compute_label(findings, zones, result, 1, acts) == label


def test_an_accept_belongs_to_its_own_review():
    findings = [finding("should_fix")]

    label = review.compute_label(findings, [], "done", 2, [action("accepted", review_number=1)])

    assert label == "Ready with warnings"


def test_no_label_says_approved():
    labels = {review.LABEL_READY, review.LABEL_WITH_WARNINGS, review.LABEL_UNABLE}

    assert not any("Approved" in text for text in labels)


def test_the_seven_check_rows_say_not_run_for_the_ai_checks_when_unable():
    rows = review.check_results([], [], ran_ai=False)

    assert [r.state for r in rows] == [
        "passed",
        "passed",
        "passed",
        "not_run",
        "not_run",
        "not_run",
        "passed",
    ]


def test_check_rows_count_kept_findings_and_zone_warnings():
    found = [finding("must_fix", 4), finding("fyi", 4, kept=False)]

    rows = review.check_results(found, ["z"], True)

    assert (rows[3].state, rows[3].findings) == ("failed", 1)
    assert (rows[6].state, rows[6].findings) == ("warning", 1)


# --- the Generator's fix input ---


def test_the_generator_gets_must_fix_lines_only():
    items = [
        Finding(finding_id="F-1", check=5, severity="must_fix", file=CREATE, line=6, quote="x = 1",
                cites="AC-1", message="Too much."),
        Finding(finding_id="F-2", check=5, severity="should_fix", file=MODIFY, line=1,
                quote="SHOULD", cites="AC-1", message="Maybe."),
        Finding(finding_id="F-3", check=5, severity="fyi", file=MODIFY, line=1, quote="FYIQ",
                cites="AC-1", message="Note."),
    ]  # fmt: skip

    text = review.report_for_generator(items)

    assert "F-1" in text and "Too much." in text
    assert "SHOULD" not in text and "FYIQ" not in text and "Maybe." not in text
    assert review.files_to_fix(items, [MODIFY, CREATE]) == [CREATE]


# --- the prompt ---


def make_input(seed_rulebook, **changes):
    values = {
        "charter": seed_rulebook.charter,
        "rules": seed_rulebook.rules,
        "record": sample_record(),
        "approach": make_approach(),
        "cases": make_cases(3),
        "policy": seed_rulebook.policy,
        "layer_b": LayerBResult(tests=[TestOutcome(name="test_t1_ac1_x", result="pass")]),
        "code": {CREATE: CODE, MODIFY: "def validate(path):\n    return True\n"},
        "start_texts": {},
        "planned_paths": [CREATE, MODIFY],
        "round": 2,
    }
    return review.ReviewInput(**{**values, **changes})


def test_7_3_the_prompt_holds_the_agreement_and_line_numbered_code(seed_rulebook):
    prompt = review.build_review_prompt(make_input(seed_rulebook))

    assert review.REVIEW_MARKER in prompt and "Round: 2" in prompt
    assert "   1| def read_sheets(book):" in prompt
    assert "T-1 (AC-1)" in prompt  # the test plan and the results
    assert "CV-PY-001" in prompt  # a judgement rule
    assert "RU-1" in prompt


def test_7_3_the_prompt_holds_no_chat_no_earlier_findings_and_no_test_file(seed_rulebook):
    prompt = review.build_review_prompt(make_input(seed_rulebook))

    assert "class T(unittest.TestCase)" not in prompt
    assert "Why the last round failed" not in prompt
    assert "developer chat" not in prompt.lower()
    assert "F-1" not in prompt


def test_the_prompt_can_hold_one_file_only(seed_rulebook):
    prompt = review.build_review_prompt(make_input(seed_rulebook), only_file=MODIFY)

    assert f"### {MODIFY}" in prompt and f"### {CREATE}" not in prompt


def test_the_round_number_is_read_back_from_the_prompt(seed_rulebook):
    prompt = review.build_review_prompt(make_input(seed_rulebook, round=3))

    assert review.round_of_prompt(prompt) == 3
