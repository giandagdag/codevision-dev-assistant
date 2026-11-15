"""FX-1 and FX-2 (Phase 8 fix 1, bug B6): the page shows the end of a run WITHOUT a reload.

FX-2: the first Build. FX-1: Check my edits after a hand edit and Re-scan. Both wait with no
page reload; the 3-second poll (`da-build-poll`) must redraw the page by itself.

Skipped, not failed, when no browser is found (like row 8-42). The browser is Playwright's
Chromium, or the Edge that Windows already has (no download), so a laptop can run it.
"""

import threading
import time

import pytest
from werkzeug.serving import make_server

from agents import da_build_runner as build_runner
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests.da_browser import READ_JS, SEED_JS
from tests.da_build_play import MODIFY, ORIGINAL
from tests.da_workspace_play import ready_to_build_id
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

FOLDER = {
    "src/web/da_page.py": "# web\n",
    "src/callbacks/da_calls.py": "# callbacks\n",
    MODIFY: ORIGINAL,
    "src/agents/secret_notes.py": "never read\n",
}
NOTE = "# my own note, written by the developer\n"
WAIT_MS = 15000
RUN_WAIT_MS = 15000  # FX-1: the result shows within this time, with no reload
FIRST_BUILD_WAIT_MS = 60000


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def live_url(settings):
    request_id = ready_to_build_id(settings)
    app = server_module.create_app()
    server = make_server("127.0.0.1", 0, app.server, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/?request={request_id}"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def slow_runner(monkeypatch):
    """The demo run ends in under a second, so the page is often drawn after it. Real runs take
    longer: hold the runner back, so the page is drawn while the run is still going."""
    real_work = build_runner._work
    delay = {"seconds": 0.0}

    def slow_work(*args, **kwargs):
        time.sleep(delay["seconds"])
        return real_work(*args, **kwargs)

    monkeypatch.setattr(build_runner, "_work", slow_work)
    return delay


def button(page, name):
    return page.get_by_role("button", name=name, exact=True).first


def wait_for_text(page, text, timeout=WAIT_MS):
    page.get_by_text(text).first.wait_for(timeout=timeout)


def start_first_build(page, url):
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, FOLDER)
    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")
    button(page, "Build").click()


def test_fx_2_the_first_build_ends_on_screen_without_a_reload(
    make_live_page, live_url, slow_runner
):
    slow_runner["seconds"] = 4.0
    page = make_live_page(live_url)
    start_first_build(page, live_url)
    wait_for_text(page, "The code files are in your folder", FIRST_BUILD_WAIT_MS)
    button(page, "Re-scan").wait_for(timeout=WAIT_MS)


def test_fx_1_check_my_edits_ends_on_screen_without_a_reload(
    make_live_page, live_url, slow_runner
):
    page = make_live_page(live_url)
    start_first_build(page, live_url)
    wait_for_text(page, "The code files are in your folder", FIRST_BUILD_WAIT_MS)
    button(page, "Re-scan").wait_for(timeout=WAIT_MS)
    written = page.evaluate(READ_JS, MODIFY)
    page.evaluate(SEED_JS, {MODIFY: NOTE + written})
    button(page, "Re-scan").click()
    wait_for_text(page, "Your edits are not tested yet")
    slow_runner["seconds"] = 4.0
    button(page, "Check my edits").click()
    # No page.reload() anywhere: the poll alone must bring the finished run to the screen.
    wait_for_text(page, "Ready for your review", RUN_WAIT_MS)
