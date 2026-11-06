"""The gate, READY_TO_BUILD, Get help, wrong-step refusals and stale windows
(rows 4-25, 4-26, 4-28, rules G1 and G6)."""

from datetime import UTC, datetime

import pytest

from agents import da_approach_flow as flow
from agents.da_tester_agent import ScriptedTesterClient
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import (
    ApproachError,
    insert_approach_version,
    read_approach_state,
    read_latest_approach,
    save_approach_state,
)
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from tests.da_approach_play import (
    at_review,
    at_tests,
    discovery_confirmed_id,
    event_types,
    events_of,
    proposed,
    texts,
)
from tests.da_discover_play import moves

pytestmark = pytest.mark.usefixtures("published_rulebook")

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return discovery_confirmed_id(settings)


def test_4_25_all_four_checks_true_gives_ready_to_build(settings, request_id):
    view = at_tests(settings, request_id)
    assert [c.passed for c in view.gate] == [True, True, True, False]

    view = flow.accept_test_plan(settings, request_id, view.revision)

    assert view.request.status == "READY_TO_BUILD" and view.step == "done"
    assert [c.passed for c in view.gate] == [True] * 4
    assert view.buttons == []
    assert ("APPROACH_PROPOSED", "READY_TO_BUILD") in moves(settings, request_id)
    for event in ("test_plan_accepted", "gate_passed"):
        assert event in event_types(settings, request_id)
    assert events_of(settings, request_id, "gate_passed")[0].actor == "system"
    assert "READY TO BUILD" in texts(view, "assistant")[-1]


def test_a_request_that_is_ready_to_build_cannot_be_changed(settings, request_id):
    view = at_tests(settings, request_id)
    view = flow.accept_test_plan(settings, request_id, view.revision)

    for action in (
        lambda: flow.accept_test_plan(settings, request_id, view.revision),
        lambda: flow.request_change(settings, request_id, view.revision),
        lambda: flow.request_help(settings, request_id, view.revision),
        lambda: flow.submit_text(settings, request_id, "hello", view.revision),
    ):
        with pytest.raises(ApproachError, match="READY TO BUILD"):
            action()


def test_4_26_a_plan_for_an_older_approach_names_the_false_check_and_keeps_the_status(
    settings, request_id
):
    view = at_tests(settings, request_id)
    # Arrange what a crash or a bug could leave: a newer approach version that is accepted,
    # while the test plan was written for the older one.
    with open_db(settings.db_path) as conn:
        latest = read_latest_approach(conn, request_id)
        newer = latest.model_copy(update={"approach_version": latest.approach_version + 1})
        insert_approach_version(conn, newer, NOW)
        state = read_approach_state(conn, request_id)
        state.accepted_approach_version = newer.approach_version
        save_approach_state(conn, state, state.revision, NOW)

    view = flow.accept_test_plan(settings, request_id, view.revision + 1)

    assert view.request.status == "APPROACH_PROPOSED" and view.step == "tests"
    assert "gate_passed" not in event_types(settings, request_id)
    assert texts(view, "assistant")[-1] == (
        "Not ready to build yet. These checks are not true:\n"
        "- Test plan accepted: The accepted test plan was written for an older approach."
    )
    assert [c.passed for c in view.gate] == [True, True, True, False]


def test_get_help_at_each_step_escalates_with_an_open_item(settings, request_id):
    view = at_review(settings, request_id)

    view = flow.request_help(settings, request_id, view.revision)

    assert view.request.status == "ESCALATION_REQUIRED" and view.step == "escalated"
    assert view.open_item == "Escalated in Approach: review"
    assert events_of(settings, request_id, "escalated")[0].details["step"] == "review"
    assert ("APPROACH_PROPOSED", "ESCALATION_REQUIRED") in moves(settings, request_id)
    assert flow.has_approach(settings, request_id) and view.buttons == []
    with pytest.raises(ApproachError, match="handed to a senior"):
        flow.accept_approach(settings, request_id, view.revision)


def test_get_help_from_the_tests_step(settings, request_id):
    view = at_tests(settings, request_id)

    view = flow.request_help(settings, request_id, view.revision)

    assert view.open_item == "Escalated in Approach: tests"


def test_has_approach_is_false_before_the_first_call(settings, request_id):
    assert not flow.has_approach(settings, request_id)
    proposed(settings, request_id)
    assert flow.has_approach(settings, request_id)


def test_buttons_follow_the_step(settings, request_id):
    view = at_review(settings, request_id)
    assert [k for k, _ in view.buttons] == ["accept", "help"]
    assert view.send_label == "Change something" and "press Change something" in view.text_prompt
    view = flow.accept_approach(
        settings, request_id, view.revision, tester=ScriptedTesterClient("test_plan")
    )
    assert [k for k, _ in view.buttons] == ["accept_plan", "change_approach", "help"]
    assert [label for _, label in view.buttons] == [
        "Accept test plan", "Go back and change the approach", "Get help"
    ]
    assert view.send_label == "Add a test case" and "press Add a test case" in view.text_prompt
    view = flow.request_plan_change(settings, request_id, view.revision)
    assert view.buttons == [] and "What should change" in view.text_prompt
    assert view.send_label == "Send"


@pytest.mark.parametrize(
    "action",
    [
        lambda s, r, rev: flow.start_approach(s, r, rev),
        lambda s, r, rev: flow.choose_design_option(s, r, "x", rev),
        lambda s, r, rev: flow.submit_text(s, r, "x", rev),
        lambda s, r, rev: flow.accept_approach(s, r, rev),
        lambda s, r, rev: flow.request_change(s, r, rev),
        lambda s, r, rev: flow.request_plan_change(s, r, rev),
        lambda s, r, rev: flow.request_help(s, r, rev),
        lambda s, r, rev: flow.write_test_plan_again(s, r, rev),
        lambda s, r, rev: flow.keep_case(s, r, rev),
        lambda s, r, rev: flow.discard_case(s, r, rev),
        lambda s, r, rev: flow.accept_test_plan(s, r, rev),
    ],
)
def test_4_28_every_action_with_an_old_revision_gets_the_stale_message(
    settings, request_id, action
):
    view = at_tests(settings, request_id)

    with pytest.raises(StaleRevisionError) as refused:
        action(settings, request_id, view.revision - 1)

    assert str(refused.value) == "This request was updated in another window. Reload to continue."
    assert flow.get_approach_view(settings, request_id).revision == view.revision


def test_the_generator_is_never_given_the_chat(settings, request_id):
    from tests.da_approach_play import Tweaked

    generator = Tweaked("propose")
    flow.start_approach(settings, request_id, 0, generator=generator)

    prompt = generator.prompts[0]
    assert "Task: propose an approach" in prompt
    assert "Searching approved sources" not in prompt  # a chat line from Discover
