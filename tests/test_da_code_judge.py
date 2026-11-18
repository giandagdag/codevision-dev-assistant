"""Fix D1 step 3c: the Tester judges failing code tests (D1-6, D1-7). No AI, no internet."""

import json

import pytest

from agents import da_build_agent as agent
from agents import da_code_judge as judge
from agents import da_tester_review as tester
from pydantic_classes.da_build_models import LayerBResult, TestOutcome
from tests.da_build_play import make_context


class Said:
    """A client that answers with fixed texts, one per call."""

    model = "said"

    def __init__(self, *texts):
        self.texts = list(texts)

    def complete(self, prompt):
        return type("Reply", (), {"text": self.texts.pop(0), "provider": "x", "model": "x"})()


@pytest.fixture
def context(seed_rulebook):
    return make_context(seed_rulebook)


FAILING = [
    ("C-2", TestOutcome(name="test_c2_empty_fails_code_bug", result="fail", message="boom")),
    ("C-3", TestOutcome(name="test_c3_odd_fails_wrong_test", result="fail", message="no")),
]


def ask(context, client):
    return judge.judge_code_tests(client, context, {"src/a.py": "x = 1\n"}, "tests", FAILING)


def test_the_fake_tester_reads_the_name_of_each_failing_test(context, make_settings):
    client = agent.get_build_client(make_settings(llm_provider="fake"), "tester")

    result = ask(context, client)

    assert result.ok
    assert {k: v[0] for k, v in result.value.items()} == {"C-2": "code_bug", "C-3": "wrong_test"}


def test_a_reply_that_misses_a_test_or_has_an_odd_verdict_is_retried_then_refused(context):
    short = json.dumps({"verdicts": [{"test": "C-2", "verdict": "code_bug", "reason": "x"}]})
    odd = json.dumps({"verdicts": [{"test": t, "verdict": "maybe"} for t in ("C-2", "C-3")]})

    result = ask(context, Said(short, odd))

    assert result.kind == "bad_reply" and result.attempts == 2


def test_a_reason_is_cut_to_200_characters(context):
    long = json.dumps({"verdicts": [{"test": t, "verdict": "code_bug", "reason": "r" * 900}
                                    for t in ("C-2", "C-3")]})

    result = ask(context, Said(long))

    assert len(result.value["C-2"][1]) == judge.REASON_LIMIT


def test_a_code_bug_is_a_must_fix_and_a_wrong_test_is_not():
    tests = LayerBResult(
        ran=True, tests=[o for _, o in FAILING] + [TestOutcome(name="test_c1_ok", result="pass")]
    )

    found = tester.check_code_tests(tests, ["C-3: the test is wrong"])

    assert [(f.cites, f.severity, f.check) for f in found] == [("C-2", "must_fix", 2)]
    assert tester.check_code_tests(None, []) == []
