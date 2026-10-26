from datetime import UTC, datetime

import pytest

from agents import da_understand_flow
from agents.da_understand_agent import FAILED_MESSAGE
from agents.da_understand_flow import (
    CHECKPOINT_HELP_ITEM,
    CORRECT_OPTION,
    HELP_OPTION,
    PROCEED_OPTION,
    SENIOR_MESSAGE,
    choose_option,
    confirm_request,
    create_understand_request,
    get_understand_view,
    list_my_requests,
    skip_optional,
    submit_answer,
)
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_requests import list_requests
from db_table_functions.db_tbl_da_rulebook import save_new_version
from db_table_functions.db_tbl_da_understand import (
    StaleRevisionError,
    UnderstandError,
    get_confirmed_record,
)
from tests.da_stub_client import StubClient, stub_reply

pytestmark = pytest.mark.usefixtures("published_rulebook")

T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
OPENING = "Users keep asking if they can upload Excel files. Can we support that?"
HIDDEN_SHEETS = (
    "Workbooks can contain hidden worksheets. Should hidden worksheets be extracted too?"
)
VISIBLE_ONLY = "Visible worksheets only"
# Made-up test value shaped like an API key: "sk-" followed by 24 key characters.
FAKE_KEY = "sk-" + "test0000fake1111notreal2"

GOOD_Q1 = stub_reply(
    {"title": "Add Excel uploads", "objective": "Accept Excel", "reason": "Users ask for it"}
)


@pytest.fixture
def settings(make_settings):
    return make_settings()


def start(settings, client=None, developer_id=None):
    return create_understand_request(
        settings, OPENING, developer_id=developer_id, client=client, now=T0
    )


def answer(settings, view, text="My answer", client=None):
    return submit_answer(settings, view.request.request_id, text, view.revision, client=client)


def choose(settings, view, option):
    return choose_option(settings, view.request.request_id, option, view.revision)


def to_decision(settings):
    """Run the fake script to the hidden-worksheets decision after question 4."""
    view = start(settings)
    for _ in range(4):
        view = answer(settings, view)
    return view


def to_checkpoint(settings):
    view = choose(settings, to_decision(settings), VISIBLE_ONLY)
    return answer(settings, view, "Use the existing PDF processing as a reference.")


def event_types(settings, view):
    return [event.event_type for event in list_audit_events(settings.db_path, rid(view))]


def status_moves(settings, view):
    return [
        (event.details["from"], event.details["to"])
        for event in list_audit_events(settings.db_path, rid(view))
        if event.event_type == "status_changed"
    ]


def rid(view):
    return view.request.request_id


def last_message(view):
    return view.messages[-1].text


# --- the full fake-script conversation ---


def test_full_fake_script_reaches_confirmed_record_v1(settings):
    view = to_checkpoint(settings)
    assert view.request.status == "READY_FOR_CONFIRMATION"
    assert view.choices == [PROCEED_OPTION, CORRECT_OPTION, HELP_OPTION]

    view = choose(settings, view, PROCEED_OPTION)

    assert view.request.status == "CONFIRMED_FOR_DISCOVERY"
    assert view.request.version == 1
    assert view.request.title == "Add Excel document processing"
    assert view.input_mode == "done"
    assert view.progress_text == "Confirmed and saved as version 1"
    record = get_confirmed_record(settings.db_path, rid(view))
    assert record == view.record
    assert record.answered_questions == [1, 2, 3, 4]
    assert [(d.question, d.choice) for d in record.decisions] == [(HIDDEN_SHEETS, VISIBLE_ONLY)]
    assert record.references == ["Existing PDF processing"]
    assert "saved as version 1" in last_message(view)
    assert "Proceed to Discovery (coming in Phase 3)" in last_message(view)


def test_full_run_writes_every_audit_event(settings):
    view = choose(settings, to_checkpoint(settings), PROCEED_OPTION)

    types = set(event_types(settings, view))

    assert {
        "request_created",
        "question_answered",
        "interpreter_reply",
        "decision_asked",
        "decision_recorded",
        "assumption_added",
        "ready_for_confirmation",
        "confirmed",
        "status_changed",
    } <= types
    assert status_moves(settings, view) == [
        ("DRAFT", "CLARIFICATION_IN_PROGRESS"),
        ("CLARIFICATION_IN_PROGRESS", "DECISION_REQUIRED"),
        ("DECISION_REQUIRED", "CLARIFICATION_IN_PROGRESS"),
        ("CLARIFICATION_IN_PROGRESS", "READY_FOR_CONFIRMATION"),
        ("READY_FOR_CONFIRMATION", "CONFIRMED_FOR_DISCOVERY"),
    ]


