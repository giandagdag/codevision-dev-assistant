"""The onprem client (Phase 2C, spec 2.1 and 2.2). No real network: requests.post is replaced."""

import logging
from types import SimpleNamespace

import pytest
import requests

from agents.da_llm_client import LLMClientError, OnPremLLMClient, get_llm_client
from configs.da_config import ConfigError

URL = "https://llm.example.com/v1/chat/completions"
KEY = "test-key-not-real-12345"


def onprem_settings(make_settings, **changes):
    values = {
        "llm_provider": "onprem",
        "onprem_url": URL,
        "onprem_model": "test-qwen",
    }
    values.update(changes)
    return make_settings(**values)


def answer(content="Hello team", model="server-model", status=200):
    """A pretend chat-completions answer."""
    payload = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    if model is not None:
        payload["model"] = model
    return reply_with(status, payload)


def reply_with(status, payload=None, text=""):
    def read_json():
        if payload is None:
            raise ValueError("not json")
        return payload

    return SimpleNamespace(status_code=status, text=text, json=read_json)


class FakePost:
    """Replaces requests.post. Gives the queued answers in order; an Exception is raised."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_client(make_settings, post, monkeypatch, **changes):
    monkeypatch.setattr(requests, "post", post)
    return get_llm_client("generator", onprem_settings(make_settings, **changes))


# --- the request (spec 2.1) ---


def test_body_with_a_system_message(make_settings, monkeypatch):
    post = FakePost(answer())
    client = make_client(make_settings, post, monkeypatch)

    client.complete("the question", system="be brief")

    call = post.calls[0]
    assert call["url"] == URL
    assert call["json"] == {
        "model": "test-qwen",
        "messages": [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "the question"},
        ],
        "temperature": 0.2,
        "top_p": 0.2,
    }


def test_default_body_has_no_max_tokens_or_stream(make_settings, monkeypatch):
    post = FakePost(answer())
    client = make_client(make_settings, post, monkeypatch)

    client.complete("hi")

    assert "max_tokens" not in post.calls[0]["json"]
    assert "stream" not in post.calls[0]["json"]


def test_max_tokens_setting_is_sent(make_settings, monkeypatch):
    post = FakePost(answer())
    client = make_client(make_settings, post, monkeypatch, onprem_max_tokens=1500)

    client.complete("hi")

    assert post.calls[0]["json"]["max_tokens"] == 1500


def test_body_without_a_system_message(make_settings, monkeypatch):
    post = FakePost(answer())
    client = make_client(make_settings, post, monkeypatch)

    client.complete("the question")

    assert post.calls[0]["json"]["messages"] == [{"role": "user", "content": "the question"}]


def test_headers_without_a_key_have_no_auth_header(make_settings, monkeypatch):
    post = FakePost(answer())
    client = make_client(make_settings, post, monkeypatch)

    client.complete("hi")

    assert post.calls[0]["headers"] == {"Content-Type": "application/json"}


def test_headers_with_a_key_use_the_default_bearer_header(make_settings, monkeypatch):
    post = FakePost(answer())
    client = make_client(make_settings, post, monkeypatch, onprem_api_key=KEY)

    client.complete("hi")

    assert post.calls[0]["headers"] == {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
    }


def test_custom_header_name_and_empty_prefix(make_settings, monkeypatch):
    post = FakePost(answer())
    client = make_client(
        make_settings,
        post,
        monkeypatch,
        onprem_api_key=KEY,
        onprem_auth_header="x-api-key",
        onprem_auth_prefix="",
    )

    client.complete("hi")

    assert post.calls[0]["headers"]["x-api-key"] == KEY
    assert "Authorization" not in post.calls[0]["headers"]


def test_timeout_and_verify_are_passed_on(make_settings, monkeypatch, tmp_path):
    cert = tmp_path / "bank-ca.pem"
    cert.write_text("made-up certificate", encoding="utf-8")
    post = FakePost(answer())
    client = make_client(
        make_settings, post, monkeypatch, onprem_timeout_seconds=45, onprem_verify=str(cert)
    )

    client.complete("hi")

    assert post.calls[0]["timeout"] == 45
    assert post.calls[0]["verify"] == str(cert)


def test_certificate_check_is_on_by_default(make_settings, monkeypatch):
    post = FakePost(answer())
    client = make_client(make_settings, post, monkeypatch)

    client.complete("hi")

    assert post.calls[0]["verify"] is True


# --- the reply ---


def test_reply_text_and_model_are_read_from_the_answer(make_settings, monkeypatch):
    post = FakePost(answer("Hi there", model="server-model"))
    client = make_client(make_settings, post, monkeypatch)

    reply = client.complete("hi")

    assert (reply.text, reply.model, reply.provider) == ("Hi there", "server-model", "onprem")


def test_model_falls_back_to_the_setting(make_settings, monkeypatch):
    client = make_client(make_settings, FakePost(answer(model=None)), monkeypatch)

    assert client.complete("hi").model == "test-qwen"


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "no choices here"},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": "oops"},
        ["not", "a", "dict"],
    ],
)
def test_wrong_shape_gives_a_plain_message(make_settings, monkeypatch, payload):
    client = make_client(make_settings, FakePost(reply_with(200, payload)), monkeypatch)

    with pytest.raises(LLMClientError, match=r"choices\[0\]\.message\.content"):
        client.complete("hi")


def test_reply_that_is_not_json_gives_a_plain_message(make_settings, monkeypatch):
    client = make_client(make_settings, FakePost(reply_with(200, None, "<html>")), monkeypatch)

    with pytest.raises(LLMClientError, match="expected chat-completions shape"):
        client.complete("hi")


# --- retries (spec 2.1) ---


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (requests.exceptions.ConnectionError("boom"), "Cannot connect.*DA_ONPREM_URL"),
        (requests.exceptions.ReadTimeout("boom"), "within 120 seconds.*timed out"),
        (requests.exceptions.ConnectTimeout("boom"), "within 120 seconds.*timed out"),
        (reply_with(429, None, "slow down"), "HTTP 429: slow down"),
        (reply_with(500, None, "server broke"), "HTTP 500: server broke"),
        (reply_with(503, None, "away"), "HTTP 503: away"),
        (reply_with(407, None, "proxy"), "proxy asked for sign-in \\(HTTP 407\\).*proxy settings"),
    ],
)
def test_these_failures_are_tried_three_times_in_total(
    make_settings, monkeypatch, sleeps, failure, message
):
    post = FakePost(failure)
    client = make_client(make_settings, post, monkeypatch)

    with pytest.raises(LLMClientError, match=message) as error:
        client.complete("hi")

    assert len(post.calls) == 3
    assert sleeps == [2, 4]
    assert "tried 3 times" in str(error.value)


def test_a_later_try_can_succeed(make_settings, monkeypatch, sleeps):
    post = FakePost(requests.exceptions.ConnectionError("boom"), reply_with(500), answer("Second"))
    client = make_client(make_settings, post, monkeypatch)

    assert client.complete("hi").text == "Second"
    assert len(post.calls) == 3 and sleeps == [2, 4]


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "HTTP 401.*DA_ONPREM_API_KEY"),
        (403, "HTTP 403.*DA_ONPREM_API_KEY"),
        (404, "HTTP 404.*path at the end of DA_ONPREM_URL"),
        (400, "refused the request as too large \\(HTTP 400\\)"),
        (422, "HTTP 422: bad request"),
    ],
)
def test_these_answers_are_not_retried(make_settings, monkeypatch, sleeps, status, message):
    post = FakePost(reply_with(status, None, "bad request"))
    client = make_client(make_settings, post, monkeypatch)

    with pytest.raises(LLMClientError, match=message):
        client.complete("hi")

    assert len(post.calls) == 1
    assert sleeps == []


def test_a_certificate_problem_is_not_retried(make_settings, monkeypatch, sleeps):
    post = FakePost(requests.exceptions.SSLError("bad certificate"))
    client = make_client(make_settings, post, monkeypatch)

    with pytest.raises(LLMClientError, match="certificate check failed.*DA_ONPREM_VERIFY"):
        client.complete("hi")

    assert len(post.calls) == 1


def test_an_invalid_address_is_not_retried(make_settings, monkeypatch, sleeps):
    post = FakePost(requests.exceptions.MissingSchema("no scheme"))
    client = make_client(make_settings, post, monkeypatch)

    with pytest.raises(LLMClientError, match="full address starting with http"):
        client.complete("hi")

    assert len(post.calls) == 1


def test_other_status_message_is_cut_at_300_characters(make_settings, monkeypatch):
    client = make_client(make_settings, FakePost(reply_with(418, None, "x" * 1000)), monkeypatch)

    with pytest.raises(LLMClientError) as error:
        client.complete("hi")

    assert str(error.value) == "The AI server answered HTTP 418: " + "x" * 300


# --- the key never shows (rule R1) ---


def test_key_never_appears_in_messages_or_logs(make_settings, monkeypatch, sleeps, caplog):
    # A server that wrongly echoes the key back in its error text.
    echoing = reply_with(500, None, f"bad request, your key {KEY} was seen")
    failures = [
        requests.exceptions.ConnectionError(KEY),
        requests.exceptions.ReadTimeout(KEY),
        requests.exceptions.SSLError(KEY),
        requests.exceptions.MissingSchema(KEY),
        echoing,
        reply_with(401, None, KEY),
        reply_with(404, None, KEY),
        reply_with(418, None, f"x{KEY}"),
        reply_with(200, {"echo": KEY}),
    ]
    caplog.set_level(logging.DEBUG)
    for failure in failures:
        client = make_client(make_settings, FakePost(failure), monkeypatch, onprem_api_key=KEY)
        with pytest.raises(LLMClientError) as error:
            client.complete("hi")
        assert KEY not in str(error.value)

    assert KEY not in caplog.text


def test_key_is_not_in_the_client_printout_or_startup_log(make_settings, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    client = make_client(make_settings, FakePost(answer()), monkeypatch, onprem_api_key=KEY)

    client.complete("hi")

    assert KEY not in caplog.text
    assert "Using onprem provider, model test-qwen, for role generator" in caplog.text


# --- setting up the client (spec 2.2) ---


@pytest.mark.parametrize(
    ("missing", "name"), [("onprem_url", "DA_ONPREM_URL"), ("onprem_model", "DA_ONPREM_MODEL")]
)
def test_missing_url_or_model_names_the_setting(make_settings, missing, name):
    with pytest.raises(ConfigError, match=f"{name} is missing"):
        get_llm_client("generator", onprem_settings(make_settings, **{missing: ""}))


def test_both_roles_use_the_same_model(make_settings):
    settings = onprem_settings(make_settings)

    assert get_llm_client("generator", settings).model == "test-qwen"
    assert get_llm_client("reviewer", settings).model == "test-qwen"


def test_verify_false_logs_a_warning_every_time_a_client_is_made(make_settings, caplog):
    settings = onprem_settings(make_settings, onprem_verify=False)

    get_llm_client("generator", settings)
    get_llm_client("reviewer", settings)

    warnings_seen = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert [r.getMessage() for r in warnings_seen] == [
        "Certificate check is OFF. Use only for the prototype."
    ] * 2


def test_verify_on_logs_no_warning(make_settings, caplog):
    get_llm_client("generator", onprem_settings(make_settings))

    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_missing_certificate_file_names_the_path(make_settings, tmp_path):
    missing = str(tmp_path / "no-such-ca.pem")

    with pytest.raises(ConfigError, match="no-such-ca.pem.*does not exist"):
        get_llm_client("generator", onprem_settings(make_settings, onprem_verify=missing))


def test_existing_certificate_file_is_accepted(make_settings, tmp_path):
    cert = tmp_path / "bank-ca.pem"
    cert.write_text("made-up certificate", encoding="utf-8")

    client = get_llm_client("generator", onprem_settings(make_settings, onprem_verify=str(cert)))

    assert isinstance(client, OnPremLLMClient)


def test_tester_uses_its_own_onprem_model_when_set(make_settings):
    settings = onprem_settings(make_settings, onprem_tester_model="test-llama")

    assert get_llm_client("tester", settings).model == "test-llama"
    assert get_llm_client("generator", settings).model == "test-qwen"


def test_tester_with_no_onprem_model_uses_the_generator_model(make_settings):
    assert get_llm_client("tester", onprem_settings(make_settings)).model == "test-qwen"
