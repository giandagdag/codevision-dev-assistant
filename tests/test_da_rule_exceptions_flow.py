"""Fix G9 step 5: a senior's exception flows into the prompts and the Tester (U7, G9-3)."""

from agents import da_tester_review as review
from tests.da_approach_samples import sample_record
from tests.da_build_play import CREATE, make_approach
from tests.test_da_tester_review import make_input, reply

CODE = "def f():\n    raise ValueError('Bad input')\n    return 1\n"


def _with_exception(criterion_id="AC-2"):
    record = sample_record()
    line = f"RX-1: CV-PY-001 allowed for {criterion_id}, approved by senior1, legacy screen"
    return record.model_copy(update={"exceptions": [line]})


def _run(record, message, rules):
    items = [reply(line=2, quote="raise ValueError('Bad input')", message=message)]
    return review.split_findings(items, {CREATE: CODE}, make_approach(), record, rules, [CREATE], 2)


def test_the_rx_lines_are_in_the_tester_prompt_only_when_there_are_some():
    from agents.da_understand_rules import exception_prompt_lines

    assert exception_prompt_lines(sample_record()) == ""
    assert "RX-1: CV-PY-001 allowed for AC-2" in exception_prompt_lines(_with_exception())


def test_a_finding_on_the_excepted_rule_for_that_criterion_becomes_fyi(seed_rulebook):
    result = _run(_with_exception("AC-2"), "AC-2 should return a message.", seed_rulebook.rules)

    assert result[0].severity == "fyi"
    assert result[0].message.startswith("Allowed by RX-1.")


def test_a_finding_for_another_criterion_stays_a_must_fix(seed_rulebook):
    result = _run(_with_exception("AC-2"), "AC-1 should return a message.", seed_rulebook.rules)

    assert result[0].kept and result[0].severity == "must_fix"


def test_the_tester_prompt_carries_the_rx_line(seed_rulebook):
    data = make_input(seed_rulebook, record=_with_exception())

    assert "RX-1: CV-PY-001 allowed for AC-2" in review.build_review_prompt(data)
    assert "RX-" not in review.build_review_prompt(make_input(seed_rulebook))
