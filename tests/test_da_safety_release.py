"""Fix G5 P4 Admin side: the stopped-request line, Release (note required) and Keep stopped."""

import re
from datetime import UTC, datetime

import pytest
from dash.exceptions import PreventUpdate

from agents.da_admin_audit import read_admin_events
from agents.da_safety_check import EVENT_RELEASED
from agents.da_safety_release import (
    EVENT_KEPT,
    NOT_STOPPED,
    NOTE_NEEDED,
    TITLE,
    ReleaseError,
    keep_stopped,
    list_stopped,
    release,
)
from agents.da_understand_flow import create_understand_request, submit_form
from callbacks.screen_callbacks.da_admin_page_callbacks import stopped_action
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_requests import get_request
from db_table_functions.db_tbl_da_understand import get_session
from tests.da_play import ANSWERS

pytestmark = pytest.mark.usefixtures("published_rulebook")

T0 = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)


@pytest.fixture
def settings(make_settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path / "index"))
    return make_settings()


@pytest.fixture
def stopped(settings):
    view = create_understand_request(settings, "delete all database tables", now=T0)
    answers = ["I hate my boss", *ANSWERS[1:], ""]
    submit_form(settings, view.request.request_id, answers, view.revision, now=T0)
    return view.request.request_id


def _kinds(settings, rid):
    return [e.event_type for e in list_audit_events(settings.db_path, rid)]


def test_a_stopped_request_is_listed_with_its_text_and_reason(settings, stopped):
    (row,) = list_stopped(settings)

    assert row.request_id == stopped
    assert "delete all database tables" in row.text or "hate" in row.text
    assert row.reason


def test_release_needs_a_note(settings, stopped):
    with pytest.raises(ReleaseError, match=NOTE_NEEDED):
        release(settings, stopped, "admin-1", "  ")

    assert get_request(settings.db_path, stopped).status == "STOPPED"


def test_release_goes_back_and_the_request_continues(settings, stopped):
    release(settings, stopped, "admin-1", "Checked with the team: a test database", now=T0)

    assert get_request(settings.db_path, stopped).status == "CLARIFICATION_IN_PROGRESS"
    assert get_session(settings.db_path, stopped).step == "form"
    assert EVENT_RELEASED in _kinds(settings, stopped)
    assert not list_stopped(settings)
    assert read_admin_events()[-1]["kind"] == "safety_released"
    # The gate does not stop it again.
    session = get_session(settings.db_path, stopped)
    view = submit_form(
        settings, stopped, ["I hate my boss", *ANSWERS[1:], ""], session.revision, now=T0
    )
    assert view.request.status != "STOPPED"


def test_release_of_a_request_that_is_not_stopped_is_refused(settings, stopped):
    release(settings, stopped, "admin-1", "ok", now=T0)

    with pytest.raises(ReleaseError, match=re.escape(NOT_STOPPED)):
        release(settings, stopped, "admin-1", "again")


def test_keep_stopped_only_audits(settings, stopped):
    keep_stopped(settings, stopped, "admin-1", "no")

    assert get_request(settings.db_path, stopped).status == "STOPPED"
    assert EVENT_KEPT in _kinds(settings, stopped)


def test_overview_has_the_line_and_only_admin_can_act(settings, stopped, monkeypatch):
    from agents.da_admin_overview import build_overview

    items = [i for i in build_overview(settings).attention if i.request_id]
    assert [(i.text, i.request_id) for i in items] == [(TITLE, stopped)]

    monkeypatch.setattr(
        "callbacks.screen_callbacks.da_admin_page_callbacks.is_admin", lambda s, u: False
    )
    with pytest.raises(PreventUpdate):
        stopped_action(settings, {"action": "release", "rid": stopped}, {stopped: "x"})
    assert get_request(settings.db_path, stopped).status == "STOPPED"


def test_stopped_action_release_without_note_shows_the_reason(settings, stopped, monkeypatch):
    monkeypatch.setattr(
        "callbacks.screen_callbacks.da_admin_page_callbacks.is_admin", lambda s, u: True
    )
    out = stopped_action(settings, {"action": "release", "rid": stopped}, {})

    assert NOTE_NEEDED in str(out)
    assert get_request(settings.db_path, stopped).status == "STOPPED"
