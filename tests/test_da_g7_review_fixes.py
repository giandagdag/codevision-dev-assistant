"""Fix G7 code review round 1: no AI text echoed, spaces never refuse, full text in chat."""

from types import SimpleNamespace

from agents.da_approach_checks import PROPOSE, find_approach_problems
from agents.da_approach_cut import cut_reply
from agents.da_approach_flow import _ask_text, _detail_for, _failure_text
from agents.da_approach_reasons import REJECTED_FOOTER, rejected_message
from pydantic_classes.da_approach_models import ApproachReply, DesignChoice
from tests.da_approach_samples import design_choice, good_plan, sample_discovery

MARKER = "ZQX-PLANTED-MARKER"


def _problems(policy, plan):
    reply = ApproachReply.model_validate(cut_reply(plan))
    return find_approach_problems(reply, policy, sample_discovery(), set(), PROPOSE)


def test_check_sentences_never_quote_the_ai_question_or_code(seed_rulebook):
    twice = design_choice(question=f"Which {MARKER} screen?")
    plan = good_plan(design_choices=[twice, twice])
    plan["summary"] = f"def {MARKER}():\n    pass"

    found = _problems(seed_rulebook.policy, plan)

    assert any("asked twice" in problem for problem in found)
    assert any("contains code" in problem for problem in found)
    assert MARKER not in rejected_message(found)
    assert MARKER not in " ".join(found)


def test_a_300_character_summary_with_a_trailing_space_is_accepted(seed_rulebook):
    plan = good_plan(summary="a" * 300 + " \n")

    reply = ApproachReply.model_validate(cut_reply(plan))

    assert reply.summary == "a" * 300


def test_the_chat_question_shows_the_uncut_text():
    choice = DesignChoice(
        question="short…",
        impact="short…",
        options=["A", "B"],
        full_text={"question": "full question", "impact": "full impact"},
    )

    text = _ask_text(choice)

    assert "full question" in text and "full impact" in text


def test_the_decision_keeps_the_uncut_option_text():
    choice = DesignChoice(
        question="Q", impact="I", options=["cut…", "B"], full_text={"option_1": "the whole text"}
    )

    assert _detail_for(choice, "cut…") == "the whole text"
    assert _detail_for(choice, "B") == "B"


def test_a_caller_closing_replaces_the_try_again_footer():
    problems = ["Library x is not approved."]
    result = SimpleNamespace(message=rejected_message(problems))

    text = _failure_text(result, "apply your change", "Nothing was saved. Press Try again.")

    assert text.count("Try again") == 1
    assert REJECTED_FOOTER not in text and text.endswith("Press Try again.")


def test_the_prompt_lists_the_impact_limit():
    from pathlib import Path

    prompt = Path("src/data/da_approach_prompt.md").read_text(encoding="utf-8")

    assert '"impact": "<up to 200 characters' in prompt
