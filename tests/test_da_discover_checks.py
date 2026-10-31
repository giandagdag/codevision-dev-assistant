import pytest
from pydantic import ValidationError

from agents.da_discover_checks import (
    describe_shape_problems,
    find_discovery_problems,
    hint_problem,
)
from pydantic_classes.da_discovery_models import DiscoveryReply, Finding

SENT = {1, 2, 3}


def finding(**changes):
    values = {
        "kind": "existing_capability",
        "title": "PDF processing exists",
        "explanation": "The PDF processor already extracts text from pages.",
        "hit_ids": [1],
        "confidence": "high",
    }
    return Finding(**(values | changes))


def reply(*findings, limitations=()):
    return DiscoveryReply(findings=list(findings), limitations=list(limitations))


def test_a_good_reply_has_no_problems():
    good = reply(finding(), finding(kind="affected_area", hit_ids=[]), limitations=["Only Python."])

    assert find_discovery_problems(good, SENT) == []


def test_invented_hit_id_is_a_plain_problem():
    problems = find_discovery_problems(reply(finding(hit_ids=[1, 9])), SENT)

    assert len(problems) == 1
    assert "Finding 1" in problems[0] and "9" in problems[0] and "not sent" in problems[0]


@pytest.mark.parametrize(
    "kind", ["existing_capability", "similar_implementation", "relevant_standard"]
)
def test_these_kinds_must_cite_a_hit(kind):
    problems = find_discovery_problems(reply(finding(kind=kind, hit_ids=[])), SENT)

    assert len(problems) == 1 and "at least one" in problems[0]


def test_affected_area_may_cite_nothing():
    assert find_discovery_problems(reply(finding(kind="affected_area", hit_ids=[])), SENT) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "```python"},
        {"explanation": "It does this:\ndef check(x):\n    return x"},
        {"explanation": "Use this\nimport os"},
    ],
)
def test_code_in_a_finding_is_refused(changes):
    problems = find_discovery_problems(reply(finding(**changes)), SENT)

    assert len(problems) == 1 and "code" in problems[0]


def test_code_in_a_limitation_is_refused():
    problems = find_discovery_problems(reply(limitations=["from os import path"]), SENT)

    assert len(problems) == 1 and "Limitation 1" in problems[0]


def test_nine_findings_is_a_shape_problem_in_plain_words():
    with pytest.raises(ValidationError) as caught:
        reply(*[finding() for _ in range(9)])

    lines = describe_shape_problems(caught.value)
    assert lines and lines[0].startswith("The reply has the wrong shape: findings")


def test_hint_that_is_fine():
    assert hint_problem("Look for the batching helper") is None


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_hint_is_refused(text):
    assert hint_problem(text)


def test_hint_with_a_secret_is_refused():
    assert "contains an API key" in hint_problem("use sk-abcdefghijklmnopqrstuvwxyz123456")


def test_hint_over_300_characters_is_refused():
    assert hint_problem("x" * 300) is None
    assert "300" in hint_problem("x" * 301)


def test_hint_with_code_is_refused():
    assert "Code cannot be used" in hint_problem("def check(x):\n    return x")
    assert "Code cannot be used" in hint_problem("```look here```")
