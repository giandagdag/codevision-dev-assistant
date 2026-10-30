import pytest
from pydantic import ValidationError

from pydantic_classes.da_discovery_models import (
    DiscoveryReply,
    Finding,
    SearchHit,
)


def hit(**changes):
    values = {"source_path": "app/upload.py", "kind": "code", "score": 0.5, "mode": "exact"}
    return SearchHit(**(values | changes))


def finding(**changes):
    values = {
        "kind": "existing_capability",
        "title": "Upload check",
        "explanation": "Already checks file types.",
        "hit_ids": [1],
        "confidence": "high",
    }
    return Finding(**(values | changes))


def test_snippet_of_500_characters_is_kept_and_501_is_refused():
    assert len(hit(snippet="x" * 500).snippet) == 500
    with pytest.raises(ValidationError):
        hit(snippet="x" * 501)


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_score_must_be_between_0_and_1(score):
    with pytest.raises(ValidationError):
        hit(score=score)


def test_hit_kind_and_mode_values_are_limited():
    with pytest.raises(ValidationError):
        hit(kind="binary")
    with pytest.raises(ValidationError):
        hit(mode="fuzzy")


def test_finding_kind_and_confidence_values_are_limited():
    with pytest.raises(ValidationError):
        finding(kind="guess")
    with pytest.raises(ValidationError):
        finding(confidence="certain")


def test_finding_text_limits():
    assert finding(title="t" * 80, explanation="e" * 300)
    with pytest.raises(ValidationError):
        finding(title="t" * 81)
    with pytest.raises(ValidationError):
        finding(explanation="e" * 301)


def test_reply_allows_8_findings_but_not_9():
    DiscoveryReply(findings=[finding() for _ in range(8)])
    with pytest.raises(ValidationError):
        DiscoveryReply(findings=[finding() for _ in range(9)])


def test_reply_limitation_limits():
    DiscoveryReply(limitations=["l" * 300] * 4)
    with pytest.raises(ValidationError):
        DiscoveryReply(limitations=["l" * 301])
    with pytest.raises(ValidationError):
        DiscoveryReply(limitations=["ok"] * 5)


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        DiscoveryReply.model_validate({"findings": [], "extra": 1})
