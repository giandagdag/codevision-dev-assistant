"""The 4-box form in a real browser (Phase 6 fixes, U1 and U2): a failing box shows its message
under that box and every box keeps its text; a good Submit moves on to the first AI question.

Skipped, not failed, when Playwright or its browser is missing.
"""

import re
import threading

import pytest
from werkzeug.serving import make_server

from agents import da_understand_flow as flow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests import da_play
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

WAIT_MS = 15000
LABELS = [f"{n}. {title}" for n, title in flow.FORM_BOXES] + [flow.OPTIONAL_QUESTION]


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def live_url(settings):
    request_id = da_play.start(settings).request.request_id
    app = server_module.create_app()
    server = make_server("127.0.0.1", 0, app.server, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/?request={request_id}"
    server.shutdown()
    thread.join(timeout=5)


def box(page, number):
    return page.get_by_label(LABELS[number - 1], exact=True)


def test_a_bad_box_shows_its_message_and_every_box_keeps_its_text(
    make_live_page, live_url, settings
):
    page = make_live_page(live_url)
    problems = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    box(page, 1).wait_for(timeout=WAIT_MS)
    box(page, 1).fill(da_play.ANSWERS[0])
    box(page, 4).fill(da_play.ANSWERS[3])  # boxes 2 and 3 are left empty

    page.get_by_role("button", name="Submit", exact=True).click()
    page.get_by_text(flow.BOX_EMPTY_MESSAGE).first.wait_for(timeout=WAIT_MS)

    assert page.get_by_text(flow.BOX_EMPTY_MESSAGE).count() == 2  # under box 2 and box 3 only
    assert box(page, 1).input_value() == da_play.ANSWERS[0]  # nothing was redrawn
    assert box(page, 4).input_value() == da_play.ANSWERS[3]
    view = flow.get_understand_view(settings, _request_id(live_url))
    assert view.input_mode == "form"  # nothing was saved
    # No Dash error about a form id. (A console error about the workspace store da-ws-ctx is
    # already there on every Understand page before this change; it is reported, not fixed here.)
    assert [p for p in problems if re.search(r"id of this object is `[^`]*da-form", p)] == []


def test_a_good_submit_moves_on_to_the_first_ai_question(make_live_page, live_url, settings):
    page = make_live_page(live_url)
    box(page, 1).wait_for(timeout=WAIT_MS)
    for number, text in enumerate(da_play.ANSWERS, start=1):
        box(page, number).fill(text)

    page.get_by_role("button", name="Submit", exact=True).click()

    page.get_by_text("Should hidden worksheets be extracted too?").first.wait_for(timeout=WAIT_MS)
    assert page.get_by_role("button", name="Submit", exact=True).count() == 0  # the form is gone
    assert page.get_by_role("button", name="Visible worksheets only").count() == 1
    view = flow.get_understand_view(settings, _request_id(live_url))
    assert view.record.answered_questions == [1, 2, 3, 4]


def _request_id(url: str) -> str:
    return url.split("request=")[1]
