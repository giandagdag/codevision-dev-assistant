"""The Build's AI calls: prompts, the fake provider, retries and the kinds of failure."""

import inspect
import json

import pytest

from agents import da_build_agent as agent
from agents.da_build_checks import (
    TOO_BIG_MESSAGE,
    find_contract_problems,
    find_test_file_problems,
)
from agents.da_llm_client import ContextTooLargeError, LLMClientError
from pydantic_classes.da_build_models import Contract
from tests.da_build_play import CREATE, MODIFY, ORIGINAL, make_context
from tests.da_stub_client import StubClient

PLANNED = [CREATE, MODIFY]


@pytest.fixture
def context(seed_rulebook):
    return make_context(seed_rulebook)


@pytest.fixture
def fake_contract():
    return Contract.model_validate(
        json.loads(agent.scripted_build_reply(f"{agent.CONTRACT_MARKER}\n"))
    )


@pytest.fixture
def fake_client(make_settings):
    return agent.get_build_client(make_settings(llm_provider="fake"), "generator")


class Failing:
    model = "x"

    def __init__(self, error):
        self.error, self.calls = error, 0

    def complete(self, prompt, system=None):
        self.calls += 1
        raise self.error


# --- the prompts ---


def test_the_contract_prompt_carries_the_rules_the_approach_and_current_files(context):
    prompt = agent.build_contract_prompt(context, {MODIFY: ORIGINAL})

    assert agent.CONTRACT_MARKER in prompt
    assert context.charter.purpose in prompt
    assert "Add Excel upload" in prompt  # the record
    assert f"- {CREATE} (create): Read sheets" in prompt
    assert f"### {MODIFY}\n{ORIGINAL}" in prompt
    assert "{{" not in prompt


def test_the_tester_prompt_takes_no_code_at_all(context, fake_contract):
    """Test 6-5, second half: the Tester never sees code (spec section 3)."""
    parameters = list(inspect.signature(agent.build_tests_prompt).parameters)
    prompt = agent.build_tests_prompt(context, fake_contract)

    assert parameters == ["context", "contract"]  # there is nowhere to pass a file's text
    assert agent.TESTS_MARKER in prompt
    for case in context.cases:
        assert f"- {case.test_id} ({case.criterion_id}): given {case.given}" in prompt
    assert f"- {MODIFY}: function validate(path)" in prompt  # names and arguments, no bodies
    assert "return True" not in prompt and "```" not in prompt


def test_the_code_prompt_sends_this_file_in_full_and_the_others_as_contract_lines(
    context, fake_contract
):
    prompt = agent.build_code_prompt(
        context, fake_contract, MODIFY, "modify", 1, "FROZEN TEST TEXT", ORIGINAL
    )

    own = prompt.split("This file:")[1].split("The other planned files")[0]
    other = prompt.split("The other planned files")[1].split("## The frozen tests")[0]
    assert "validate(path)" in own and "read_sheets" not in own
    assert "read_sheets(workbook)" in other and "validate" not in other
    assert "FROZEN TEST TEXT" in prompt and ORIGINAL in prompt
    assert agent.FAILURE_HEADING not in prompt
    assert "edit blocks" in prompt and "<<<<<<< FIND" in prompt
    assert "File: " + MODIFY in prompt and "Round: 1" in prompt
    assert "approved" not in prompt.lower().split("allowed third-party libraries:")[0]
    assert "requests" in prompt.split("Never import:")[1].split("\n")[0]


def test_a_fix_prompt_adds_the_failure_report_and_a_new_file_gets_the_whole_file_rule(
    context, fake_contract
):
    prompt = agent.build_code_prompt(
        context, fake_contract, CREATE, "create", 2, "TESTS", "old text", "T-2 failed"
    )

    assert f"{agent.FAILURE_HEADING}\n\nT-2 failed" in prompt
    assert "Do not change the tests" in prompt
    assert "complete new file" in prompt and "edit blocks" not in prompt
    assert "(new file)" not in prompt  # round 2 shows the build's own current text
    first = agent.build_code_prompt(context, fake_contract, CREATE, "create", 1, "T", "")
    assert "(new file)" in first


