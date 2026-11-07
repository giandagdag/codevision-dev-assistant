"""The AI call of Layer C: retries, unusable replies, the size split, and the scripted reply
(Phase 7 tests 7-10, 7-24, 7-25, 7-26, 7-29, 7-30, 7-34)."""

import json
import pathlib

import pytest

from agents import da_build_agent as build_agent
from agents import da_tester_review as review
from agents import da_tester_review_agent as agent
from agents.da_llm_client import ContextTooLargeError, LLMClientError, LLMReply, get_llm_client
from tests.da_build_play import CREATE, MODIFY, make_context
from tests.test_da_fake_onprem_server import settings_for
from tests.test_da_tester_review import make_input
from web.da_fake_onprem_server import running_fake_onprem_server

REQUEST_ID = "CVDA-2026-0001"


class Sequence:
    """A client that answers from a list; an exception in the list is raised."""

    model = "seq-model"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return LLMReply(text=answer, provider="fake", model="seq-model")


GOOD = json.dumps({"findings": []})
JUNK = "no json here"


def finding_json(path=CREATE, line=1, quote="def read_sheets(book):"):
    item = {
        "check": 5,
        "severity": "fyi",
        "file": path,
        "line": line,
        "quote": quote,
        "cites": f"PLAN:{path}",
        "message": "Fine.",
    }
    return json.dumps({"findings": [item]})


@pytest.fixture
def data(seed_rulebook):
    return make_input(seed_rulebook)


def test_a_good_reply_is_one_call_and_one_attempt(data):
    client = Sequence(finding_json())

    outcome = agent.review_code(client, data, REQUEST_ID)

    assert outcome.ok and (outcome.calls, outcome.attempts) == (1, 1)
    assert len(outcome.findings) == 1 and outcome.model == "seq-model"
    assert outcome.prompt_chars == len(client.prompts[0])


def test_7_10_an_unusable_reply_then_a_valid_one_uses_the_valid_one(data):
    client = Sequence(JUNK, finding_json())

    outcome = agent.review_code(client, data, REQUEST_ID)

    assert outcome.ok and outcome.attempts == 2 and len(outcome.findings) == 1
    assert "not accepted" in client.prompts[1] and "not valid JSON" in client.prompts[1]


def test_7_11_an_unusable_reply_twice_means_unable(data):
    client = Sequence(JUNK)

    outcome = agent.review_code(client, data, REQUEST_ID)

    assert outcome.kind == "unable" and outcome.attempts == 2 and outcome.findings == []


@pytest.mark.parametrize("bad", [{"severity": "blocker"}, {"check": 9}, {"line": "x"}])
def test_a_severity_or_check_outside_the_lists_is_unusable(data, bad):
    item = json.loads(finding_json())["findings"][0] | bad

    outcome = agent.review_code(Sequence(json.dumps({"findings": [item]})), data, REQUEST_ID)

    assert outcome.kind == "unable"


def test_7_26_no_answer_is_unreachable_and_not_unable(data):
    outcome = agent.review_code(Sequence(LLMClientError("did not answer")), data, REQUEST_ID)

    assert outcome.kind == "unreachable" and "did not answer" in outcome.message


# --- the size guard ---


def split_limit(data):
    """A limit that one file fits in but the whole prompt does not."""
    per_file = max(len(review.build_review_prompt(data, only_file=p)) for p in data.planned_paths)
    return per_file + 5


def smaller(data, limit):
    policy = data.policy.model_copy(update={"tester_max_prompt_chars": limit})
    return review.ReviewInput(**{**data.__dict__, "policy": policy})


def test_7_24_a_prompt_over_the_limit_is_split_into_one_call_per_file(data):
    data = smaller(data, split_limit(data))
    client = Sequence(finding_json())

    outcome = agent.review_code(client, data, REQUEST_ID)

    assert outcome.ok and outcome.calls == 2
    assert len(client.prompts) == 2
    assert f"### {CREATE}" in client.prompts[0] and f"### {MODIFY}" not in client.prompts[0]
    assert f"### {MODIFY}" in client.prompts[1] and f"### {CREATE}" not in client.prompts[1]
    assert len(outcome.findings) == 2  # merged from both calls


def test_7_24_an_http_400_on_the_whole_prompt_also_splits(data):
    client = Sequence(ContextTooLargeError("too much"), GOOD)

    outcome = agent.review_code(client, data, REQUEST_ID)

    assert outcome.ok and outcome.calls == 2 and outcome.findings == []
    assert f"### {MODIFY}" in client.prompts[0] and f"### {CREATE}" in client.prompts[0]


