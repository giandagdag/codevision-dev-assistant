"""Fix G9 B1/B2: the required results list and the Builder prompt rules."""

import json
from types import SimpleNamespace

from agents import da_build_agent as agent
from agents import da_required_results as rr
from pydantic_classes.da_build_models import Contract
from pydantic_classes.da_request_record_models import AcceptanceCriterion
from tests.da_build_play import MODIFY, ORIGINAL, make_context


def criterion(number, when, then):
    return AcceptanceCriterion(
        id=f"AC-{number}", kind="success", given="a user", when=when, then=then
    )


def record_of(*items):
    return SimpleNamespace(acceptance_criteria=list(items))  # only the criteria are read


def test_a_function_call_with_a_literal_result_is_a_pair():
    item = criterion(2, "check('abc') is called", "check('abc') returns 'INVALID PASSWORD'")

    [pair] = rr.required_results(record_of(item))

    assert (pair.kind, pair.name, pair.args, pair.value) == (
        "function",
        "check",
        ("abc",),
        "INVALID PASSWORD",
    )
    assert pair.line() == "- AC-2: check('abc') -> returns 'INVALID PASSWORD'"


def test_a_command_line_gives_output_and_exit_code():
    item = criterion(
        3, "`python tool.py ''` is run", "it prints 'NO INPUT PROVIDED', exit code non-zero"
    )

    [pair] = rr.required_results(record_of(item))

    assert pair.line() == "- AC-3: tool.py '' -> output 'NO INPUT PROVIDED', exit code non-zero"


def test_a_vague_criterion_gives_no_pair_and_arguments_must_be_literals():
    vague = criterion(1, "the user uploads a file", "it is rejected with the standard error")
    names = criterion(4, "check(user_name) is called", "it returns 'OK'")

    assert rr.required_results(record_of(vague, names)) == []


def test_the_builder_prompt_holds_the_pairs_and_the_never_raise_rule(seed_rulebook):
    context = make_context(seed_rulebook)
    item = criterion(9, "check('abc') is called", "check('abc') returns 'INVALID PASSWORD'")
    context.record.acceptance_criteria = [item]
    contract = Contract.model_validate(
        json.loads(agent.scripted_build_reply(f"{agent.CONTRACT_MARKER}\n"))
    )

    prompt = agent.build_code_prompt(context, contract, MODIFY, "modify", 1, "T", ORIGINAL)

    assert "They beat coding habits and every rule except an exception RX-n" in prompt
    assert "- AC-9: check('abc') -> returns 'INVALID PASSWORD'" in prompt
    assert "Never raise instead" in prompt
