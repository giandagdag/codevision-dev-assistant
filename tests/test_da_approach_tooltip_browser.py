"""Fix G7 (G7-12): the full text of a design option opens on keyboard focus, not only on hover.

Skipped, not failed, when Playwright or its browser is missing."""

import threading

import pytest
from werkzeug.serving import make_server

from agents import da_approach_flow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests import da_play
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

OPTION = "Existing upload screen"
FULL_TEXT = "Keep the Excel upload on the existing upload screen, next to the PDF one, in full."


@pytest.fixture
def live(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    monkeypatch.setattr(da_approach_flow, "_option_hints", lambda state: {OPTION: FULL_TEXT})
    view = da_play.to_checkpoint(settings)
    app = server_module.create_app()
    server = make_server("127.0.0.1", 0, app.server, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/?request={view.request.request_id}"
    server.shutdown()


def test_the_option_text_opens_when_the_button_gets_keyboard_focus(make_live_page, live):
    page = make_live_page(live)
    page.get_by_role("button", name="Proceed with this understanding", exact=True).click(
        timeout=15000
    )
    page.get_by_role("button").filter(has_text="Findings look right").click(timeout=20000)
    option = page.get_by_role("button", name=OPTION, exact=True)
    option.wait_for(timeout=30000)

    # Like a keyboard user: a key press first, so the browser treats the focus as keyboard focus.
    page.keyboard.press("Shift")
    option.focus()

    page.get_by_text(FULL_TEXT).wait_for(state="visible", timeout=5000)
