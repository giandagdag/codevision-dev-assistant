"""Fix G9 step 13: a finding that says the code complies is dropped (F1, F2, G9-13)."""

from agents import da_tester_review as review
from tests.da_approach_samples import sample_record
from tests.test_da_rule_exceptions_flow import _run
from tests.test_da_tester_review import make_input

PRAISE = "The error message is a plain sentence, which complies with the rule."
MIXED = "The code complies with the rule, but the message names no fix."


def test_a_praise_finding_is_dropped_as_not_a_problem(seed_rulebook):
    result = _run(sample_record(), PRAISE, seed_rulebook.rules)

    assert not result[0].kept
    assert result[0].reject_reason == "Not a problem: the finding says the code complies"


def test_complies_but_names_a_problem_is_kept(seed_rulebook):
    result = _run(sample_record(), MIXED, seed_rulebook.rules)

    assert result[0].kept


def test_the_prompt_tells_the_tester_to_write_no_praise(seed_rulebook):
    prompt = review.build_review_prompt(make_input(seed_rulebook))

    assert "If the code follows the rule, write no finding" in prompt
