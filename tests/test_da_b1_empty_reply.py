"""Fix batch B1 step 7 (F8, B1-9): an AI reply with no text is logged and named, never silent."""

import logging

import pytest

from agents.da_llm_client import EMPTY_REPLY_LOG_LIMIT, LLMClientError
from tests.test_da_llm_client_onprem import KEY, FakePost, make_client, reply_with


def _empty(finish_reason, message=None, text=""):
    choice = {"message": {"content": None, **(message or {})}, "finish_reason": finish_reason}
    payload = {
        "model": "test-qwen-x",
        "choices": [choice],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33},
    }
    return reply_with(200, payload, text=text)


def test_b1_9_length_limit_is_logged_and_named(make_settings, monkeypatch, caplog):
    body = f"{KEY} " + "x" * 5000
    client = make_client(make_settings, FakePost(_empty("length", text=body)), monkeypatch,
                         onprem_api_key=KEY)

    with caplog.at_level(logging.WARNING), pytest.raises(LLMClientError) as error:
        client.complete("hi")

    assert "length limit" in str(error.value)
    line = next(r.getMessage() for r in caplog.records if "no text" in r.getMessage())
    assert "test-qwen-x" in line and "finish_reason=length" in line
    for counts in ("prompt_tokens=11", "completion_tokens=22", "total_tokens=33"):
        assert counts in line
    assert KEY not in line
    assert len(line.split("body=", 1)[1]) <= EMPTY_REPLY_LOG_LIMIT


def test_b1_9_a_thinking_only_reply_is_named(make_settings, monkeypatch):
    reply = _empty("stop", {"reasoning_content": "let me think"})
    client = make_client(make_settings, FakePost(reply), monkeypatch)

    with pytest.raises(LLMClientError, match="only its thinking"):
        client.complete("hi")


def test_b1_9_an_empty_string_is_also_refused(make_settings, monkeypatch):
    reply = _empty("stop", {"content": ""})
    client = make_client(make_settings, FakePost(reply), monkeypatch)

    with pytest.raises(LLMClientError, match="reason 'stop'"):
        client.complete("hi")
