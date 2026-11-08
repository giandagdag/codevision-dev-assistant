"""Phase 8 AI calls: lane, revision, repro test (tests 8-9 prompt side, 8-10, 8-11, 8-15, 8-21)."""

import inspect
import json

import pytest

from agents import da_build_agent as build_agent
from agents import da_refine_agent as refine
from agents.da_build_agent import ScriptedBuildClient
from agents.da_refine_checks import apply_revision
from pydantic_classes.da_build_models import Contract, ContractFile, ContractItem
from pydantic_classes.da_refine_models import RevisionReply
from tests.da_approach_samples import sample_record
from tests.da_build_play import CREATE, MODIFY, ORIGINAL, make_approach, make_cases
from web.da_fake_onprem_server import reply_text

FEEDBACK = "The upload crashes when a sheet is empty."


@pytest.fixture
def context(seed_rulebook):
    return refine.RefineContext(
        charter=seed_rulebook.charter,
        record=sample_record(),
        approach=make_approach(),
        cases=make_cases(),
        policy=seed_rulebook.policy,
        label="Ready with warnings",
    )


@pytest.fixture
def contract():
    return Contract(
        files=[
            ContractFile(
                path=CREATE,
                items=[
                    ContractItem(
                        name="read_sheets", kind="function", args=["book"], summary="Reads."
                    )
                ],
            ),
            ContractFile(
                path=MODIFY,
                items=[
                    ContractItem(name="validate", kind="function", args=["path"], summary="Checks.")
                ],
            ),
        ]
    )


class Counting:
    """A client that counts calls and gives a fixed reply."""

    model = "fake"

    def __init__(self, text):
        self.text = text
        self.prompts = []

    def complete(self, prompt, system=None):
        from agents.da_llm_client import LLMReply

        self.prompts.append(prompt)
        return LLMReply(text=self.text, provider="fake", model="fake")


def switches(monkeypatch, *names):
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset(names))


# --- the lane call ---


def test_8_9_the_lane_prompt_holds_the_facts_and_his_words_and_no_chat_and_no_code(context):
    prompt = refine.build_lane_prompt(context, FEEDBACK)

    assert refine.LANE_MARKER in prompt.splitlines()
    assert (
        "--- developer feedback starts ---\n" + FEEDBACK + "\n--- developer feedback ends ---"
        in prompt
    )
    assert '"id": "AC-1"' in prompt  # the record with criterion IDs
    assert "T-1 (AC-1)" in prompt  # the test plan cases
    assert "Label: Ready with warnings" in prompt
    assert "<<<<<<<" not in prompt and "```" not in prompt
    # The function takes no chat and no code: only the context object and his words.
    assert list(inspect.signature(refine.build_lane_prompt).parameters) == ["context", "feedback"]


def test_8_9_a_bug_reply_with_a_real_criterion_is_kept(context):
    result = refine.suggest_lane(ScriptedBuildClient("tester"), context, FEEDBACK)

    assert result.ok
    assert (result.value.lane, result.value.criterion_id) == ("bug", "AC-1")


def test_the_scripted_lane_follows_the_words(context):
    client = ScriptedBuildClient("tester")

    approach = refine.suggest_lane(client, context, "Use a different design instead.")
    requirement = refine.suggest_lane(client, context, "Reject files over 5 MB.")

    assert approach.value.lane == "approach"
    assert requirement.value.lane == "requirement"


def test_8_10_a_bug_with_no_criterion_is_shown_as_a_requirement_suggestion(context, monkeypatch):
    switches(monkeypatch, "lane_bug_no_criterion")

    result = refine.suggest_lane(ScriptedBuildClient("tester"), context, FEEDBACK)

    assert result.value.lane == "requirement"
    assert result.value.reason == "No criterion covers this, so it is a missing requirement."


def test_8_11_an_unusable_lane_reply_twice_gives_no_suggestion(context, monkeypatch):
    switches(monkeypatch, "lane_unusable")
    client = Counting("Here is my answer in words and not in JSON.")

    result = refine.suggest_lane(client, context, FEEDBACK)

    assert not result.ok
    assert result.kind == "bad_reply"
    assert len(client.prompts) == context.policy.refine_lane_max_attempts == 2
    assert "Your previous reply was not accepted" in client.prompts[1]


def test_a_wrong_criterion_in_a_lane_reply_is_retried_then_unusable(context):
    reply = json.dumps({"lane": "bug", "reason": "Broken.", "criterion_id": "AC-9"})
    client = Counting(reply)

    result = refine.suggest_lane(client, context, FEEDBACK)

    assert result.kind == "bad_reply"
    assert "AC-9" in result.problems[0]


def test_no_answer_and_too_big_are_not_the_replys_fault(context, monkeypatch):
    switches(monkeypatch, "no_answer")
    assert (
        refine.suggest_lane(ScriptedBuildClient("tester"), context, FEEDBACK).kind == "unreachable"
    )

    switches(monkeypatch)
    small = context.policy.model_copy(update={"build_max_prompt_chars": 1000})
    context = refine.RefineContext(
        charter=context.charter,
        record=context.record,
        approach=context.approach,
        cases=context.cases,
        policy=small,
    )
    assert refine.suggest_lane(ScriptedBuildClient("tester"), context, FEEDBACK).kind == "too_big"


def test_the_lane_role_is_one_setting():
    assert refine.LANE_ROLE in ("generator", "reviewer", "tester")


# --- the revision call ---


def test_the_revision_prompt_asks_for_changes_only_and_holds_no_chat_and_no_code(context):
    prompt = refine.build_revision_prompt(context, "Reject files over 5 MB.")

    assert refine.REVISION_MARKER in prompt.splitlines()
    assert "Reject files over 5 MB." in prompt
    assert "CHANGES only" in prompt
    assert "```" not in prompt


