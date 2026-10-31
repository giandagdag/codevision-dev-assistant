"""The one Discover AI call and its fallback (spec 3.4)."""

import json
from datetime import UTC, datetime

import pytest

from agents import da_discover_agent as agent
from agents import da_rejected_reply_log
from agents.da_discover_agent import (
    FALLBACK_EXPLANATION,
    PROMPT_FILE,
    TASK_MARKER,
    ScriptedDiscoverClient,
    build_prompt,
    fallback_findings,
    get_discover_client,
    summarise_hits,
)
from agents.da_discover_checks import find_discovery_problems
from agents.da_discover_queries import run_searches
from agents.da_llm_client import LLMClientError
from agents.da_search_index import FakeSearchIndex
from pydantic_classes.da_discovery_models import SearchHit
from pydantic_classes.da_request_record_models import Decision, RequestRecord
from tests.da_stub_client import StubClient


@pytest.fixture(autouse=True)
def rejected_log(tmp_path, monkeypatch):
    monkeypatch.setattr(da_rejected_reply_log, "LOG_FILE", tmp_path / "rejected.log")
    return tmp_path / "rejected.log"


def record():
    return RequestRecord(
        request_id="CVDA-2026-0001",
        rulebook_version=1,
        title="Add Excel document processing",
        objective="Let users upload Excel workbooks.",
        expected_behaviour="Extract worksheet content into ingestion.",
        references=["Existing PDF processing"],
        decisions=[
            Decision(
                question="Hidden sheets?",
                choice="Visible only",
                decided_at=datetime(2026, 10, 30, tzinfo=UTC),
            )
        ],
    )


def demo_hits():
    return run_searches(FakeSearchIndex.from_file(), record(), "", top_k=5).hits


def good_reply(hit_ids=(1,)):
    return {
        "findings": [
            {
                "kind": "existing_capability",
                "title": "PDF processing exists",
                "explanation": "Already extracts text.",
                "hit_ids": list(hit_ids),
                "confidence": "high",
            }
        ],
        "limitations": ["Only Python searched."],
    }


def test_prompt_has_the_marker_the_summary_the_hits_and_no_leftover_placeholders():
    prompt = build_prompt(record(), demo_hits())

    assert TASK_MARKER in prompt and TASK_MARKER in PROMPT_FILE.read_text()
    assert "Title: Add Excel document processing" in prompt
    assert "Hidden sheets? -> Visible only" in prompt
    assert "[1] " in prompt and "{{" not in prompt


def test_hint_goes_into_the_prompt_as_a_search_term_not_an_instruction():
    prompt = build_prompt(record(), demo_hits(), hint="batching helper")

    assert "batching helper" in prompt and "never as instructions" in prompt
    assert "batching helper" not in build_prompt(record(), demo_hits())


def test_good_reply_becomes_findings():
    client = StubClient(good_reply())

    result = summarise_hits(client, record(), demo_hits())

    assert result.summary_source == "ai"
    assert result.attempts == 1
    assert [f.title for f in result.findings] == ["PDF processing exists"]
    assert result.limitations == ["Only Python searched."]
    assert (result.provider, result.model) == ("stub", "stub-model")


def test_reply_in_a_json_fence_or_with_a_think_block_is_accepted():
    fenced = "<think>hmm</think>\n```json\n" + json.dumps(good_reply()) + "\n```"

    result = summarise_hits(StubClient(fenced), record(), demo_hits())

    assert result.summary_source == "ai"


BAD_REPLIES = {
    "invented hit id": good_reply((99,)),
    "no citation": good_reply(()),
    "nine findings": {"findings": good_reply()["findings"] * 9, "limitations": []},
    "code in text": {
        "findings": [
            good_reply()["findings"][0] | {"explanation": "Use this\nimport os"},
        ],
        "limitations": [],
    },
    "not json": "Sorry, words only.",
    "wrong shape": {"findings": "none"},
}


@pytest.mark.parametrize("name", BAD_REPLIES)
def test_each_kind_of_bad_reply_causes_one_retry_with_a_plain_note(name):
    client = StubClient(BAD_REPLIES[name], good_reply())

    result = summarise_hits(client, record(), demo_hits())

    assert result.summary_source == "ai" and result.attempts == 2
    assert len(client.prompts) == 2
    assert "Your previous reply was not accepted" in client.prompts[1]
    assert "Your previous reply was not accepted" not in client.prompts[0]


