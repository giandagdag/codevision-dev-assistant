"""The pretend work LLM server (Phase 2C, spec 2.5). It runs on 127.0.0.1 only, started here."""

import json

import pytest
import requests

from agents import da_rejected_reply_log
from agents import da_understand_agent as agent
from agents.da_llm_client import LLMClientError, get_llm_client
from agents.da_understand_flow import QUESTIONS, get_understand_view
from tests.da_play import answer, start, to_confirmed
from web.da_fake_onprem_server import (
    HOST,
    NOT_JSON_REPLY,
    RETRY_MARKER,
    SCRIPT_STEPS,
    running_fake_onprem_server,
)


def settings_for(make_settings, server, **changes):
    values = {
        "llm_provider": "onprem",
        "onprem_url": server.url,
        "onprem_model": "fake-qwen",
        "onprem_timeout_seconds": 5,
    }
    values.update(changes)
    return make_settings(**values)


def post(server, body=None, headers=None, url=None):
    body = {"model": "m", "messages": [{"role": "user", "content": "hi"}]} if body is None else body
    return requests.post(url or server.url, json=body, headers=headers, timeout=5)


def test_it_listens_on_127_0_0_1_only():
    with running_fake_onprem_server() as server:
        assert server.server_address[0] == HOST == "127.0.0.1"
        assert server.url.startswith("http://127.0.0.1:")


def test_normal_mode_answers_in_the_chat_completions_shape():
    with running_fake_onprem_server() as server:
        body = {"model": "fake-qwen", "messages": [{"role": "user", "content": "x"}]}
        data = post(server, body).json()

    assert data["model"] == "fake-qwen"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"] == "OK"  # not an Understand prompt


def test_a_wrong_path_is_404_and_a_bad_body_is_400():
    with running_fake_onprem_server() as server:
        wrong_path = post(server, url=f"http://127.0.0.1:{server.server_port}/v1/other")
        no_messages = post(server, body={"model": "m"})
        not_json = requests.post(server.url, data="plain text", timeout=5)

    codes = (wrong_path.status_code, no_messages.status_code, not_json.status_code)
    assert codes == (404, 400, 400)


def test_error_mode_answers_500():
    with running_fake_onprem_server("error") as server:
        assert post(server).status_code == 500


def test_with_a_key_set_it_refuses_requests_without_the_matching_header():
    with running_fake_onprem_server(key="home-test-key") as server:
        none = post(server)
        wrong = post(server, headers={"Authorization": "Bearer other"})
        right = post(server, headers={"Authorization": "Bearer home-test-key"})

    assert (none.status_code, wrong.status_code, right.status_code) == (401, 401, 200)


def test_every_script_step_is_reached_by_its_own_prompt(seed_rulebook, make_settings):
    # The pretend server must give the same reply as the fake provider for every step.
    from agents.da_understand_agent import build_prompt
    from pydantic_classes.da_request_record_models import RequestRecord

    record = RequestRecord(request_id="CVDA-2026-0001", rulebook_version=1)
    script = json.loads(agent.FAKE_SCRIPT_FILE.read_text(encoding="utf-8"))
    with running_fake_onprem_server() as server:
        client = get_llm_client("generator", settings_for(make_settings, server))
        for question, step in SCRIPT_STEPS.items():
            prompt = build_prompt(question, "an answer", record, seed_rulebook.charter, 1)
            assert json.loads(client.complete(prompt).text) == script[step], step
    assert set(SCRIPT_STEPS.values()) == {k for k in script if k != "_about"}


def test_the_retry_marker_matches_the_engines_retry_note():
    assert RETRY_MARKER in agent._retry_note(["a problem"])


# --- through the real client and the real engine ---


def test_the_client_sends_what_the_spec_says_to_the_server(make_settings):
    with running_fake_onprem_server(key="home-test-key") as server:
        settings = settings_for(make_settings, server, onprem_api_key="home-test-key")
        client = get_llm_client("generator", settings)
        client.complete("ping", system="Reply with the single word OK.")
        seen = server.seen[0]

    assert seen["headers"]["Authorization"] == "Bearer home-test-key"
    assert seen["headers"]["Content-Type"] == "application/json"
    assert seen["body"]["messages"][0] == {
        "role": "system",
        "content": "Reply with the single word OK.",
    }


def test_wrong_key_gives_the_plain_401_message(make_settings, sleeps):
    with running_fake_onprem_server(key="home-test-key") as server:
        client = get_llm_client("generator", settings_for(make_settings, server))
        with pytest.raises(LLMClientError, match="HTTP 401.*DA_ONPREM_API_KEY"):
            client.complete("hi")
    assert sleeps == []


def test_error_mode_is_retried_then_gives_the_plain_message(make_settings, sleeps):
    with running_fake_onprem_server("error") as server:
        client = get_llm_client("generator", settings_for(make_settings, server))
        with pytest.raises(LLMClientError, match="HTTP 500.*tried 3 times"):
            client.complete("hi")
    assert sleeps == [2, 4]


def test_a_closed_port_gives_the_cannot_connect_message(make_settings, sleeps):
    with running_fake_onprem_server() as server:
        settings = settings_for(make_settings, server)
    # The server is stopped now, so nothing listens on that port.
    with pytest.raises(LLMClientError, match="Cannot connect.*tried 3 times"):
        get_llm_client("generator", settings).complete("hi")


def test_full_conversation_reaches_confirmed_for_discovery(
    make_settings, published_rulebook, monkeypatch
):
    with running_fake_onprem_server() as server:
        settings = settings_for(make_settings, server)
        view = to_confirmed(settings)

    assert view.request.status == "CONFIRMED_FOR_DISCOVERY"
    assert view.demo_mode is False
    assert not da_rejected_reply_log.LOG_FILE.exists()


def test_bad_json_mode_still_confirms_and_fills_the_rejected_reply_log(
    make_settings, published_rulebook
):
    with running_fake_onprem_server("bad-json") as server:
        settings = settings_for(make_settings, server)
        view = to_confirmed(settings)

    text = da_rejected_reply_log.LOG_FILE.read_text(encoding="utf-8")
    assert view.request.status == "CONFIRMED_FOR_DISCOVERY"
    assert NOT_JSON_REPLY in text
    assert "provider onprem" in text and "model fake-qwen" in text
    assert "attempt 1" in text and "attempt 2" not in text  # the engine's retry worked every time
    assert text.count("=== 20") == 5  # one per turn: the opening message and questions 1 to 4


def test_error_mode_shows_the_plain_message_in_the_chat(
    make_settings, published_rulebook, sleeps
):
    with running_fake_onprem_server("error") as server:
        settings = settings_for(make_settings, server)
        view = start(settings)  # the request is still created; question 1 has no hint
        after = answer(settings, view, "Users keep asking to upload Excel files")

    last = get_understand_view(settings, after.request.request_id).messages[-1].text
    assert "HTTP 500" in last and "tried 3 times" in last
    assert after.request.status == "CLARIFICATION_IN_PROGRESS"
    assert QUESTIONS[1] in after.messages[1].text  # question 1 was asked, without a hint
