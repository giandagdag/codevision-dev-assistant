"""Fix D1 step 3a: code tests (C-n): the prompt, the Layer A checks and the fake reply (D1-5 part).

No AI and no internet. The loop wiring and the Tester's judgement come in steps 3b and 3c."""

import json

import pytest

from agents import da_build_agent as agent
from agents import da_code_tests as code_tests
from agents.da_enhance_build_script import scripted_contract
from pydantic_classes.da_build_models import Contract
from tests.da_build_play import make_context

BUILD_NEW = Contract.model_validate(
    json.loads(agent.scripted_build_reply(f"{agent.CONTRACT_MARKER}\n"))
)
SCRIPT = json.loads(agent.FAKE_SCRIPT_FILE.read_text(encoding="utf-8"))
ENHANCE = Contract.model_validate(json.loads(scripted_contract(SCRIPT)))
PATH = BUILD_NEW.files[0].path
NAME = BUILD_NEW.files[0].items[0].name
MODULE = PATH.removeprefix("src/").removesuffix(".py").replace("/", ".")

GOOD = f'''
import unittest
from {MODULE} import {NAME}
from da_evidence import evidence


class Checks(unittest.TestCase):
    def test_c1_first_branch(self):
        """Targets: {PATH}:{NAME} the first branch."""
        evidence(self, "callable", "{NAME}", True, callable({NAME}))
        self.assertTrue(callable({NAME}))
'''


@pytest.fixture
def context(seed_rulebook):
    return make_context(seed_rulebook)


@pytest.fixture
def policy(seed_rulebook):
    return seed_rulebook.policy


def test_a_good_code_test_file_has_no_problems(policy):
    assert code_tests.find_code_test_problems(GOOD, BUILD_NEW, policy) == []


def test_a_syntax_error_and_an_empty_file_are_refused(policy):
    assert "syntax error" in code_tests.find_code_test_problems("def (:", BUILD_NEW, policy)[0]
    assert code_tests.find_code_test_problems("x = 1\n", BUILD_NEW, policy) == [
        "The test file has no test method."
    ]


def test_a_code_test_needs_a_targets_line_in_a_contract_file(policy):
    bare = GOOD.replace(f"Targets: {PATH}:{NAME} the first branch.", "Checks it.")
    elsewhere = GOOD.replace(PATH, "src/agents/other.py")

    assert any("needs a docstring line 'Targets:" in p for p in
               code_tests.find_code_test_problems(bare, BUILD_NEW, policy))
    assert any("is not a file of the contract" in p for p in
               code_tests.find_code_test_problems(elsewhere, BUILD_NEW, policy))


def test_names_must_be_c_numbers_in_order_with_no_gaps(policy):
    wrong_name = GOOD.replace("test_c1_first_branch", "test_t1_ac1_first_branch")
    gap = GOOD.replace("test_c1_first_branch", "test_c2_first_branch")

    assert any("name it test_c1_" in p for p in
               code_tests.find_code_test_problems(wrong_name, BUILD_NEW, policy))
    assert any("in order from 1" in p for p in
               code_tests.find_code_test_problems(gap, BUILD_NEW, policy))


def test_more_than_fifteen_code_tests_are_refused(policy):
    extra = "".join(
        f'    def test_c{n}_more(self):\n        """Targets: {PATH}:{NAME} more."""\n'
        f'        evidence(self, "x", 1, 1, 1)\n'
        for n in range(2, 18)
    )

    found = code_tests.find_code_test_problems(GOOD + extra, BUILD_NEW, policy)

    assert any("at most 15" in p for p in found)


def test_a_code_test_without_evidence_gets_its_c_number_in_the_note(policy):
    call = f'        evidence(self, "callable", "{NAME}", True, callable({NAME}))\n'
    text = GOOD.replace(call, "")

    assert code_tests.find_code_test_problems(text, BUILD_NEW, policy) == [
        "Test C-1 records no evidence"
    ]


def test_code_tests_follow_the_same_import_and_call_rules(policy):
    text = GOOD.replace("import unittest", "import unittest\nimport subprocess").replace(
        f"        self.assertTrue(callable({NAME}))", '        eval("1")'
    )

    found = " ".join(code_tests.find_code_test_problems(text, BUILD_NEW, policy))

    assert "'subprocess', which is blocked" in found and "eval() is not allowed" in found


def test_the_prompt_holds_the_criteria_contract_code_and_limit_but_no_server_path(context):
    prompt = code_tests.build_code_tests_prompt(context, BUILD_NEW, {PATH: "def f():\n    pass\n"})

    assert code_tests.is_code_tests_prompt(prompt)
    assert f"### {PATH}" in prompt and "def f()" in prompt and "at most 15" in prompt
    assert "{{" not in prompt and "C:\\" not in prompt and "/home/" not in prompt


@pytest.mark.parametrize("contract", [BUILD_NEW, ENHANCE], ids=["build_new", "enhance"])
@pytest.mark.parametrize("switch", [None, "code_test_bug", "code_test_wrong"])
def test_the_fake_code_tests_pass_their_own_checks(
    context, make_settings, monkeypatch, contract, switch
):
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({switch} if switch else ()))
    client = agent.get_build_client(make_settings(llm_provider="fake"), "tester")

    result = code_tests.write_code_tests(client, context, contract, {PATH: "x = 1\n"})

    assert result.ok and result.attempts == 1
    count = result.value.count("    def test_c")
    assert 1 <= count <= code_tests.CODE_TEST_LIMIT
    assert ("fails_code_bug" in result.value) == (switch == "code_test_bug")
    assert ("fails_wrong_test" in result.value) == (switch == "code_test_wrong")
