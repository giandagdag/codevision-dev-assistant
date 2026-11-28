"""Fix G9 step 2: the Understand prompt sees the whole rulebook; the rule check call (U1, U2)."""

import json

from agents import da_rule_check_agent as agent
from agents.da_llm_client import LLMClientError, LLMReply
from agents.da_rule_conflicts import LIST_CUT, rulebook_text
from agents.da_understand_agent import build_prompt as understand_prompt
from pydantic_classes.da_request_record_models import AcceptanceCriterion, RequestRecord


class Scripted:
    model = "fake"

    def __init__(self, text=None, error=None):
        self.text, self.error, self.prompts = text, error, []

    def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return LLMReply(text=self.text, provider="fake", model=self.model)


def _record() -> RequestRecord:
    criterion = AcceptanceCriterion(
        id="AC-2", kind="failure", given="No input is given", when="The tool runs",
        then="It prints NO INPUT PROVIDED",
    )  # fmt: skip
    return RequestRecord(
        request_id="CVDA-2026-0001", rulebook_version=1, acceptance_criteria=[criterion]
    )


def _reply(**conflict) -> str:
    item = {"criterion": "AC-2", "rule": "CV-PY-001", "why": "Not a plain sentence", "fix": "x"}
    return json.dumps({"conflicts": [item | conflict]})


def test_rulebook_text_holds_every_list_and_no_senior(seed_rulebook):
    text = rulebook_text(seed_rulebook)

    for heading in ("Constraints", "Architecture principles", "Judgement rules",
                    "Approved libraries", "Blocked imports", "Flag-for-review zones"):  # fmt: skip
        assert heading + ":" in text
    assert "CV-PY-001 Error messages are plain sentences" in text
    for capability in seed_rulebook.policy.capabilities:
        assert capability.named_senior not in text


def test_long_lists_are_cut_with_a_count(seed_rulebook):
    policy = seed_rulebook.policy.model_copy(
        update={"approved_libraries": [f"lib{n}" for n in range(LIST_CUT + 5)]}
    )

    text = rulebook_text(seed_rulebook.model_copy(update={"policy": policy}))

    assert "(and 5 more not shown)" in text
    assert f"lib{LIST_CUT}\n" not in text


def test_understand_prompt_now_carries_the_rules(seed_rulebook):
    prompt = understand_prompt(
        "q", "a", _record(), seed_rulebook.charter, 1, rules_text=rulebook_text(seed_rulebook)
    )

    assert "CV-PY-001" in prompt
    assert "{{" not in prompt


def test_rule_check_keeps_a_real_conflict(seed_rulebook):
    client = Scripted(_reply())

    result = agent.run_rule_check(None, _record(), seed_rulebook, client)

    assert result.ran
    assert [(c.criterion, c.rule) for c in result.conflicts] == [("AC-2", "CV-PY-001")]
    assert "NO INPUT PROVIDED" in client.prompts[0]
    assert len(client.prompts) == 1


def test_rule_check_drops_an_unknown_rule(seed_rulebook):
    client = Scripted(_reply(rule="CV-PY-999"))

    result = agent.run_rule_check(None, _record(), seed_rulebook, client)

    assert result.ran
    assert result.conflicts == []


def test_rule_check_reads_a_wrapped_reply(seed_rulebook):
    wrapped = "<think>hmm</think> Sure:\n```json\n" + _reply() + "\n```"

    result = agent.run_rule_check(None, _record(), seed_rulebook, Scripted(wrapped))

    assert len(result.conflicts) == 1


def test_a_failed_call_or_unreadable_reply_is_could_not_run(seed_rulebook):
    broken = Scripted(error=LLMClientError("down"))
    garbage = Scripted("no json here")

    assert agent.run_rule_check(None, _record(), seed_rulebook, broken).ran is False
    assert agent.run_rule_check(None, _record(), seed_rulebook, garbage).ran is False


def test_plain_and_ai_conflict_for_the_same_place_are_not_repeated(seed_rulebook):
    record = _record().model_copy(update={"title": "Use the socket module"})
    client = Scripted(_reply(criterion="SUMMARY", rule="LIB:socket"))

    result = agent.run_rule_check(None, record, seed_rulebook, client)

    assert [(c.criterion, c.rule) for c in result.conflicts] == [("SUMMARY", "LIB:socket")]


def test_the_fake_script_step_exists_and_finds_nothing(seed_rulebook):
    from agents.da_understand_agent import ScriptedUnderstandClient

    reply = ScriptedUnderstandClient(agent.STEP).complete("x")

    assert json.loads(reply.text) == {"conflicts": []}
