"""Design choices, one at a time, then ONE settle call (rows 4-12 to 4-15, 4-28)."""

import pytest

from agents import da_approach_flow as flow
from agents.da_approach_agent import ScriptedApproachClient
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import ApproachError, read_approach_versions
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from tests.da_approach_play import (
    Tweaked,
    discovery_confirmed_id,
    event_types,
    events_of,
    proposed,
    texts,
)
from tests.da_stub_client import StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")

SECOND = {
    "question": "Which sheets are read?",
    "impact": "Decides whether hidden sheets are read.",
    "options": ["Visible sheets only", "All sheets"],
}


def two_choices(data):
    data["design_choices"].append(SECOND)


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return discovery_confirmed_id(settings)


def versions(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_approach_versions(conn, request_id)


def test_4_12_two_choices_are_asked_one_at_a_time_and_settled_once(settings, request_id):
    view = proposed(settings, request_id, two_choices)
    assert [label for _, label in view.buttons] == [
        "Existing upload screen", "New upload screen", "I need help deciding"
    ]
    settle = Tweaked("settle")

    # First answer by button: the next question is asked, no settle call yet.
    view = flow.choose_design_option(
        settings, request_id, "Existing upload screen", view.revision, generator=settle
    )
    assert settle.prompts == [] and view.step == "choices"
    assert "Which sheets are read?" in texts(view, "assistant")[-1]
    assert [label for _, label in view.buttons][:2] == ["Visible sheets only", "All sheets"]

    # Second answer typed (150 characters): ONE settle call, version 2 has no choices.
    typed = "Read the visible sheets and " + "x" * 122
    assert len(typed) == 150
    view = flow.submit_text(settings, request_id, typed, view.revision, generator=settle)

    assert len(settle.prompts) == 1
    assert view.step == "review" and view.approach.approach_version == 2
    assert view.approach.source == "settled" and view.approach.plan.design_choices == []
    saved = versions(settings, request_id)
    assert [v.approach_version for v in saved] == [1, 2]
    assert len(saved[0].plan.design_choices) == 2  # version 1 is still stored as proposed
    assert [(d.choice == typed, d.custom) for d in saved[1].decisions] == [(False, False),
                                                                           (True, True)]
    assert "Existing upload screen" in settle.prompts[0] and typed in settle.prompts[0]
    assert len(events_of(settings, request_id, "design_choice_recorded")) == 2
    assert len(events_of(settings, request_id, "approach_settled")) == 1


def test_a_typed_answer_equal_to_a_button_counts_as_the_button(settings, request_id):
    view = proposed(settings, request_id)

    view = flow.submit_text(
        settings, request_id, "New upload screen", view.revision,
        generator=ScriptedApproachClient("settle"),
    )

    assert view.approach.decisions[0].custom is False
    assert view.approach.decisions[0].choice == "New upload screen"


def test_4_13_a_301_character_answer_is_refused_and_nothing_is_saved(settings, request_id):
    view = proposed(settings, request_id)

    with pytest.raises(ApproachError) as refused:
        flow.submit_text(settings, request_id, "x" * 301, view.revision)

    assert str(refused.value) == (
        "Please keep your own answer under 300 characters, or choose a button."
    )
    after = flow.get_approach_view(settings, request_id)
    assert after.revision == view.revision and len(versions(settings, request_id)) == 1


def test_a_secret_in_a_typed_answer_is_refused(settings, request_id):
    view = proposed(settings, request_id)

    with pytest.raises(ApproachError, match="looks like it contains"):
        flow.submit_text(settings, request_id, "password: hunter2", view.revision)


def test_a_value_that_is_not_a_button_is_refused(settings, request_id):
    view = proposed(settings, request_id)

    with pytest.raises(ApproachError, match="is not one of the choices"):
        flow.choose_design_option(settings, request_id, "Something else", view.revision)


def test_4_14_a_settle_reply_with_a_design_choice_is_refused_and_nothing_is_saved(
    settings, request_id
):
    view = proposed(settings, request_id)
    settle = Tweaked("settle", lambda data: data["design_choices"].append(SECOND))

    with pytest.raises(ApproachError, match="Nothing was saved"):
        flow.choose_design_option(
            settings, request_id, "Existing upload screen", view.revision, generator=settle
        )

    assert len(settle.prompts) == 2  # refused, retried once, refused again
    after = flow.get_approach_view(settings, request_id)
    assert after.step == "choices" and after.revision == view.revision
    assert len(versions(settings, request_id)) == 1
    assert "design_choice_recorded" not in event_types(settings, request_id)


def test_a_settle_failure_can_be_retried_with_the_same_choice(settings, request_id):
    view = proposed(settings, request_id)
    with pytest.raises(ApproachError):
        flow.choose_design_option(
            settings, request_id, "Existing upload screen", view.revision,
            generator=StubClient("bad", "bad"),
        )

    view = flow.choose_design_option(
        settings, request_id, "Existing upload screen", view.revision,
        generator=ScriptedApproachClient("settle"),
    )

    assert view.step == "review"


def test_4_15_help_waits_with_an_open_item_and_choosing_later_clears_it(settings, request_id):
    view = proposed(settings, request_id)

    view = flow.choose_design_option(settings, request_id, "I need help deciding", view.revision)

    assert view.request.status == "APPROACH_PROPOSED" and view.step == "choices"
    assert view.open_item == "Help requested: Where does Excel upload live?"
    assert len(events_of(settings, request_id, "help_requested")) == 1
    assert [label for _, label in view.buttons][0] == "Existing upload screen"

    view = flow.choose_design_option(
        settings, request_id, "Existing upload screen", view.revision,
        generator=ScriptedApproachClient("settle"),
    )

    assert view.open_item == "" and view.step == "review"


def test_asking_for_help_twice_is_audited_once(settings, request_id):
    view = proposed(settings, request_id)
    view = flow.choose_design_option(settings, request_id, "I need help deciding", view.revision)
    flow.choose_design_option(settings, request_id, "I need help deciding", view.revision)

    assert len(events_of(settings, request_id, "help_requested")) == 1


def test_4_28_a_stale_choice_is_refused(settings, request_id):
    view = proposed(settings, request_id)

    for action in (
        lambda: flow.choose_design_option(settings, request_id, "New upload screen", 0),
        lambda: flow.submit_text(settings, request_id, "my own answer", view.revision + 5),
    ):
        with pytest.raises(StaleRevisionError):
            action()


def test_buttons_at_the_wrong_step_are_refused(settings, request_id):
    view = proposed(settings, request_id)

    for action in (
        lambda: flow.accept_approach(settings, request_id, view.revision),
        lambda: flow.request_change(settings, request_id, view.revision),
        lambda: flow.accept_test_plan(settings, request_id, view.revision),
        lambda: flow.keep_case(settings, request_id, view.revision),
        lambda: flow.request_case(settings, request_id, view.revision),
        lambda: flow.write_test_plan_again(settings, request_id, view.revision),
        lambda: flow.request_help(settings, request_id, view.revision),
    ):
        with pytest.raises(ApproachError, match="design choice is waiting"):
            action()
