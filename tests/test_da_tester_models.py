import pytest
from pydantic import ValidationError

from pydantic_classes import da_build_models
from pydantic_classes.da_tester_models import CHECK_NAMES, ReplyFinding, TesterReviewReply


def good(**changes):
    base = {
        "check": 4,
        "severity": "must_fix",
        "file": "src/agents/x.py",
        "line": 3,
        "quote": "x = 1",
        "cites": "DD-1",
        "message": "It ignores the decision.",
    }
    return {**base, **changes}


def test_an_empty_reply_is_valid():
    assert TesterReviewReply.model_validate({"findings": []}).findings == []


def test_a_good_finding_is_accepted():
    reply = TesterReviewReply.model_validate({"findings": [good()]})

    assert isinstance(reply.findings[0], ReplyFinding)


@pytest.mark.parametrize(
    "bad", [{"severity": "blocker"}, {"check": 3}, {"check": 7}, {"line": "abc"}, {"extra": 1}]
)
def test_a_severity_or_check_outside_the_lists_makes_the_reply_unusable(bad):
    with pytest.raises(ValidationError):
        TesterReviewReply.model_validate({"findings": [good(**bad)]})


def test_a_long_message_does_not_make_the_reply_unusable():
    """Too-long text drops one finding later (rule E5); it is not a schema problem."""
    reply = TesterReviewReply.model_validate({"findings": [good(message="x" * 900)]})

    assert len(reply.findings[0].message) == 900


def test_the_seven_checks_have_names():
    assert sorted(CHECK_NAMES) == [1, 2, 3, 4, 5, 6, 7]


def test_7_23_the_old_layer_c_warning_is_gone():
    assert not hasattr(da_build_models, "LAYER_C_WARNING")
    assert da_build_models.LABEL_READY == "Ready for your review"
    assert "Approved" not in da_build_models.LABEL_READY