# --- the fake provider ---


def test_the_fake_contract_covers_every_planned_file(fake_client, context):
    result = agent.write_contract(fake_client, context, {MODIFY: ORIGINAL})

    assert result.ok and result.model == "fake-build-script"
    assert [entry.path for entry in result.value.files] == PLANNED
    assert find_contract_problems(result.value, PLANNED, {MODIFY: ORIGINAL}) == []


def test_the_fake_tests_have_one_checked_method_per_accepted_case(
    fake_client, context, fake_contract
):
    """Test 6-5: one method per case, named with the case and criterion IDs."""
    result = agent.write_tests(fake_client, context, fake_contract)

    assert result.ok and result.attempts == 1
    assert find_test_file_problems(result.value, context.cases, fake_contract, context.policy) == []
    assert "def test_t1_ac1_" in result.value and "def test_t9_ac3_" in result.value
    assert result.value.count("    def test_") == 9


def test_developer_added_cases_get_a_method_too(fake_client, seed_rulebook, fake_contract):
    from tests.da_build_play import make_cases

    context = make_context(seed_rulebook, cases=4)
    context = type(context)(
        charter=context.charter,
        record=context.record,
        approach=context.approach,
        cases=make_cases(4, developer=(4,)),
        policy=context.policy,
    )

    assert agent.write_tests(fake_client, context, fake_contract).value.count("    def test_") == 4


def test_a_test_file_missing_a_case_twice_gives_up(
    fake_client, context, fake_contract, monkeypatch
):
    """Test 6-6, first half: the Tester is asked twice and the second prompt lists the problem."""
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"bad_tests"}))
    prompts = []
    real = fake_client.complete
    fake_client.complete = lambda prompt, system=None: (prompts.append(prompt), real(prompt))[1]

    result = agent.write_tests(fake_client, context, fake_contract)

    assert not result.ok and result.kind == "bad_reply" and result.attempts == 2
    assert any("Case T-9 (AC-3) needs exactly one test method" in p for p in result.problems)
    assert "Your previous reply was not accepted" in prompts[1]


def test_the_fake_code_for_a_new_file_is_the_whole_text_and_for_an_old_file_edit_blocks(
    fake_client, context, fake_contract
):
    new = agent.write_code(
        fake_client,
        context,
        agent.build_code_prompt(context, fake_contract, CREATE, "create", 1, "T", ""),
        "create",
    )
    old = agent.write_code(
        fake_client,
        context,
        agent.build_code_prompt(context, fake_contract, MODIFY, "modify", 1, "T", ORIGINAL),
        "modify",
    )

    assert new.value.text.startswith('"""Read the sheets') and new.value.edits is None
    assert old.value.text is None and old.value.edits[0].find == "return True"


def test_the_fix_round_repairs_the_buggy_file_unless_always_fail_is_set(
    fake_client, context, fake_contract, monkeypatch
):
    def code_for(round_number, failures):
        prompt = agent.build_code_prompt(
            context, fake_contract, CREATE, "create", round_number, "T", "x", failures
        )
        return agent.write_code(fake_client, context, prompt, "create").value.text

    first = code_for(1, "")
    fixed = code_for(2, "T-2 failed")
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"always_fail"}))
    stuck = code_for(2, "T-2 failed")

    assert 'not sheet.get("hidden")' in fixed and "hidden" not in first
    assert stuck == first


def test_the_bad_edit_switch_makes_a_block_that_matches_nothing(
    fake_client, context, fake_contract, monkeypatch
):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"bad_edit"}))
    prompt = agent.build_code_prompt(context, fake_contract, MODIFY, "modify", 1, "T", ORIGINAL)

    edits = agent.write_code(fake_client, context, prompt, "modify").value.edits

    assert edits[0].find == "this text is not in the file"


def test_the_fake_client_refuses_a_prompt_it_does_not_know(fake_client):
    with pytest.raises(LLMClientError, match="does not know"):
        fake_client.complete("Task: something else\n")


