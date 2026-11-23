"""Fix G7 step 2: the chat says the real reason a plan failed (G7-1, G7-2, R2 to R4)."""

import pytest
from pydantic import ValidationError

from agents import da_approach_flow as flow
from agents.da_approach_reasons import (
    LIBRARY_HINT,
    MAX_KEPT,
    kept_problems,
    plain_shape_problems,
    rejected_message,
)
from pydantic_classes.da_approach_models import ApproachReply
from tests.da_approach_play import discovery_confirmed_id, events_of, texts
from tests.da_approach_samples import good_plan
from tests.da_stub_client import FailingClient, StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return discovery_confirmed_id(settings)


def test_g7_1_a_rejected_plan_says_so_names_the_library_and_gives_the_hint(settings, request_id):
    bad = good_plan(libraries=["python-docx"])

    view = flow.start_approach(settings, request_id, 0, generator=StubClient(bad, bad))

    said = texts(view, "assistant")[-1]
    assert "The AI answered, but its plan broke these rules:" in said
    assert "python-docx" in said
    assert LIBRARY_HINT.format(name="python-docx") in said
    assert "Press Try again, or change the request." in said
    assert "could not be reached" not in said
    assert view.failed_first_call and view.failed_problems  # the tab can list them


def test_g7_2_an_unreachable_ai_still_says_it_could_not_be_reached(settings, request_id):
    view = flow.start_approach(
        settings, request_id, 0, generator=FailingClient("The AI could not be reached.")
    )

    said = texts(view, "assistant")[-1]
    assert "The AI could not be reached." in said
    assert "The AI answered" not in said


def test_the_approach_tab_keeps_up_to_twelve_problems_from_the_audit(settings, request_id):
    many = good_plan(
        files=[
            {"path": f"../x{n}.py", "action": "create", "purpose": "p"} for n in range(1, 9)
        ],
        libraries=["badone", "badtwo", "badthree", "badfour"],
    )

    view = flow.start_approach(settings, request_id, 0, generator=StubClient(many, many))

    assert len(view.failed_problems) == 12
    event = events_of(settings, request_id, "approach_failed")[-1]
    assert len(event.details["problems"]) == 12
    assert "...and 10 more (see the Approach tab)" in texts(view, "assistant")[-1]


def test_the_message_shows_three_problems_then_the_count():
    problems = [f"Problem {n}." for n in range(1, 6)]

    text = rejected_message(problems)

    assert "- Problem 3." in text and "Problem 4." not in text
    assert "...and 2 more (see the Approach tab)" in text
    assert "Ask your admin" not in text  # no library problem, no hint


def test_the_approach_bar_lists_the_failed_problems():
    from layouts.da_developer_assistant_page import _approach_bar

    bar = _approach_bar([("start", "Try again")], "note", ["Problem A.", "Problem B."])

    shown = [c for c in bar.children if getattr(c, "className", "") == "da-failed-problem"]
    assert [child.children for child in shown] == ["Problem A.", "Problem B."]


def test_kept_problems_are_capped_in_number_and_length():
    kept = kept_problems(["x" * 500] * 20)

    assert len(kept) == MAX_KEPT and len(kept[0]) == 300


def test_r3_shape_errors_use_plain_words_with_no_field_path():
    data = good_plan(
        design_choices=[
            {"question": "Q?", "impact": "I", "options": ["a", "b" * 150]},
        ]
    )
    with pytest.raises(ValidationError) as caught:
        ApproachReply.model_validate(data)

    lines = plain_shape_problems(caught.value)

    assert lines == [
        "The reply has the wrong shape: Option 2 of design question 1 is too long."
    ]
    assert "design_choices" not in lines[0] and ".1" not in lines[0]
