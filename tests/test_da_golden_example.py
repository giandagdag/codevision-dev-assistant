"""Fix 11-1, AF-21: the golden example reaches the Generator prompt only."""

import dataclasses
import json

import pytest

from agents import da_build_agent as agent
from agents.da_golden_example import HEADING, MAX_LINES, program_type_of
from pydantic_classes.da_build_models import Contract
from pydantic_classes.da_rulebook_models import GoldenExample
from tests.da_build_play import CREATE, make_context


@pytest.fixture
def contract():
    return Contract.model_validate(
        json.loads(agent.scripted_build_reply(f"{agent.CONTRACT_MARKER}\n"))
    )


def _example(kind: str) -> GoldenExample:
    body = "\n".join(f"line_{n} = {n}" for n in range(200))
    return GoldenExample(title="Made-up model", code=body, program_type=kind, why="Short.")


@pytest.mark.parametrize(
    ("path", "text", "kind"),
    [
        ("src/layouts/da_x.py", "", "Screen"),
        ("src/callbacks/screen_callbacks/da_x.py", "", "Screen"),
        ("src/agents/da_x.py", "if __name__ == '__main__':\n    pass", "Batch or ingestion"),
        ("src/agents/da_x.py", "def run_batch():\n    pass", "Batch or ingestion"),
        ("src/agents/da_x.py", "def helper():\n    pass", "Utility"),
        ("src/configs/da_x.py", "", "Utility"),
    ],
)
def test_plain_code_maps_a_path_to_a_program_type(path, text, kind):
    assert program_type_of(path, text) == kind


def test_the_code_prompt_gets_the_first_80_lines_of_the_matching_example(
    seed_rulebook, contract
):
    context = dataclasses.replace(
        make_context(seed_rulebook), golden_examples=(_example("Screen"), _example("Utility"))
    )
    prompt = agent.build_code_prompt(context, contract, "src/layouts/da_x.py", "create", 1, "T", "")

    assert HEADING in prompt and "Made-up model" in prompt
    assert f"line_{MAX_LINES - 1} = " in prompt and f"line_{MAX_LINES} = " not in prompt


def test_no_matching_example_means_no_block(seed_rulebook, contract):
    context = dataclasses.replace(
        make_context(seed_rulebook), golden_examples=(_example("Screen"),)
    )
    prompt = agent.build_code_prompt(context, contract, CREATE, "create", 1, "T", "")

    assert HEADING not in prompt


def test_the_tester_and_contract_prompts_never_carry_it(seed_rulebook, contract):
    context = dataclasses.replace(
        make_context(seed_rulebook), golden_examples=(_example("Utility"),)
    )

    assert HEADING not in agent.build_tests_prompt(context, contract)
    assert HEADING not in agent.build_contract_prompt(context, {})