def test_7_25_a_file_that_is_still_too_big_pauses(data):
    data = smaller(data, 1000)

    outcome = agent.review_code(Sequence(GOOD), data, REQUEST_ID)

    assert outcome.kind == "too_big" and outcome.message == review.TOO_BIG_FOR_TESTER


def test_7_25_an_http_400_on_a_single_file_pauses(data):
    client = Sequence(ContextTooLargeError("too much"))

    outcome = agent.review_code(client, data, REQUEST_ID)

    assert outcome.kind == "too_big"


def test_an_unusable_reply_on_one_file_of_a_split_review_means_unable(data):
    data = smaller(data, split_limit(data))

    outcome = agent.review_code(Sequence(GOOD, JUNK), data, REQUEST_ID)

    assert outcome.kind == "unable"


# --- the scripted reply ---


def scripted(data, number, *switches):
    prompt = review.build_review_prompt(
        review.ReviewInput(**{**data.__dict__, "round": number})
    )
    return json.loads(agent.scripted_review_reply(prompt, frozenset(switches)))["findings"]


def kept_after_rules(data, items, seed_rulebook):
    from pydantic_classes.da_tester_models import ReplyFinding

    return review.split_findings(
        [ReplyFinding(**item) for item in items],
        data.code,
        data.approach,
        data.record,
        seed_rulebook.rules,
        data.planned_paths,
        2,
    )


def test_round_one_finds_nothing_and_round_two_gives_one_must_fix(data, seed_rulebook):
    assert scripted(data, 1) == []
    items = scripted(data, 2)

    result = kept_after_rules(data, items, seed_rulebook)

    assert [(f.severity, f.kept) for f in result] == [("must_fix", True)]
    assert result[0].file.endswith("excel_processor.py")


def test_round_three_gives_should_fix_and_fyi_with_evidence_and_one_dropped(data, seed_rulebook):
    result = kept_after_rules(data, scripted(data, 3), seed_rulebook)

    assert [(f.severity, f.kept) for f in result] == [
        ("should_fix", True),
        ("fyi", True),
        ("must_fix", False),
    ]
    assert "not found" in result[2].reject_reason


def test_the_test_only_switches(data, seed_rulebook):
    assert scripted(data, 3, "review_empty") == []
    assert scripted(data, 1, "review_must_fix_always")[0]["severity"] == "must_fix"
    assert agent.scripted_review_reply("x", frozenset({"review_unusable"})).startswith("Sorry")


def test_the_fake_build_client_answers_a_review_prompt(data):
    prompt = review.build_review_prompt(data)

    reply = build_agent.scripted_build_reply(prompt, frozenset())

    assert "findings" in json.loads(reply)


# --- the pretend work server (7-29) ---


@pytest.mark.parametrize(
    ("tester_model", "expected"), [("tester-llama", "tester-llama"), ("", "fake-qwen")]
)
def test_7_29_the_tester_model_or_the_generators_is_called_and_saved(
    make_settings, data, tester_model, expected
):
    with running_fake_onprem_server() as server:
        settings = settings_for(make_settings, server, onprem_tester_model=tester_model)
        client = get_llm_client("tester", settings)

        outcome = agent.review_code(client, data, REQUEST_ID)
        seen = [item["body"]["model"] for item in server.seen]

    assert outcome.ok and outcome.model == expected and seen == [expected]


# --- 7-30 and 7-34 ---


def test_7_30_no_tester_model_name_is_hard_coded_in_the_new_files():
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    names = ("claude-", "qwen", "llama", "maverick", "gpt-")
    for file in ("agents/da_tester_review.py", "agents/da_tester_review_agent.py",
                 "agents/da_tester_flow.py", "data/da_tester_review_prompt.md"):  # fmt: skip
        path = root / file
        if path.exists():
            text = path.read_text(encoding="utf-8").lower()
            assert not any(name in text for name in names), file


def test_7_34_the_test_writing_prompt_still_holds_no_code(seed_rulebook):
    from pydantic_classes.da_build_models import Contract

    context = make_context(seed_rulebook)
    contract = Contract.model_validate(
        {"files": [{"path": CREATE, "items": [{"name": "read_sheets", "kind": "function",
                                               "args": ["book"], "summary": "Reads sheets."}]}]}
    )  # fmt: skip

    prompt = build_agent.build_tests_prompt(context, contract)

    assert "def " not in prompt.split("## How to reply")[0]
    assert "return True" not in prompt and "```" not in prompt.split("## How to reply")[0]
