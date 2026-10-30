import json

import pytest

from agents import da_rejected_reply_log
from agents.da_understand_agent import (
    FAILED_MESSAGE,
    ScriptedUnderstandClient,
    build_prompt,
    get_understand_client,
    interpret,
    parse_reply,
    strip_think_block,
)
from configs.da_config import ConfigError
from pydantic_classes.da_request_record_models import RequestRecord
from tests.da_stub_client import StubClient, stub_reply

QUESTION = "What needs to change, and why?"
ANSWER = "Let users upload Excel workbooks."


@pytest.fixture
def record():
    return RequestRecord(request_id="CVDA-2026-0001", rulebook_version=1)


@pytest.fixture
def charter(seed_rulebook):
    return seed_rulebook.charter


def run(client, record, charter, developer_text=ANSWER):
    return interpret(client, QUESTION, ANSWER, record, charter, 1, developer_text)


# --- the prompt ---


def test_prompt_holds_question_answer_record_and_charter(record, charter):
    prompt = build_prompt(QUESTION, ANSWER, record, charter, 1)

    assert QUESTION in prompt
    assert ANSWER in prompt
    assert '"request_id": "CVDA-2026-0001"' in prompt
    assert charter.purpose in prompt
    assert f"- {charter.glossary[0].term}: {charter.glossary[0].meaning}" in prompt
    assert "rulebook v1 charter" in prompt
    assert "{{" not in prompt


def test_prompt_leaves_out_rules_and_policy(record, seed_rulebook):
    prompt = build_prompt(QUESTION, ANSWER, record, seed_rulebook.charter, 1)

    assert seed_rulebook.rules[0].rule_id not in prompt
    assert seed_rulebook.charter.architecture_principles[0] not in prompt


def test_placeholder_typed_by_the_developer_is_not_filled(record, charter):
    prompt = build_prompt(QUESTION, "Please show {{purpose}}", record, charter, 1)

    assert "Please show {{purpose}}" in prompt


# --- good and bad replies ---


def test_good_reply_gives_the_updated_record(record, charter):
    client = StubClient(stub_reply({"title": "Add Excel uploads"}, hint="Next?"))

    result = run(client, record, charter)

    assert result.ok
    assert result.record.title == "Add Excel uploads"
    assert result.reply.hint == "Next?"
    assert (result.provider, result.model, result.attempts) == ("stub", "stub-model", 1)
    assert record.title == ""


def test_fenced_json_reply_is_accepted(record, charter):
    fenced = "```json\n" + json.dumps(stub_reply({"title": "Add Excel uploads"})) + "\n```"

    assert run(StubClient(fenced), record, charter).ok


def test_bad_reply_is_retried_once_with_a_note(record, charter):
    client = StubClient("not json at all", stub_reply({"title": "Add Excel uploads"}))

    result = run(client, record, charter)

    assert result.ok
    assert result.attempts == 2
    assert "Your previous reply was not accepted" in client.prompts[1]
    assert "The reply was not valid JSON" in client.prompts[1]
    assert "previous reply" not in client.prompts[0]


def test_two_bad_replies_give_the_plain_message(record, charter):
    client = StubClient(
        stub_reply({"colour": "blue"}), stub_reply({"objective": "def x():\n    pass"})
    )

    result = run(client, record, charter)

    assert not result.ok
    assert result.record is None
    assert result.message == FAILED_MESSAGE
    assert result.attempts == 2
    assert any("contains code" in problem for problem in result.problems)
    assert client.replies == []


def test_wrong_shape_is_reported(record):
    reply, problems = parse_reply(json.dumps({"updates": [], "extra": 1}), record, "")

    assert reply is None
    assert all(problem.startswith("The reply has the wrong shape") for problem in problems)


# --- the fake script ---


def test_fake_provider_uses_the_script(make_settings):
    client = get_understand_client(make_settings(), "question_1")

    reply = json.loads(client.complete("anything").text)

    assert reply["updates"]["title"] == "Add Excel document processing"


def test_script_reuses_a_repeated_step():
    client = ScriptedUnderstandClient("correction")

    assert client.complete("first").text == client.complete("second").text


def test_unknown_step_gives_an_empty_reply():
    reply = json.loads(ScriptedUnderstandClient("no_such_step").complete("x").text)

    assert reply == {"updates": {}, "ambiguities": [], "hint": ""}


@pytest.mark.parametrize(
    "step", ["opening", "question_1", "question_2", "question_3", "question_4", "optional"]
)
def test_every_script_entry_passes_the_checks(step, record):
    text = ScriptedUnderstandClient(step).complete("x").text

    reply, problems = parse_reply(text, record, "")

    assert reply is not None
    assert problems == []


def test_onprem_without_settings_names_the_missing_one(make_settings):
    with pytest.raises(ConfigError, match="DA_ONPREM_URL is missing"):
        get_understand_client(make_settings(llm_provider="onprem"), "question_1")


# --- reasoning block (spec P13 2.3) ---

GOOD = json.dumps(stub_reply({"title": "Add Excel uploads"}))


def test_reply_wrapped_in_a_think_block_is_accepted(record, charter):
    wrapped = f"<think>Let me\nthink {{about}} it.</think>\n\n{GOOD}"

    assert run(StubClient(wrapped), record, charter).ok


def test_think_tag_is_case_insensitive(record, charter):
    assert run(StubClient(f"<THINK>hmm</Think> {GOOD}"), record, charter).ok


def test_reply_with_only_a_closing_think_tag_is_accepted(record, charter):
    assert run(StubClient(f"I reasoned a lot.\n</think>\n{GOOD}"), record, charter).ok


def test_normal_reply_is_unchanged():
    assert strip_think_block(GOOD) == GOOD
    assert strip_think_block("no tags here") == "no tags here"


def test_rejected_log_keeps_the_raw_reply_with_the_think_block(
    record, charter, tmp_path, monkeypatch
):
    monkeypatch.setattr(da_rejected_reply_log, "LOG_FILE", tmp_path / "rejected.log")
    raw = "<think>secret thoughts</think> not json"

    run(StubClient(raw, raw), record, charter)

    assert "<think>secret thoughts</think>" in (tmp_path / "rejected.log").read_text("utf-8")
