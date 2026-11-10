"""Phase 9 step 18a: the card 1 switch offer through the screen callbacks (code review round 1).
Click-through style: the test presses the buttons, not the engine. Made-up data, no AI."""

import pytest

from agents import da_enhance_flow as enhance
from agents import da_understand_flow as understand
from agents.da_search_index import FakeSearchIndex, IndexData, IndexPiece
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_understand import get_session
from layouts import da_developer_assistant_page as page
from pydantic_classes.da_workspace_models import FileFact
from tests import da_play

LIMITS = "src/agents/limits_expiry_report.py"

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    piece = IndexPiece(
        piece_no=0, path=LIMITS, symbol="format_expiry", line_start=1, kind="code",
        language="python", snippet="def format_expiry(day): date text",
    )
    index = FakeSearchIndex(IndexData(build_id="t", built_at="", pieces=(piece,)))
    monkeypatch.setattr(enhance, "get_search_index", lambda _settings: index)
    return settings


@pytest.fixture
def card_1(settings):
    view = understand.create_understand_request(
        settings, "limits_expiry_report shows the wrong date at weekends"
    )
    return da_play.submit_form(settings, view)


def state_of(view):
    return {"request_id": view.request.request_id, "revision": view.revision}


def test_the_two_buttons_show_only_while_the_offer_is_open(settings, card_1):
    request_id = card_1.request.request_id

    assert enhance.has_open_offer(settings, request_id)
    shown = str(page.render_workspace(card_1, switch_offer=True))
    assert page.SWITCH_ID in shown and page.DECLINE_ID in shown
    assert page.SWITCH_ID not in str(page.render_workspace(card_1))


def test_switch_button_then_start_understand_works(settings, card_1):
    request_id = card_1.request.request_id

    outputs = cb.perform_switch_answer(settings, page.SWITCH_ID, state_of(card_1), 4)

    assert outputs == (5, "")
    assert get_session(settings.db_path, request_id) is None
    view = enhance.get_enhance_view(settings, request_id)
    assert (view.kind, view.step) == ("enhance", "e_pick")
    done = enhance.confirm_targets(settings, request_id, [LIMITS], {}, view.revision)
    text = (settings.fake_main_dir / LIMITS).read_text(encoding="utf-8")
    fact = FileFact(path=LIMITS, exists=True, parent_exists=True, text=text)
    fresh = enhance.run_freshness(settings, request_id, [fact], done.revision)
    assert fresh.step == "e_fresh"
    enhance.start_understand(settings, request_id, fresh.revision)
    assert get_session(settings.db_path, request_id).step == "form"


def test_decline_button_closes_the_offer_for_good(settings, card_1):
    request_id = card_1.request.request_id

    outputs = cb.perform_switch_answer(settings, page.DECLINE_ID, state_of(card_1), 0)

    assert outputs == (1, "")
    assert not enhance.has_open_offer(settings, request_id)
    events = [e.event_type for e in list_audit_events(settings.db_path, request_id)]
    assert "switch_declined" in events


def test_an_old_window_shows_the_stale_message_and_writes_nothing(settings, card_1):
    stale = {"request_id": card_1.request.request_id, "revision": card_1.revision + 5}

    refresh, message = cb.perform_switch_answer(settings, page.SWITCH_ID, stale, 0)

    assert refresh is cb.no_update and message != ""
    assert enhance.has_open_offer(settings, card_1.request.request_id)
