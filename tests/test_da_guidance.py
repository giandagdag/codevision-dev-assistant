"""Phase 10 step 9: a senior's guidance goes once into the next AI call (tests 10-37, 10-51)."""

import json
from datetime import UTC, datetime

import pytest

from agents import da_approach_flow as approach_flow
from agents import da_build_agent as agent
from agents import da_refine_agent as refine
from agents import da_tester_review as review
from agents.da_approach_agent import build_prompt
from agents.da_approach_checks import PROPOSE
from agents.da_guidance import (
    HEADING,
    USED_APPROACH,
    USED_TESTER_REVIEW,
    guidance_block,
    take_guidance,
)
from agents.da_senior_actions import close_escalation, send_guidance
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_escalation import read_escalations
from pydantic_classes.da_build_models import Contract
from tests.da_approach_samples import sample_record
from tests.da_build_play import CREATE, MODIFY, ORIGINAL, event_types, make_approach, make_cases
from tests.da_build_play import make_context as make_build_context
from tests.da_stub_client import StubClient
from tests.test_da_senior_actions import row_of, seed
from tests.test_da_tester_review import make_input

pytestmark = pytest.mark.usefixtures("published_rulebook")
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
NOTE = "Use the batch limit from the bank policy page."


@pytest.fixture
def settings(make_settings):
    return make_settings()


def returned_with_guidance(settings, how="returned"):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    send_guidance(settings, row.escalation_id, row.revision, "ann", NOTE, NOW)
    row = row_of(settings, request_id)
    close_escalation(settings, row.escalation_id, row.revision, "ann", how, "Go on.", NOW)
    return request_id


# --- the block ---


def test_an_empty_note_adds_nothing():
    assert guidance_block("") == "" and guidance_block("   ") == ""


def test_the_block_names_the_senior_and_holds_the_text():
    block = guidance_block(NOTE)
    assert HEADING in block and NOTE in block


# --- the four prompt builders (10-51: no new prompt file, only an optional block) ---


def test_the_approach_prompt_gets_the_block_only_when_given(seed_rulebook):
    from tests.test_da_approach_agent import context

    plain = build_prompt(PROPOSE, context(seed_rulebook))
    given = build_prompt(PROPOSE, context(seed_rulebook, senior_guidance=NOTE))
    assert HEADING not in plain
    assert given.count(NOTE) == 1 and given.startswith(plain)


def test_the_fix_round_prompt_gets_the_block_only_when_given(seed_rulebook):
    context = make_build_context(seed_rulebook)
    contract = Contract.model_validate(
        json.loads(agent.scripted_build_reply(f"{agent.CONTRACT_MARKER}\n"))
    )
    args = (context, contract, MODIFY, "modify", 2, "TESTS", ORIGINAL, "T-2 failed")
    plain = agent.build_code_prompt(*args)
    given = agent.build_code_prompt(*args, senior_guidance=NOTE)
    assert HEADING not in plain
    assert given.count(NOTE) == 1 and given.startswith(plain)
    assert CREATE not in NOTE  # the block is text from a person, nothing else rides along


def test_the_lane_prompt_gets_the_block_only_when_given(seed_rulebook):
    values = {
        "charter": seed_rulebook.charter, "record": sample_record(), "approach": make_approach(),
        "cases": make_cases(), "policy": seed_rulebook.policy,
    }  # fmt: skip
    plain = refine.build_lane_prompt(refine.RefineContext(**values), "It crashes.")
    given = refine.build_lane_prompt(
        refine.RefineContext(**values, senior_guidance=NOTE), "It crashes."
    )
    assert HEADING not in plain
    assert given.count(NOTE) == 1 and given.startswith(plain)


def test_the_tester_prompt_gets_the_block_and_still_holds_no_code_or_chat(seed_rulebook):
    plain = review.build_review_prompt(make_input(seed_rulebook))
    given = review.build_review_prompt(make_input(seed_rulebook, senior_guidance=NOTE))
    assert HEADING not in plain
    assert given.count(NOTE) == 1 and given.startswith(plain)
    assert "class T(unittest.TestCase)" not in given
    assert "developer chat" not in given.lower()


# --- taking it ---


def test_10_37_returned_guidance_is_taken_once_and_marked_used(settings):
    request_id = returned_with_guidance(settings)

    assert take_guidance(settings.db_path, request_id, USED_APPROACH, NOW) == NOTE
    assert take_guidance(settings.db_path, request_id, USED_APPROACH, NOW) == ""

    with open_db(settings.db_path) as conn:
        row = read_escalations(conn, request_id)[-1]
    assert [g.used_in for g in row.guidance] == [USED_APPROACH]
    assert row.outcome == "returned" and row.closed_at is not None
    assert event_types(settings, request_id).count("guidance_used") == 1


def test_guidance_on_a_still_open_row_is_not_taken(settings):
    request_id = seed(settings)
    row = row_of(settings, request_id)
    send_guidance(settings, row.escalation_id, row.revision, "ann", NOTE, NOW)
    assert take_guidance(settings.db_path, request_id, USED_APPROACH, NOW) == ""


def test_guidance_of_an_abandoned_request_is_never_used(settings):
    request_id = returned_with_guidance(settings, how="abandoned")
    assert take_guidance(settings.db_path, request_id, USED_APPROACH, NOW) == ""


def test_a_database_without_escalations_gives_nothing(settings):
    from tests.da_approach_play import discovery_confirmed_id

    request_id = discovery_confirmed_id(settings)
    assert take_guidance(settings.db_path, request_id, USED_TESTER_REVIEW, NOW) == ""


# --- the real call: the fake client gets the block once (10-37) ---


def test_10_37_the_approach_call_sends_the_guidance_once(settings, seed_rulebook):
    from tests.test_da_approach_agent import context

    request_id = returned_with_guidance(settings)
    record = sample_record().model_copy(update={"request_id": request_id})
    first, second = StubClient("not json", "not json"), StubClient("not json", "not json")

    approach_flow._generate(settings, PROPOSE, context(seed_rulebook, record=record), first)
    approach_flow._generate(settings, PROPOSE, context(seed_rulebook, record=record), second)

    assert NOTE in first.prompts[0]
    assert all(NOTE not in prompt for prompt in second.prompts)
    assert "guidance_used" in event_types(settings, request_id)