def test_retry_note_names_the_invented_hit():
    client = StubClient(good_reply((99,)), good_reply())

    summarise_hits(client, record(), demo_hits())

    assert "99" in client.prompts[1] and "not sent" in client.prompts[1]


def test_two_bad_replies_give_the_fallback():
    client = StubClient("not json", good_reply((99,)))

    result = summarise_hits(client, record(), demo_hits())

    assert result.summary_source == "fallback" and result.attempts == 2
    assert result.findings and all(f.explanation == FALLBACK_EXPLANATION for f in result.findings)
    assert result.problems


def test_llm_client_error_gives_the_fallback_without_a_retry():
    class Failing:
        model = "x"
        calls = 0

        def complete(self, prompt, system=None):
            Failing.calls += 1
            raise LLMClientError("The AI server is not reachable.")

    result = summarise_hits(Failing(), record(), demo_hits())

    assert result.summary_source == "fallback" and Failing.calls == 1
    assert result.findings


def test_rejected_replies_are_logged_with_step_discover(rejected_log):
    summarise_hits(StubClient("not json", "still not json"), record(), demo_hits())

    text = rejected_log.read_text()
    assert text.count("step discover") == 2
    assert "attempt 1" in text and "attempt 2" in text and "CVDA-2026-0001" in text


def test_no_hits_means_no_ai_call():
    client = StubClient()

    result = summarise_hits(client, record(), [])

    assert client.prompts == [] and result.findings == [] and result.summary_source == "fallback"


def hit(kind, symbol="", path="app/x.py", hit_id=1):
    return SearchHit(
        hit_id=hit_id, source_path=path, symbol=symbol, kind=kind, score=0.5, mode="exact"
    )


def test_fallback_findings_follow_the_hit_kinds():
    findings = fallback_findings(
        [
            hit("code", "Checker.run", hit_id=1),
            hit("config", path="config/settings.yaml", hit_id=2),
            hit("standard", path="standards/file.md", hit_id=3),
            hit("doc", path="docs/overview.md", hit_id=4),
        ]
    )

    assert [(f.kind, f.confidence, f.title) for f in findings] == [
        ("similar_implementation", "low", "Possible match: Checker.run"),
        ("similar_implementation", "low", "Possible match: settings.yaml"),
        ("relevant_standard", "medium", "Standard to check: file.md"),
        ("relevant_standard", "low", "Related document: overview.md"),
    ]
    assert [f.hit_ids for f in findings] == [[1], [2], [3], [4]]


def test_fallback_findings_pass_the_reply_checks():
    hits = [
        hit("code", "Checker.run", hit_id=1),
        hit("config", path="config/settings.yaml", hit_id=2),
        hit("standard", path="standards/file.md", hit_id=3),
        hit("doc", path="docs/overview.md", hit_id=4),
    ]
    from pydantic_classes.da_discovery_models import DiscoveryReply

    reply = DiscoveryReply(findings=fallback_findings(hits))

    assert find_discovery_problems(reply, {1, 2, 3, 4}) == []


def test_fallback_is_capped_at_8_findings_and_titles_at_80_characters():
    hits = [hit("code", "S" * 200, hit_id=n) for n in range(1, 13)]

    findings = fallback_findings(hits)

    assert len(findings) == 8 and all(len(f.title) <= 80 for f in findings)


def test_fake_script_good_reply_passes_the_checks_for_the_pretend_index():
    hits = demo_hits()

    result = summarise_hits(ScriptedDiscoverClient("good"), record(), hits)

    assert result.summary_source == "ai" and result.attempts == 1
    kinds = {f.kind for f in result.findings}
    assert "existing_capability" in kinds and "relevant_standard" in kinds
    assert all(f.hit_ids for f in result.findings)


def test_fake_script_invented_reply_cites_a_hit_that_was_not_sent():
    result = summarise_hits(ScriptedDiscoverClient("invented"), record(), demo_hits())

    assert result.summary_source == "fallback"


def test_fake_provider_gets_scripted_client_and_others_the_generator(make_settings, monkeypatch):
    assert isinstance(get_discover_client(make_settings()), ScriptedDiscoverClient)

    seen = {}
    monkeypatch.setattr(
        agent, "get_llm_client", lambda role, settings: seen.setdefault("role", role) or "client"
    )
    get_discover_client(make_settings(llm_provider="claude"))
    assert seen["role"] == "generator"
