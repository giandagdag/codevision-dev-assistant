"""Test helper: drive the scripted Excel conversation (fake provider) through the 2A engine."""

from agents import da_understand_flow as flow

# Answers are ignored by the fake provider (it plays its script), but must pass the checks.
ANSWERS = (
    "Users keep asking to upload Excel files",
    "The upload screen only takes PDF and DOCX",
    "Check the workbook, read the sheets, pass them on",
    "Workbooks in, normal ingestion format out; reject empty or damaged files",
)


def start(settings):
    return flow.create_understand_request(settings, "Can we support Excel uploads?")


def answer(settings, view, text):
    return flow.submit_answer(settings, view.request.request_id, text, view.revision)


def choose(settings, view, option):
    return flow.choose_option(settings, view.request.request_id, option, view.revision)


def skip(settings, view):
    return flow.skip_optional(settings, view.request.request_id, view.revision)


def to_decision(settings):
    """Questions 1 to 4 answered; a material decision is waiting (input mode: choices)."""
    view = start(settings)
    for text in ANSWERS:
        view = answer(settings, view, text)
    return view


def to_checkpoint(settings):
    view = to_decision(settings)
    view = choose(settings, view, view.choices[0])
    return skip(settings, view)


def to_confirmed(settings):
    view = to_checkpoint(settings)
    return choose(settings, view, flow.PROCEED_OPTION)
