"""The 4-box form in Understand (Phase 6 fixes batch, section 1: U1 to U8).

Requests saved before this change finish the old one-at-a-time way; that is tested in
test_da_understand_flow.py. Everything here is made up and uses the fake provider or a stub.
"""

from datetime import UTC, datetime

import pytest

from agents import da_understand_flow as flow
from agents.da_understand_agent import ScriptedUnderstandClient
from agents.da_understand_flow import (
    BOX_EMPTY_MESSAGE,
    FORM_MESSAGE,
    HELP_OPTION,
    PROCEED_OPTION,
    FormError,
    choose_option,
    create_understand_request,
    get_understand_view,
    submit_answer,
    submit_form,
)
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_rulebook import save_new_version
from db_table_functions.db_tbl_da_understand import (
    StaleRevisionError,
    UnderstandError,
    get_session,
)
from tests.da_play import ANSWERS
from tests.da_stub_client import FailingClient, StubClient, stub_reply

pytestmark = pytest.mark.usefixtures("published_rulebook")

T0 = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
VAGUE_OPENING = "I need an Excel ingestion module"
HIDDEN_SHEETS = (
    "Workbooks can contain hidden worksheets. Should hidden worksheets be extracted too?"
)
VISIBLE_ONLY = "Visible worksheets only"
# A reply that fills the four mandatory areas and raises no question.
FILLED = stub_reply(
    {
        "title": "Add Excel uploads",
        "objective": "Accept Excel workbooks",
        "reason": "Users ask for it",
        "current_behaviour": "Only PDF and DOCX are accepted",
        "expected_behaviour": "Excel workbooks are accepted",
        "inputs": "Excel workbooks",
        "outputs": "Normal ingestion format",
        "functional_flow": ["Upload the workbook", "Read the sheets"],
        "in_scope": ["Excel upload"],
        "out_of_scope": ["Macros"],
    }
)


@pytest.fixture
def settings(make_settings):
    return make_settings()


class CountingClient:
    """The scripted fake provider, counting every call and keeping every prompt."""

    def __init__(self, step="form"):
        self._inner = ScriptedUnderstandClient(step)
        self.prompts: list[str] = []
        self.model = self._inner.model

    def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        return self._inner.complete(prompt)


def rid(view):
    return view.request.request_id


def boxes(optional=""):
    return [*ANSWERS, optional]


def create(settings, opening=VAGUE_OPENING):
    return create_understand_request(settings, opening, now=T0)


def submit(settings, view, answers=None, client=None):
    return submit_form(
        settings, rid(view), answers or boxes(), view.revision, client=client, now=T0
    )


def event_types(settings, view):
    return [event.event_type for event in list_audit_events(settings.db_path, rid(view))]


# --- creating the request shows the form (U1, U3) ---


def test_the_opening_statement_creates_the_request_and_shows_the_form(settings):
    view = create(settings)

    assert view.request.status == "CLARIFICATION_IN_PROGRESS"
    assert view.request.title == "New change request"
    assert view.input_mode == "form"
    assert [m.speaker for m in view.messages] == ["developer", "assistant"]
    assert view.messages[0].text == VAGUE_OPENING
    assert view.messages[1].text == FORM_MESSAGE
    assert view.progress_text == "0 of 4 mandatory questions answered"
    assert view.answered_count == 0
    assert view.visible_fields == ["assumptions", "decisions", "open_items"]
    assert get_session(settings.db_path, rid(view)).step == "form"


