import pytest

from agents.da_llm_client import LLMClientError, LLMReply
from agents.da_reply_reader import read_json_object
from agents.da_safety_check import (
    DECISION_GO,
    DECISION_P5,
    DECISION_STOP,
    SafetyVerdict,
    build_prompt,
    check_request,
    decide,
)
from agents.da_safety_gate import scan
from configs.da_config import load_settings


class _Client:
    def __init__(self, text=None, error=False):
        self.text, self.error = text, error

    def complete(self, prompt, system=None):
        if self.error:
            raise LLMClientError("down")
        return LLMReply(text=self.text, provider="fake", model="m")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('Sure! Here it is: {"a": 1} hope it helps', {"a": 1}),
        ('```json\n{"a": {"b": "}"}}\n```', {"a": {"b": "}"}}),
        ('<think>I should {think} first</think>{"a": 1}', {"a": 1}),
        ("thinking without a tag </think> {\"a\": 2}", {"a": 2}),
        ('{not json} then {"a": 3}', {"a": 3}),
        ("no json here", None),
        ('{"a": 1', None),
        ("", None),
    ],
)
def test_reader(text, expected):
    assert read_json_object(text) == expected


def _verdict(reply, **kwargs):
    return check_request(load_settings(), "text", _Client(reply, **kwargs))


def test_ai_verdicts_are_read_with_the_forgiving_reader():
    got = _verdict('Answer: {"verdict": "STOP", "reason": "revenge"}')
    assert got == SafetyVerdict("stop", "revenge")


@pytest.mark.parametrize("reply", ["no json", '{"verdict": "maybe"}', '{"x": 1}'])
def test_unreadable_reply_counts_as_failed(reply):
    assert _verdict(reply).ai_failed


def test_failed_call_counts_as_failed():
    assert _verdict(None, error=True).ai_failed


def test_request_text_is_put_in_the_prompt_once():
    prompt = build_prompt("drop {{request_text}} now")
    assert prompt.count("drop {{request_text}} now") == 1


OK = SafetyVerdict("ok")


@pytest.mark.parametrize(
    ("text", "verdict", "decision"),
    [
        ("add a report column", OK, DECISION_GO),
        ("add a report column", SafetyVerdict("stop", "x"), DECISION_STOP),
        ("report to get back at my manager", OK, DECISION_STOP),  # G5-2
        ("delete all database tables", OK, DECISION_P5),
        ("delete all database tables", SafetyVerdict("review"), DECISION_P5),
        ("delete all database tables", SafetyVerdict("ok", ai_failed=True), DECISION_P5),  # G5-4
        ("add a report column", SafetyVerdict("review"), DECISION_P5),
        ("delete all tables, I hate my boss", OK, DECISION_STOP),
    ],
)
def test_decide(text, verdict, decision):
    assert decide(scan(text), verdict) == decision