def test_first_message_creates_the_request_and_asks_question_1_with_a_hint(settings):
    view = start(settings)

    assert view.request.request_id == "CVDA-2026-0001"
    assert view.request.title == "New change request"
    assert view.request.status == "CLARIFICATION_IN_PROGRESS"
    assert view.request.rulebook_version == 1
    assert view.request.developer_id == "dev-home-01"
    assert [m.speaker for m in view.messages] == ["developer", "assistant"]
    assert last_message(view) == (
        "Question 1 of 4: What needs to change, and why?\n"
        "Is the goal to let Excel content go through the same document-ingestion flow as PDFs?"
    )
    assert view.progress_text == "0 of 4 mandatory questions answered"
    assert view.input_mode == "text"
    assert view.demo_mode is True


def test_each_answer_fills_the_record_and_shows_what_changed(settings):
    view = answer(settings, start(settings))

    assert view.record.title == "Add Excel document processing"
    assert view.request.title == "Add Excel document processing"
    assert set(view.changed_fields) == {"title", "objective", "reason", "answered_questions"}
    assert view.progress_text == "1 of 4 mandatory questions answered"
    assert last_message(view).startswith("Question 2 of 4: What happens today?")


def test_questions_are_always_asked_in_order(settings):
    view = start(settings)
    asked = []
    for _ in range(3):
        view = answer(settings, view)
        asked.append(view.prompt)

    assert [p[:20] for p in asked] == [
        "Question 2 of 4: Wha",
        "Question 3 of 4: Wha",
        "Question 4 of 4: Wha",
    ]


# --- decisions (R3) ---


def test_material_ambiguity_is_asked_with_help_added(settings):
    view = to_decision(settings)

    assert view.request.status == "DECISION_REQUIRED"
    assert view.input_mode == "choices"
    assert view.prompt == HIDDEN_SHEETS
    assert view.choices == [VISIBLE_ONLY, "All worksheets, including hidden ones", HELP_OPTION]
    assert view.progress_text == "Clarification required: 1 open item"


def test_text_answer_is_refused_while_a_decision_is_waiting(settings):
    view = to_decision(settings)

    with pytest.raises(UnderstandError, match="A decision is waiting"):
        answer(settings, view, "Just extract everything")

    assert get_understand_view(settings, rid(view)).messages == view.messages


def test_choosing_records_the_decision_and_moves_on(settings):
    view = choose(settings, to_decision(settings), VISIBLE_ONLY)

    assert view.request.status == "CLARIFICATION_IN_PROGRESS"
    assert view.record.decisions[0].choice == VISIBLE_ONLY
    assert view.can_skip is True
    assert view.prompt == "Optional: constraints, exclusions, or references?"


def test_an_option_that_was_not_offered_is_refused(settings):
    with pytest.raises(UnderstandError, match="is not one of the choices"):
        choose(settings, to_decision(settings), "Only the first sheet")


def test_help_waits_then_choosing_later_resumes(settings):
    view = choose(settings, to_decision(settings), HELP_OPTION)

    assert view.request.status == "DECISION_REQUIRED"
    assert view.record.open_items == [f"Help requested: {HIDDEN_SHEETS}"]
    assert view.choices[-1] == HELP_OPTION
    assert "help_requested" in event_types(settings, view)

    later = choose(settings, get_understand_view(settings, rid(view)), VISIBLE_ONLY)

    assert later.request.status == "CLARIFICATION_IN_PROGRESS"
    assert later.record.open_items == []
    assert later.record.decisions[0].choice == VISIBLE_ONLY


def test_more_than_5_material_decisions_need_a_senior(settings):
    many = [
        {"text": f"Decision {n}?", "material": True, "options": ["Yes", "No"]} for n in range(7)
    ]
    view = start(settings)
    view = answer(settings, view, client=StubClient(stub_reply(GOOD_Q1["updates"], many)))

    assert view.request.status == "DECISION_REQUIRED"
    assert view.record.open_items == [
        "Needs a senior decision: Decision 5?",
        "Needs a senior decision: Decision 6?",
    ]
    assert any(message.text == SENIOR_MESSAGE for message in view.messages)

    for _ in range(5):
        view = choose(settings, view, "Yes")

    assert view.input_mode == "waiting"
    assert view.request.status == "DECISION_REQUIRED"
    with pytest.raises(UnderstandError, match="get help from a senior"):
        answer(settings, view)


# --- minor ambiguity (R4) ---


def test_minor_ambiguity_becomes_a_labelled_assumption(settings):
    view = to_decision(settings)

    assert [(a.text, a.basis) for a in view.record.assumptions] == [
        (
            "Excel workbooks means the .xlsx format",
            "Developer's answer to question 4 (.xlsx workbooks in)",
        )
    ]
    assert "assumption_added" in event_types(settings, view)


# --- optional area and the checkpoint ---