def test_the_scripted_revision_adds_one_criterion_numbered_by_the_app(context):
    result = refine.revise_record(
        ScriptedBuildClient("generator"), context, "Reject files over 5 MB."
    )

    assert result.ok
    assert isinstance(result.value, RevisionReply)
    v2, problems = apply_revision(context.record, result.value, [context.record])
    assert problems == []
    assert v2.acceptance_criteria[-1].id == "AC-4"
    assert v2.version == 2


def test_a_revision_reply_in_the_wrong_shape_is_unusable(context):
    result = refine.revise_record(Counting('{"criteria_ops": "all of them"}'), context, "x")

    assert result.kind == "bad_reply"


# --- the repro-test call ---


def repro_prompt(context, contract, own_test=False):
    return refine.build_repro_prompt(
        context.record, contract, context.cases, "AC-2", "T-10", FEEDBACK, own_test
    )


def test_8_15_the_repro_and_add_a_test_prompts_hold_no_code_text(context, contract):
    for own_test in (False, True):
        prompt = repro_prompt(context, contract, own_test)

        assert ORIGINAL not in prompt
        assert "return True" not in prompt
        assert "<<<<<<<" not in prompt
        assert FEEDBACK in prompt
        assert "validate(path)" in prompt  # the contract: names only
    assert refine.REPRO_MARKER in repro_prompt(context, contract).splitlines()
    assert refine.OWN_TEST_MARKER in repro_prompt(context, contract, True).splitlines()
    parameters = inspect.signature(refine.write_repro_test).parameters
    assert not any("code" in name or "text" in name for name in parameters)


def test_the_repro_prompt_names_only_the_cases_of_its_criterion(context, contract):
    prompt = repro_prompt(context, contract)

    assert "T-2 (AC-2)" in prompt
    assert "T-1 (AC-1)" not in prompt
    assert "Next case id: T-10" in prompt
    assert "Criterion: AC-2" in prompt


def test_the_scripted_repro_reply_is_one_named_method_for_the_next_case(context, contract):
    result = refine.write_repro_test(
        ScriptedBuildClient("tester"),
        context.record,
        contract,
        context.cases,
        context.policy,
        "AC-2",
        "T-10",
        FEEDBACK,
    )

    assert result.ok
    reply = result.value
    assert reply.criterion_id == "AC-2"
    assert "def test_t10_ac2_shows_bug(self):" in reply.method
    assert "assertFalse" in reply.method


def test_8_23_the_passes_today_switch_gives_a_test_that_passes_on_the_fake_code(
    context, contract, monkeypatch
):
    switches(monkeypatch, "repro_passes_today")

    result = refine.write_repro_test(
        ScriptedBuildClient("tester"), context.record, contract, context.cases,
        context.policy, "AC-2", "T-10", FEEDBACK,
    )  # fmt: skip

    assert "assertTrue" in result.value.method


GOOD = (
    "CASE\ncriterion: AC-2\ngiven: g\nexpect: e\nMETHOD\n"
    'def test_t10_ac2_x(self):\n    """It works."""\n    self.assertEqual(1, 1)\n'
)


def test_a_good_repro_reply_parses_even_inside_a_code_fence():
    reply, problems = refine.parse_repro_reply(f"```\n{GOOD}```", "AC-2", "test_t10_ac2_")

    assert problems == []
    assert (reply.given, reply.expect) == ("g", "e")
    assert reply.method.startswith("def test_t10_ac2_x(self):")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("just some words", "CASE part"),
        (GOOD.replace("criterion: AC-2", "criterion: AC-3"), "criterion must be AC-2"),
        (GOOD.replace("test_t10_ac2_x", "test_t99_ac2_x"), "Name the method"),
        (GOOD.replace('    """It works."""\n', ""), "docstring"),
        (GOOD + "def test_t10_ac2_y(self):\n    pass\n", "exactly one"),
        (GOOD.replace("self.assertEqual(1, 1)", "import os\n    os.system('x')"), "not allowed"),
        (GOOD.replace("self.assertEqual(1, 1)", "self.assertEqual(open('x').read(), 1)"), "file"),
        (GOOD.replace("(self):", "(self"), "syntax"),
    ],
)
def test_a_bad_repro_reply_is_refused_with_a_plain_reason(text, expected):
    reply, problems = refine.parse_repro_reply(text, "AC-2", "test_t10_ac2_")

    assert reply is None
    assert any(expected in problem for problem in problems), problems


def test_a_repro_reply_that_stays_bad_is_unusable_after_two_tries(context, contract):
    client = Counting("not the format")

    result = refine.write_repro_test(
        client, context.record, contract, context.cases, context.policy, "AC-2", "T-10", "x"
    )

    assert result.kind == "bad_reply"
    assert len(client.prompts) == context.policy.refine_repro_max_attempts


# --- the pretend work server answers the same script ---


def test_the_pretend_work_server_answers_the_refine_prompts_like_the_fake_provider(
    context, contract
):
    lane = reply_text(refine.build_lane_prompt(context, FEEDBACK), "normal")
    revision = reply_text(
        refine.build_revision_prompt(context, "Reject files over 5 MB."), "normal"
    )
    repro = reply_text(repro_prompt(context, contract), "normal")

    assert json.loads(lane)["lane"] == "bug"
    assert json.loads(revision)["criteria_ops"][0]["op"] == "add"
    assert repro.startswith("CASE")
    assert reply_text(refine.build_lane_prompt(context, FEEDBACK), "bad-json").startswith("Sorry")
