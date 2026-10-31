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
    # one per turn: the opening message, questions 1 to 4, and the decision after question 4
    assert text.count("=== 20") == 6


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


# --- Discover (Phase 3, spec 3.9) ---


def test_a_discover_prompt_gets_the_discover_reply_and_understand_replies_are_unchanged():
    from agents.da_discover_agent import TASK_MARKER
    from web.da_fake_onprem_server import reply_text

    discover_prompt = f"{TASK_MARKER}\n[4] app/x.py :: PdfProcessor.extract_text (code)\n    x"

    reply = json.loads(reply_text(discover_prompt, "normal"))

    assert reply["findings"][0]["hit_ids"] == [4]
    assert reply_text("hello", "normal") == "OK"


def test_discover_through_the_real_client_gives_ai_findings(make_settings, published_rulebook):
    from agents.da_discover_flow import start_discovery

    with running_fake_onprem_server() as server:
        settings = settings_for(make_settings, server)
        request_id = to_confirmed(settings).request.request_id
        view = start_discovery(settings, request_id, 0)

    assert view.result.summary_source == "ai" and view.result.model == "fake-qwen"
    assert view.request.status == "SIMILAR_IMPLEMENTATION_FOUND"


def test_bad_json_mode_is_bad_on_every_discover_try_so_the_fallback_shows(
    make_settings, published_rulebook
):
    from agents.da_discover_flow import start_discovery

    with running_fake_onprem_server("bad-json") as server:
        settings = settings_for(make_settings, server)
        request_id = to_confirmed(settings).request.request_id
        view = start_discovery(settings, request_id, 0)

    assert view.result.summary_source == "fallback" and view.result.findings
    assert view.request.status in ("SIMILAR_IMPLEMENTATION_FOUND", "NO_RELIABLE_MATCH")
    text = da_rejected_reply_log.LOG_FILE.read_text(encoding="utf-8")
    assert text.count("step discover") == 2


# --- Approach and the Tester (Phase 4, spec 11) ---


def _approach_settings(make_settings, server):
    return settings_for(make_settings, server)


def test_every_approach_and_tester_marker_gets_its_scripted_reply():
    from agents.da_approach_agent import TASK_MARKERS
    from agents.da_tester_agent import CASE_MARKER, PLAN_MARKER
    from web.da_fake_onprem_server import reply_text

    hits = "[1] app/ingestion/pdf_processor.py :: PdfProcessor.extract_text (code)\n"
    hits += "[2] app/ingestion/docx_processor.py :: DocxProcessor.extract_text (code)\n"

    for marker in TASK_MARKERS.values():
        reply = json.loads(reply_text(f"{marker}\n{hits}", "normal"))
        assert reply["files"][0]["reuses"] == [1]
        assert [d["hit_id"] for d in reply["reuse_decisions"]] == [1, 2]
    assert len(json.loads(reply_text(PLAN_MARKER, "normal"))["cases"]) == 9
    assert json.loads(reply_text(CASE_MARKER, "normal"))["case"]["criterion_id"] == "AC-4"
    assert reply_text(PLAN_MARKER, "bad-json") == NOT_JSON_REPLY
    assert reply_text(TASK_MARKERS["propose"], "bad-json") == NOT_JSON_REPLY


def _confirmed_discovery(settings):
    from agents.da_discover_flow import confirm_discovery, start_discovery

    request_id = to_confirmed(settings).request.request_id
    view = start_discovery(settings, request_id, 0)
    confirm_discovery(settings, request_id, view.revision)
    return request_id


def test_4_29_a_full_approach_against_the_pretend_server_reaches_ready_to_build(
    make_settings, published_rulebook
):
    from agents import da_approach_flow as flow

    with running_fake_onprem_server() as server:
        settings = _approach_settings(make_settings, server)
        request_id = _confirmed_discovery(settings)

        view = flow.start_approach(settings, request_id, 0)
        assert view.approach.source == "proposal" and view.step == "choices"
        cited = {n for f in view.approach.plan.files for n in f.reuses}
        assert cited <= {hit.hit_id for hit in view.discovery.hits} and cited
        view = flow.choose_design_option(settings, request_id, view.buttons[0][1], view.revision)
        view = flow.accept_approach(settings, request_id, view.revision)
        assert view.step == "tests" and len(view.plan.cases) == 9
        view = flow.request_case(settings, request_id, view.revision)
        view = flow.submit_text(settings, request_id, "Every visible sheet empty", view.revision)
        view = flow.keep_case(settings, request_id, view.revision)
        view = flow.accept_test_plan(settings, request_id, view.revision)
        seen = [item["body"]["messages"][-1]["content"] for item in server.seen]

    assert view.request.status == "READY_TO_BUILD"
    assert view.demo_mode is False
    assert not da_rejected_reply_log.LOG_FILE.exists()
    tester_prompts = [text for text in seen if "Task: write a test plan" in text]
    assert tester_prompts and "AC-7" in tester_prompts[0]
    assert "excel_processor" not in tester_prompts[0]


def test_bad_json_on_the_first_call_leaves_the_request_with_try_again(
    make_settings, published_rulebook
):
    from agents import da_approach_flow as flow

    with running_fake_onprem_server("bad-json") as server:
        settings = _approach_settings(make_settings, server)
        request_id = _confirmed_discovery(settings)
        view = flow.start_approach(settings, request_id, 0)

    assert view.request.status == "DISCOVERY_CONFIRMED"
    assert view.buttons == [("start", "Try again")]
    assert "attempt 2" in da_rejected_reply_log.LOG_FILE.read_text(encoding="utf-8")


def test_bad_json_from_the_tester_leaves_the_plan_to_be_written_again(
    make_settings, published_rulebook
):
    from agents import da_approach_flow as flow

    with running_fake_onprem_server() as good:
        settings = _approach_settings(make_settings, good)
        request_id = _confirmed_discovery(settings)
        view = flow.start_approach(settings, request_id, 0)
        view = flow.choose_design_option(settings, request_id, view.buttons[0][1], view.revision)
    with running_fake_onprem_server("bad-json") as bad:
        settings = _approach_settings(make_settings, bad)
        view = flow.accept_approach(settings, request_id, view.revision)

    assert view.step == "tests_pending" and view.plan is None
    assert view.buttons == [("write_plan", "Write the test plan")]