def test_skip_optional_goes_to_the_checkpoint(settings):
    view = choose(settings, to_decision(settings), VISIBLE_ONLY)

    view = skip_optional(settings, rid(view), view.revision)

    assert view.request.status == "READY_FOR_CONFIRMATION"
    assert view.progress_text == "Ready for confirmation"
    assert view.record.references == []


def test_correct_something_reopens_text_then_returns_to_the_checkpoint(settings):
    view = choose(settings, to_checkpoint(settings), CORRECT_OPTION)

    assert view.request.status == "CLARIFICATION_IN_PROGRESS"
    assert view.prompt == "What should change?"
    assert "correction_requested" in event_types(settings, view)

    view = answer(settings, view, "Also mention the sheet names in the output.")

    assert view.request.status == "READY_FOR_CONFIRMATION"
    assert view.choices == [PROCEED_OPTION, CORRECT_OPTION, HELP_OPTION]


def test_help_at_checkpoint_then_proceed_confirms_in_one_action(settings):
    view = choose(settings, to_checkpoint(settings), HELP_OPTION)
    assert view.request.status == "DECISION_REQUIRED"
    assert view.record.open_items == [CHECKPOINT_HELP_ITEM]
    assert view.choices == [PROCEED_OPTION, CORRECT_OPTION, HELP_OPTION]

    view = choose(settings, view, PROCEED_OPTION)

    assert view.request.status == "CONFIRMED_FOR_DISCOVERY"
    assert view.record.open_items == []
    assert status_moves(settings, view)[-4:] == [
        ("READY_FOR_CONFIRMATION", "DECISION_REQUIRED"),
        ("DECISION_REQUIRED", "CLARIFICATION_IN_PROGRESS"),
        ("CLARIFICATION_IN_PROGRESS", "READY_FOR_CONFIRMATION"),
        ("READY_FOR_CONFIRMATION", "CONFIRMED_FOR_DISCOVERY"),
    ]


def test_help_at_checkpoint_then_correct_clears_the_help_item(settings):
    view = choose(settings, to_checkpoint(settings), HELP_OPTION)

    view = choose(settings, view, CORRECT_OPTION)

    assert view.request.status == "CLARIFICATION_IN_PROGRESS"
    assert view.record.open_items == []
    assert view.prompt == "What should change?"


def test_gate_failure_lists_every_missing_item(settings):
    # Every interpreter reply is empty, so nothing gets filled in.
    view = start(settings, client=StubClient(stub_reply()))
    for _ in range(4):
        view = answer(settings, view, client=StubClient(stub_reply()))
    view = skip_optional(settings, rid(view), view.revision)

    assert view.request.status == "CLARIFICATION_IN_PROGRESS"
    assert view.prompt == "What should change?"
    message = last_message(view)
    assert message.startswith("Before you can confirm, these items need attention:")
    for missing in ("Title is empty.", "Outputs is empty.", "At least 1 failure scenario"):
        assert missing in message


def test_scope_conflict_becomes_an_open_item(settings):
    view = start(settings)
    clash = stub_reply({"in_scope": ["Hidden sheets"], "out_of_scope": ["Hidden sheets"]})

    view = answer(settings, view, client=StubClient(clash))

    assert view.record.open_items == [
        'Scope conflict: "Hidden sheets" is both in scope and out of scope.'
    ]
    assert view.progress_text == "Clarification required: 1 open item"


def test_confirm_is_refused_before_the_checkpoint(settings):
    view = start(settings)

    with pytest.raises(UnderstandError, match="answer the question"):
        confirm_request(settings, rid(view), view.revision)


def test_a_confirmed_request_cannot_be_answered_again(settings):
    view = choose(settings, to_checkpoint(settings), PROCEED_OPTION)

    with pytest.raises(UnderstandError, match="already confirmed"):
        answer(settings, view)


# --- interpreter failures ---


def test_bad_reply_is_retried_once_then_plain_message_and_record_unchanged(settings):
    view = start(settings)
    client = StubClient("not json", stub_reply({"colour": "blue"}))

    after = answer(settings, view, "We want Excel uploads.", client=client)

    assert client.replies == []
    assert len(client.prompts) == 2
    assert after.record == view.record
    assert after.request.status == "CLARIFICATION_IN_PROGRESS"
    assert [m.text for m in after.messages[-2:]] == ["We want Excel uploads.", FAILED_MESSAGE]
    assert after.prompt.startswith("Question 1 of 4")
    assert "interpreter_failed" in event_types(settings, after)


def test_invented_names_are_refused_through_the_flow(settings):
    view = start(settings)
    invented = stub_reply({"functional_flow": ["Call excel_reader.py", "Save it"]})

    after = answer(settings, view, client=StubClient(invented, invented))

    assert last_message(after) == FAILED_MESSAGE
    assert after.record.functional_flow == []