def test_creating_the_request_makes_no_interpreter_call(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The interpreter must not run before the form is submitted.")

    monkeypatch.setattr(flow, "interpret", forbidden)

    view = create(settings)

    assert "interpreter_reply" not in event_types(settings, view)
    assert [
        (e.details["from"], e.details["to"])
        for e in list_audit_events(settings.db_path, rid(view))
        if e.event_type == "status_changed"
    ] == [("DRAFT", "CLARIFICATION_IN_PROGRESS")]


def test_the_form_has_the_four_questions_in_their_wording_and_an_optional_box():
    assert [title for _, title in flow.FORM_BOXES] == [
        "What needs to change, and why?",
        "What happens today? (you don't need to know the source files)",
        "What should happen after the change?",
        "What are the inputs, outputs, and important success or failure cases?",
    ]
    assert flow.OPTIONAL_QUESTION == "Optional: constraints, exclusions, or references?"
    assert flow.FORM_OPTIONAL_BOX == 5


# --- a vague opening reaches the checkpoint with the 4 answers first (Done-when) ---


def test_a_vague_opening_reaches_the_checkpoint_with_the_four_questions_answered(settings):
    view = create(settings)

    view = submit(settings, view)

    # The one AI question comes AFTER the form; the 4 mandatory questions are already answered.
    assert view.request.status == "DECISION_REQUIRED"
    assert view.record.answered_questions == [1, 2, 3, 4]
    assert view.answered_count == 4
    assert view.prompt == HIDDEN_SHEETS
    assert view.choices == [VISIBLE_ONLY, "All worksheets, including hidden ones", HELP_OPTION]

    view = choose_option(settings, rid(view), VISIBLE_ONLY, view.revision, now=T0)

    assert view.request.status == "READY_FOR_CONFIRMATION"
    assert view.choices == [PROCEED_OPTION, HELP_OPTION]
    view = choose_option(settings, rid(view), PROCEED_OPTION, view.revision, now=T0)
    assert view.request.status == "CONFIRMED_FOR_DISCOVERY"
    assert view.record.answered_questions == [1, 2, 3, 4]


def test_the_whole_run_never_says_noted_as_a_confirmed_decision(settings):
    view = submit(settings, create(settings))
    view = choose_option(settings, rid(view), VISIBLE_ONLY, view.revision, now=T0)
    view = choose_option(settings, rid(view), PROCEED_OPTION, view.revision, now=T0)

    assert all("Noted as a confirmed decision." not in m.text for m in view.messages)


def test_the_answers_are_saved_as_one_readable_developer_message(settings):
    view = submit(settings, create(settings), boxes("Use the PDF flow as a reference"))

    message = next(m for m in view.messages if m.text.startswith("1. "))
    assert message.speaker == "developer"
    assert "1. What needs to change, and why?\nUsers keep asking" in message.text
    assert "4. What are the inputs, outputs" in message.text
    assert flow.OPTIONAL_QUESTION + "\nUse the PDF flow as a reference" in message.text
    assert "form_submitted" in event_types(settings, view)


def test_an_empty_optional_box_is_left_out_of_the_message(settings):
    view = submit(settings, create(settings))

    message = next(m for m in view.messages if m.text.startswith("1. "))
    assert flow.OPTIONAL_QUESTION not in message.text


# --- one interpreter call per Submit, and what it sees (U3) ---


def test_one_interpreter_call_per_submit_sees_the_opening_and_all_answers(settings):
    view = create(settings)
    client = CountingClient()

    submit(settings, view, boxes("Reference: the PDF flow"), client=client)

    assert len(client.prompts) == 1
    prompt = client.prompts[0]
    assert VAGUE_OPENING in prompt
    for text in ANSWERS:
        assert text in prompt
    assert "Reference: the PDF flow" in prompt


def test_a_failed_submit_makes_no_further_call_and_a_later_submit_one_call(settings):
    view = create(settings)
    failing = FailingClient()

    with pytest.raises(UnderstandError):
        submit(settings, view, client=failing)
    assert len(failing.prompts) == 1

    good = CountingClient()
    submit(settings, view, client=good)
    assert len(good.prompts) == 1


# --- every box is checked; a failing box is named; nothing is saved (U2) ---


def test_empty_mandatory_boxes_are_named_and_nothing_is_saved(settings):
    view = create(settings)
    answers = boxes()
    answers[1] = "   "
    answers[2] = ""

    with pytest.raises(FormError) as caught:
        submit(settings, view, answers)

    assert caught.value.problems == {2: BOX_EMPTY_MESSAGE, 3: BOX_EMPTY_MESSAGE}
    after = get_understand_view(settings, rid(view))
    assert after.revision == view.revision
    assert [m.text for m in after.messages] == [m.text for m in view.messages]


def test_the_optional_box_may_be_empty_but_is_checked_when_filled(settings):
    view = create(settings)

    with pytest.raises(FormError) as caught:
        submit(settings, view, boxes("my key is sk-" + "test0000fake1111notreal2"))

    assert list(caught.value.problems) == [5]
    assert "API key" in caught.value.problems[5]


def test_a_box_with_a_secret_or_too_long_is_refused_with_its_own_message(settings):
    view = create(settings)
    answers = boxes()
    answers[0] = "x" * 4001
    answers[3] = "token sk-" + "test0000fake1111notreal2"

    with pytest.raises(FormError) as caught:
        submit(settings, view, answers)

    assert sorted(caught.value.problems) == [1, 4]
    assert "4,000" in caught.value.problems[1]
    assert "API key" in caught.value.problems[4]


def test_a_form_with_the_wrong_number_of_boxes_is_refused(settings):
    view = create(settings)

    with pytest.raises(UnderstandError, match="5 boxes"):
        submit(settings, view, list(ANSWERS))


# --- the AI fails at Submit: nothing in the chat, the failure is audited (X4) ---


def test_when_the_ai_fails_nothing_is_saved_in_the_chat_and_the_failure_is_audited(settings):
    view = create(settings)

    with pytest.raises(UnderstandError, match="did not answer"):
        submit(settings, view, client=FailingClient("The AI server did not answer."))

    after = get_understand_view(settings, rid(view))
    assert [m.text for m in after.messages] == [m.text for m in view.messages]
    assert after.revision == view.revision
    assert after.input_mode == "form"
    assert "interpreter_failed" in event_types(settings, view)


def test_a_reply_that_is_not_usable_is_retried_once_then_refused(settings):
    view = create(settings)
    client = StubClient("not json", "still not json")

    with pytest.raises(UnderstandError, match="couldn't process"):
        submit(settings, view, client=client)

    assert len(client.prompts) == 2
    assert get_understand_view(settings, rid(view)).input_mode == "form"


# --- wrong step and stale window ---


def test_the_form_can_only_be_submitted_once(settings):
    view = submit(settings, create(settings))

    with pytest.raises(StaleRevisionError):
        submit_form(settings, rid(view), boxes(), view.revision - 1, now=T0)
    with pytest.raises(UnderstandError, match="decision is waiting"):
        submit_form(settings, rid(view), boxes(), view.revision, now=T0)


def test_typing_into_the_chat_box_is_refused_while_the_form_is_open(settings):
    view = create(settings)

    with pytest.raises(UnderstandError, match="form"):
        submit_answer(settings, rid(view), "An answer", view.revision, now=T0)


def test_a_stale_window_is_refused_before_the_ai_is_asked(settings):
    view = create(settings)
    client = CountingClient()

    with pytest.raises(StaleRevisionError):
        submit_form(settings, rid(view), boxes(), view.revision + 5, client=client, now=T0)

    assert client.prompts == []


# --- the Summary shows everything the form answered at once (U8) ---


def test_after_submit_every_form_field_is_revealed_at_once_and_highlighted(settings):
    before = create(settings)

    after = submit(settings, before)

    assert before.visible_fields == ["assumptions", "decisions", "open_items"]
    for name in ("objective", "reason", "current_behaviour", "expected_behaviour", "inputs",
                 "outputs", "functional_flow", "in_scope", "out_of_scope", "constraints",
                 "references"):
        assert name in after.visible_fields
    assert {"objective", "current_behaviour", "expected_behaviour", "inputs"} <= set(
        after.changed_fields
    )


def test_the_progress_bar_goes_from_0_to_4_of_4_together(settings):
    before = create(settings)
    assert (before.answered_count, before.progress_text) == (
        0,
        "0 of 4 mandatory questions answered",
    )

    after = submit(settings, before, client=StubClient(FILLED))

    assert after.answered_count == 4
    assert after.record.answered_questions == [1, 2, 3, 4]


# --- the AI questions after the form (U4, U5, U6) ---


def ambiguity(text, *options):
    return {"text": text, "material": True, "options": list(options) or ["Yes", "No"]}


def test_only_questions_still_open_after_the_form_are_asked(settings):
    view = create(settings)

    view = submit(settings, view, client=StubClient(stub_reply(FILLED["updates"], [])))

    # Nothing is open: no AI question, the gate decides (criteria are missing, so a correction).
    assert view.request.status != "DECISION_REQUIRED"
    assert view.choices == []


def test_a_duplicate_ai_question_is_not_asked_twice(settings):
    first = ambiguity("Should hidden sheets count?", "Yes", "No")
    other = ambiguity("Which file types?", "xlsx", "xls")
    view = submit(
        settings, create(settings), client=StubClient(stub_reply(FILLED["updates"], [first, first]))
    )
    assert [p.question for p in get_session(settings.db_path, rid(view)).pending_decisions] == [
        first["text"]
    ]

    # The reply to the decision repeats the decided question and adds one new one.
    view = choose_option(
        settings, rid(view), "Yes", view.revision, now=T0,
        client=StubClient(stub_reply({}, [first, other])),
    )

    assert view.prompt == other["text"]
    asked = [e.details["question"] for e in list_audit_events(settings.db_path, rid(view))
             if e.event_type == "decision_asked"]
    assert asked == [first["text"], other["text"]]


def test_the_prompt_tells_the_interpreter_what_is_decided_and_what_is_queued(settings):
    first = ambiguity("Should hidden sheets count?", "Yes", "No")
    second = ambiguity("Which file types?", "xlsx", "xls")
    view = submit(
        settings,
        create(settings),
        client=StubClient(stub_reply(FILLED["updates"], [first, second])),
    )
    client = StubClient(stub_reply({}, []))

    choose_option(settings, rid(view), "Yes", view.revision, now=T0, client=client)

    prompt = client.prompts[0]
    decided_block = prompt.split("Already decided by the developer:")[1].split("Already waiting")[0]
    queued_block = prompt.split("Already waiting to be asked:")[1].split("Never ask")[0]
    assert first["text"] in decided_block
    assert second["text"] in queued_block
    assert "only NEW ambiguities" in prompt


def test_the_prompt_says_none_when_nothing_is_decided_or_queued(settings):
    client = CountingClient()

    submit(settings, create(settings), client=client)

    assert "Already decided by the developer:\n- (none)" in client.prompts[0]
    assert "Already waiting to be asked:\n- (none)" in client.prompts[0]


def _with_limit(settings, published_rulebook, limit):
    policy = published_rulebook.rulebook.policy.model_copy(
        update={"max_material_decisions": limit}
    )
    newer = published_rulebook.rulebook.model_copy(update={"policy": policy})
    save_new_version(settings.db_path, newer, 1, "admin-0001", f"Limit {limit}")


def test_the_number_of_ai_questions_is_read_from_the_policy(
    settings, published_rulebook
):
    _with_limit(settings, published_rulebook, 2)
    many = [ambiguity(f"Question number {n}?") for n in range(4)]

    view = submit(
        settings, create(settings), client=StubClient(stub_reply(FILLED["updates"], many))
    )

    session = get_session(settings.db_path, rid(view))
    assert len(session.pending_decisions) == 2
    assert session.material_decisions_asked == 2
    assert session.needs_senior is True
    assert sum(1 for item in view.record.open_items if item.startswith("Needs a senior")) == 2


def test_a_higher_policy_limit_allows_more_questions_than_the_seed_8(settings, published_rulebook):
    # Fix 11-1: the seed default is now 8, so the "higher" limit is 12.
    _with_limit(settings, published_rulebook, 12)
    many = [ambiguity(f"Question number {n}?") for n in range(10)]

    view = submit(
        settings, create(settings), client=StubClient(stub_reply(FILLED["updates"], many))
    )

    assert len(get_session(settings.db_path, rid(view)).pending_decisions) == 10
    assert view.request.status == "DECISION_REQUIRED"


def test_the_limit_of_the_pinned_version_wins_over_a_newer_one(settings, published_rulebook):
    view = create(settings)  # pinned to v1 (seed limit 8)
    _with_limit(settings, published_rulebook, 1)
    many = [ambiguity(f"Question number {n}?") for n in range(3)]

    view = submit(settings, view, client=StubClient(stub_reply(FILLED["updates"], many)))

    assert len(get_session(settings.db_path, rid(view)).pending_decisions) == 3
