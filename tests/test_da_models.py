from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pydantic_classes.da_models import AuditEvent, Request

NOW = datetime(2026, 10, 25, 9, 30, tzinfo=UTC)


def make_request(**changes):
    values = {
        "request_id": "CVDA-2026-0001",
        "title": "Add interest calculation field",
        "developer_id": "dev-0001",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return Request(**values)


def make_event(**changes):
    values = {
        "request_id": "CVDA-2026-0001",
        "timestamp": NOW,
        "actor": "developer",
        "event_type": "request_created",
    }
    values.update(changes)
    return AuditEvent(**values)


def test_new_request_has_starting_values():
    request = make_request()

    assert request.status == "DRAFT"
    assert request.version == 1
    assert request.rulebook_version is None


@pytest.mark.parametrize("bad_id", ["CVDA-26-0001", "ABC-2026-0001", "CVDA-2026-01", ""])
def test_bad_request_id_is_rejected(bad_id):
    with pytest.raises(ValidationError):
        make_request(request_id=bad_id)


def test_empty_title_is_rejected():
    with pytest.raises(ValidationError):
        make_request(title="")


def test_time_without_time_zone_is_rejected():
    with pytest.raises(ValidationError):
        make_request(created_at=datetime(2026, 10, 25, 9, 30))


@pytest.mark.parametrize("actor", ["developer", "system", "llm"])
def test_allowed_actors_are_accepted(actor):
    assert make_event(actor=actor).actor == actor


def test_unknown_actor_is_rejected():
    with pytest.raises(ValidationError):
        make_event(actor="admin")


def test_audit_event_cannot_be_changed_after_creation():
    event = make_event()

    with pytest.raises(ValidationError):
        event.event_type = "something_else"


def test_audit_event_details_default_to_empty():
    assert make_event().details == {}