def test_interpreter_failure_at_creation_still_creates_the_request(settings):
    view = start(settings, client=StubClient("bad", "still bad"))

    assert view.request.status == "CLARIFICATION_IN_PROGRESS"
    assert last_message(view) == "Question 1 of 4: What needs to change, and why?"
    assert FAILED_MESSAGE not in [m.text for m in view.messages]
    assert "interpreter_failed" in event_types(settings, view)


def test_onprem_gives_a_plain_message_in_the_chat(make_settings, settings):
    view = start(settings)
    onprem = make_settings(llm_provider="onprem")

    after = answer(onprem, view)

    assert "not configured yet" in last_message(after)
    assert after.demo_mode is False


# --- safety rules ---


def test_stale_revision_is_refused_and_nothing_is_written(settings):
    view = start(settings)
    answer(settings, view)  # another window answers first
    current = get_understand_view(settings, rid(view))
    client = StubClient(GOOD_Q1)

    with pytest.raises(StaleRevisionError, match="updated in another window"):
        answer(settings, view, "From the old window", client=client)

    assert client.prompts == []
    assert get_understand_view(settings, rid(view)) == current


def test_stale_revision_on_a_choice_is_refused(settings):
    view = to_decision(settings)
    choose(settings, view, HELP_OPTION)

    with pytest.raises(StaleRevisionError):
        choose(settings, view, VISIBLE_ONLY)


def test_first_message_with_a_fake_key_is_refused_and_not_saved(settings):
    with pytest.raises(UnderstandError, match="an API key"):
        create_understand_request(settings, f"Connect with {FAKE_KEY}")

    assert list_requests(settings.db_path) == []


def test_answer_with_a_fake_key_is_refused_and_not_saved(settings):
    view = start(settings)

    with pytest.raises(UnderstandError, match="not saved or sent"):
        answer(settings, view, f"The key is {FAKE_KEY}")

    assert get_understand_view(settings, rid(view)).messages == view.messages


def test_message_over_4000_characters_is_refused(settings):
    with pytest.raises(UnderstandError, match="4,000"):
        answer(settings, start(settings), "x" * 4001)


def test_prompt_uses_the_pinned_charter_after_a_newer_version(settings, published_rulebook):
    view = start(settings)
    newer_charter = published_rulebook.rulebook.charter.model_copy(
        update={"purpose": "A brand new purpose for version 2."}
    )
    newer = published_rulebook.rulebook.model_copy(update={"charter": newer_charter})
    save_new_version(settings.db_path, newer, 1, "admin-0001", "New purpose")
    client = StubClient(GOOD_Q1)

    answer(settings, view, client=client)

    assert published_rulebook.rulebook.charter.purpose in client.prompts[0]
    assert "A brand new purpose for version 2." not in client.prompts[0]
    assert "rulebook v1 charter" in client.prompts[0]


# --- my requests ---


def test_my_requests_are_listed_newest_first(settings):
    first = start(settings)
    second = create_understand_request(settings, "Another made-up change")
    start(settings, developer_id="dev-other")

    listed = [request.request_id for request in list_my_requests(settings)]

    assert listed == [rid(second), rid(first)]


# --- one action, one transaction (R6, R7) ---


def test_failure_halfway_through_confirm_writes_nothing(settings, monkeypatch):
    view = to_checkpoint(settings)
    events_before = event_types(settings, view)
    real_insert = da_understand_flow.insert_audit_event

    def fail_on_confirmed(conn, request_id, actor, event_type, *args, **kwargs):
        # By now record v1 is inserted and the status has moved; all of it must roll back.
        if event_type == "confirmed":
            raise RuntimeError("Simulated failure during confirm")
        return real_insert(conn, request_id, actor, event_type, *args, **kwargs)

    monkeypatch.setattr(da_understand_flow, "insert_audit_event", fail_on_confirmed)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        choose(settings, view, PROCEED_OPTION)

    assert get_confirmed_record(settings.db_path, rid(view)) is None
    assert get_understand_view(settings, rid(view)) == view
    assert event_types(settings, view) == events_before


class SavesFirstClient(StubClient):
    """Another window saves while this answer is with the interpreter."""

    def __init__(self, settings, view, *replies):
        super().__init__(*replies)
        self.settings = settings
        self.view = view

    def complete(self, prompt, system=None):
        if not self.prompts:
            answer(self.settings, self.view, "Answer from the other window")
        return super().complete(prompt, system)


def test_save_during_the_interpreter_call_makes_this_answer_stale(settings):
    view = start(settings)
    client = SavesFirstClient(settings, view, GOOD_Q1)

    with pytest.raises(StaleRevisionError, match="updated in another window"):
        answer(settings, view, "Answer from this window", client=client)

    texts = [m.text for m in get_understand_view(settings, rid(view)).messages]
    assert "Answer from the other window" in texts
    assert "Answer from this window" not in texts
