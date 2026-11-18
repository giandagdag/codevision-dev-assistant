"""B2 P34: a Proceed assumption can be edited at the checkpoint, and Confirm uses the edit."""

from datetime import UTC, datetime

import pytest

from agents.da_understand_assume import ASSUME_BASIS
from agents.da_understand_flow import (
    EDIT_ASSUMPTION_PREFIX,
    PROCEED_OPTION,
    edit_assumption,
    get_understand_view,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_understand import (
    UnderstandError,
    get_confirmed_record,
    get_session,
    save_session,
)
from pydantic_classes.da_request_record_models import AssumedCase, Assumption
from tests.test_da_understand_flow import choose, to_checkpoint

pytestmark = pytest.mark.usefixtures("published_rulebook")

NEW = "Hidden sheets are read, hidden columns are not"


@pytest.fixture
def settings(make_settings):
    return make_settings()


def case(text):
    return AssumedCase(text=text, given="a workbook", when="it is uploaded", then=text)


def checkpoint_with_two_assumptions(settings):
    """The fake script's checkpoint, with two Proceed assumptions as Proceed leaves them."""
    view = to_checkpoint(settings)
    session = get_session(settings.db_path, view.request.request_id)
    cases = [case("First assumption"), case("Second assumption")]
    record = session.record.model_copy(
        update={
            "assumptions": [
                *session.record.assumptions,
                *[Assumption(text=c.text, basis=ASSUME_BASIS) for c in cases],
            ]
        }
    )
    session.record, session.assumed_cases = record, cases
    with open_db(settings.db_path) as conn:
        save_session(conn, session, session.revision, datetime.now(UTC))
    return get_understand_view(settings, view.request.request_id)


def test_edit_changes_the_assumption_and_confirm_makes_a_criterion_of_it(settings):
    view = checkpoint_with_two_assumptions(settings)
    assert f"{EDIT_ASSUMPTION_PREFIX}2" in view.choices

    view = edit_assumption(
        settings, view.request.request_id, f"{EDIT_ASSUMPTION_PREFIX}2", NEW, view.revision
    )
    assert [a.text for a in view.record.assumptions][-2:] == ["First assumption", NEW]

    view = choose(settings, view, PROCEED_OPTION)
    saved = get_confirmed_record(settings.db_path, view.request.request_id)
    assert [c.then for c in saved.acceptance_criteria][-2:] == ["First assumption", NEW]
    events = [e.event_type for e in list_audit_events(settings.db_path, view.request.request_id)]
    assert "assumption_edited" in events


@pytest.mark.parametrize("option", [f"{EDIT_ASSUMPTION_PREFIX}3", f"{EDIT_ASSUMPTION_PREFIX}x"])
def test_a_number_with_no_assumption_is_refused(settings, option):
    view = checkpoint_with_two_assumptions(settings)

    with pytest.raises(UnderstandError, match="not one of the choices"):
        edit_assumption(settings, view.request.request_id, option, NEW, view.revision)

    assert get_understand_view(settings, view.request.request_id).revision == view.revision


def test_an_empty_or_too_long_sentence_is_refused(settings):
    view = checkpoint_with_two_assumptions(settings)
    option = f"{EDIT_ASSUMPTION_PREFIX}1"

    for text in ("  ", "x" * 5000):
        with pytest.raises(UnderstandError):
            edit_assumption(settings, view.request.request_id, option, text, view.revision)

    assert get_understand_view(settings, view.request.request_id).revision == view.revision


def test_no_edit_buttons_without_proceed_assumptions(settings):
    view = to_checkpoint(settings)

    assert not [c for c in view.choices if c.startswith(EDIT_ASSUMPTION_PREFIX)]
