"""Change something, the 3-change cap, the file limit reason (rows 4-16, 4-17, 4-28)."""

import pytest

from agents import da_approach_flow as flow
from agents.da_tester_agent import ScriptedTesterClient
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import ApproachError, read_approach_versions
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from tests.da_approach_play import (
    Tweaked,
    at_review,
    discovery_confirmed_id,
    events_of,
    proposed,
    texts,
)
from tests.da_stub_client import StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")

CAP = "You have used all 3 changes, so you can only accept the approach or get help."


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return discovery_confirmed_id(settings)


def change(settings, request_id, view, text="Please also log each skipped sheet"):
    """Typing in the open box and pressing Send ("Change something")."""
    assert view.step == "review" and view.send_label == "Change something"
    return flow.submit_text(
        settings, request_id, text, view.revision, generator=Tweaked("change")
    )


def test_4_16_change_something_saves_a_new_version_and_keeps_the_old_one(settings, request_id):
    view = at_review(settings, request_id)

    view = change(settings, request_id, view)

    assert view.step == "review" and view.approach.approach_version == 3
    assert view.approach.source == "change" and view.change_count == 1
    assert "skipped sheet" in view.approach.plan.summary or "Changed as you asked" in (
        view.approach.plan.summary
    )
    with open_db(settings.db_path) as conn:
        assert [v.approach_version for v in read_approach_versions(conn, request_id)] == [1, 2, 3]
    assert len(events_of(settings, request_id, "approach_change_requested")) == 1
    assert len(events_of(settings, request_id, "approach_changed")) == 1
    assert "Please also log each skipped sheet" in texts(view, "developer")


def test_the_typed_change_reaches_the_generator_between_lines(settings, request_id):
    view = at_review(settings, request_id)
    generator = Tweaked("change")

    flow.submit_text(settings, request_id, "Log skipped sheets", view.revision,
                     generator=generator)

    assert "----------\nLog skipped sheets\n----------" in generator.prompts[0]
    assert "information only" in generator.prompts[0]


def test_4_16_after_three_changes_the_button_is_gone_and_the_chat_says_why(settings, request_id):
    view = at_review(settings, request_id)
    for number in range(3):
        assert view.text_prompt  # the box is open
        view = change(settings, request_id, view, f"Change number {number + 1}")

    assert view.change_count == 3
    assert [label for _, label in view.buttons] == ["Accept approach", "Get help"]
    # The box is closed and the cap message is what it shows.
    assert view.text_prompt == ""
    assert view.note == CAP and texts(view, "assistant")[-1] == CAP
    with pytest.raises(ApproachError, match="used all 3 changes"):
        flow.submit_text(settings, request_id, "A fourth change", view.revision)


def test_a_change_text_over_1000_characters_is_refused(settings, request_id):
    view = at_review(settings, request_id)

    with pytest.raises(ApproachError, match="under 1,000 characters"):
        flow.submit_text(settings, request_id, "x" * 1001, view.revision)
    with pytest.raises(ApproachError, match="Please type a message first"):
        flow.submit_text(settings, request_id, "  ", view.revision)


def test_a_failed_change_call_saves_nothing(settings, request_id):
    view = at_review(settings, request_id)

    with pytest.raises(ApproachError, match="Nothing was saved"):
        flow.submit_text(settings, request_id, "Do it", view.revision,
                         generator=StubClient("x", "x"))

    after = flow.get_approach_view(settings, request_id)
    assert after.step == "review" and after.approach.approach_version == 2
    assert after.change_count == 0


def test_a_change_reply_can_ask_a_new_design_choice(settings, request_id):
    view = at_review(settings, request_id)
    asks = Tweaked("change", lambda data: data["design_choices"].append({
        "question": "Which sheets are read?", "impact": "Hidden sheets",
        "options": ["Visible only", "All"],
    }))

    view = flow.submit_text(settings, request_id, "Also read sheets", view.revision,
                            generator=asks)

    assert view.step == "choices" and view.approach.plan.design_choices


def test_the_review_step_has_an_open_box_and_no_change_button(settings, request_id):
    """Phase 6 fixes, section 2: typing + Send is the change; the old button is gone."""
    view = at_review(settings, request_id)

    assert [label for _, label in view.buttons] == ["Accept approach", "Get help"]
    assert view.send_label == "Change something"
    assert view.text_prompt == "Type what should change, then press Change something."


def test_empty_text_at_the_review_step_does_nothing(settings, request_id):
    view = at_review(settings, request_id)

    for blank in ("", "   "):
        with pytest.raises(ApproachError, match="Please type a message first"):
            flow.submit_text(settings, request_id, blank, view.revision)

    after = flow.get_approach_view(settings, request_id)
    assert after.revision == view.revision and after.change_count == 0
    assert after.messages == view.messages


def test_the_old_change_button_is_refused_at_the_review_step(settings, request_id):
    view = at_review(settings, request_id)

    with pytest.raises(ApproachError, match="Change something"):
        flow.request_change(settings, request_id, view.revision)


def six_files(data):
    data["files"] = [
        {"path": f"src/agents/part_{n}.py", "action": "create", "purpose": "A part",
         "reuses": []}
        for n in range(6)
    ]
    data["design_choices"] = []


def test_4_17_more_files_than_the_limit_asks_for_a_reason(settings, request_id):
    view = proposed(settings, request_id, six_files)
    assert view.approach.warnings[0] == (
        "6 code files; the limit is 5. Splitting the request is safer."
    )

    view = flow.accept_approach(settings, request_id, view.revision)

    assert view.step == "limit_reason"
    assert [label for _, label in view.buttons] == ["Change something", "Get help"]
    assert "6 code files; the limit is 5" in texts(view, "assistant")[-1]
    with pytest.raises(ApproachError, match="10 to 300"):
        flow.submit_text(settings, request_id, "tiny", view.revision)
    assert flow.get_approach_view(settings, request_id).step == "limit_reason"

    view = flow.submit_text(
        settings, request_id, "A dozen steps need it", view.revision,
        tester=ScriptedTesterClient("test_plan"),
    )

    assert view.step == "tests"
    audit = events_of(settings, request_id, "file_limit_overridden")[0]
    assert audit.actor == "developer"
    assert audit.details["reason"] == "A dozen steps need it" and audit.details["limit"] == 5
    assert events_of(settings, request_id, "approach_accepted")


def test_at_the_limit_step_change_something_is_still_possible(settings, request_id):
    view = proposed(settings, request_id, six_files)
    view = flow.accept_approach(settings, request_id, view.revision)

    view = flow.request_change(settings, request_id, view.revision)

    assert view.step == "change"


def test_exactly_five_files_needs_no_reason(settings, request_id):
    def five(data):
        six_files(data)
        data["files"].pop()

    view = proposed(settings, request_id, five)

    view = flow.accept_approach(
        settings, request_id, view.revision, tester=ScriptedTesterClient("test_plan")
    )

    assert view.step == "tests"
    assert not events_of(settings, request_id, "file_limit_overridden")


def test_4_28_a_stale_change_is_refused(settings, request_id):
    view = at_review(settings, request_id)

    with pytest.raises(StaleRevisionError):
        flow.request_change(settings, request_id, view.revision - 1)
    with pytest.raises(StaleRevisionError):
        flow.accept_approach(settings, request_id, view.revision + 1)
