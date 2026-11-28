"""Fix G9 finish F8: what was checked only by hand, now in a real browser (G9-15, G9-16).

G9-15: See the findings pressed three times scrolls the findings table into view each time.
G9-16: the Tests tab stays open after a Dispute (the page is redrawn, the tab is kept).

Skipped, not failed, when Playwright or its browser is missing (like the poll tests).
"""

import threading

import pytest
from werkzeug.serving import make_server

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from layouts import da_tester_panel as tp
from tests.da_build_play import ready_with_workspace
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

WAIT_MS = 15000
SMOOTH_SCROLL_MS = 1200
IN_VIEW_JS = """
(id) => {
  const box = document.getElementById(id).getBoundingClientRect();
  return box.top < window.innerHeight && box.bottom > 0;
}
"""


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def not_passing_url(settings, monkeypatch):
    """A request whose build ended Not passing, so the Tests tab has Must fix findings."""
    request_id = ready_with_workspace(settings)[0]
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"review_must_fix_always"}))
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    app = server_module.create_app()
    server = make_server("127.0.0.1", 0, app.server, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/?request={request_id}"
    server.shutdown()
    thread.join(timeout=5)


def open_tests_tab(page):
    tab = page.get_by_role("tab", name="Tests", exact=True)
    tab.wait_for(timeout=WAIT_MS)
    tab.click()
    return tab


def test_g9_15_see_the_findings_scrolls_the_table_into_view_every_time(
    make_live_page, not_passing_url
):
    page = make_live_page(not_passing_url)
    page.set_viewport_size({"width": 1280, "height": 500})
    open_tests_tab(page)
    button = page.locator(f"#{tp.SEE_FINDINGS_ID}")
    button.wait_for(timeout=WAIT_MS)
    for _ in range(3):
        page.evaluate(f"document.getElementById('{tp.REPORT_ID}').scrollIntoView()")
        button.click()
        page.wait_for_timeout(SMOOTH_SCROLL_MS)
        assert page.evaluate(IN_VIEW_JS, tp.FINDINGS_ID)


def test_g9_16_the_tests_tab_is_still_open_after_a_dispute(make_live_page, not_passing_url):
    page = make_live_page(not_passing_url)
    tab = open_tests_tab(page)
    page.get_by_role("button", name="Dispute", exact=True).first.wait_for(timeout=WAIT_MS)
    page.get_by_placeholder("Reason (", exact=False).first.fill("I checked it, the plan is fine")
    page.get_by_role("button", name="Dispute", exact=True).first.click()

    page.get_by_text("Disputed, not sent yet").first.wait_for(timeout=WAIT_MS)  # visible: tab open

    assert tab.get_attribute("aria-selected") == "true"
