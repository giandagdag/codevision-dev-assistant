from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pydantic_classes.da_request_record_models import (
    INTERPRETER_FIELDS,
    Assumption,
    ChatMessage,
    Decision,
    InterpreterReply,
    RequestRecord,
)

NOW = datetime(2026, 10, 25, 9, 30, tzinfo=UTC)


def make_record(**changes):
    values = {"request_id": "CVDA-2026-0001", "rulebook_version": 1}
    values.update(changes)
    return RequestRecord(**values)


def test_new_record_starts_empty_at_version_1():
    record = make_record()

    assert record.version == 1
    assert record.title == ""
    assert record.functional_flow == []
    assert record.answered_questions == []


def test_title_up_to_80_characters():
    assert make_record(title="x" * 80).title == "x" * 80
    with pytest.raises(ValidationError):
        make_record(title="x" * 81)


def test_text_field_up_to_1000_characters():
    with pytest.raises(ValidationError):
        make_record(objective="x" * 1001)


def test_list_up_to_12_items_of_300_characters():
    make_record(in_scope=["x" * 300] * 12)
    with pytest.raises(ValidationError):
        make_record(in_scope=["item"] * 13)
    with pytest.raises(ValidationError):
        make_record(in_scope=["x" * 301])


def test_answered_questions_are_1_to_4():
    with pytest.raises(ValidationError):
        make_record(answered_questions=[5])


def test_unknown_field_is_refused():
    with pytest.raises(ValidationError):
        make_record(colour="blue")


def test_app_filled_fields_are_not_interpreter_fields():
    for app_field in ("request_id", "version", "rulebook_version", "decisions", "open_items"):
        assert app_field not in INTERPRETER_FIELDS


def test_decision_and_assumption_shapes():
    decision = Decision(question="Hidden sheets?", choice="Visible only", decided_at=NOW)
    assumption = Assumption(text="Excel means .xlsx", basis="Rulebook v1 glossary")

    record = make_record(decisions=[decision], assumptions=[assumption])

    assert record.decisions[0].choice == "Visible only"
    assert record.assumptions[0].basis == "Rulebook v1 glossary"


def test_interpreter_reply_hint_up_to_200_characters():
    with pytest.raises(ValidationError):
        InterpreterReply(hint="x" * 201)


def test_interpreter_reply_refuses_unknown_keys():
    with pytest.raises(ValidationError):
        InterpreterReply.model_validate({"updates": {}, "code": "print(1)"})


def test_chat_message_cannot_be_changed():
    message = ChatMessage(
        request_id="CVDA-2026-0001", sent_at=NOW, speaker="developer", text="Hello"
    )

    with pytest.raises(ValidationError):
        message.text = "Changed"


def test_chat_speaker_must_be_known():
    with pytest.raises(ValidationError):
        ChatMessage(request_id="CVDA-2026-0001", sent_at=NOW, speaker="admin", text="Hi")
