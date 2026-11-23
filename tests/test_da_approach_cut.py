"""Fix G7 step 3a: long text is cut, never refused (G7-3, G7-5, G7-8, G7-13, L1, L2, L7)."""

import json

import pytest

from agents.da_approach_agent import ApproachContext, generate_approach
from agents.da_approach_checks import PROPOSE
from agents.da_approach_cut import cut_reply, was_cut
from pydantic_classes.da_approach_models import ApproachReply, ApproachState, DesignChoice
from pydantic_classes.da_approach_text import cut_text, make_label, unique_labels
from tests.da_approach_samples import design_choice, good_plan, sample_discovery, sample_record
from tests.da_stub_client import StubClient

LONG_OPTION = (
    "Read the Word file with the standard zipfile module and pull the text out of the XML "
    "parts by hand, one paragraph at a time, keeping the heading levels in a small table"
)


def context(seed_rulebook):
    return ApproachContext(
        charter=seed_rulebook.charter,
        record=sample_record(),
        discovery=sample_discovery(),
        policy=seed_rulebook.policy,
    )


def test_cut_text_ends_at_a_word_with_an_ellipsis_and_fits_the_limit():
    text = "alpha beta gamma delta epsilon"

    cut = cut_text(text, 20)

    assert cut == "alpha beta gamma…" and len(cut) <= 20
    assert cut_text("short", 20) == "short"
    assert cut_text("x" * 100, 20) == "x" * 19 + "…"  # one huge word is cut hard


def test_labels_made_from_the_same_start_are_told_apart():
    labels = unique_labels(["Use the file", "Use the file", "Other"])

    assert labels == ["Use the file", "Use the file (2)", "Other"]


def test_g7_3_a_150_character_plain_option_is_accepted_on_attempt_one(seed_rulebook):
    option = LONG_OPTION[:150]
    plan = good_plan(design_choices=[design_choice(options=(option, "Short"))])

    result = generate_approach(StubClient(plan), PROPOSE, context(seed_rulebook))

    choice = result.reply.design_choices[0]
    assert result.ok and result.attempts == 1
    assert choice.options[0] == option  # the full text is what is kept
    label = choice.button_labels()[0]
    assert len(label) <= 60 and label.endswith("…") and LONG_OPTION.startswith(label[:-1])


def test_g7_4_label_and_detail_options_keep_both(seed_rulebook):
    options = [{"label": "Zip and XML", "detail": LONG_OPTION}, {"label": "Other", "detail": "B"}]
    plan = good_plan(design_choices=[{**design_choice(), "options": options}])

    reply = generate_approach(StubClient(plan), PROPOSE, context(seed_rulebook)).reply

    choice = reply.design_choices[0]
    assert choice.options == [LONG_OPTION, "B"]
    assert choice.button_labels() == ["Zip and XML", "Other"]


def test_an_overlong_detail_and_label_are_cut_and_the_full_text_kept():
    huge = "word " * 120  # 600 characters
    data = {"design_choices": [{"question": "Q?", "impact": "i",
                                "options": [{"label": "L " * 40, "detail": huge}, "B"]}]}

    choice = cut_reply(data)["design_choices"][0]

    assert len(choice["options"][0]) <= 300 and choice["options"][0].endswith("…")
    assert len(choice["labels"][0]) <= 60
    assert choice["full_text"]["option_1"] == huge.strip()


def test_g7_5_a_450_character_summary_is_cut_to_300_and_the_full_text_kept(seed_rulebook):
    summary = ("Convert the document and keep headings. " * 12)[:450]
    plan = good_plan(summary=summary)

    result = generate_approach(StubClient(plan), PROPOSE, context(seed_rulebook))

    assert result.ok and result.attempts == 1
    assert len(result.reply.summary) <= 300 and result.reply.summary.endswith("…")
    assert result.reply.full_text["summary"] == summary.strip()
    assert was_cut(result.reply)


def test_the_ai_cannot_set_the_apps_own_fields():
    data = {"summary": "s", "full_text": {"summary": "forged"},
            "design_choices": [{"question": "Q?", "impact": "i", "options": ["a", "b"],
                                "labels": ["x", "y"], "full_text": {"question": "forged"}}]}

    cut = cut_reply(data)

    assert cut["full_text"] == {} and cut["design_choices"][0]["full_text"] == {}
    assert cut["design_choices"][0]["labels"] == ["a", "b"]


def test_g7_8_four_design_choices_are_still_refused():
    four = [design_choice(question=f"Question {n}?") for n in range(4)]

    with pytest.raises(ValueError):  # a count rule of the reply shape, not formatting
        ApproachReply.model_validate(cut_reply(good_plan(design_choices=four)))


def test_a_count_over_the_policy_limit_is_refused_not_cut(seed_rulebook):
    policy = seed_rulebook.policy.model_copy(update={"max_design_choices": 1})
    plan = good_plan(design_choices=[design_choice("One?"), design_choice("Two?")])
    ctx = ApproachContext(
        charter=seed_rulebook.charter, record=sample_record(),
        discovery=sample_discovery(), policy=policy,
    )

    result = generate_approach(StubClient(plan, plan), PROPOSE, ctx)

    assert not result.ok and result.kind == "rejected"
    assert any("design choices" in problem for problem in result.problems)


def test_code_hiding_in_the_cut_off_part_is_still_found(seed_rulebook):
    summary = "A plain sentence. " * 20 + "\ndef steal():\n    pass"
    plan = good_plan(summary=summary)

    result = generate_approach(StubClient(plan, plan), PROPOSE, context(seed_rulebook))

    assert not result.ok and any("contains code" in problem for problem in result.problems)


def test_g7_13_and_l7_an_old_saved_plan_and_state_still_open():
    old_choice = {"question": "Q?", "impact": "i", "options": ["Existing screen", "New screen"]}
    old_plan = {"summary": "s", "design_choices": [old_choice]}  # no labels, no full_text

    reply = ApproachReply.model_validate(json.loads(json.dumps(old_plan)))
    state = ApproachState.model_validate(
        {"request_id": "CVDA-2026-0001", "pending_choices": [old_choice]}
    )

    assert reply.design_choices[0].button_labels() == ["Existing screen", "New screen"]
    assert state.pending_choices[0].labels == [] and state.pending_choices[0].full_text == {}
    assert DesignChoice.model_validate(old_choice).button_labels()[1] == make_label("New screen")
