"""Test helper: drive the scripted Excel conversation (fake provider) through the 2A engine."""

from datetime import UTC, datetime

from agents import da_understand_flow as flow
from db_table_functions.db_tbl_da_understand import get_session

# Answers are ignored by the fake provider (it plays its script), but must pass the checks.
ANSWERS = (
    "Users keep asking to upload Excel files",
    "The upload screen only takes PDF and DOCX",
    "Check the workbook, read the sheets, pass them on",
    "Workbooks in, normal ingestion format out; reject empty or damaged files",
)


def start(settings):
    return flow.create_understand_request(settings, "Can we support Excel uploads?")


def start_old_way(settings, client=None, developer_id=None, now=None):
    """A request as it was saved BEFORE the Phase 6 fixes batch: the opening statement was read by
    the interpreter and question 1 is asked, one question at a time. Such a request must still
    open and finish the old way (plan X1); tests of that path start here."""
    view = flow.create_understand_request(
        settings, "Can we support Excel uploads?", developer_id=developer_id, now=now
    )
    request_id = view.request.request_id
    session = get_session(settings.db_path, request_id)
    opening = "Can we support Excel uploads?"
    result = flow._interpret(settings, session, "opening", flow.OPENING_QUESTION, opening, client)
    when = now or datetime.now(UTC)
    with flow._turn(settings.db_path, request_id, session.revision, when) as turn:
        turn.session.step = "question"
        if result.ok:
            flow._apply_result(turn, result)
        else:
            flow._audit_failure(turn, "opening", result)
        flow._advance(turn)
    return flow.get_understand_view(settings, request_id)


def answer(settings, view, text):
    return flow.submit_answer(settings, view.request.request_id, text, view.revision)


def choose(settings, view, option):
    return flow.choose_option(settings, view.request.request_id, option, view.revision)


def skip(settings, view):
    return flow.skip_optional(settings, view.request.request_id, view.revision)


def submit_form(settings, view, answers=ANSWERS, optional="", client=None):
    """Fill the 4-box form (box 5 may stay empty) and press Submit."""
    return flow.submit_form(
        settings, view.request.request_id, [*answers, optional], view.revision, client=client
    )


def to_decision(settings):
    """The form is submitted; a material decision is waiting (input mode: choices)."""
    return submit_form(settings, start(settings))


def to_checkpoint(settings):
    """The decision is answered with its first button; the optional box was left empty."""
    view = to_decision(settings)
    return choose(settings, view, view.choices[0])


def to_confirmed(settings):
    view = to_checkpoint(settings)
    return choose(settings, view, flow.PROCEED_OPTION)