# --- replies, retries and failures ---


def test_a_code_fence_and_a_think_block_around_the_code_are_removed(context):
    stub = StubClient("<think>hmm</think>\n```python\nx = 1\n```")

    result = agent.write_code(stub, context, "prompt", "create")

    assert result.value.text == "x = 1\n"


def test_an_empty_reply_is_retried_once_with_a_note_then_gives_up(context):
    stub = StubClient("   ", "")

    result = agent.write_code(stub, context, "prompt", "create")

    assert (result.kind, result.attempts, result.ok) == ("bad_reply", 2, False)
    assert result.problems == [agent.NO_CODE_NOTE]
    assert "Your previous reply was not accepted" in stub.prompts[1]


def test_a_modify_reply_without_edit_blocks_is_a_bad_reply(context):
    stub = StubClient("Sure! Here is the whole file:\nx = 1\n", "still no blocks")

    result = agent.write_code(stub, context, "prompt", "modify")

    assert result.kind == "bad_reply" and result.problems == [agent.NO_BLOCKS_NOTE]


def test_a_second_try_can_succeed(context):
    stub = StubClient("", "x = 2\n")

    result = agent.write_code(stub, context, "prompt", "create")

    assert result.ok and result.attempts == 2 and result.value.text == "x = 2\n"


def test_a_contract_that_is_not_json_or_has_the_wrong_shape_is_retried(context):
    stub = StubClient("not json", {"files": []})

    result = agent.write_contract(stub, context, {})

    assert result.kind == "bad_reply" and result.attempts == 2
    assert any("wrong shape" in p for p in result.problems)


def test_a_contract_for_an_unplanned_file_is_refused(context):
    wrong = {"files": [{"path": "src/agents/other.py", "items": []}]}

    result = agent.write_contract(StubClient(wrong, wrong), context, {})

    assert any("other.py is not a planned code file" in p for p in result.problems)


def test_an_ai_that_does_not_answer_is_not_retried_and_is_not_the_codes_fault(context):
    client = Failing(LLMClientError("The AI server did not answer."))

    result = agent.write_code(client, context, "prompt", "create")

    assert (result.kind, result.attempts, client.calls) == ("unreachable", 1, 1)
    assert "did not answer" in result.message


def test_an_http_400_reply_means_too_big_and_is_not_retried(context):
    client = Failing(ContextTooLargeError("too large (HTTP 400)"))

    result = agent.write_code(client, context, "prompt", "create")

    assert (result.kind, result.message, client.calls) == ("too_big", TOO_BIG_MESSAGE, 1)


def test_a_prompt_over_the_limit_is_never_sent(seed_rulebook):
    """Test 6-12, size half."""
    small = make_context(seed_rulebook, build_max_prompt_chars=1000)
    client = Failing(AssertionError("must not be called"))

    result = agent.write_code(client, small, "x" * 1001, "create")

    assert (result.kind, result.message, client.calls) == ("too_big", TOO_BIG_MESSAGE, 0)


def test_the_fake_client_can_be_told_not_to_answer_or_that_the_prompt_is_big(
    fake_client, monkeypatch
):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"no_answer"}))
    with pytest.raises(LLMClientError, match="did not answer"):
        fake_client.complete(f"{agent.CONTRACT_MARKER}\n")
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"too_big"}))
    with pytest.raises(ContextTooLargeError):
        fake_client.complete(f"{agent.CONTRACT_MARKER}\n")


def test_other_providers_use_the_generator_and_tester_roles(make_settings, monkeypatch):
    roles = []
    monkeypatch.setattr(
        agent, "get_llm_client",
        lambda role, settings, model=None, build=False: roles.append((role, build)) or role,
    )

    agent.get_build_client(make_settings(llm_provider="onprem"), "tester")
    agent.get_build_client(make_settings(llm_provider="onprem"), "generator")

    # build=True is what gives the build its own length (G4 T3)
    assert roles == [("tester", True), ("generator", True)]
